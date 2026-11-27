"""support in-progress deletion execution claims and recovery details

Revision ID: c4f8a2d91b60
Revises: 9b1d5f3c7a20
Create Date: 2026-11-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4f8a2d91b60"
down_revision: Union[str, Sequence[str], None] = "9b1d5f3c7a20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("deletion_executions", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_deletion_executions_status", type_="check")
        batch_op.alter_column(
            "completed_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )
        batch_op.add_column(sa.Column("failure_code", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("failure_message", sa.Text(), nullable=True))
        batch_op.create_check_constraint(
            "ck_deletion_executions_status",
            "status IN ('IN_PROGRESS', 'COMPLETED', 'FAILED', 'CANCELLED')",
        )


def downgrade() -> None:
    connection = op.get_bind()
    non_completed_count = connection.execute(
        sa.text("SELECT count(*) FROM deletion_executions WHERE status != 'COMPLETED'")
    ).scalar_one()
    if non_completed_count:
        raise RuntimeError(
            "Cannot downgrade while deletion executions are not all COMPLETED."
        )

    with op.batch_alter_table("deletion_executions", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_deletion_executions_status", type_="check")
        batch_op.drop_column("failure_message")
        batch_op.drop_column("failure_code")
        batch_op.alter_column(
            "completed_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
        batch_op.create_check_constraint(
            "ck_deletion_executions_status",
            "status = 'COMPLETED'",
        )
