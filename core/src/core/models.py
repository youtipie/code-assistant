from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_owner_updated", "owner", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Who this conversation belongs to: a client-generated token, not an
    # identity. It scopes one browser's history so people sharing a deployment
    # do not read each other's questions; it is forgeable, not a boundary.
    owner: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    turns: Mapped[list[Turn]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    messages: Mapped[list[Message]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Turn(Base):
    __tablename__ = "turns"
    __table_args__ = (Index("ix_turns_session_started", "session_id", "started_at"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str | None] = mapped_column(String(64))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    # already inside prompt_tokens; kept apart because each is billed at its
    # own rate
    cached_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer)
    # Numeric, not Float: money. Six decimals -- a turn can cost fractions of
    # a cent.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    ttft_ms: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    steps: Mapped[int | None] = mapped_column(Integer)
    tool_calls: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped[Session] = relationship(back_populates="turns")
    tool_invocations: Mapped[list[ToolInvocation]] = relationship(
        back_populates="turn",
        cascade="all, delete-orphan",
        # the FK already cascades in the database; without this, deleting a
        # session would load every tool row just to delete them one at a time
        passive_deletes=True,
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_session_created", "session_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped[Session] = relationship(back_populates="messages")


class ToolInvocation(Base):
    """One tool call the model made, as the UI showed it.

    `messages` records only the two ends of a turn -- the question and the
    final answer -- so without this a reloaded conversation drops the work in
    between. This is transcript, not telemetry: `turns.tool_calls` counts.

    Not named `ToolCall`, which in `core.events` is the wire frame announcing
    a call before it has a result; this row is the whole call.
    """

    __tablename__ = "tool_invocations"
    __table_args__ = (
        Index("ix_tool_invocations_turn_ordinal", "turn_id", "ordinal"),
        UniqueConstraint("turn_id", "call_id", name="uq_tool_invocations_call"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    turn_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("turns.id", ondelete="CASCADE"),
        nullable=False,
    )
    # the interceptor's id, which is what ties retrieval hits to their call
    call_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # call order within the turn: the UI numbers the steps, and `created_at`
    # cannot separate two calls issued in the same millisecond
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # "ok" | "error", or "running" for a call whose turn died mid-flight
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    preview: Mapped[str | None] = mapped_column(Text)
    # RetrievalHit dicts; denormalised because they are only read back
    # alongside the row
    hits: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    # NULL for a call with no result, which is not a call that took no time
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    turn: Mapped[Turn] = relationship(back_populates="tool_invocations")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("repo", "path", name="uq_documents_repo_path"),
        Index("ix_documents_source_type", "source_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # code | doc
    repo: Mapped[str] = mapped_column(String(255), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


EMBEDDING_DIM = 384  # BAAI/bge-small-en-v1.5


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_document", "document_id"),
        Index("ix_chunks_source_type", "source_type"),
        Index("ix_chunks_doc_hash", "doc_hash"),
        # cosine because bge embeddings are normalised; must match the
        # distance operator used at query time or the index is ignored
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_search_tsv", "search_tsv", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)

    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    repo: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(32), nullable=False)

    symbol: Mapped[str | None] = mapped_column(Text)
    symbol_kind: Mapped[str | None] = mapped_column(String(16))
    heading_path: Mapped[str | None] = mapped_column(Text)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)

    # what a human reads in a citation
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # the breadcrumb we prepend before embedding, so a chunk carries its
    # own context: code rarely states its purpose, paths and docstrings do
    context_header: Mapped[str] = mapped_column(Text, nullable=False)
    # text + identifiers split on snake_case/camelCase, so a search for
    # "invoice generation" can match generate_invoice
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    search_tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', search_text)", persisted=True),
        nullable=False,
    )

    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))

    # hash of the parent document when this chunk was built; lets `chunk`
    # skip documents that have not changed
    doc_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
