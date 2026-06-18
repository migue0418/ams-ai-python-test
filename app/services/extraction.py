import ast
import json
import re
from typing import NamedTuple

from core.config import settings
from services import ai_client

# the provider wraps clean json in a few predictable ways (markdown fences,
# a sentence around it, python-style quoting, bare keys) before it ever
# resorts to giving up entirely, so each layer below targets one of those.
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_BARE_KEY_RE = re.compile(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)")

_TO_ALIASES = ("to", "recipient", "destination")
_MESSAGE_ALIASES = ("message", "body", "text")
_TYPE_ALIASES = ("type", "channel", "method")
_VALID_TYPES = {"email", "sms"}


class ExtractedIntent(NamedTuple):
    to: str
    message: str
    type: str


class ExtractionFailed(Exception):
    """Raised once the attempt budget is spent without a usable intent."""


async def extract_with_retry(user_input: str) -> ExtractedIntent:
    """Asks the AI for an intent, re-rolling on a genuinely unparseable answer.

    Most noise (markdown, alt key names, broken quoting) is recovered by
    parse_intent without ever calling the AI again. Only the truly missing
    or truncated cases need a fresh attempt, and that's capped on purpose -
    see decisions.md for the budget math.
    """
    last_content = ""
    for _ in range(settings.extract_max_attempts):
        last_content = await ai_client.fetch_completion(user_input)
        intent = parse_intent(last_content)
        if intent is not None:
            return intent
    raise ExtractionFailed(f"unparseable after retries, last answer: {last_content!r}")


def parse_intent(content: str) -> ExtractedIntent | None:
    data = _parse_json_loosely(content)
    if data is None:
        return None
    return _normalize(data)


def _parse_json_loosely(content: str) -> dict | None:
    for candidate in _candidates(content):
        data = _try_json(candidate)
        if data is not None:
            return data
    return None


def _candidates(content: str):
    yield content  # layer 1: take it at face value

    fenced = _FENCE_RE.search(content)
    if fenced is not None:
        yield fenced.group(1)  # layer 2: unwrap a ```json ... ``` block

    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end > start:
        yield content[start : end + 1]  # layer 3: grab the {...} embedded in prose


def _try_json(candidate: str) -> dict | None:
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return _repair_quoting(candidate)  # layer 4: last resort, not strict json
    return data if isinstance(data, dict) else None


def _repair_quoting(candidate: str) -> dict | None:
    # single-quoted, python dict-literal style
    try:
        value = ast.literal_eval(candidate)
        if isinstance(value, dict):
            return value
    except (ValueError, SyntaxError):
        pass

    # bare/unquoted keys, e.g. {to: "x"} -> {"to": "x"}
    try:
        return json.loads(_BARE_KEY_RE.sub(r'\1"\2"\3', candidate))
    except json.JSONDecodeError:
        return None


def _normalize(data: dict) -> ExtractedIntent | None:
    lowered = {str(key).lower(): value for key, value in data.items()}

    to = _first_present(lowered, _TO_ALIASES)
    message = _first_present(lowered, _MESSAGE_ALIASES)
    notif_type = _first_present(lowered, _TYPE_ALIASES)

    if not to or not message or not isinstance(notif_type, str):
        return None
    if notif_type.lower() not in _VALID_TYPES:
        return None

    return ExtractedIntent(to=str(to), message=str(message), type=notif_type.lower())


def _first_present(data: dict, aliases: tuple[str, ...]):
    for alias in aliases:
        if alias in data:
            return data[alias]
    return None
