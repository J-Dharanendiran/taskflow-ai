
from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, Date, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.types import UTCDateTime


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(UTC)


class Task(Base):
    __tablename__ = "tasks"

    __table_args__ = (
        CheckConstraint(
            "length(trim(title)) > 0",
            name="ck_tasks_title_not_empty",
        ),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high')",
            name="ck_tasks_valid_priority",
        ),
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed')",
            name="ck_tasks_valid_status",
        ),
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_priority", "priority"),
        Index("ix_tasks_due_date", "due_date"),
    )

    # Primary key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    # Task information
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    due_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    # Task organization
    priority: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="medium",
        server_default="medium",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    # Timestamps — consistently handled as UTC
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(),
        nullable=True,
    )
