from fastapi import FastAPI
from app.core.config import settings
from app.api.v1.api import api_router

app = FastAPI(title=settings.PROJECT_NAME)

@app.get("/")
def status():
    return {"message": "API running"}

app.include_router(api_router, prefix="/api/v1")