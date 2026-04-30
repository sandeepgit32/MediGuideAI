import uuid
from sqlalchemy import Column, String
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True
    )
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
