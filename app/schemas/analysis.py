from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.enums import MediaTypeEnum, StatusEnum

class AnalysisBase(BaseModel):
    media_type: MediaTypeEnum = MediaTypeEnum.image
    media_id: Optional[str] = None

class AnalysisCreate(AnalysisBase):
    user_id: str

class AnalysisUpdate(BaseModel):
    status: Optional[StatusEnum] = None
    media_id: Optional[str] = None

class AnalysisResponse(AnalysisBase):
    id: str
    user_id: str
    status: StatusEnum
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}