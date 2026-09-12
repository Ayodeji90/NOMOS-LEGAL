"""Chunk retrieval DDL: vector(768) fix, tuned HNSW, tsvector + GIN indexes

Revision ID: 002
Revises: 001
Create Date: 2026-09-10

Retrieval-layer changes owned by the search/retrieval workstream:

1. chunk.embedding: 001 created it as float8[], which breaks the HNSW index
   (vector opclasses require the pgvector `vector` type). Convert to
   vector(768) -- matching settings.EMBEDDING_DIMENSIONS (Vertex
   text-embedding-005) and the ORM model.

2. HNSW (dense ANN): drop the broken/unparametrised index and recreate with
   m=16, ef_construction=64, vector_cosine_ops (cosine distance matches
   Vertex embeddings). pgvector >= 0.5.0 required (0.7+ recommended).

3. Lexical (sparse): add a STORED GENERATED tsvector column `text_tsv`
   (to_tsvector('english', heading || ' ' || text)) with a GIN index.
   Generated columns require PostgreSQL >= 12.

Every statement is server-side guarded (IF [NOT] EXISTS / DO blocks), so the
migration is idempotent and works in Alembic offline mode (--sql): it also
converges databases bootstrapped via Base.metadata.create_all() instead of
001. No Python-side catalog probing is used.

Downgrade restores the 001 state: plain hnsw index on embedding, no text_tsv
column, no GIN index.
"""
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Tunables (retrieval workstream defaults)
# ---------------------------------------------------------------------------
EMBEDDING_DIM = 768  # settings.EMBEDDING_DIMENSIONS (text-embedding-005)
HNSW_M = 16  # graph out-degree: recall/size tradeoff
HNSW_EF_CONSTRUCTION = 64  # build-time beam; higher = better recall, slower build
TSPVECTOR_LANG = "english"  # GIN-indexed lexisation for the sparse leg

# Converge chunk.embedding to vector(768). Check + conversion happen entirely
# server-side so this works online and offline.
_CONVERGE_EMBEDDING = f"""
DO $$
DECLARE
    actual_type text;
BEGIN
    SELECT format_type(a.atttypid, a.atttypmod)
      INTO actual_type
      FROM pg_attribute a
     WHERE a.attrelid = 'chunk'::regclass
       AND a.attname = 'embedding'
       AND NOT a.attisdropped;

    IF actual_type IS NULL THEN
        RAISE EXCEPTION 'chunk.embedding column not found';
    END IF;

    IF actual_type <> 'vector({EMBEDDING_DIM})' THEN
        -- e.g. float8[] -> vector: rebuild via text cast.
        EXECUTE 'ALTER TABLE chunk
                 ALTER COLUMN embedding TYPE vector({EMBEDDING_DIM})
                 USING embedding::text::vector';
    END IF;
END $$;
"""

# Add the stored generated tsvector column if missing (server-side check).
_ADD_TEXT_TSV = f"""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'chunk' AND column_name = 'text_tsv'
    ) THEN
        ALTER TABLE chunk
        ADD COLUMN text_tsv tsvector
        GENERATED ALWAYS AS (
            to_tsvector('{TSPVECTOR_LANG}',
                coalesce(heading, '') || ' ' || coalesce(text, '')
            )
        ) STORED;
    END IF;
END $$;
"""


def upgrade() -> None:
    conn = op.get_bind()

    # -- 1. pgvector must be present before vector(768)/HNSW exist ----------
    conn.execute(text('CREATE EXTENSION IF NOT EXISTS "vector"'))

    # -- 2. Drop whichever dense index variant is present. The column type
    #       cannot change while an index depends on it.
    conn.execute(text("DROP INDEX IF EXISTS ix_chunk_embedding_hnsw"))
    conn.execute(text("DROP INDEX IF EXISTS ix_chunk_embedding_hnsw_tuned"))

    # -- 3. Converge embedding to vector(768) (no-op if already correct) ----
    conn.execute(text(_CONVERGE_EMBEDDING))

    # -- 4. Tuned HNSW for dense ANN (cosine distance) -----------------------
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_chunk_embedding_hnsw_tuned "
            "ON chunk USING hnsw (embedding vector_cosine_ops) "
            f"WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION})"
        )
    )

    # -- 5. Lexical leg: stored generated tsvector + GIN ---------------------
    conn.execute(text(_ADD_TEXT_TSV))
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_chunk_text_tsv_gin "
            "ON chunk USING gin (text_tsv)"
        )
    )

    # -- 6. Prefilter companion: partial index for the in-force scan used
    #      before both ANN and FTS lookups (as_at lives on version).
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_chunk_inforce_effective "
            "ON chunk (in_force, effective_from, effective_to) "
            "WHERE in_force"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(text("DROP INDEX IF EXISTS ix_chunk_inforce_effective"))
    conn.execute(text("DROP INDEX IF EXISTS ix_chunk_text_tsv_gin"))
    conn.execute(text("ALTER TABLE chunk DROP COLUMN IF EXISTS text_tsv"))

    # Restore 001 state: plain hnsw index, default pgvector params.
    conn.execute(text("DROP INDEX IF EXISTS ix_chunk_embedding_hnsw_tuned"))
    conn.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_chunk_embedding_hnsw "
            "ON chunk USING hnsw (embedding vector_cosine_ops)"
        )
    )

    # NOTE: embedding type intentionally left as vector(768); reverting to
    # float8[] would only reintroduce the 001 bug.
