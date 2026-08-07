"""session owner

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("owner", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_sessions_owner_updated", "sessions", ["owner", "updated_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_sessions_owner_updated", table_name="sessions")
    op.drop_column("sessions", "owner")
