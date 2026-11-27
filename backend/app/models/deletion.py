"""Durable records for deletion approval and execution."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.types import UTCDateTime


def utc_now() -> datetime:
    return datetime.now(UTC)


class DeletionRequest(Base):
    """A request to delete one task, pending explicit human authorization."""

    __tablename__ = "deletion_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'COMPLETED', "
            "'FAILED', 'CANCELLED', 'EXPIRED')",
            name="ck_deletion_requests_status",
        ),
        Index("ix_deletion_requests_thread_status", "thread_id", "status"),
        Index("ix_deletion_requests_task_status", "task_id", "status"),
        UniqueConstraint(
            "thread_id", "execution_id", "tool_call_id",
            name="uq_deletion_requests_tool_call",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    task_title_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(36), nullable=False)
    execution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)

    approval: Mapped["DeletionApproval"] = relationship(
        back_populates="deletion_request", uselist=False
    )
    execution: Mapped["DeletionExecution | None"] = relationship(
        back_populates="deletion_request", uselist=False
    )


class DeletionApproval(Base):
    """One explicit approval decision associated with one deletion request."""

    __tablename__ = "deletion_approvals"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_deletion_approvals_decision",
        ),
        UniqueConstraint("deletion_request_id", name="uq_deletion_approvals_request"),
        Index("ix_deletion_approvals_thread", "thread_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deletion_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("deletion_requests.id", ondelete="RESTRICT"), nullable=False
    )
    thread_id: Mapped[str] = mapped_column(String(36), nullable=False)
    execution_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[str] = mapped_column(String(12), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    deletion_request: Mapped[DeletionRequest] = relationship(back_populates="approval")


class DeletionExecution(Base):
    """Durable claim and outcome record for one deletion attempt."""

    __tablename__ = "deletion_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('IN_PROGRESS', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_deletion_executions_status",
        ),
        UniqueConstraint("deletion_request_id", name="uq_deletion_executions_request"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    deletion_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("deletion_requests.id", ondelete="RESTRICT"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="IN_PROGRESS")
    started_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    deletion_request: Mapped[DeletionRequest] = relationship(back_populates="execution")
