from datetime import datetime, timezone, timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.exceptions.errors import AuthenticationFailed, BadRequestError, EntityAlreadyExistsError, UnauthorizedError,WeakPasswordError
from app.schemas.auth import LoginRequest, ForgotPasswordRequest, ResetPasswordRequest

from app import schemas, models
from app.api import deps
from app.core import security
from app.core.config import settings

import secrets
from app.models.password_reset_token import PasswordResetToken
from app.core.email import send_reset_email
from app.core.security import get_password_hash

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

    # if not is_password_secure(user_in.password) or user_in.email == user_in.password:
    #     raise WeakPasswordError(name="Senha fraca", message="Use pelo menos 8 caracteres, incluindo letras maiúsculas e minúsculas, números e símbolos.")
    
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
    
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    
    refresh_token = security.create_refresh_token(user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }
    

@router.get("/me", response_model=schemas.UserResponse)
def read_user_me(current_user: models.User = Depends(deps.get_current_user)) -> Any:
    return current_user

@router.post("/refresh", response_model=schemas.token.RefreshTokenResponse)
def refresh_token(
    body: schemas.token.RefreshTokenRequest,
    db: Session = Depends(deps.get_db)
):
    payload = security.verify_refresh_token(body.refresh_token)
    if not payload:
        raise UnauthorizedError(
            message="Refresh token inválido ou expirado"
        )

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedError(
            message="Token inválido"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise AuthenticationFailed(
            message="Utilizador não encontrado"
        )

    return schemas.RefreshTokenResponse(
        access_token=security.create_access_token({"sub": str(user.id)}),
        refresh_token=security.create_refresh_token({"sub": str(user.id)}),
    )
    
@router.put("/profile")
@router.put("/profile")
def update_profile(
    body: schemas.UpdateProfileRequest,
    current_user: models.User = Depends(deps.get_current_user),
    db: Session = Depends(deps.get_db)
):
    if not security.verify_password(body.current_password, current_user.password):
        raise BadRequestError(message="Senha incorreta")

    current_user.name = body.name
    current_user.email = body.email

    if body.new_password:
        current_user.password = security.get_password_hash(body.new_password)

    db.commit()
    db.refresh(current_user)
    return current_user

# def is_password_secure(password: str) -> bool:
#     import re
#     if len(password) < 8:
#         return False
#     if not re.search(r"[A-Z]", password):
#         return False
#     if not re.search(r"[a-z]", password):
#         return False
#     if not re.search(r"\d", password):
#         return False
#     if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
#         return False
#     return True

@router.post("/forgot-password", status_code=200)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(deps.get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()

    if not user:
        return {"message": "Se o email existir, receberás um link de recuperação."}

    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at == None,
    ).delete()

    token      = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

    db.add(PasswordResetToken(
        user_id    = user.id,
        token      = token,
        expires_at = expires_at,
    ))
    db.commit()

    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    send_reset_email(user.email, reset_link)

    return {"message": "Se o email existir, receberás um link de recuperação."}


@router.post("/reset-password", status_code=200)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(deps.get_db)):
    if payload.password != payload.password_confirmation:
        raise HTTPException(status_code=422, detail="As senhas não coincidem.")

    reset_token = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token == payload.token)
        .first()
    )

    if not reset_token:
        raise HTTPException(status_code=400, detail="Token inválido.")

    if reset_token.used_at is not None:
        raise HTTPException(status_code=400, detail="Token já utilizado.")

    if reset_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token expirado.")

    user          = reset_token.user
    user.password = get_password_hash(payload.password)

    reset_token.used_at = datetime.now(timezone.utc)

    db.commit()

    return {"message": "Senha redefinida com sucesso."}