from domain.models import (
    RequestCreatedOut,
    RequestIn,
    RequestStatus,
    RequestStatusOut,
)
from domain.repository import InMemoryRequestRepository, get_repository
from fastapi import APIRouter, Depends, HTTPException, Response, status
from services import pipeline

router = APIRouter(prefix="/requests", tags=["Requests"])


@router.post(
    "",
    response_model=RequestCreatedOut,
    status_code=status.HTTP_201_CREATED,
)
def create_request(
    payload: RequestIn,
    repository: InMemoryRequestRepository = Depends(get_repository),
) -> RequestCreatedOut:
    record = repository.create(payload)
    return RequestCreatedOut(id=record.id)


@router.post("/{request_id}/process", response_model=RequestStatusOut)
async def process_request(
    request_id: str,
    response: Response,
    repository: InMemoryRequestRepository = Depends(get_repository),
) -> RequestStatusOut:
    record = repository.get(request_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    # only the first call enqueues, a repeat call just returns the current status
    if record.status == RequestStatus.queued:
        if not pipeline.enqueue(request_id):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Queue is full, try again later",
            )
        record = repository.start_processing(request_id)
        response.status_code = status.HTTP_202_ACCEPTED

    return RequestStatusOut(id=record.id, status=record.status)


@router.get("/{request_id}", response_model=RequestStatusOut)
def get_request(
    request_id: str,
    repository: InMemoryRequestRepository = Depends(get_repository),
) -> RequestStatusOut:
    record = repository.get(request_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )
    return RequestStatusOut(id=record.id, status=record.status)
