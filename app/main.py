from fastapi import FastAPI
from app.core.config import settings
from app.api.v1.api import api_router

from app.exceptions.errors import DeepFakeApiError
from app.exceptions.handler import deepfake_exception_handler

app = FastAPI(title=settings.PROJECT_NAME)
app.add_exception_handler(DeepFakeApiError, deepfake_exception_handler)

@app.get("/")
def status():
    return {"message": "API running"}

app.include_router(api_router, prefix="/api/v1")