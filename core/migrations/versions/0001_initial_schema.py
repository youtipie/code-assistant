"""initial schema

Revision ID: f2f44b72fdf4
Revises: 
Create Date: 2026-08-04 09:14:47.817279
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table('documents',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('source_type', sa.String(length=16), nullable=False),
    sa.Column('repo', sa.String(length=255), nullable=False),
    sa.Column('commit_sha', sa.String(length=40), nullable=False),
    sa.Column('path', sa.Text(), nullable=False),
    sa.Column('language', sa.String(length=32), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('line_count', sa.Integer(), nullable=False),
    sa.Column('indexed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('repo', 'path', name='uq_documents_repo_path')
    )
    op.create_index('ix_documents_source_type', 'documents', ['source_type'], unique=False)
    op.create_table('sessions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('title', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('messages',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('session_id', sa.UUID(), nullable=False),
    sa.Column('turn_id', sa.UUID(), nullable=True),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_messages_session_created', 'messages', ['session_id', 'created_at'], unique=False)
    op.create_table('turns',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('session_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('model', sa.String(length=64), nullable=True),
    sa.Column('prompt_tokens', sa.Integer(), nullable=True),
    sa.Column('completion_tokens', sa.Integer(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_turns_session_started', 'turns', ['session_id', 'started_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_turns_session_started', table_name='turns')
    op.drop_table('turns')
    op.drop_index('ix_messages_session_created', table_name='messages')
    op.drop_table('messages')
    op.drop_table('sessions')
    op.drop_index('ix_documents_source_type', table_name='documents')
    op.drop_table('documents')
