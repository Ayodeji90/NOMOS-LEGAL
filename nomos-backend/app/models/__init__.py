import enum
import uuid
from datetime import datetime
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Jurisdiction(str, enum.Enum):
    ZA = "za"
    NG = "ng"


class DocumentType(str, enum.Enum):
    ACT = "act"
    REGULATION = "regulation"
    CASE_LAW = "case_law"
    CODE = "code"
    DRAFT_REFERENCE = "draft_reference"


class SourceStatus(str, enum.Enum):
    IN_FORCE = "in_force"
    REPEALED = "repealed"
    PENDING = "pending"
    SUPERSEDED = "superseded"


class User(Base):
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey", back_populates="user", cascade="all, delete-orphan"
    )


class APIKey(Base):
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="api_keys")

    __table_args__ = (Index("ix_api_key_user_active", "user_id", "is_active"),)


class Source(Base):
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jurisdiction: Mapped[Jurisdiction] = mapped_column(
        # values_callable: persist enum .value ('za'), not .name ('ZA').
        # Without it this column was written as 'ZA', which broke the
        # lowercase jurisdiction filter in retrieval (and created a
        # duplicate-source hazard re-ingestion).
        Enum(Jurisdiction, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        index=True,
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    short_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, native_enum=False), index=True, nullable=False
    )
    authority_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    versions: Mapped[list["Version"]] = relationship(
        "Version", back_populates="source", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("jurisdiction", "source_id", name="uq_source_jurisdiction_source_id"),
        Index("ix_source_jurisdiction_type", "jurisdiction", "document_type"),
    )


class Version(Base):
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    as_at_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[SourceStatus] = mapped_column(
        Enum(SourceStatus, native_enum=False),
        index=True,
        nullable=False,
        default=SourceStatus.IN_FORCE,
    )
    amendment_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    token_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    source: Mapped["Source"] = relationship("Source", back_populates="versions")
    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk", back_populates="version", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("source_id", "version_id", name="uq_version_source_version"),
        Index("ix_version_source_asat", "source_id", "as_at_date"),
        Index("ix_version_status_asat", "status", "as_at_date"),
    )


class Chunk(Base):
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("version.id", ondelete="CASCADE"), nullable=False
    )
    as_at_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version_string: Mapped[str] = mapped_column(String(100), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section_no: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    subsection: Mapped[str | None] = mapped_column(String(100), nullable=True)
    heading: Mapped[str | None] = mapped_column(String(500), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Lexical search leg: stored-generated tsvector over heading + body.
    # Maintained by PostgreSQL (immutable to_tsvector with explicit regconfig);
    # never write to this column from application code.
    text_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(heading, '') || ' ' || coalesce(text, ''))",
            persisted=True,
        ),
        nullable=False,
    )
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(768), nullable=True)
    in_force: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    version: Mapped["Version"] = relationship("Version", back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("version_id", "chunk_index", name="uq_chunk_version_index"),
        Index("ix_chunk_version_inforce", "version_id", "in_force"),
        Index("ix_chunk_section", "section_no"),
        # Dense leg: HNSW over pgvector, cosine distance (Vertex text-embedding-005).
        # Params kept in lockstep with alembic/versions/002_chunk_retrieval_indexes.py.
        Index(
            "ix_chunk_embedding_hnsw_tuned",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
        # Sparse leg: GIN over the stored generated tsvector.
        Index("ix_chunk_text_tsv_gin", "text_tsv", postgresql_using="gin"),
        # Prefilter companion for the in-force scan both legs run first.
        Index(
            "ix_chunk_inforce_effective",
            "in_force",
            "effective_from",
            "effective_to",
            postgresql_where=sa_text("in_force"),
        ),
    )


class IngestionRun(Base):
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jurisdiction: Mapped[Jurisdiction] = mapped_column(
        Enum(Jurisdiction, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    sources_processed: Mapped[int] = mapped_column(Integer, default=0)
    versions_created: Mapped[int] = mapped_column(Integer, default=0)
    chunks_created: Mapped[int] = mapped_column(Integer, default=0)
    embeddings_generated: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (Index("ix_ingestion_run_jurisdiction_started", "jurisdiction", "started_at"),)
