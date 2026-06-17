import json
from typing import NamedTuple

import httpx
from core.config import settings

EXTRACT_PATH = "/v1/ai/extract"

SYSTEM_PROMPT = """Eres un asistente que extrae intenciones de notificación a partir de un mensaje en lenguaje natural.
Responde únicamente con un objeto JSON, sin texto adicional, sin explicaciones y sin bloques de markdown.
El objeto debe tener exactamente estas claves:
- "to": el email o teléfono del destinatario, tal como aparece en el mensaje.
- "message": el texto que se debe enviar.
- "type": exactamente "email" o "sms", en minúsculas, sin ningún otro valor posible.

Ejemplo:
Usuario: "Manda un correo a ana@test.com: te espero a las 5"
Respuesta: {"to": "ana@test.com", "message": "te espero a las 5", "type": "email"}
"""

_client: httpx.AsyncClient | None = None


class ExtractedIntent(NamedTuple):
    to: str
    message: str
    type: str


async def start() -> None:
    global _client
    _client = httpx.AsyncClient(
        base_url=settings.provider_base_url,
        timeout=settings.provider_timeout_seconds,
    )


async def stop() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def extract_intent(user_input: str) -> ExtractedIntent:
    """Calls the AI engine and parses its answer into to/message/type."""
    assert _client is not None, "ai_client.start() must run before extract_intent()"

    response = await _client.post(
        EXTRACT_PATH,
        json={
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
        },
        headers={"X-API-Key": settings.provider_api_key},
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]

    # anything that isn't clean json, or is missing a key, just fails the request.
    data = json.loads(content)
    return ExtractedIntent(to=data["to"], message=data["message"], type=data["type"])
