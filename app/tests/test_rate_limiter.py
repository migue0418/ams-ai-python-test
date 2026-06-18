import time

from services.rate_limiter import SlidingWindowRateLimiter


async def test_allows_up_to_max_requests_immediately():
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=1.0)
    start = time.monotonic()
    for _ in range(3):
        await limiter.acquire()
    assert time.monotonic() - start < 0.1


async def test_blocks_until_the_window_frees_a_slot():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=0.3)
    await limiter.acquire()
    await limiter.acquire()

    start = time.monotonic()
    await limiter.acquire()
    elapsed = time.monotonic() - start

    assert elapsed >= 0.2
