from pydantic import BaseModel, EmailStr, validator
from datetime import datetime
from typing import Optional

class UserBase(BaseModel):
    name: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None

class UserResponse(UserBase):
    id: str
    tokens: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}    

class UpdateProfileRequest(BaseModel):
    name: str
    email: EmailStr
    current_password: str
    new_password: Optional[str] = None
    password_confirmation: Optional[str] = None

    @validator('password_confirmation')
    def passwords_match(cls, v, values):
        if values.get('new_password') and v != values['new_password']:
            raise ValueError('As senhas não coincidem')
        return v

    @validator('new_password')
    def password_min_length(cls, v):
        if v and len(v) < 8:
            raise ValueError('A senha deve ter no mínimo 8 caracteres')
        return v
    
    model_config = {"from_attributes": True}