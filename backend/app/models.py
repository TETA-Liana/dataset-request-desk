from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

ROLES = ("client", "operator", "admin")
QUALITIES = ("good", "usable", "bad")
STATUSES = ("submitted", "in_progress", "delivered", "accepted", "rejected")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    organisation: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Episode(Base):
    __tablename__ = "episodes"

    # The id from the recording system is the primary key. This is what makes
    # re-importing the same file safe: the same episode can never be inserted twice.
    episode_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    robot_id: Mapped[str] = mapped_column(String(50))
    task_name: Mapped[str] = mapped_column(String(255))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_seconds: Mapped[int] = mapped_column(Integer)
    operator_name: Mapped[str | None] = mapped_column(String(255))
    quality: Mapped[str] = mapped_column(String(10))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DatasetRequest(Base):
    __tablename__ = "dataset_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    task_name: Mapped[str] = mapped_column(String(255))
    episodes_requested: Mapped[int] = mapped_column(Integer)
    deadline: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="submitted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    client: Mapped[User] = relationship()
    history: Mapped[list["StatusChange"]] = relationship(order_by="StatusChange.id")


class StatusChange(Base):
    """Append-only history. We never update or delete these rows."""
    __tablename__ = "status_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("dataset_requests.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(20))  # NULL for the first "submitted" row
    to_status: Mapped[str] = mapped_column(String(20))
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    comment: Mapped[str | None] = mapped_column(Text)

    changed_by: Mapped[User] = relationship()


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    # unique=True is the real guarantee that an episode sits on at most one request.
    # Even if two operators click at the same moment, the database rejects the second one.
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.episode_id"), unique=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("dataset_requests.id"), index=True)
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    episode: Mapped[Episode] = relationship()
