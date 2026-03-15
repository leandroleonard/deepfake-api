from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class MediaBase(BaseModel):
    location: str
    size: Optional[int] = None
    extension: Optional[str] = None

class MediaCreate(MediaBase):
    pass

class MediaResponse(MediaBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}