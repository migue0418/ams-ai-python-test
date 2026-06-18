import asyncio
import logging

from core.config import settings
from domain.repository import InMemoryRequestRepository
from services import extraction, provider_client

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[str] | None = None
_workers: list[asyncio.Task] = []


async def start(repository: InMemoryRequestRepository) -> None:
    global _queue, _workers
    _queue = asyncio.Queue()
    # pool size caps concurrency against the provider, regardless of incoming HTTP burst
    _workers = [
        asyncio.create_task(_worker(repository, name=f"worker-{i}"))
        for i in range(settings.worker_concurrency)
    ]


async def stop() -> None:
    global _workers
    for task in _workers:
        task.cancel()
    await asyncio.gather(*_workers, return_exceptions=True)
    _workers = []


def enqueue(request_id: str) -> None:
    assert _queue is not None, "pipeline.start() must run before enqueue()"
    _queue.put_nowait(request_id)  # never block the request handler


async def _worker(repository: InMemoryRequestRepository, name: str) -> None:
    """Pull request ids off the queue forever and run each through extraction + notify."""
    assert _queue is not None
    while True:
        request_id = await _queue.get()
        try:
            record = repository.get(request_id)
            if record is not None:
                intent = await extraction.extract_with_retry(record.user_input)
                await provider_client.send_notification(
                    intent.to,
                    intent.message,
                    intent.type,
                )
                repository.mark_sent(request_id)
        except Exception:
            # bad ai response (markdown, wrong keys, broken json) and provider
            # failures that survive all retries both just land here as a failure
            logger.exception("[%s] failed to process request %s", name, request_id)
            repository.mark_failed(request_id)
        finally:
            _queue.task_done()
