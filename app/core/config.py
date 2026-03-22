from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import json

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "Deepfake Detector"

    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str

    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    CURRENT_VERSION: str = "1"
    CURRENT_VERSION_API: str = f"v{CURRENT_VERSION}"

    ALLOWED_HOSTS_ORIGIN: List[str] = ["*"]

    BASE_DIR: Path = BASE_DIR
    UPLOAD_DIR: Path = BASE_DIR / "uploads"
    MODELS_DIR: Path = BASE_DIR / "models"

    DEEPFAKE_PYTHON: str = "python3"
    DEEPFAKE_SCRIPT: Path = BASE_DIR / "deepfake_ai/predict.py"

    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CELERY_TASK_ALWAYS_EAGER: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow"
    )

settings = Settings()