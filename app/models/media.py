from sqlalchemy import Column, String, Integer, DateTime, func, text
from sqlalchemy.orm import relationship
from app.db.base import Base

class Media(Base):
    __tablename__ = "media"

    id = Column(String(32), primary_key=True, server_default=text("DEFAULT"))
    location = Column(String, nullable=False)
    size = Column(Integer, nullable=True)
    extension = Column(String(10), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True, default=None)

    analyses = relationship("Analysis", back_populates="media")