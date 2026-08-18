"""add hashed refresh tokens

Revision ID: 71c4d8e2a906
Revises: 17384dfab4bd
Create Date: 2026-08-18 20:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "71c4d8e2a906"
down_revision: Union[str, None] = "17384dfab4bd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "refresh_token",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_refresh_token_expires_at"), "refresh_token", ["expires_at"])
    op.create_index(op.f("ix_refresh_token_id"), "refresh_token", ["id"], unique=True)
    op.create_index(
        op.f("ix_refresh_token_token_hash"), "refresh_token", ["token_hash"], unique=True
    )
    op.create_index(
        "ix_refresh_token_user_revoked_expires",
        "refresh_token",
        ["user_id", "revoked_at", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_token_user_revoked_expires", table_name="refresh_token")
    op.drop_index(op.f("ix_refresh_token_token_hash"), table_name="refresh_token")
    op.drop_index(op.f("ix_refresh_token_id"), table_name="refresh_token")
    op.drop_index(op.f("ix_refresh_token_expires_at"), table_name="refresh_token")
    op.drop_table("refresh_token")
