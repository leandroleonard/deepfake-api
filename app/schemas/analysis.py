from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List, Any
from app.enums import MediaTypeEnum, StatusEnum
from app.schemas.result import ResultResponse

class AnalysisBase(BaseModel):
    media_type: MediaTypeEnum = MediaTypeEnum.image
    media_id: Optional[str] = None

class AnalysisCreate(AnalysisBase):
    user_id: str

class AnalysisUpdate(BaseModel):
    status: Optional[StatusEnum] = None
    media_id: Optional[str] = None

class AnalysisListItem(BaseModel):
    id: str
    status: StatusEnum
    media_type: MediaTypeEnum
    media_url: Optional[str] = None
    created_at: datetime
    result: Optional[Any] = None

    model_config = {"from_attributes": True}

class AnalysisDetailResponse(BaseModel):
    id: str
    status: StatusEnum
    media_type: MediaTypeEnum
    media_url: Optional[str] = None
    created_at: datetime
    results: List[ResultResponse] = []

    model_config = {"from_attributes": True}

class AnalysisStatusResponse(BaseModel):
    status: StatusEnum
    results: List[ResultResponse] = []

    model_config = {"from_attributes": True}