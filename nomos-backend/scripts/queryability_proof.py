#!/usr/bin/env python3
"""
Queryability proof for the Week-2 corpus: the two ingested ZA Acts must be
reachable via all three retrieval legs:

1. dense   - pgvector HNSW cosine KNN (embedding-based)
2. lexical - generated tsvector + GIN index (plainto_tsquery)
3. hybrid  - Week-1 rrf_fuse over the dense + lexical ranked lists

Runs entirely against the live database with the configured embedding
provider (mock vectors prove the plumbing; swap EMBEDDING_PROVIDER=vertex
for semantic quality once credentials are present).

Usage:
    PYTHONPATH=. python3 scripts/queryability_proof.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from app.db.session import db_manager
from app.services.ai.embedding_service import embedding_service
from app.services.retrieval.rrf import fuse_ranked_lists

PROOF_QUERIES = [
    "overtime pay",
    "annual leave entitlement",
    "business rescue",
    "notice of termination",
    "company name reservation",
]


async def dense_search(conn, query: str, k: int = 5) -> list[str]:
    """Dense leg: cosine KNN over chunk.embedding. Returns chunk ids."""
    vec = (await embedding_service.generate_embeddings([query]))[0]
    rows = await conn.fetch(
        """
        SELECT c.id
        FROM chunk c
        JOIN version v ON c.version_id = v.id
        JOIN source s ON v.source_id = s.id
        WHERE s.jurisdiction = 'ZA' AND c.in_force
        ORDER BY c.embedding <=> $1::vector
        LIMIT $2
        """,
        "[" + ",".join(f"{x:.7f}" for x in vec) + "]",
        k,
    )
    return [str(r["id"]) for r in rows]


async def lexical_search(conn, query: str, k: int = 5) -> list[str]:
    """Lexical leg: plainto_tsquery over the generated text_tsv (GIN)."""
    rows = await conn.fetch(
        """
        SELECT c.id
        FROM chunk c
        JOIN version v ON c.version_id = v.id
        JOIN source s ON v.source_id = s.id
        WHERE s.jurisdiction = 'ZA' AND c.in_force
          AND c.text_tsv @@ plainto_tsquery('english', $1)
        ORDER BY ts_rank(c.text_tsv, plainto_tsquery('english', $1)) DESC
        LIMIT $2
        """,
        query,
        k,
    )
    return [str(r["id"]) for r in rows]


async def fetch_details(conn, ids: list) -> dict:
    rows = await conn.fetch(
        """
        SELECT c.id, c.section_no, c.heading, LEFT(c.text, 90) AS preview,
               s.source_id
        FROM chunk c
        JOIN version v ON c.version_id = v.id
        JOIN source s ON v.source_id = s.id
        WHERE c.id::text = ANY($1::text[])
        """,
        [str(i) for i in ids],
    )
    return {str(r["id"]): r for r in rows}


async def main() -> int:
    if db_manager._engine is None:
        db_manager.initialize()
    conn = await asyncpg_connect()

    print("=" * 72)
    print("QUERYABILITY PROOF: dense / lexical / hybrid over BCEA + Companies Act")
    print("=" * 72)

    counts = await conn.fetch(
        """
        SELECT s.source_id,
               COUNT(*) AS chunks,
               COUNT(*) FILTER (WHERE c.embedding IS NOT NULL) AS embedded,
               COUNT(*) FILTER (WHERE c.text_tsv IS NOT NULL) AS tsv
        FROM chunk c
        JOIN version v ON c.version_id = v.id
        JOIN source s ON v.source_id = s.id
        WHERE s.jurisdiction = 'ZA' AND c.in_force
        GROUP BY s.source_id ORDER BY s.source_id
        """
    )
    for r in counts:
        print(f"  {r['source_id']}: {r['chunks']} chunks "
              f"({r['embedded']} embedded, {r['tsv']} with tsvector)")

    all_ok = True
    for q in PROOF_QUERIES:
        print(f"\nQUERY: {q!r}")
        dense = await dense_search(conn, q)
        lexical = await lexical_search(conn, q)
        if not dense and not lexical:
            print("  !! no results on either leg")
            all_ok = False
            continue

        fused = fuse_ranked_lists([dense, lexical], k=60, limit=5)

        ids = [str(r.id) for r in fused]
        details = await fetch_details(conn, ids)

        dense_ids = set(dense)
        lex_ids = set(lexical)
        for rank, fr in enumerate(fused, 1):
            cid = str(fr.id)
            d = details.get(cid, {})
            on_dense = "D" if cid in dense_ids else "-"
            on_lex = "L" if cid in lex_ids else "-"
            print(
                f"  #{rank} {on_dense}{on_lex} "
                f"{d.get('source_id', '?')[:9]} s{d.get('section_no', '?')} "
                f"| {d.get('heading', '?')[:34]} "
                f"| {d.get('preview', '')[:46]!r}"
            )
        # proof bar: hybrid returns hits and both acts appear overall
        if not fused:
            all_ok = False

    # cross-act coverage: a lexical query should hit both acts somewhere
    print("\n" + "=" * 72)
    cov = await conn.fetch(
        """
        SELECT s.source_id, COUNT(DISTINCT c.id) AS lex_hits
        FROM chunk c
        JOIN version v ON c.version_id = v.id
        JOIN source s ON v.source_id = s.id
        WHERE s.jurisdiction = 'ZA' AND c.in_force
          AND c.text_tsv @@ websearch_to_tsquery('english', 'overtime OR leave OR company OR director')
        GROUP BY s.source_id
        """
    )
    print("LEXICAL COVERAGE (common legal terms):")
    for r in cov:
        print(f"  {r['source_id']}: {r['lex_hits']} chunks matched")
    if len(cov) < 2:
        print("  !! expected matches from BOTH acts")
        all_ok = False

    await conn.close()
    print("\nPROOF " + ("PASSED" if all_ok else "FAILED"))
    return 0 if all_ok else 1


async def asyncpg_connect():
    """Raw asyncpg connection using the app's DATABASE_URL (asyncpg driver)."""
    import asyncpg

    from app.core.config import settings

    dsn = str(settings.DATABASE_URL)
    dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
    return await asyncpg.connect(dsn)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
