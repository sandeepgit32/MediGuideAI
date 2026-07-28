import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
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

    # relationship() defines an ORM relationship between two SQLAlchemy models.
    # In this example, a User has a one-to-many relationship with ConsultationHistory,
    # allowing access to all of a user's consultations through user.consultations.
    # The back_populates="user" option creates a bidirectional relationship so each
    # ConsultationHistory object can access its parent user through consultation.user.
    # The cascade="all, delete-orphan" option propagates operations such as save and
    # delete from the parent to its children, and automatically deletes child records
    # that are removed from the parent's collection and no longer belong to any parent.
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
