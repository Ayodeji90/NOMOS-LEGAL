-- Initialize PostgreSQL extensions required by NOMOS
-- This runs automatically when the postgres container starts

-- UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Vector similarity search (pgvector)
CREATE EXTENSION IF NOT EXISTS "vector";

-- Trigram similarity for full-text search
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Optional: for more advanced text search
-- CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";

-- Verify extensions are installed
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        RAISE EXCEPTION 'pgvector extension failed to install';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
        RAISE EXCEPTION 'pg_trgm extension failed to install';
    END IF;
    RAISE NOTICE 'All required extensions installed successfully';
END $$;