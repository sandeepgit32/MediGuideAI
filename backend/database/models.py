import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True
    )
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)

    consultations = relationship(
        "ConsultationHistory", back_populates="user", cascade="all, delete-orphan"
    )


class ConsultationHistory(Base):
    """One row per completed triage result, keyed by user."""

    __tablename__ = "consultation_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    severity = Column(String(16), nullable=False)
    symptoms = Column(Text, nullable=False)
    recommended_action = Column(Text, nullable=False)
    urgency = Column(String(64), nullable=False)
    notes = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)

    user = relationship("User", back_populates="consultations")
