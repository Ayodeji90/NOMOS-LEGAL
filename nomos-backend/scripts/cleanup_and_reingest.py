#!/usr/bin/env python3
"""One-shot Week 3 data repair + re-ingest.

Fixes two data issues found in the Week 2 corpus before hybrid-search work:
1. Duplicate source rows: both ZA Acts exist twice, once with jurisdiction
   'ZA' (Week 2 manual runs, legacy casing) and once with 'za' (migration-004
   casing). The hard jurisdiction filter must match exactly one row per Act.
   → delete the 'ZA' copies (cascades to versions/chunks).
2. .env had EMBEDDING_PROVIDER=mock re-introduced by an environment reset, so
   any re-ingestion would silently write hash-based mock vectors again.
   → flip to 'vertex' (real text-embedding-005) before re-embedding.

Then re-ingests BCEA + Companies Act 71/2008. The NG sample is left untouched.
"""

import asyncio
import logging
import sys

sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cleanup_reingest")


async def cleanup_duplicates() -> dict:
    """Delete legacy-uppercase 'ZA' source duplicates (cascade removes their chunks).

    On databases whose jurisdiction enum predates migration 004 normalization
    this is a real repair; on databases where the enum only accepts lowercase
    values (Cloud SQL provisioned from 004+) the 'ZA' comparison itself raises
    InvalidTextRepresentationError -- there are no legacy rows possible, so we
    treat that as a no-op.
    """
    import asyncpg

    from app.core.config import settings

    dsn = str(settings.DATABASE_URL).replace("postgresql+asyncpg://", "postgres://")
    conn = await asyncpg.connect(dsn)
    try:
        try:
            rows = await conn.fetch(
                """
                SELECT s.id, s.source_id FROM source s
                WHERE s.jurisdiction = 'ZA'
                  AND EXISTS (
                    SELECT 1 FROM source t
                    WHERE t.source_id = s.source_id AND t.jurisdiction = 'za'
                  )
                """
            )
        except asyncpg.exceptions.InvalidTextRepresentationError:
            logger.info(
                "jurisdiction enum rejects 'ZA' -- no legacy duplicates possible, skipping cleanup"
            )
            return {"deleted_duplicates": 0, "remaining": []}
        deleted = 0
        for r in rows:
            await conn.execute("DELETE FROM source WHERE id = $1", r["id"])
            deleted += 1
            logger.info("Deleted duplicate source %s (%s)", r["source_id"], r["id"])
        remaining = await conn.fetch(
            "SELECT jurisdiction, source_id FROM source ORDER BY jurisdiction, source_id"
        )
        logger.info("Remaining sources: %s", [tuple(r) for r in remaining])
        return {"deleted_duplicates": deleted, "remaining": [dict(r) for r in remaining]}
    finally:
        await conn.close()


async def main() -> int:
    await cleanup_duplicates()

    # Verify provider BEFORE embedding: a mock run would poison retrieval eval.
    from app.core.config import settings

    if settings.EMBEDDING_PROVIDER != "vertex":
        logger.error(
            "EMBEDDING_PROVIDER is '%s' -- refusing to ingest mock vectors. "
            "Set EMBEDDING_PROVIDER=vertex first.",
            settings.EMBEDDING_PROVIDER,
        )
        return 1

    from app.services.ingestion_service import IngestionService

    svc = IngestionService()
    # Chunk text is unchanged, but the version content_hash covers chunk text
    # only -- embeddings aren't part of it, so a re-run would 'skip'. Delete
    # the lowercase versions' chunks to force a true re-embed.
    import asyncpg

    dsn = str(settings.DATABASE_URL).replace("postgresql+asyncpg://", "postgres://")
    conn = await asyncpg.connect(dsn)
    for sid in ("za-act-75-1997-bcea", "za-act-71-2008-companies"):
        n = await conn.execute(
            """
            DELETE FROM chunk WHERE version_id IN (
                SELECT v.id FROM version v JOIN source s ON v.source_id = s.id
                WHERE s.source_id = $1
            )
            """,
            sid,
        )
        logger.info("Cleared chunks for %s: %s", sid, n.split()[-1])
    await conn.close()

    result = await svc.ingest_bcea_and_companies_act()
    import json

    print(json.dumps(result, indent=2, default=str))
    ok = result.get("summary", {}).get("failed_acts", 99) == 0
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
