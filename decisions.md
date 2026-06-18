# Decisiones de diseño

## Primera aproximación: parseo directo

`/v1/ai/extract` siempre devuelve `200`, así que aquí el fallo nunca está en el código de estado, está en el contenido de la respuesta (lo vi mirando `provider/responses.py`). Mi primera versión de `ai_client.py` hacía un `json.loads` directo sobre lo que devolvía la IA, sin ningún tipo de guardrails. Acertaba solo cuando la respuesta venía como JSON limpio, que es aproximadamente el 50% de los casos según la distribución del mock.

## Mejora: parsing en capas y reintento acotado

El resto del ruido no es aleatorio en su forma, son patrones fijos: bloques de markdown, claves con otro nombre, comillas de Python en vez de comillas dobles, claves sin comillas, JSON metido en medio de una frase. Todo eso se puede recuperar parseando mejor, sin necesidad de volver a llamar a la IA. Y conviene evitar esa llamada si se puede, porque cada intento de más a `/extract` son 1.5-3 segundos de latencia y un punto extra en el ratio de intentos por request que mide Grafana (el panel se pone en verde por debajo de 1.5).

Así que en `services/extraction.py` fui metiendo capas, cada una se intenta solo si la anterior no consigue un JSON válido: primero pruebo `json.loads` tal cual viene el contenido; si falla, busco un bloque ` ```json ... ``` ` o ` ``` ... ``` ` y lo extraigo; si tampoco hay suerte, cojo la subcadena entre el primer `{` y el último `}`, que cubre el caso de JSON incrustado en una frase; y si sigue sin parsear, prueba con `ast.literal_eval` (para las comillas simples estilo dict de Python) y como último recurso una regex que entrecomilla las claves sueltas. Una vez hay un diccionario válido, normalizo los alias de nombres (`recipient`/`destination` a `to`, `body`/`text` a `message`, `channel`/`method` a `type`, todo sin distinguir mayúsculas) y descarto cualquier campo de más que venga sobrando. Por último valido que `to` y `message` no estén vacíos y que `type` sea `email` o `sms`.

Si después de todo eso sigue sin salir nada válido es porque genuinamente falta un dato (no vino `to` o `type`), el JSON viene truncado, o la IA se negó a responder. Ahí ya no es un problema de parsing sino del dato en sí, y ahí sí tiene sentido reintentar la llamada, porque es una tirada nueva.

## El presupuesto de reintentos

Sumando la distribución de `provider/responses.py`, las capas de parsing cubren sobre el 80% de los casos sin volver a tocar la IA (el JSON limpio, los alias, el ruido con los tres campos presentes, el markdown o texto incrustado, y las comillas o claves rotas). El 20% restante (falta un campo, JSON truncado, rechazo explícito) es irrecuperable en ese momento y necesita una llamada nueva.

Con `EXTRACT_MAX_ATTEMPTS` en 2, es decir un solo reintento, el ratio esperado de intentos por request sale en 1 + 0.20, o sea 1.2, que queda cómodo en verde. Que los dos intentos fallen seguidos es 0.20 al cuadrado, un 4%, así que ese es el failure rate que cabía esperar en régimen normal. Subir el límite a 3 intentos bajaría eso a un 0.8%, pero a cambio de poco: ese tercer intento es otra llamada de 1.5-3 segundos en serie solo para ese 4% que ya es minoría, y pasar de 96% a 99.2% pesa mucho menos que lo que ya se ganó al pasar de 80% a 96% con el primer reintento. Es apostar más por la fuerza bruta contra la IA que por parsear mejor, justo lo contrario de lo que se busca en esta prueba.

## Resultados

Lo probé contra el stack real: `docker-compose up -d --build app` y luego `docker-compose run --rm load-test`, con 200 VUs y 2748 requests en total, esperando a que la cola terminara de drenar del todo (comprobé que el contador de intentos a `/extract` ya no se movía antes de medir nada). De esas 2748, 2645 acabaron en `sent` y 103 en `failed`, un 96.3% de éxito, con 3307 llamadas a `/extract` en total, lo que da un ratio de 1.20 intentos por request.

El 3.75% de fallos coincide casi exacto con el 4% calculado arriba, y los 103 fallos son todos `ExtractionFailed`, ninguno viene del provider. De hecho ni hizo falta que el retry de `tenacity` en `provider_client.py` entrara en juego: revisé `results/layered-extraction/provider.log` entero y no aparece un solo 429, así que el rate limiter (`rate_limiter.py`, reutilizado de `ams-backend-python-test`, ventana de 45 peticiones cada 10 segundos) bastó solo para mantenernos por debajo del límite del provider. El retry sigue ahí como red de seguridad para el día que eso falle, pero en esta ejecución no tuvo que dispararse ni una vez.

Los logs completos y el `summary.json` de esta ejecución están en `results/layered-extraction/`, generados por `results/extract.py` a partir de `docker-compose logs`. También hay un dashboard en `results/dashboard.html` que lee esos mismos archivos.

## Por qué la cola tiene un límite

Lanzar `load-test` antes de que la ejecución anterior hubiera drenado del todo me hizo ver números distintos cada vez que miraba el dashboard, primero 0.61, luego 0.49, luego 1.35. No era un fallo de cálculo: la cola interna (`asyncio.Queue`) no tenía límite, así que las ejecuciones que se solapaban se iban apilando sin que nada avisara, y el contador de intentos a `/extract` seguía subiendo en segundo plano mucho después de que k6 ya había terminado.

Para que esto no pase desapercibido otra vez, le puse un tope a la cola (`QUEUE_MAX_SIZE`, 5000 por defecto en `core/config.py`). Una ejecución normal de `load-test` con sus 2748 requests se queda muy por debajo y no nota el cambio, pero si se llegan a apilar varias ejecuciones sin esperar a que la anterior termine, `POST /process` empieza a devolver `503` en vez de seguir aceptando trabajo sin límite. También añadí timestamp a los logs (`logging.basicConfig` en `main.py`) para poder situar qué pasó y cuándo sin depender de la marca de tiempo de Docker.

## Por qué no "structured output" / JSON mode

Pensé en pedirle a la IA un `response_format` para forzar la salida en JSON, pero revisando `provider/app.py` vi que `AIRequest` solo declara el campo `messages`, así que cualquier campo de más que se mande se descarta sin más (es el comportamiento por defecto de Pydantic con campos que no reconoce). La respuesta la decide un dado fijo en `generate_ai_response()`, que ni siquiera mira el contenido del request. Pedir JSON mode aquí sería código muerto, no cambiaría nada. Contra un proveedor real sí sería la primera línea de defensa, y el parsing en capas seguiría existiendo como red de seguridad, solo que se usaría mucho menos.
