from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "deepfake",
    broker=settings.REDIS_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

import app.services.deepfake_tasks
import app.services.illumination_task
import app.services.jpeg_artifact_task