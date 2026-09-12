"""Initial migration - create all tables

Revision ID: 001
Revises: 
Create Date: 2026-09-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
import uuid

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # Users table
    op.create_table(
        'user',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('email', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('is_superuser', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Note: ix_user_email is created inline by the column's index=True above.

    # API Keys table
    op.create_table(
        'api_key',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('key_hash', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('key_prefix', sa.String(20), nullable=False),
        sa.Column('name', sa.String(100), nullable=True),
        sa.Column('is_active', sa.Boolean, default=True, nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_api_key_user_active', 'api_key', ['user_id', 'is_active'])

    # Sources table
    op.create_table(
        'source',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('jurisdiction', sa.String(10), nullable=False, index=True),
        sa.Column('source_id', sa.String(100), nullable=False, index=True),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('short_title', sa.String(200), nullable=True),
        sa.Column('document_type', sa.String(50), nullable=False, index=True),
        sa.Column('authority_level', sa.Integer, default=0, nullable=False),
        sa.Column('metadata_json', JSONB, default=dict, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint('uq_source_jurisdiction_source_id', 'source', ['jurisdiction', 'source_id'])
    op.create_index('ix_source_jurisdiction_type', 'source', ['jurisdiction', 'document_type'])

    # Versions table
    op.create_table(
        'version',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('source_id', UUID(as_uuid=True), sa.ForeignKey('source.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version_id', sa.String(100), nullable=False, index=True),
        sa.Column('as_at_date', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('effective_from', sa.DateTime(timezone=True), nullable=True),
        sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, index=True, default='in_force'),
        sa.Column('amendment_note', sa.Text, nullable=True),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('chunk_count', sa.Integer, default=0, nullable=False),
        sa.Column('token_count', sa.BigInteger, default=0, nullable=False),
        sa.Column('metadata_json', JSONB, default=dict, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint('uq_version_source_version', 'version', ['source_id', 'version_id'])
    op.create_index('ix_version_source_asat', 'version', ['source_id', 'as_at_date'])
    op.create_index('ix_version_status_asat', 'version', ['status', 'as_at_date'])

    # Chunks table
    op.create_table(
        'chunk',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('version_id', UUID(as_uuid=True), sa.ForeignKey('version.id', ondelete='CASCADE'), nullable=False),
        sa.Column('chunk_index', sa.Integer, nullable=False),
        sa.Column('section_no', sa.String(50), nullable=True, index=True),
        sa.Column('subsection', sa.String(100), nullable=True),
        sa.Column('heading', sa.String(500), nullable=True),
        sa.Column('text', sa.Text, nullable=False),
        sa.Column('token_count', sa.Integer, nullable=False),
        sa.Column('embedding', Vector(768), nullable=True),  # pgvector vector(768); matches settings.EMBEDDING_DIMENSIONS (text-embedding-005)
        sa.Column('in_force', sa.Boolean, default=True, nullable=False),
        sa.Column('effective_from', sa.DateTime(timezone=True), nullable=True),
        sa.Column('effective_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata_json', JSONB, default=dict, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint('uq_chunk_version_index', 'chunk', ['version_id', 'chunk_index'])
    op.create_index('ix_chunk_version_inforce', 'chunk', ['version_id', 'in_force'])
    op.create_index('ix_chunk_section', 'chunk', ['section_no'])
    # HNSW index for vector search - will be created after pgvector is available
    op.execute('CREATE INDEX IF NOT EXISTS ix_chunk_embedding_hnsw ON chunk USING hnsw (embedding vector_cosine_ops)')

    # Ingestion Runs table
    op.create_table(
        'ingestion_run',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('jurisdiction', sa.String(10), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('sources_processed', sa.Integer, default=0),
        sa.Column('versions_created', sa.Integer, default=0),
        sa.Column('chunks_created', sa.Integer, default=0),
        sa.Column('embeddings_generated', sa.Integer, default=0),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata_json', JSONB, default=dict, nullable=False),
    )
    op.create_index('ix_ingestion_run_jurisdiction_started', 'ingestion_run', ['jurisdiction', 'started_at'])


def downgrade() -> None:
    op.drop_table('ingestion_run')
    op.drop_index('ix_chunk_embedding_hnsw', table_name='chunk')
    op.drop_index('ix_chunk_section', table_name='chunk')
    op.drop_index('ix_chunk_version_inforce', table_name='chunk')
    op.drop_constraint('uq_chunk_version_index', 'chunk', type_='unique')
    op.drop_table('chunk')

    op.drop_index('ix_version_status_asat', table_name='version')
    op.drop_index('ix_version_source_asat', table_name='version')
    op.drop_constraint('uq_version_source_version', 'version', type_='unique')
    op.drop_table('version')

    op.drop_index('ix_source_jurisdiction_type', table_name='source')
    op.drop_constraint('uq_source_jurisdiction_source_id', 'source', type_='unique')
    op.drop_table('source')

    op.drop_index('ix_api_key_user_active', table_name='api_key')
    op.drop_table('api_key')

    op.drop_index('ix_user_email', table_name='user')
    op.drop_table('user')

    op.execute('DROP EXTENSION IF EXISTS "pg_trgm"')
    op.execute('DROP EXTENSION IF EXISTS "vector"')
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')