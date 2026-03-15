from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.exceptions.errors import AuthenticationFailed, EntityAlreadyExistsError
from app.schemas.auth import LoginRequest

from app import schemas, models
from app.api import deps
from app.core import security
from app.core.config import settings

router = APIRouter()

@router.post("/register", response_model=schemas.UserResponse)
def register(
    *,
    db: Session = Depends(deps.get_db),
    user_in: schemas.UserCreate
) -> Any:
    user = db.query(models.User).filter(models.User.email == user_in.email).first()
    if user:
        raise EntityAlreadyExistsError(name="Dados duplicados", message="Usuário já existe")

    if not is_password_secure(user_in.password) or user_in.email == user_in.password:
        raise WeakPasswordError(name="Senha fraca", message="Use pelo menos 8 caracteres, incluindo letras maiúsculas e minúsculas, números e símbolos.")
    
    db_obj = models.User(
        name=user_in.name,
        email=user_in.email,
        password=security.get_password_hash(user_in.password),
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

@router.post("/login", response_model=schemas.token.Token)
def login(
    *,
    db: Session = Depends(deps.get_db),
    credentials: LoginRequest = Body(...)
):
    user = db.query(models.User).filter(models.User.email == credentials.email).first()
    if not user or not security.verify_password(credentials.password, user.password):
        raise AuthenticationFailed(name="Erro no login", message="Email ou senha inválida")
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return {
        "access_token": security.create_access_token(user.id, expires_delta=access_token_expires),
        "token_type": "bearer",
    }

@router.get("/me", response_model=schemas.UserResponse)
def read_user_me(current_user: models.User = Depends(deps.get_current_user)) -> Any:
    return current_user


def is_password_secure(password: str) -> bool:
    import re
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False
    return True