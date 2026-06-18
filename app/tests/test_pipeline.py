import asyncio

import httpx
import pytest
import respx
from domain.models import RequestIn, RequestStatus
from domain.repository import InMemoryRequestRepository
from services import ai_client, pipeline, provider_client

EXTRACT_URL = "http://localhost:3001/v1/ai/extract"
NOTIFY_URL = "http://localhost:3001/v1/notify"


def _extract_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": content}}]},
    )


async def _wait_until_terminal(repo, request_id, timeout=5.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        record = repo.get(request_id)
        if record.status in (RequestStatus.sent, RequestStatus.failed):
            return record
        await asyncio.sleep(0.05)
    raise TimeoutError(f"{request_id} never reached a terminal state")


@pytest.fixture
async def repo():
    repository = InMemoryRequestRepository()
    await ai_client.start()
    await provider_client.start()
    await pipeline.start(repository)
    yield repository
    await pipeline.stop()
    await provider_client.stop()
    await ai_client.stop()


@respx.mock
async def test_enqueued_request_ends_up_sent(repo):
    respx.post(EXTRACT_URL).mock(
        return_value=_extract_response(
            '{"to": "user@example.com", "message": "hi", "type": "email"}',
        ),
    )
    respx.post(NOTIFY_URL).mock(
        return_value=httpx.Response(
            200,
            json={"status": "delivered", "provider_id": "p-1"},
        ),
    )

    record = repo.create(RequestIn(user_input="manda un email a user@example.com: hi"))
    repo.start_processing(record.id)
    assert pipeline.enqueue(record.id) is True

    final = await _wait_until_terminal(repo, record.id)
    assert final.status == RequestStatus.sent


@respx.mock
async def test_enqueued_request_ends_up_failed_when_extraction_unparseable(repo):
    respx.post(EXTRACT_URL).mock(
        return_value=_extract_response("Lo siento, no puedo procesar eso."),
    )
    # never expected to be hit, mocked anyway so a stray call doesn't blow up
    respx.post(NOTIFY_URL).mock(
        return_value=httpx.Response(
            200,
            json={"status": "delivered", "provider_id": "p-1"},
        ),
    )

    record = repo.create(RequestIn(user_input="hola"))
    repo.start_processing(record.id)
    pipeline.enqueue(record.id)

    final = await _wait_until_terminal(repo, record.id)
    assert final.status == RequestStatus.failed


@respx.mock
async def test_enqueued_request_ends_up_failed_after_provider_retries_exhausted(repo):
    respx.post(EXTRACT_URL).mock(
        return_value=_extract_response(
            '{"to": "user@example.com", "message": "hi", "type": "email"}',
        ),
    )
    respx.post(NOTIFY_URL).mock(return_value=httpx.Response(429))

    record = repo.create(RequestIn(user_input="hola"))
    repo.start_processing(record.id)
    pipeline.enqueue(record.id)

    final = await _wait_until_terminal(repo, record.id, timeout=15.0)
    assert final.status == RequestStatus.failed


async def test_enqueue_returns_false_when_queue_is_full(monkeypatch):
    monkeypatch.setattr(pipeline, "_queue", asyncio.Queue(maxsize=1))
    assert pipeline.enqueue("a") is True
    assert pipeline.enqueue("b") is False
