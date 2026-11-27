"""add durable deletion approval and execution records

Revision ID: 9b1d5f3c7a20
Revises: e08e4db1d85c
Create Date: 2026-11-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b1d5f3c7a20"
down_revision: Union[str, Sequence[str], None] = "e08e4db1d85c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deletion_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("task_title_snapshot", sa.String(length=255), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.Column("tool_call_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("cancellation_reason", sa.String(length=120), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'COMPLETED', 'FAILED', 'CANCELLED', 'EXPIRED')",
            name="ck_deletion_requests_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "thread_id", "execution_id", "tool_call_id",
            name="uq_deletion_requests_tool_call",
        ),
    )
    op.create_index(
        "ix_deletion_requests_thread_status",
        "deletion_requests",
        ["thread_id", "status"],
    )
    op.create_index(
        "ix_deletion_requests_task_status",
        "deletion_requests",
        ["task_id", "status"],
    )

    op.create_table(
        "deletion_approvals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deletion_request_id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.Column("tool_call_id", sa.String(length=255), nullable=False),
        sa.Column("decision", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "decision IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_deletion_approvals_decision",
        ),
        sa.ForeignKeyConstraint(
            ["deletion_request_id"], ["deletion_requests.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deletion_request_id", name="uq_deletion_approvals_request"),
    )
    op.create_index("ix_deletion_approvals_thread", "deletion_approvals", ["thread_id"])

    op.create_table(
        "deletion_executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deletion_request_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status = 'COMPLETED'", name="ck_deletion_executions_status"),
        sa.ForeignKeyConstraint(
            ["deletion_request_id"], ["deletion_requests.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deletion_request_id", name="uq_deletion_executions_request"),
    )


def downgrade() -> None:
    op.drop_table("deletion_executions")
    op.drop_index("ix_deletion_approvals_thread", table_name="deletion_approvals")
    op.drop_table("deletion_approvals")
    op.drop_index("ix_deletion_requests_task_status", table_name="deletion_requests")
    op.drop_index("ix_deletion_requests_thread_status", table_name="deletion_requests")
    op.drop_table("deletion_requests")
