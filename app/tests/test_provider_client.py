import json

import httpx
import pytest
import respx
from services import provider_client
from services.provider_client import ProviderError, RetryableProviderError

NOTIFY_URL = "http://localhost:3001/v1/notify"


@pytest.fixture(autouse=True)
async def _provider_client_lifecycle():
    await provider_client.start()
    yield
    await provider_client.stop()


@respx.mock
async def test_send_notification_succeeds_on_first_try():
    route = respx.post(NOTIFY_URL).mock(
        return_value=httpx.Response(
            200,
            json={"status": "delivered", "provider_id": "p-1"},
        ),
    )
    await provider_client.send_notification("user@example.com", "hi", "email")
    assert route.call_count == 1


@respx.mock
async def test_retries_transient_failures_then_succeeds():
    route = respx.post(NOTIFY_URL).mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(429),
            httpx.Response(200, json={"status": "delivered", "provider_id": "p-1"}),
        ],
    )
    await provider_client.send_notification("user@example.com", "hi", "sms")
    assert route.call_count == 3


@respx.mock
async def test_exhausts_retries_and_raises_retryable_error():
    respx.post(NOTIFY_URL).mock(return_value=httpx.Response(429))
    with pytest.raises(RetryableProviderError):
        await provider_client.send_notification("user@example.com", "hi", "email")


@respx.mock
async def test_non_retryable_response_fails_without_retrying():
    route = respx.post(NOTIFY_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(ProviderError):
        await provider_client.send_notification("user@example.com", "hi", "email")
    assert route.call_count == 1


@respx.mock
async def test_sends_expected_payload_and_headers():
    route = respx.post(NOTIFY_URL).mock(
        return_value=httpx.Response(
            200,
            json={"status": "delivered", "provider_id": "p-1"},
        ),
    )
    await provider_client.send_notification("user@example.com", "hi", "email")

    request = route.calls.last.request
    assert request.headers["X-API-Key"] == "test-dev-2026"
    assert json.loads(request.content) == {
        "to": "user@example.com",
        "message": "hi",
        "type": "email",
    }
