import httpx
from core.config import settings
from services.rate_limiter import SlidingWindowRateLimiter
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

NOTIFY_PATH = "/v1/notify"

_client: httpx.AsyncClient | None = None
_rate_limiter = SlidingWindowRateLimiter(
    max_requests=settings.rate_limit_max_requests,
    window_seconds=settings.rate_limit_window_seconds,
)


# split so tenacity only retries the transient one, not e.g. a bad payload
class ProviderError(Exception):
    """Non-retryable provider failure (auth, validation, unexpected response)."""


class RetryableProviderError(ProviderError):
    """Transient provider failure (429/500/timeout/connection), safe to retry."""


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


@retry(
    retry=retry_if_exception_type(RetryableProviderError),
    wait=wait_exponential_jitter(
        initial=settings.retry_wait_initial_seconds,
        max=settings.retry_wait_max_seconds,
    ),
    stop=stop_after_attempt(settings.retry_max_attempts),
    reraise=True,
)
async def send_notification(to: str, message: str, notif_type: str) -> None:
    """Send to the provider; raises if it never succeeds after retries."""
    assert _client is not None, (
        "provider_client.start() must run before send_notification()"
    )

    await _rate_limiter.acquire()
    try:
        response = await _client.post(
            NOTIFY_PATH,
            json={"to": to, "message": message, "type": notif_type},
            headers={"X-API-Key": settings.provider_api_key},
        )
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        raise RetryableProviderError(str(exc)) from exc

    if response.status_code == 200:
        return
    if response.status_code in (429, 500):
        raise RetryableProviderError(f"provider returned {response.status_code}")
    raise ProviderError(
        f"unexpected provider response {response.status_code}: {response.text}",
    )
