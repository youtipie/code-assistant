"""cache write tokens

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Not backfilled to 0: older turns billed their cache writes as plain
    # input, so cost_usd understates them. A 0 would assert there were none.
    op.add_column("turns", sa.Column("cache_write_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("turns", "cache_write_tokens")
