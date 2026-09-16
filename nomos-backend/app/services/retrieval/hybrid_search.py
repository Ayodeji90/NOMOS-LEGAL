"""Hybrid retrieval for ZA legislation (dense + lexical, RRF fusion).

Week 3 E2: the v2 retrieval path. Two independent legs, fused via Week 1's
``fuse_ranked_lists`` (Cormack-Clarke-Buettcher RRF):

- Dense leg: query embedded by the same model as the corpus
  (text-embedding-005, 768-dim), cosine KNN over the tuned HNSW index.
- Lexical leg: ``ts_rank_cd`` over the stored-generated ``text_tsv``
  tsvector (english), GIN-indexed, websearch syntax for quoted phrases.

Both legs apply the same HARD filters before ranking (never post-hoc):

- ``source.jurisdiction = :jurisdiction`` (exact lowercase id; migration 004
  normalized the column, and the ORM now persists enum values not names).
- ``chunk.in_force = true`` (repealed chunks are invisible to v2 retrieval).
- ``as_at_date`` currency: ``chunk.as_at_date <= COALESCE(:as_of, now())``
  so point-in-time questions can pin the law as it stood on a date.

The fuse step uses chunk UUIDs as the identity; chunk rows are then
re-fetched in fused order. An ``explain`` trace is returned for staging
observability (per-leg timings, hit counts) so the p95 harness can attribute
latency.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy import bindparam

from app.db.session import db_manager
from app.services.ai.embedding_service import embedding_service
from app.services.retrieval.rrf import fuse_ranked_lists

logger = logging.getLogger(__name__)

# Hard top-K per leg before fusion. 50 matches the rerank budget: rerank
# consumes <=50 candidates, so retrieving deeper than this per leg wastes
# latency without changing the rerank input.
DEFAULT_PER_LEG_K = 50


@dataclass
class HybridHit:
    """One retrieved chunk with fused rank and retrieval metadata."""

    chunk_id: str
    version_id: str
    source_id: str
    source_title: str
    act_name: str
    section_no: str | None
    heading: str | None
    text: str
    as_at_date: Any
    dense_rank: int | None  # 1-based; None = not in dense top-K
    lexical_rank: int | None
    rrf_score: float
    # Week 9/13: carried through for structural boosts + doc-type traces.
    document_type: str | None = None
    authority_level: int = 0


@dataclass
class HybridResult:
    hits: list[HybridHit] = field(default_factory=list)
    explain: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalScope:
    """Single-path retrieval scope (Week 9 E2, milestone M3).

    One code path serves every jurisdiction; per-jurisdiction behavior is
    data (this scope + configs), never a code branch.

    Attributes:
        jurisdiction: lowercase jurisdiction id (hard filter).
        as_of: point-in-time currency cutoff (hard filter).
        doc_types: optional document-type restriction on
            ``source.document_type`` (case-insensitive; e.g. ``("ACT",)``).
            Week 13 makes this a first-class pilot feature (regs/cases).
        tenant_id: RESERVED for future matter-level ACLs (plan M3/E6).
            Carried and logged but NOT enforced -- no ACL semantics exist in
            the prototype.
    """

    jurisdiction: str
    as_of: Any = None
    doc_types: tuple[str, ...] = ()
    tenant_id: str | None = None


def _websearch_query(raw: str) -> str:
    """Build a Postgres ``websearch_to_tsquery`` string from a user query.

    websearch default joins terms with AND, so one off-topic word in a
    natural-language question ("How *much* annual leave..." -- 'much' never
    appears in the Act) kills every match. We therefore tokenize the query
    with the same 'english' stemmer Postgres uses, drop stopwords/punctuation,
    and join the remaining stems with OR so the lexical leg still contributes
    candidates when only some terms hit. Phrases are lost in this fallback
    (acceptable: exact-phrase pinning is a rerank concern, not recall).

    The tokenization must match the indexed tsvector, so it is computed by
    Postgres itself via ``ts_lexize`` on the english dictionary.
    """
    # Token-level OR needs the parsed lexemes; do it in SQL at query time
    # instead of approximating in Python. This function therefore only
    # sanitizes; the OR-join happens in the SQL (see _lexical_leg).
    cleaned = (raw or "").replace('"', " ").strip()
    return " ".join(cleaned.split())[:512]


def _or_fallback_tsquery_sql() -> str:
    """SQL expression producing an OR-joined tsquery from sanitized text.

    array_to_string over the lexized tokens, OR-separated, then cast back to
    tsquery. Deterministic, runs inside the same query (no round trip).
    """
    return """(
        SELECT to_tsquery('english',
            COALESCE(
                array_to_string(
                    ARRAY(
                        SELECT lexeme
                        FROM unnest(to_tsvector('english', :tsq))
                        WHERE char_length(lexeme) >= 2
                        LIMIT 24
                    ),
                    ' | '
                ),
                'null'
            )
        )
    )"""


class HybridSearchService:
    """Two-legged hybrid retrieval with hard jurisdiction/in-force filters."""

    def __init__(self, embedding_svc=None):
        self._embedding_service = embedding_svc or embedding_service

    # ------------------------------------------------------------------
    # SQL fragments
    # ------------------------------------------------------------------

    @staticmethod
    def _base_filter(jurisdiction: str, as_of: Any, doc_types: tuple[str, ...] = ()) -> str:
        """Shared WHERE for both legs (hard filters, parameterized)."""
        sql = """
            FROM chunk c
            JOIN version v ON c.version_id = v.id
            JOIN source s ON v.source_id = s.id
            WHERE s.jurisdiction = :jurisdiction
              AND c.in_force = true
              AND c.embedding IS NOT NULL
              AND (c.as_at_date IS NULL OR c.as_at_date <= COALESCE(:as_of, now()))
        """
        if doc_types:
            sql += "          AND s.document_type = ANY(:doc_types)\n"
        return sql

    async def _dense_leg(
        self,
        session,
        query_embedding: list[float],
        jurisdiction: str,
        as_of: Any,
        k: int,
        doc_types: tuple[str, ...] = (),
    ) -> list[sa.Row]:
        sql = sa.text(
            f"""
            SELECT c.id, 1 - (c.embedding <=> :qvec) AS similarity
            {self._base_filter(jurisdiction, as_of, doc_types)}
            ORDER BY c.embedding <=> :qvec
            LIMIT :k
            """
        )
        rows = (
            await session.execute(
                sql,
                {
                    "qvec": str(query_embedding),
                    "jurisdiction": jurisdiction.lower(),
                    "as_of": as_of,
                    "k": k,
                    "doc_types": [d.lower() for d in doc_types],
                },
            )
        ).fetchall()
        return rows

    async def _lexical_leg(
        self,
        session,
        query: str,
        jurisdiction: str,
        as_of: Any,
        k: int,
        doc_types: tuple[str, ...] = (),
    ) -> list[sa.Row]:
        tsq = _websearch_query(query)
        # OR-joined tsquery (see _or_fallback_tsquery_sql): recall-oriented.
        # ts_rank_cd still prefers chunks matching many/rare terms.
        tsq_expr = _or_fallback_tsquery_sql()
        sql = sa.text(
            f"""
            SELECT c.id, ts_rank_cd(c.text_tsv, {tsq_expr}) AS rank_score
            {self._base_filter(jurisdiction, as_of, doc_types)}
              AND c.text_tsv @@ {tsq_expr}
            ORDER BY rank_score DESC
            LIMIT :k
            """
        )
        rows = (
            await session.execute(
                sql,
                {
                    "tsq": tsq,
                    "jurisdiction": jurisdiction.lower(),
                    "as_of": as_of,
                    "k": k,
                    "doc_types": [d.lower() for d in doc_types],
                },
            )
        ).fetchall()
        return rows

    # ------------------------------------------------------------------
    # Metadata fetch (fused order)
    # ------------------------------------------------------------------

    async def _fetch_hit_rows(self, session, chunk_ids: list[str]) -> dict[str, sa.Row]:
        if not chunk_ids:
            return {}
        sql = sa.text(
            """
            SELECT c.id, c.version_id, c.section_no, c.heading, c.text,
                   c.as_at_date, s.source_id, s.title, s.document_type,
                   s.authority_level,
                   COALESCE(s.metadata_json->>'act_no', s.title) AS act_name
            FROM chunk c
            JOIN version v ON c.version_id = v.id
            JOIN source s ON v.source_id = s.id
            WHERE c.id IN :ids
            """
        ).bindparams(bindparam("ids", expanding=True))
        rows = (await session.execute(sql, {"ids": chunk_ids})).fetchall()
        return {str(r.id): r for r in rows}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        jurisdiction: str = "za",
        as_of: Any = None,
        per_leg_k: int = DEFAULT_PER_LEG_K,
        limit: int | None = None,
        doc_types: tuple[str, ...] = (),
        tenant_id: str | None = None,
    ) -> HybridResult:
        """Run both legs, fuse with RRF, return hits in fused order.

        Args:
            query: user query text.
            jurisdiction: lowercase jurisdiction id (hard filter).
            as_of: optional point-in-time date for currency filtering.
            per_leg_k: how many candidates to pull per leg (default 50).
            limit: cap on fused hits (default per_leg_k).
            doc_types: optional source.document_type restriction (hard filter;
                Week 13 pilot feature).
            tenant_id: RESERVED for future ACLs; logged, not enforced.

        Returns:
            HybridResult with hits in RRF order and an explain dict with
            per-leg counts/timings for the latency harness.
        """
        t0 = time.perf_counter()
        limit = limit or per_leg_k

        t1 = time.perf_counter()
        query_embedding = (await self._embedding_service.generate_embeddings([query]))[0]
        embed_ms = round((time.perf_counter() - t1) * 1000, 1)

        async with db_manager.session() as session:
            t2 = time.perf_counter()
            dense_rows = await self._dense_leg(
                session, query_embedding, jurisdiction, as_of, per_leg_k, doc_types
            )
            dense_ms = round((time.perf_counter() - t2) * 1000, 1)

            t3 = time.perf_counter()
            lex_rows = await self._lexical_leg(
                session, query, jurisdiction, as_of, per_leg_k, doc_types
            )
            lex_ms = round((time.perf_counter() - t3) * 1000, 1)

            dense_ids = [str(r.id) for r in dense_rows]
            lex_ids = [str(r.id) for r in lex_rows]

            t4 = time.perf_counter()
            fused = fuse_ranked_lists(
                [dense_ids, lex_ids],
                k=60,
                weights=[1.0, 1.0],
                limit=limit,
            )
            fuse_ms = round((time.perf_counter() - t4) * 1000, 1)

            hit_rows = await self._fetch_hit_rows(
                session, [f.id for f in fused]
            )

        dense_rank = {cid: i + 1 for i, cid in enumerate(dense_ids)}
        lex_rank = {cid: i + 1 for i, cid in enumerate(lex_ids)}

        hits: list[HybridHit] = []
        for f in fused:
            row = hit_rows.get(f.id)
            if row is None:  # pragma: no cover - deleted between legs
                continue
            hits.append(
                HybridHit(
                    chunk_id=f.id,
                    version_id=str(row.version_id),
                    source_id=row.source_id,
                    source_title=row.title,
                    act_name=row.act_name,
                    section_no=row.section_no,
                    heading=row.heading,
                    text=row.text,
                    as_at_date=row.as_at_date,
                    dense_rank=dense_rank.get(f.id),
                    lexical_rank=lex_rank.get(f.id),
                    rrf_score=f.score,
                    document_type=row.document_type,
                    authority_level=int(row.authority_level or 0),
                )
            )

        total_ms = round((time.perf_counter() - t0) * 1000, 1)
        explain = {
            "jurisdiction": jurisdiction.lower(),
            "per_leg_k": per_leg_k,
            "query_chars": len(query or ""),
            "doc_types": list(doc_types) or None,
            "tenant_id": tenant_id,  # reserved; logged only (no ACL yet)
            "embed_ms": embed_ms,
            "dense_ms": dense_ms,
            "lexical_ms": lex_ms,
            "fuse_ms": fuse_ms,
            "total_retrieval_ms": total_ms,
            "dense_hits": len(dense_ids),
            "lexical_hits": len(lex_ids),
            "fused_hits": len(hits),
            "both_legs_hits": sum(
                1 for f in fused if f.id in dense_rank and f.id in lex_rank
            ),
        }
        logger.info("hybrid_search explain: %s", explain)
        return HybridResult(hits=hits, explain=explain)

    async def search_scoped(
        self,
        query: str,
        scope: RetrievalScope,
        per_leg_k: int = DEFAULT_PER_LEG_K,
        limit: int | None = None,
    ) -> HybridResult:
        """Single-path entry point taking a full :class:`RetrievalScope`.

        Week 9 E2: the one code path for every jurisdiction. ``search``
        remains as the keyword convenience form and delegates here.
        """
        return await self.search(
            query=query,
            jurisdiction=scope.jurisdiction,
            as_of=scope.as_of,
            per_leg_k=per_leg_k,
            limit=limit,
            doc_types=scope.doc_types,
            tenant_id=scope.tenant_id,
        )


# Module-level singleton (mirrors embedding_service convention).
hybrid_search_service = HybridSearchService()
