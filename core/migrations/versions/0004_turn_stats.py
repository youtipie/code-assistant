"""turn stats

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# All nullable: turns predating this migration have no stats, and neither
# does one that died before accounting. A zero would claim it was free.
COLUMNS = (
    ("cached_tokens", sa.Integer()),
    ("cost_usd", sa.Numeric(12, 6)),
    ("ttft_ms", sa.Integer()),
    ("duration_ms", sa.Integer()),
    ("steps", sa.Integer()),
    ("tool_calls", sa.Integer()),
)


def upgrade() -> None:
    for name, type_ in COLUMNS:
        op.add_column("turns", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column("turns", name)
