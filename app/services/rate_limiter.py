import asyncio
import time


class SlidingWindowRateLimiter:
    """Mirrors the provider's own rolling-window check, so we hold off before it 429s us."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._timestamps: list[float] = []

    async def acquire(self) -> None:
        while True:
            now = time.monotonic()
            self._timestamps = [
                t for t in self._timestamps if now - t < self._window_seconds
            ]
            if len(self._timestamps) < self._max_requests:
                self._timestamps.append(now)
                return
            await asyncio.sleep(self._window_seconds - (now - self._timestamps[0]))
