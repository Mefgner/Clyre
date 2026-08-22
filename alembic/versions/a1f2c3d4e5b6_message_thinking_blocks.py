"""message thinking blocks

Revision ID: a1f2c3d4e5b6
Revises: 71c4d8e2a906
Create Date: 2026-08-21 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1f2c3d4e5b6"
down_revision: Union[str, None] = "71c4d8e2a906"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("message", sa.Column("thinking_value", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("message", "thinking_value")
