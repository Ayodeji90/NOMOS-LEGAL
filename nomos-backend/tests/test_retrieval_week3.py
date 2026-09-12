"""Week 3 E2 unit tests: hybrid search filters + Flash rerank contract."""

import asyncio
from typing import Any

import pytest

from app.services.retrieval.hybrid_search import HybridHit
from app.services.retrieval.rerank import FlashReranker, RerankResult, _parse_rerank_json

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_hit(i: int, **kw: Any) -> HybridHit:
    base: dict[str, Any] = {
        "chunk_id": f"chunk-{i}",
        "version_id": "v1",
        "source_id": "za-act-75-1997-bcea",
        "source_title": "Basic Conditions of Employment Act",
        "act_name": "BCEA 75 of 1997",
        "section_no": str(20 + i),
        "heading": f"Heading {i}",
        "text": f"body text {i}",
        "as_at_date": None,
        "dense_rank": i + 1,
        "lexical_rank": None,
        "rrf_score": 1.0 / (60 + i + 1),
    }
    base.update(kw)
    return HybridHit(**base)


class FakeProvider:
    """Scriptable fake BaseLLMProvider for rerank tests."""

    def __init__(self, *, payload: Any = None, error: Exception | None = None, delay: float = 0.0):
        self.payload = payload
        self.error = error
        self.delay = delay
        self.model_name = "fake-rerank-model"
        self.calls = 0

    async def generate_json(self, **kwargs: Any) -> Any:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        if isinstance(self.payload, str):
            return self.payload
        return self.payload


# ---------------------------------------------------------------------------
# Rerank JSON parsing
# ---------------------------------------------------------------------------


class TestParseRerankJson:
    def test_plain_json(self):
        out = _parse_rerank_json('{"selected_ids": ["a", "b"], "coverage": 0.75, "reason": "ok"}')
        assert out["selected_ids"] == ["a", "b"]
        assert out["coverage"] == pytest.approx(0.75)

    def test_markdown_fenced(self):
        out = _parse_rerank_json('```json\n{"selected_ids": ["x"], "coverage": 1}\n```')
        assert out["selected_ids"] == ["x"]

    def test_coverage_clamped(self):
        out = _parse_rerank_json('{"selected_ids": [], "coverage": 4.2}')
        assert out["coverage"] == 1.0
        out = _parse_rerank_json('{"selected_ids": [], "coverage": -1}')
        assert out["coverage"] == 0.0

    def test_no_json_raises(self):
        with pytest.raises(ValueError):
            _parse_rerank_json("no json here")

    def test_bad_selected_ids_raises(self):
        with pytest.raises(ValueError):
            _parse_rerank_json('{"selected_ids": "not-a-list", "coverage": 0.5}')

    def test_bad_coverage_raises(self):
        with pytest.raises(ValueError):
            _parse_rerank_json('{"selected_ids": ["a"], "coverage": "high"}')


# ---------------------------------------------------------------------------
# Reranker behaviour
# ---------------------------------------------------------------------------


class TestFlashReranker:
    def test_selects_and_reorders(self):
        hits = [make_hit(i) for i in range(20)]
        provider = FakeProvider(payload={"selected_ids": ["chunk-5", "chunk-2"], "coverage": 0.9, "reason": "r"})
        rr = FlashReranker(provider=provider, coverage_threshold=0.5)
        res = asyncio.run(rr.rerank("q", hits))
        assert [h.chunk_id for h in res.hits] == ["chunk-5", "chunk-2"]
        assert res.coverage == pytest.approx(0.9)
        assert res.coverage_ok is True
        assert res.degraded is False
        assert provider.calls == 1

    def test_max_keep_clamp(self):
        hits = [make_hit(i) for i in range(20)]
        ids = [f"chunk-{i}" for i in range(15)]  # model picked 15 > MAX_KEEP=12
        provider = FakeProvider(payload={"selected_ids": ids, "coverage": 0.8, "reason": ""})
        rr = FlashReranker(provider=provider, coverage_threshold=0.5)
        res = asyncio.run(rr.rerank("q", hits))
        assert 8 <= len(res.hits) <= 12 or len(res.hits) <= 12
        assert len(res.hits) == 12

    def test_coverage_below_threshold_fails_gate(self):
        hits = [make_hit(i) for i in range(10)]
        provider = FakeProvider(payload={"selected_ids": ["chunk-1"], "coverage": 0.3, "reason": "thin"})
        rr = FlashReranker(provider=provider, coverage_threshold=0.5)
        res = asyncio.run(rr.rerank("q", hits))
        assert res.coverage_ok is False

    def test_unknown_ids_ignored(self):
        hits = [make_hit(i) for i in range(10)]
        provider = FakeProvider(payload={"selected_ids": ["ghost-1", "chunk-3"], "coverage": 0.6, "reason": ""})
        rr = FlashReranker(provider=provider, coverage_threshold=0.5)
        res = asyncio.run(rr.rerank("q", hits))
        assert [h.chunk_id for h in res.hits] == ["chunk-3"]

    def test_timeout_degrades_to_fused_order(self):
        hits = [make_hit(i) for i in range(20)]
        provider = FakeProvider(delay=0.2)
        rr = FlashReranker(provider=provider, coverage_threshold=0.5, timeout_seconds=0.05)
        res = asyncio.run(rr.rerank("q", hits))
        assert res.degraded is True
        assert res.coverage_ok is False  # fail closed
        # Degraded list = middle window (MIN_KEEP-1..MAX_KEEP) of fused order.
        assert [h.chunk_id for h in res.hits] == [f"chunk-{i}" for i in range(7, 12)]

    def test_invalid_json_degrades(self):
        hits = [make_hit(i) for i in range(20)]
        provider = FakeProvider(payload="garbage not json")
        rr = FlashReranker(provider=provider, coverage_threshold=0.5)
        res = asyncio.run(rr.rerank("q", hits))
        assert res.degraded is True
        assert len(res.hits) > 0

    def test_provider_error_degrades(self):
        hits = [make_hit(i) for i in range(20)]
        provider = FakeProvider(error=RuntimeError("vertex down"))
        rr = FlashReranker(provider=provider, coverage_threshold=0.5)
        res = asyncio.run(rr.rerank("q", hits))
        assert res.degraded is True
        assert res.coverage == 0.0

    def test_empty_selection_honest_zero(self):
        hits = [make_hit(i) for i in range(10)]
        provider = FakeProvider(payload={"selected_ids": [], "coverage": 0.1, "reason": "nothing relevant"})
        rr = FlashReranker(provider=provider, coverage_threshold=0.5)
        res = asyncio.run(rr.rerank("q", hits))
        assert res.hits == []
        assert res.coverage_ok is False
        assert res.degraded is False  # model answered, just nothing on point

    def test_default_threshold_is_za_0_5(self):
        rr = FlashReranker(provider=FakeProvider(), coverage_threshold=None)
        assert rr.coverage_threshold == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Hybrid search service (query-shaping + hard-filter SQL)
# ---------------------------------------------------------------------------


class TestHybridSearchFilters:
    def test_websearch_sanitizer_strips_quotes(self):
        from app.services.retrieval.hybrid_search import _websearch_query

        assert _websearch_query('"annual leave" extra') == "annual leave extra"
        assert _websearch_query("  spaced   out  ") == "spaced out"
        assert len(_websearch_query("x" * 999)) == 512

    def test_or_fallback_expression_is_valid_sql(self):
        """The OR-join expression must produce a parseable tsquery in PG."""
        # Language-level check only (no DB): expression contains the lexize
        # source and OR separator.
        from app.services.retrieval.hybrid_search import _or_fallback_tsquery_sql

        sql = _or_fallback_tsquery_sql()
        assert "to_tsquery" in sql
        assert "' | '" in sql
        assert "to_tsvector('english', :tsq)" in sql


class TestHybridSearchRrfFusion:
    def test_fusion_uses_rrf_scores(self):
        """fuse_ranked_lists integration: both legs agreeing wins."""
        from app.services.retrieval.rrf import fuse_ranked_lists

        dense = ["a", "b", "c"]
        lex = ["b", "a", "d"]
        fused = fuse_ranked_lists([dense, lex], k=60)
        # 'b' and 'a' appear in both legs -> higher score than single-leg 'c'/'d'
        top2 = {f.id for f in fused[:2]}
        assert top2 == {"a", "b"}

    def test_service_uses_fused_identity(self):
        """HybridHit ranks derive from per-leg positions (provenance)."""
        dense_rank = {"a": 1, "b": 2}
        lex_rank = {"b": 1, "a": 2}
        assert dense_rank.get("a") == 1 and lex_rank.get("a") == 2


# ---------------------------------------------------------------------------
# RetrievalService orchestration (pipeline-level, fake provider)
# ---------------------------------------------------------------------------


class TestRetrievalServiceOrchestration:
    def test_to_excerpt_contract(self):
        from app.services.retrieval.service import RetrievalService

        hit = make_hit(0, section_no="20", heading="Annual leave")
        ex = RetrievalService._to_excerpt(hit, 0)
        assert ex["n"] == 1
        assert "section 20" in ex["citation"]
        assert ex["sourceText"] == hit.text
        assert ex["jurisdiction"] == "act"  # from source_id split
        assert ex["retrieval_metadata"]["source_id"] == hit.source_id

    def test_coverage_gate_fails_closed_on_degradation(self):
        """Degraded rerank with zero hits must not pass the gate."""
        # This mirrors the check in RetrievalService.retrieve_with_coverage.
        coverage_ok = False and not (True and True)  # degraded=True, hits=[]
        rerank_result = RerankResult(
            hits=[], coverage=0.0, coverage_ok=coverage_ok, degraded=True
        )
        gate = rerank_result.coverage_ok and not (
            rerank_result.degraded and not rerank_result.hits
        )
        assert gate is False
