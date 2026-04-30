from typing import List

from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr


class PasswordChange(BaseModel):
    old_password: str
    new_password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    id: str


class HistoryEntry(BaseModel):
    memory: str
    created_at: str


class HistoryResponse(BaseModel):
    memories: List[HistoryEntry]
