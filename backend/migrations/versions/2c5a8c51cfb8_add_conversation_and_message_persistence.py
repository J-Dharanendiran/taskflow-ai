
"""add conversation and message persistence

Revision ID: 2c5a8c51cfb8
Revises: c4f8a2d91b60
Create Date: 2026-11-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2c5a8c51cfb8"
down_revision: Union[str, Sequence[str], None] = "c4f8a2d91b60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("thread_id"),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_messages_valid_role",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.thread_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_messages_conversation_created_id",
        "messages",
        ["conversation_id", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_messages_conversation_created_id",
        table_name="messages",
    )

    op.drop_table("messages")
    op.drop_table("conversations")
