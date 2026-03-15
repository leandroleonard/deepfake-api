from sqlalchemy import Column, String, DateTime, ForeignKey, func, Enum as SAEnum
from sqlalchemy.orm import relationship
from app.db.base import Base
from app.enums import MediaTypeEnum, StatusEnum
import uuid

class Analysis(Base):
    __tablename__ = "analysis"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    user_id = Column(String(32), ForeignKey("users.id"), nullable=False)
    media_type = Column(SAEnum(MediaTypeEnum), default=MediaTypeEnum.image)
    media_id = Column(String(32), ForeignKey("media.id"), nullable=True)
    status = Column(SAEnum(StatusEnum), default=StatusEnum.pending)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True, default=None)

    user = relationship("User", back_populates="analyses")
    media = relationship("Media", back_populates="analyses")
    results = relationship("Result", back_populates="analysis")