import os
from dataclasses import dataclass


def _float_env(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _int_env(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    provider_base_url: str = os.environ.get(
        "PROVIDER_BASE_URL",
        "http://localhost:3001",
    )
    provider_api_key: str = os.environ.get("PROVIDER_API_KEY", "test-dev-2026")
    provider_timeout_seconds: float = _float_env("PROVIDER_TIMEOUT_SECONDS", 5.0)

    # caps how many requests hit the provider at once, well under its 50 in-flight limit
    worker_concurrency: int = _int_env("WORKER_CONCURRENCY", 30)

    retry_max_attempts: int = _int_env("RETRY_MAX_ATTEMPTS", 5)
    retry_wait_initial_seconds: float = _float_env("RETRY_WAIT_INITIAL_SECONDS", 0.2)
    retry_wait_max_seconds: float = _float_env("RETRY_WAIT_MAX_SECONDS", 5.0)


settings = Settings()
