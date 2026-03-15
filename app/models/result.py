from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.db.base import Base

class Result(Base):
    __tablename__ = "results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(String(32), ForeignKey("analysis.id"), nullable=False)
    type = Column(String(40), nullable=False)
    result = Column(JSON, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    analysis = relationship("Analysis", back_populates="results")