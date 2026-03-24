import logging
import json
import os
import subprocess
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session, joinedload

from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.session import SessionLocal
from app.enums import StatusEnum, MediaTypeEnum
from app.models.analysis import Analysis
from app.models.result import Result


@celery_app.task(name="process_deepfake_analysis", bind=True, acks_late=True)
def process_deepfake_analysis(self, analysis_id: str) -> None:
    db: Session = SessionLocal()
    analysis = None

    try:
        analysis = (
            db.query(Analysis)
            .options(joinedload(Analysis.media))
            .filter(Analysis.id == analysis_id)
            .first()
        )

        if not analysis or not analysis.media:
            logger.warning(f"[analysis {analysis_id}] Not found or has no media. Skipping.")
            return

        if analysis.status != StatusEnum.pending:
            logger.warning(f"[analysis {analysis_id}] Status is '{analysis.status}', expected 'pending'. Skipping.")
            return

        analysis.status = StatusEnum.processing
        db.commit()

        media = analysis.media

        UPLOAD_DIR = "app/uploads"

        file_path = os.path.join(UPLOAD_DIR, media.location)

        if not os.path.exists(file_path):
            logger.error(f"[analysis {analysis_id}] File not found: {file_path}")
            analysis.status = StatusEnum.failed
            db.commit()
            return

        script_path = settings.DEEPFAKE_SCRIPT

        if analysis.media_type == MediaTypeEnum.video:
            cmd = [settings.DEEPFAKE_PYTHON, script_path, "--video", file_path]
        else:
            cmd = [settings.DEEPFAKE_PYTHON, script_path, "--image", file_path]

        started_at = datetime.now(timezone.utc)

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60 * 20, 
        )

        output = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()

        if err:
            logger.warning(f"[analysis {analysis_id}] stderr:\n{err}")

        if proc.returncode != 0:
            logger.error(
                f"[analysis {analysis_id}] Script exited with code {proc.returncode}.\n"
                f"stdout: {output[:300]}\nstderr: {err[:300]}"
            )
            analysis.status = StatusEnum.failed
            db.commit()
            return

        if not output:
            logger.error(f"[analysis {analysis_id}] Script returned empty stdout. stderr: {err[:300]}")
            analysis.status = StatusEnum.failed
            db.commit()
            return

        try:
            result_data = json.loads(output)
        except json.JSONDecodeError:
            logger.error(f"[analysis {analysis_id}] Failed to parse JSON. Raw output: {output[:300]}")
            analysis.status = StatusEnum.failed
            db.commit()
            return

        db.add(
            Result(
                analysis_id=analysis.id,
                type="deepfake_detection",
                result=result_data,  
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )
        )

        analysis.status = StatusEnum.completed
        db.commit()

    except subprocess.TimeoutExpired:
        logger.error(f"[analysis {analysis_id}] Script timed out after {60 * 20}s")
        if analysis:
            analysis.status = StatusEnum.failed
            db.commit()
    except Exception as e:
        logger.exception(f"[analysis {analysis_id}] Unexpected error: {e}")
        if analysis:
            analysis.status = StatusEnum.failed
            db.commit()
        raise
    finally:
        db.close()