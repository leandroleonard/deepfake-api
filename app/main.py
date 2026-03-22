from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.api.v1.api import api_router

from app.exceptions.errors import DeepFakeApiError
from app.exceptions.handler import deepfake_exception_handler
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title=settings.PROJECT_NAME)
app.add_exception_handler(DeepFakeApiError, deepfake_exception_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def status():
    return {"message": "API running"}

# Serve os arquivos de upload como estáticos
app.mount("/uploads", StaticFiles(directory="app/uploads"), name="uploads")
app.include_router(api_router, prefix="/api/v1")