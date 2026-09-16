"""
Real retrieval service using the hybrid search pipeline implemented by E2/E4.
This replaces the mock service with the actual hybrid retrieval pipeline:
- Ingested full ZA corpus (E4)
- Shipped hybrid query (tsvector + pgvector, RRF, hard jurisdiction + in-force filter) (E2)
- Shipped Flash rerank 50 to 8-12, coverage threshold 0.5 (E2)

Week 9 E1: Unified retrieval path for ZA/NG - single retrieve() with scope param.
All jurisdictions use the same hybrid retrieval pipeline with jurisdiction filtering.

Pipeline: hybrid_search (dense+lexical, RRF) -> Flash rerank (50->8-12)
-> coverage gate (0.5 ZA default). When coverage is below threshold the
result is flagged as a refusal so the endpoint can answer honestly instead
of from weak evidence.
"""

from typing import Any

import structlog

from app.services.ai.query_understanding import QueryUnderstandingOutput
from app.services.retrieval.boosts import structural_boosts
from app.services.retrieval.coverage import coverage_gate
from app.services.retrieval.hybrid_search import (
    HybridHit,
    HybridResult,
    RetrievalScope,
    hybrid_search_service,
)
from app.services.retrieval.rerank import RerankResult, flash_reranker
from app.services.retrieval.synonyms import load_synonym_dict

logger = structlog.get_logger(__name__)


class RetrievalResult:
    """Full pipeline output: excerpts + coverage verdict + explain traces."""

    def __init__(
        self,
        excerpts: list[dict[str, Any]],
        coverage: float,
        coverage_ok: bool,
        degraded: bool,
        reason: str,
        hybrid_explain: dict[str, Any],
        rerank_explain: dict[str, Any],
    ):
        self.excerpts = excerpts
        self.coverage = coverage
        self.coverage_ok = coverage_ok
        self.degraded = degraded
        self.reason = reason
        self.hybrid_explain = hybrid_explain
        self.rerank_explain = rerank_explain


class RetrievalService:
    """Real retrieval service using E2/E4's hybrid search pipeline."""

    def __init__(self):
        self.logger = logger.bind(service="RetrievalService")
        self.logger.info("Retrieval service initialized with hybrid search pipeline")

    @staticmethod
    def _to_excerpt(hit: HybridHit, i: int) -> dict[str, Any]:
        """HybridHit -> excerpt dict contract expected by writer/verifier."""
        return {
            "n": i + 1,  # 1-based citation number for writer/verifier
            "citation": (
                f"{hit.act_name} section {hit.section_no}"
                if hit.section_no
                else f"{hit.act_name}"
            ),
            "sourceText": hit.text,
            "text": hit.text,
            "act": hit.act_name,
            "section": hit.section_no,
            "jurisdiction": (
                hit.source_id.split("-")[0] if "-" in hit.source_id else "za"
            ),
            "title": hit.source_title,
            # Retrieval scores for debugging/observability
            "dense_rank": hit.dense_rank,
            "lexical_rank": hit.lexical_rank,
            "rrf_score": hit.rrf_score,
            "retrieval_metadata": {
                "version_id": hit.version_id,
                "source_id": hit.source_id,
                "heading": hit.heading,
                "as_at_date": str(hit.as_at_date) if hit.as_at_date else None,
            },
        }

    async def retrieve(
        self,
        query: str,
        jurisdiction: str,
        understanding: QueryUnderstandingOutput | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Back-compat helper: full pipeline, excerpt dicts only."""
        result = await self.retrieve_with_coverage(
            query=query, jurisdiction=jurisdiction, understanding=understanding, limit=limit
        )
        return result.excerpts

    async def retrieve_with_coverage(
        self,
        query: str,
        jurisdiction: str,
        understanding: QueryUnderstandingOutput | None = None,
        limit: int = 10,
        scope: RetrievalScope | None = None,
    ) -> RetrievalResult:
        """Hybrid retrieve -> boost -> rerank -> coverage gate.

        Args:
            query: User query
            jurisdiction: Target jurisdiction (e.g., 'za', 'ng')
            understanding: Optional query understanding output (for future use)
            limit: Max excerpts to return after rerank
            scope: Optional full RetrievalScope (Week 9 single-path). When
                given, its jurisdiction/as_of/doc_types win over the args.

        Returns:
            RetrievalResult with excerpts in reranked order plus the
            coverage verdict the endpoint uses for the refusal decision.
        """
        # Week 9: single path. Scope (when provided) is authoritative.
        if scope is None:
            scope = RetrievalScope(jurisdiction=jurisdiction)
        effective_jur = scope.jurisdiction or jurisdiction

        self.logger.info(
            "Real retrieval called",
            query=query[:50],
            jurisdiction=effective_jur,
            doc_types=list(scope.doc_types) or None,
            tenant_id=scope.tenant_id,
            understanding_available=understanding is not None,
        )

        # 1. Hybrid retrieval (dense + lexical, hard filters, RRF fusion).
        hybrid_result: HybridResult = await hybrid_search_service.search_scoped(
            query=query,
            scope=scope,
        )

        # 1b. Structural boosts (Week 5/13: post-fusion soft reorder).
        try:
            act_dict = load_synonym_dict(effective_jur)
            alias_lookup = act_dict.lookup_act
        except Exception:
            alias_lookup = None  # no dict -> no act-alias boost, still correct
        boost_result = structural_boosts.apply(
            hybrid_result.hits,
            query,
            act_alias_lookup=alias_lookup,
            authority_levels={
                h.source_id: h.authority_level for h in hybrid_result.hits
            },
        )

        # 2. Flash rerank 50 -> 8-12 with graceful degradation.
        rerank_result: RerankResult = await flash_reranker.rerank(
            query, boost_result.hits
        )

        # 3. Coverage gate (Week 6: standardized jurisdiction-aware gate;
        # degraded reranks carry coverage=0.0 -> gate fails closed).
        decision = coverage_gate.evaluate(
            effective_jur,
            rerank_result.coverage,
            degraded=rerank_result.degraded,
            n_hits=len(rerank_result.hits),
        )
        coverage_ok = decision.coverage_ok

        excerpts = [
            self._to_excerpt(hit, i)
            for i, hit in enumerate(rerank_result.hits[:limit])
        ]

        self.logger.info(
            "Real retrieval completed",
            query=query[:30],
            jurisdiction=jurisdiction,
            results_count=len(excerpts),
            fused_hits=len(hybrid_result.hits),
            coverage=round(rerank_result.coverage, 3),
            coverage_ok=coverage_ok,
            rerank_degraded=rerank_result.degraded,
            rerank_ms=rerank_result.rerank_ms,
            hybrid_explain=hybrid_result.explain,
        )

        return RetrievalResult(
            excerpts=excerpts,
            coverage=rerank_result.coverage,
            coverage_ok=coverage_ok,
            degraded=rerank_result.degraded,
            reason=decision.reason,
            hybrid_explain={
                **hybrid_result.explain,
                "boosts": boost_result.explain,
            },
            rerank_explain={
                "model": rerank_result.model,
                "rerank_ms": rerank_result.rerank_ms,
                "selected": len(rerank_result.hits),
                **(rerank_result.explain or {}),
            },
        )


# Global instance for dependency injection
retrieval_service = RetrievalService()


async def retrieve_excerpts(
    query: str,
    jurisdiction: str,
    understanding: QueryUnderstandingOutput | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Convenience function to get excerpts from the real retrieval pipeline.

    This is the function that the search endpoint calls.
    """
    return await retrieval_service.retrieve(
        query=query,
        jurisdiction=jurisdiction,
        understanding=understanding,
        limit=limit,
    )
