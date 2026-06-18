import json

import httpx
import pytest
import respx
from services import ai_client

EXTRACT_URL = "http://localhost:3001/v1/ai/extract"


@pytest.fixture(autouse=True)
async def _client_lifecycle():
    await ai_client.start()
    yield
    await ai_client.stop()


@respx.mock
async def test_fetch_completion_returns_message_content():
    route = respx.post(EXTRACT_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": '{"to": "a@b.com"}'}},
                ],
            },
        ),
    )
    content = await ai_client.fetch_completion("manda un email a a@b.com")
    assert content == '{"to": "a@b.com"}'
    assert route.calls.last.request.headers["X-API-Key"] == "test-dev-2026"


@respx.mock
async def test_fetch_completion_sends_system_and_user_messages():
    respx.post(EXTRACT_URL).mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        ),
    )
    await ai_client.fetch_completion("hola")

    body = json.loads(respx.calls.last.request.content)
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1] == {"role": "user", "content": "hola"}


@respx.mock
async def test_fetch_completion_raises_on_http_error():
    respx.post(EXTRACT_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await ai_client.fetch_completion("hola")
