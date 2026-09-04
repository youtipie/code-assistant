"""chunks

Revision ID: b70f27d81248
Revises: 0001
Create Date: 2026-08-04 12:49:52.845240
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
# autogenerate renders pgvector.sqlalchemy.vector.VECTOR but does not add this
# import -- a known gap. Without it the migration fails at import time.
import pgvector.sqlalchemy
from sqlalchemy.dialects import postgresql

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('chunks',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('document_id', sa.BigInteger(), nullable=False),
    sa.Column('ordinal', sa.Integer(), nullable=False),
    sa.Column('source_type', sa.String(length=16), nullable=False),
    sa.Column('repo', sa.String(length=255), nullable=False),
    sa.Column('path', sa.Text(), nullable=False),
    sa.Column('language', sa.String(length=32), nullable=False),
    sa.Column('symbol', sa.Text(), nullable=True),
    sa.Column('symbol_kind', sa.String(length=16), nullable=True),
    sa.Column('heading_path', sa.Text(), nullable=True),
    sa.Column('start_line', sa.Integer(), nullable=False),
    sa.Column('end_line', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('context_header', sa.Text(), nullable=False),
    sa.Column('search_text', sa.Text(), nullable=False),
    sa.Column('search_tsv', postgresql.TSVECTOR(), sa.Computed("to_tsvector('english', search_text)", persisted=True), nullable=False),
    sa.Column('embedding', pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=False),
    sa.Column('doc_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_chunks_doc_hash', 'chunks', ['doc_hash'], unique=False)
    op.create_index('ix_chunks_document', 'chunks', ['document_id'], unique=False)
    op.create_index('ix_chunks_embedding_hnsw', 'chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('ix_chunks_search_tsv', 'chunks', ['search_tsv'], unique=False, postgresql_using='gin')
    op.create_index('ix_chunks_source_type', 'chunks', ['source_type'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_chunks_source_type', table_name='chunks')
    op.drop_index('ix_chunks_search_tsv', table_name='chunks', postgresql_using='gin')
    op.drop_index('ix_chunks_embedding_hnsw', table_name='chunks', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_index('ix_chunks_document', table_name='chunks')
    op.drop_index('ix_chunks_doc_hash', table_name='chunks')
    op.drop_table('chunks')
