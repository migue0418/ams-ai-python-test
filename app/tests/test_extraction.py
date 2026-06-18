import pytest
from services import extraction
from services.extraction import ExtractedIntent, ExtractionFailed, parse_intent

TO = "user@example.com"
MESSAGE = "hola"
TYPE = "email"

# each fixture below mirrors one exact branch of provider/responses.py's
# 50/10/10/10/10/10 distribution, so the recoverable/unrecoverable split here
# can be checked against the math in decisions.md.

CLEAN = '{"to": "user@example.com", "message": "hola", "type": "email"}'

ALT_KEYS_RECIPIENT = (
    '{"Recipient": "user@example.com", "body": "hola", "channel": "email"}'
)
ALT_KEYS_TO_CAP = '{"To": "user@example.com", "Message": "hola", "Type": "email"}'
ALT_KEYS_DESTINATION = (
    '{"destination": "user@example.com", "text": "hola", "method": "email"}'
)

EXTRA_NOISE = (
    '{"to": "user@example.com", "message": "hola", "type": "email", '
    '"confidence": 0.99, "latency_ms": 120}'
)
MISSING_TYPE = '{"to": "user@example.com", "message": "hola"}'
MISSING_DESTINATION = '{"message": "hola", "type": "email"}'

MARKDOWN_JSON_BLOCK = (
    "He extraído la información correctamente:\n```json\n"
    '{"to": "user@example.com", "message": "hola", "type": "email"}\n```'
)
GENERIC_CODE_BLOCK = (
    'Output:\n```\n{"to": "user@example.com", "message": "hola", "type": "email"}\n```'
)
EMBEDDED_IN_TEXT = (
    "Claro, el destino es user@example.com y enviaré hola por email. "
    'En formato JSON: {"to": "user@example.com", "message": "hola", "type": "email"}'
)

TRUNCATED = '{"to": "user@example.com", "message": "hola", "type": "email" ...'
SINGLE_QUOTES = "{'to': 'user@example.com', 'message': 'hola', 'type': 'email'}"
UNQUOTED_KEYS = '{to: "user@example.com", message: "hola", type: "email"}'

REFUSAL_1 = (
    "Lo siento, como IA no tengo permitido procesar datos de contacto personales."
)
REFUSAL_2 = (
    "Error: El contenido del mensaje viola las políticas de seguridad (Potential Spam)."
)
REFUSAL_3 = "Refused: Content analysis flagged sensitive information."

EXPECTED = ExtractedIntent(to=TO, message=MESSAGE, type=TYPE)

RECOVERABLE = [
    CLEAN,
    ALT_KEYS_RECIPIENT,
    ALT_KEYS_TO_CAP,
    ALT_KEYS_DESTINATION,
    EXTRA_NOISE,
    MARKDOWN_JSON_BLOCK,
    GENERIC_CODE_BLOCK,
    EMBEDDED_IN_TEXT,
    SINGLE_QUOTES,
    UNQUOTED_KEYS,
]

UNRECOVERABLE = [
    MISSING_TYPE,
    MISSING_DESTINATION,
    TRUNCATED,
    REFUSAL_1,
    REFUSAL_2,
    REFUSAL_3,
]


@pytest.mark.parametrize("content", RECOVERABLE)
def test_parse_intent_recovers_known_noise_patterns(content):
    assert parse_intent(content) == EXPECTED


@pytest.mark.parametrize("content", UNRECOVERABLE)
def test_parse_intent_gives_up_on_genuinely_missing_data(content):
    assert parse_intent(content) is None


def test_parse_intent_rejects_invalid_type_value():
    assert parse_intent('{"to": "a@b.com", "message": "hi", "type": "fax"}') is None


def test_parse_intent_alias_lookup_is_case_insensitive():
    content = '{"TO": "user@example.com", "MESSAGE": "hola", "TYPE": "EMAIL"}'
    assert parse_intent(content) == EXPECTED


async def test_extract_with_retry_succeeds_on_first_attempt(monkeypatch):
    calls = []

    async def fake_fetch(user_input):
        calls.append(user_input)
        return CLEAN

    monkeypatch.setattr(extraction.ai_client, "fetch_completion", fake_fetch)

    intent = await extraction.extract_with_retry(
        "manda un email a user@example.com: hola",
    )
    assert intent == EXPECTED
    assert len(calls) == 1


async def test_extract_with_retry_recovers_on_second_attempt(monkeypatch):
    answers = iter([REFUSAL_1, CLEAN])

    async def fake_fetch(user_input):
        return next(answers)

    monkeypatch.setattr(extraction.ai_client, "fetch_completion", fake_fetch)

    intent = await extraction.extract_with_retry("hola")
    assert intent == EXPECTED


async def test_extract_with_retry_gives_up_after_exhausting_attempts(monkeypatch):
    calls = []

    async def fake_fetch(user_input):
        calls.append(user_input)
        return REFUSAL_1

    monkeypatch.setattr(extraction.ai_client, "fetch_completion", fake_fetch)

    with pytest.raises(ExtractionFailed):
        await extraction.extract_with_retry("hola")
    assert len(calls) == extraction.settings.extract_max_attempts
