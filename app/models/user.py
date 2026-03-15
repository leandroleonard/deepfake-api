from sqlalchemy import Column, String, Integer, DateTime, func
from sqlalchemy.orm import relationship
from app.db.base import Base
import uuid

class User(Base):
    __tablename__ = "users"

    id = Column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    name = Column(String(50), nullable=False)
    email = Column(String(50), nullable=False, unique=True)
    password = Column(String, nullable=False)
    tokens = Column(Integer, default=10)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True, default=None)

    analyses = relationship("Analysis", back_populates="user")