# Decisiones de diseño

## Por qué parsing en capas en vez de pedirle más a la IA

`/v1/ai/extract` siempre devuelve `200`, así que el fallo nunca está en el
status code, está en el contenido (ver `provider/responses.py`). La primera
versión (`ai_client.py` con `json.loads` directo, sin guardrails) acertaba
solo en la rama de JSON limpio: ~50% de los casos.

El resto del ruido no es aleatorio en su forma, son patrones fijos y
conocidos (markdown, claves alternativas, comillas de Python, claves sin
comillas, JSON incrustado en una frase). Eso se puede recuperar parseando
mejor, sin volver a llamar a la IA. Cada llamada de más a `/extract` es
1.5-3s de latencia y un punto extra en el panel "RATIO INTENTOS/REQ" de
Grafana (verde si <1.5).

`services/extraction.py` intenta, en orden, parar en el primer paso que
funcione:

1. `json.loads` directo.
2. Si hay un bloque ` ```json ... ``` ` o ` ``` ... ``` `, lo extrae y reintenta.
3. Si no, toma la subcadena entre el primer `{` y el último `}` (cubre el
   caso de JSON incrustado en una frase) y reintenta.
4. Si sigue sin ser JSON válido, prueba `ast.literal_eval` (cubre comillas
   simples estilo dict de Python) y, si tampoco, una regex que entrecomilla
   claves sueltas (`{to: "x"}` → `{"to": "x"}`).
5. Una vez hay un dict, normaliza alias case-insensitive: `recipient`/`destination` → `to`,
   `body`/`text` → `message`, `channel`/`method` → `type`. Campos extra se ignoran.
6. Valida que `to` y `message` no estén vacíos y que `type` sea `email` o `sms`.

Si todo eso falla, es porque genuinamente falta un dato (`to` o `type` no
vinieron en la respuesta), el JSON está truncado, o la IA se negó a
responder. No es un problema de parsing, es un problema del dato. Ahí sí
tiene sentido volver a preguntarle a la IA, porque es una tirada nueva.

## El presupuesto de reintentos

Sumando la distribución de `provider/responses.py`, las capas 1-5 cubren el
**~80%** de los casos sin tocar la IA otra vez (limpio + alias + ruido con
los 3 campos + markdown/incrustado + comillas/claves rotas). El **20%**
restante (falta un campo, truncado, rechazo explícito) es irrecuperable en
el momento y necesita una llamada nueva.

Con `EXTRACT_MAX_ATTEMPTS = 2` (1 reintento), el ratio esperado de intentos
por request es `1 + 0.20 ≈ 1.2`, cómodamente verde. Dos reintentos
seguidos fallando es `0.20 × 0.20 = 4%`, así que ese es el failure rate
esperado en régimen permanente. Subir el límite a 3 intentos bajaría eso a
~0.8%, pero a cambio de poco: ese tercer intento es otra llamada de 1.5-3s
en serie solo para el 4% que ya es minoría, y pasar de 96% a 99.2% pesa
mucho menos que lo ya ganado al pasar de 80% a 96%. Es apostar más por la
fuerza bruta contra la IA que por parsear mejor, justo lo contrario de lo
que premia el test.

## Evidencia

Contra el stack real (`docker-compose up -d --build app` seguido de
`docker-compose run --rm load-test`, 200 VUs, 2748 requests), con la
ventana ya asentada (comprobado que el contador de intentos a `/extract`
no se movía más antes de medir):

| sent | failed | sent % | ratio intentos/req |
|---|---|---|---|
| 2645 | 103 | 96.3% | 1.20 (3307 llamadas a `/extract` / 2748 requests) |

El 3.75% de fallos coincide con el 4% esperado (`0.20²`). Los 103 fallos
son `ExtractionFailed` en su totalidad, cero `ProviderError`, y el ratio
1.20 está prácticamente clavado en el `1 + 0.20` calculado arriba. Ninguno
vino del lado del provider, y de hecho ni siquiera hizo falta que el retry
de `tenacity` en `provider_client.py` entrara en acción: en
`results/layered-extraction/provider.log` no aparece ningún "429 Rate
Limit Exceeded" en toda la ejecución, así que `rate_limiter.py` (reutilizado
de `ams-backend-python-test`, ventana de 45 req/10s) bastó por sí solo para
mantenernos por debajo del umbral del provider. El retry sigue ahí como
red de seguridad para cuando eso falle, pero en esta ejecución no tuvo que
usarse.

Logs completos y el `summary.json` de esta ejecución están en
[`results/layered-extraction/`](../results/layered-extraction/), generados
por [`results/extract.py`](../results/extract.py) a partir de
`docker-compose logs`. Ver también
[`results/dashboard.html`](../results/dashboard.html).

## Por qué la cola tiene un límite

Lanzar `load-test` antes de que la ejecución anterior hubiera drenado del
todo hizo que el ratio y el porcentaje de éxito leídos en el dashboard
salieran distintos cada vez (0.61, luego 0.49, luego 1.35) según el
momento exacto en que se miraba. No era un error de cálculo: la cola
interna (`asyncio.Queue`) no tenía límite, así que las ejecuciones
solapadas se iban apilando sin avisar, y el conteo de intentos a
`/extract` seguía subiendo en segundo plano mucho después de que k6 ya
hubiera terminado.

Para que esto no pase desapercibido, la cola ahora tiene un tope
(`QUEUE_MAX_SIZE`, 5000 por defecto, en `core/config.py`). Una ejecución
normal de `load-test` (2748 requests) se queda muy por debajo de ese
límite y no nota el cambio. Si se llegan a apilar varias ejecuciones sin
esperar a que la anterior drene, `POST /process` empieza a devolver `503`
en vez de seguir aceptando trabajo sin límite. También se añadió
timestamp a los logs (`logging.basicConfig` en `main.py`) para poder
acotar qué pasó y cuándo sin depender de la marca de tiempo de Docker.

## Por qué no "structured output" / JSON mode

`AIRequest` en el provider solo acepta `messages`; cualquier
`response_format` que se mande se ignora (Pydantic descarta campos extra
por defecto) y la respuesta la decide un dado fijo en
`generate_ai_response()` que no mira el request en absoluto. Pedir JSON
mode aquí sería código muerto. En un proveedor real sí sería la primera
línea de defensa. El parsing en capas seguiría existiendo como red de
seguridad, pero se usaría mucho menos.
