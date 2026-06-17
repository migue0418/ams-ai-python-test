from api.routes import router as api_router
from fastapi import FastAPI

app = FastAPI(title="Notification Service (Technical Test)")

app.include_router(api_router, prefix="/v1")
