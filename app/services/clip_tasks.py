import logging
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.enums import StatusEnum, MediaTypeEnum
from app.models.analysis import Analysis
from app.models.result import Result
from app.services.predictors.clip_predictor import predict_image, predict_video

logger     = logging.getLogger(__name__)
UPLOAD_DIR = "app/uploads"


@celery_app.task(name="process_clip_analysis", bind=True, acks_late=True)
def process_clip_analysis(self, analysis_id: str) -> None:
    db: Session = SessionLocal()

    try:
        analysis = (
            db.query(Analysis)
            .options(joinedload(Analysis.media))
            .filter(Analysis.id == analysis_id)
            .first()
        )

        if not analysis or not analysis.media:
            logger.warning(f"[CLIP {analysis_id}] Análise não encontrada ou sem media. Skipping.")
            return

        file_path = os.path.join(UPLOAD_DIR, analysis.media.location)

        if not os.path.exists(file_path):
            logger.error(f"[CLIP {analysis_id}] Ficheiro não encontrado: {file_path}")
            return

        started_at = datetime.now(timezone.utc)

        if analysis.media_type == MediaTypeEnum.video:
            result_data = predict_video(file_path)
        else:
            result_data = predict_image(file_path)

        db.add(Result(
            analysis_id=analysis.id,
            type="clip_detection",
            result=result_data,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        ))
        db.commit()

        logger.info(
            f"[CLIP {analysis_id}] → "
            f"{result_data.get('prediction')} ({result_data.get('confidence')})"
        )

    except Exception as e:
        logger.exception(f"[CLIP {analysis_id}] Erro inesperado: {e}")
        db.rollback()
        raise

    finally:
        db.close()