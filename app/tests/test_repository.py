from domain.models import RequestIn, RequestStatus
from domain.repository import InMemoryRequestRepository


def _payload(text: str = "manda un email a juan@test.com diciendo hola") -> RequestIn:
    return RequestIn(user_input=text)


def test_create_starts_as_queued():
    repo = InMemoryRequestRepository()
    record = repo.create(_payload())
    assert record.status == RequestStatus.queued
    assert repo.get(record.id) is record


def test_get_missing_returns_none():
    repo = InMemoryRequestRepository()
    assert repo.get("does-not-exist") is None


def test_start_processing_transitions_to_processing():
    repo = InMemoryRequestRepository()
    record = repo.create(_payload())
    updated = repo.start_processing(record.id)
    assert updated.status == RequestStatus.processing
    assert repo.get(record.id).status == RequestStatus.processing


def test_mark_sent():
    repo = InMemoryRequestRepository()
    record = repo.create(_payload())
    repo.mark_sent(record.id)
    assert repo.get(record.id).status == RequestStatus.sent


def test_mark_failed():
    repo = InMemoryRequestRepository()
    record = repo.create(_payload())
    repo.mark_failed(record.id)
    assert repo.get(record.id).status == RequestStatus.failed


def test_records_are_independent_per_repository_instance():
    repo_a = InMemoryRequestRepository()
    repo_b = InMemoryRequestRepository()
    record = repo_a.create(_payload())
    assert repo_b.get(record.id) is None
