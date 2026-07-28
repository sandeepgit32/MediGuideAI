from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    # `model_config = ConfigDict(from_attributes=True)` is used to allow Pydantic
    # models to be created from ORM objects, such as SQLAlchemy models, instead
    # of only from dictionaries. In FastAPI applications, database queries
    # return objects with attributes (user.id, user.email), so `from_attributes=True `
    # tells Pydantic to read values from those object attributes and convert
    # them into a response model.
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
    summary: Optional[str] = None


class HistoryResponse(BaseModel):
    memories: List[HistoryEntry]
