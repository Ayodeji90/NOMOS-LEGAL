"""Multi-query batch retrieval with dedupe + coverage diagnostics.

Week 12 E2 (re-scoped compound subsets to ZA+NG). Supports E3's bounded agent
loop (plan W12: compound questions decompose to one retrieval per part, merge
with per-part cites; the loop re-retrieves only the still-missing parts):

- ``retrieve_batch``: run several sub-queries through the hybrid path in
  parallel, dedupe chunks retrieved by multiple parts (keep best fused rank),
  and record per-chunk part provenance.
- Diagnostics: which parts are covered vs missing (too few fused hits), so
  the next agent round can target only the gaps instead of re-retrieving
  everything.

Rerank is deliberately NOT part of the batch: the agent loop either reranks
the merged pool once (single writer call) or reranks per part when it needs
per-part citations; both consume the deduped ``BatchRetrievalResult``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from app.services.retrieval.hybrid_search import (
    HybridHit,
    HybridResult,
    RetrievalScope,
    hybrid_search_service,
)

logger = logging.getLogger(__name__)

# A sub-question with fewer fused hits than this is diagnosed "missing".
DEFAULT_MIN_HITS_PER_PART = 3


@dataclass
class PartResult:
    """Per-sub-question retrieval outcome + diagnostics."""

    query: str
    index: int
    hits: list[HybridHit] = field(default_factory=list)
    error: str | None = None
    fused_hits: int = 0

    @property
    def covered(self) -> bool:
        """False when this part needs another retrieval round."""
        return self.error is None and self.fused_hits >= DEFAULT_MIN_HITS_PER_PART


@dataclass
class BatchRetrievalResult:
    """Deduped merge across parts, with per-part provenance."""

    # Deduped hits, best fused rank first.
    hits: list[HybridHit] = field(default_factory=list)
    parts: list[PartResult] = field(default_factory=list)
    # chunk_id -> 0-based part indexes that retrieved it.
    chunk_parts: dict[str, list[int]] = field(default_factory=dict)
    explain: dict[str, Any] = field(default_factory=dict)

    @property
    def missing_parts(self) -> list[PartResult]:
        """Parts the agent loop should target in its next round."""
        return [p for p in self.parts if not p.covered]

    @property
    def covered_parts(self) -> list[PartResult]:
        return [p for p in self.parts if p.covered]


class MultiQueryRetriever:
    """Batched multi-query retrieval with dedupe + gap diagnostics."""

    def __init__(self, search_svc: Any = None):
        self._search = search_svc or hybrid_search_service

    async def _run_part(
        self,
        query: str,
        index: int,
        scope: RetrievalScope,
        per_leg_k: int,
    ) -> PartResult:
        try:
            result: HybridResult = await self._search.search_scoped(
                query=query, scope=scope, per_leg_k=per_leg_k
            )
            return PartResult(
                query=query,
                index=index,
                hits=list(result.hits),
                fused_hits=len(result.hits),
            )
        except Exception as exc:  # isolate per-part failure
            logger.warning("batch part %d failed: %s", index, exc)
            return PartResult(query=query, index=index, error=str(exc)[:200])

    @staticmethod
    def _merge(parts: list[PartResult], max_total: int) -> tuple[
        list[HybridHit], dict[str, list[int]]
    ]:
        """Dedupe across parts: keep a chunk's best (lowest) fused rank.

        Order: by best fused rank across parts, then by chunk_id for
        determinism on ties. A part hit ordering is its list position, which
        is fused (RRF) order.
        """
        best: dict[str, tuple[int, int, HybridHit]] = {}
        chunk_parts: dict[str, list[int]] = {}
        for part in parts:
            for pos, hit in enumerate(part.hits):
                rank = pos + 1
                prev = best.get(hit.chunk_id)
                if prev is None or rank < prev[0]:
                    best[hit.chunk_id] = (rank, part.index, hit)
                chunk_parts.setdefault(hit.chunk_id, []).append(part.index)

        ordered_ids = sorted(best, key=lambda cid: (best[cid][0], best[cid][1], cid))
        hits = [best[cid][2] for cid in ordered_ids][:max_total]
        return hits, chunk_parts

    async def retrieve_batch(
        self,
        queries: list[str],
        scope: RetrievalScope,
        per_leg_k: int = 50,
        max_total: int = 50,
        dedupe: bool = True,
    ) -> BatchRetrievalResult:
        """Run sub-queries in parallel; merge with dedupe + diagnostics.

        Args:
            queries: sub-question strings (from E3's decomposition).
            scope: retrieval scope applied to every part.
            per_leg_k: per-leg depth for each part's hybrid search.
            max_total: cap on the deduped merged pool.
            dedupe: when False, part-local ordering is preserved and the
                merged list is simple concatenation (per-part-cite mode).

        Returns:
            BatchRetrievalResult with parts, deduped hits, provenance, and
            explain (per-part hit counts + missing parts for the loop).
        """
        if not queries:
            return BatchRetrievalResult()

        parts = await asyncio.gather(
            *(
                self._run_part(q, i, scope, per_leg_k)
                for i, q in enumerate(queries)
            )
        )
        parts = list(parts)

        if dedupe:
            hits, chunk_parts = self._merge(parts, max_total)
        else:
            hits = [h for p in parts for h in p.hits][:max_total]
            chunk_parts = {}
            for p in parts:
                for h in p.hits:
                    chunk_parts.setdefault(h.chunk_id, []).append(p.index)

        explain = {
            "n_parts": len(parts),
            "part_hit_counts": [p.fused_hits for p in parts],
            "part_errors": [p.error for p in parts if p.error],
            "missing_part_indexes": [p.index for p in self._missing(parts)],
            "deduped_unique": len({h.chunk_id for p in parts for h in p.hits}),
            "merged_returned": len(hits),
        }
        logger.info("multi_query batch explain: %s", explain)
        return BatchRetrievalResult(
            hits=hits, parts=parts, chunk_parts=chunk_parts, explain=explain
        )

    @staticmethod
    def _missing(parts: list[PartResult]) -> list[PartResult]:
        return [p for p in parts if not p.covered]


# Module-level singleton (mirrors retrieval_service convention).
multi_query_retriever = MultiQueryRetriever()
