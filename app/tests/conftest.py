import sys
from pathlib import Path

# bare `pytest` only puts tests/ on sys.path (no __init__.py here), not app/;
# `python -m pytest` would add it automatically, but this works either way.
# Kept as the first thing this module does, on purpose: domain/services aren't
# imported at module level here so an import-sorter can't hoist them above
# this line and reintroduce the ModuleNotFoundError it's working around.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


@pytest.fixture(autouse=True)
def _clean_state():
    from domain.repository import get_repository
    from services.provider_client import _rate_limiter

    get_repository()._records.clear()
    _rate_limiter._timestamps.clear()
    yield
    get_repository()._records.clear()
    _rate_limiter._timestamps.clear()
