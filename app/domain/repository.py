import uuid
from typing import Optional

from domain.models import RequestIn, RequestRecord, RequestStatus


class InMemoryRequestRepository:
    def __init__(self) -> None:
        self._records: dict[str, RequestRecord] = {}

    def create(self, data: RequestIn) -> RequestRecord:
        record = RequestRecord(id=str(uuid.uuid4()), user_input=data.user_input)
        self._records[record.id] = record
        return record

    def get(self, request_id: str) -> Optional[RequestRecord]:
        return self._records.get(request_id)

    def start_processing(self, request_id: str) -> RequestRecord:
        record = self._records[request_id]
        record.status = RequestStatus.processing
        return record

    def mark_sent(self, request_id: str) -> None:
        self._records[request_id].status = RequestStatus.sent

    def mark_failed(self, request_id: str) -> None:
        self._records[request_id].status = RequestStatus.failed


_repository = InMemoryRequestRepository()


def get_repository() -> InMemoryRequestRepository:
    return _repository
