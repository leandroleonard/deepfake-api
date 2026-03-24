from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import os
import uuid
import shutil

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.media import Media
from app.models.analysis import Analysis
from app.schemas.analysis import (
    AnalysisListItem,
    AnalysisDetailResponse,
    AnalysisStatusResponse,
)
from app.enums import MediaTypeEnum, StatusEnum
from app.exceptions.errors import EntityDoesNotExistError, BadRequestError, PaymentRequiredError, DeepFakeApiError

from app.services.deepfake_tasks import process_deepfake_analysis
from app.services.illumination_task import process_illumination_analysis
from app.services.jpeg_artifact_task import process_jpeg_artifact_analysis
from app.services.face_swap_task import process_face_swap_analysis
from app.services.metadata_ai_task import process_metadata_ai_analysis

router = APIRouter()

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "mp4", "mov"}
MAX_FILE_SIZE = 5120 * 1024
UPLOAD_DIR = "app/uploads"

def get_media_url(location: str) -> str:
    return f"/uploads/{location}"

def save_upload_file(upload_file: UploadFile) -> tuple[str, int, str]:
    """Salva o arquivo e retorna (location, size, extension)"""
    extension = upload_file.filename.split(".")[-1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise BadRequestError(
            message=f"Extensão '{extension}' não permitida. Use: jpg, jpeg, png, mp4, mov",
            name="InvalidFileType"
        )

    os.makedirs(os.path.join(UPLOAD_DIR, "media"), exist_ok=True)

    filename = f"{uuid.uuid4().hex}.{extension}"
    relative_location = f"media/{filename}" 
    file_path = os.path.join(UPLOAD_DIR, relative_location)

    file_size = 0
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
        file_size = os.path.getsize(file_path)

    if file_size > MAX_FILE_SIZE:
        os.remove(file_path)
        raise BadRequestError(
            message=f"Arquivo muito grande. Máximo permitido: 5MB",
            name="FileTooLarge"
        )

    return relative_location, file_size, extension 


# POST /analysis — store
@router.post("/", response_model=AnalysisDetailResponse, status_code=201)
def store(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    COST = 2
    if current_user.tokens < COST:
        raise PaymentRequiredError(
            message="Créditos insuficientes para realizar a análise."
        )

    filename, file_size, extension = save_upload_file(file)

    media_type = (
        MediaTypeEnum.video
        if file.content_type and file.content_type.startswith("video")
        else MediaTypeEnum.image
    )

    try:
        media = Media(
            location=filename,
            size=file_size,
            extension=extension,
        )
        db.add(media)
        db.flush()

        analysis = Analysis(
            user_id=current_user.id,
            media_type=media_type,
            media_id=media.id,
            status=StatusEnum.pending,
        )
        db.add(analysis)

        current_user.tokens -= COST
        db.add(current_user)

        db.commit()
        
        db.refresh(analysis)
        db.refresh(media)
        db.refresh(current_user)

        process_illumination_analysis.delay(analysis.id, analysis.media_type)
        process_face_swap_analysis.delay(analysis.id, analysis.media_type)
        process_metadata_ai_analysis.delay(analysis.id)
        
        process_deepfake_analysis.delay(analysis.id)
        
        if analysis.media_type == 'image':
            process_jpeg_artifact_analysis.delay(analysis.id)

        return AnalysisDetailResponse(
            id=analysis.id,
            status=analysis.status,
            media_type=analysis.media_type,
            media_url=get_media_url(media.location),
            created_at=analysis.created_at,
            results=[],
        )

    except Exception as e:
        db.rollback()
        raise DeepFakeApiError(
            message=f"Erro ao processar análise: {str(e)}"
        )

@router.get("/{id}", response_model=AnalysisDetailResponse)
def show(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    analysis = (
        db.query(Analysis)
        .filter(Analysis.id == id, Analysis.user_id == current_user.id, Analysis.deleted_at == None)
        .first()
    )

    if not analysis:
        raise EntityDoesNotExistError(message="Análise não encontrada", name="AnalysisNotFound")

    media_url = get_media_url(analysis.media.location) if analysis.media else None

    return AnalysisDetailResponse(
        id=analysis.id,
        status=analysis.status,
        media_type=analysis.media_type,
        media_url=media_url,
        created_at=analysis.created_at,
        results=analysis.results,
    )


# GET /analysis/{id}/status — status
@router.get("/{id}/status", response_model=AnalysisStatusResponse)
def status(
    id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    analysis = (
        db.query(Analysis)
        .filter(Analysis.id == id, Analysis.user_id == current_user.id, Analysis.deleted_at == None)
        .first()
    )

    if not analysis:
        raise EntityDoesNotExistError(message="Análise não encontrada", name="AnalysisNotFound")

    return AnalysisStatusResponse(
        status=analysis.status,
        results=analysis.results,
    )


# GET /history — index
@router.get("/", response_model=List[AnalysisListItem])
def index(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    analyses = (
        db.query(Analysis)
        .filter(Analysis.user_id == current_user.id, Analysis.deleted_at == None)
        .order_by(Analysis.created_at.desc())
        .all()
    )

    result = []
    for analysis in analyses:
        first_result = analysis.results[0] if analysis.results else None
        result.append(
            AnalysisListItem(
                id=analysis.id,
                status=analysis.status,
                media_type=analysis.media_type,
                media_url=get_media_url(analysis.media.location) if analysis.media else None,
                created_at=analysis.created_at,
                result=first_result.result if first_result else None,
            )
        )

    return result