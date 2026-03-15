from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Any

class ResultBase(BaseModel):
    type: str
    result: Any
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

class ResultCreate(ResultBase):
    analysis_id: str

class ResultResponse(ResultBase):
    id: int
    analysis_id: str

    model_config = {"from_attributes": True}