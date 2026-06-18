import logging
from contextlib import asynccontextmanager

from api.routes import router as api_router
from domain.repository import get_repository
from fastapi import FastAPI
from services import ai_client, pipeline, provider_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ai_client.start()
    await provider_client.start()
    await pipeline.start(get_repository())

    yield

    await pipeline.stop()
    await provider_client.stop()
    await ai_client.stop()


app = FastAPI(title="Notification Service (Technical Test)", lifespan=lifespan)

app.include_router(api_router, prefix="/v1")
