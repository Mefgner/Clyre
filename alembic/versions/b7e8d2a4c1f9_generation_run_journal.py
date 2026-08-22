"""generation_run journal

Revision ID: b7e8d2a4c1f9
Revises: a1f2c3d4e5b6
Create Date: 2026-08-21 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e8d2a4c1f9"
down_revision: Union[str, None] = "a1f2c3d4e5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "generation_run",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "thread_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("side_effects", sa.SmallInteger(), nullable=False),
        sa.Column("creation_date", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("update_time", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["thread_id"], ["thread.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generation_run_id"), "generation_run", ["id"], unique=True)
    op.create_index(op.f("ix_generation_run_thread_id"), "generation_run", ["thread_id"])
    op.create_index(op.f("ix_generation_run_user_id"), "generation_run", ["user_id"])
    op.create_index(op.f("ix_generation_run_status"), "generation_run", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_generation_run_status"), table_name="generation_run")
    op.drop_index(op.f("ix_generation_run_user_id"), table_name="generation_run")
    op.drop_index(op.f("ix_generation_run_thread_id"), table_name="generation_run")
    op.drop_index(op.f("ix_generation_run_id"), table_name="generation_run")
    op.drop_table("generation_run")
