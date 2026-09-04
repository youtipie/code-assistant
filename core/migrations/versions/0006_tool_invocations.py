"""tool invocations

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Not backfilled: turns predating this migration streamed their tool calls
    # and never wrote them down, so they read back as turns with no tools.
    op.create_table(
        "tool_invocations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("turn_id", UUID(as_uuid=True), nullable=False),
        sa.Column("call_id", sa.String(32), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("arguments", JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("preview", sa.Text(), nullable=True),
        sa.Column("hits", JSONB(), server_default="[]", nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["turn_id"], ["turns.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("turn_id", "call_id", name="uq_tool_invocations_call"),
    )
    # (turn_id, ordinal): every read is "this turn's calls, in the order the
    # model made them", which this serves without a sort
    op.create_index(
        "ix_tool_invocations_turn_ordinal", "tool_invocations", ["turn_id", "ordinal"]
    )


def downgrade() -> None:
    op.drop_index("ix_tool_invocations_turn_ordinal", table_name="tool_invocations")
    op.drop_table("tool_invocations")
