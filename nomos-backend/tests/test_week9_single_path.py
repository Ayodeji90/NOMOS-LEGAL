"""Week 9 E2 tests: single retrieval path with scope param (milestone M3).

One code path serves every jurisdiction; per-jurisdiction behavior is data
(scope + configs), never code branches. tenant_id is reserved, not enforced.
"""

from __future__ import annotations

import dataclasses

import pytest

from app.services.retrieval import hybrid_search as hs
from app.services.retrieval.hybrid_search import (
    HybridSearchService,
    RetrievalScope,
)
from app.services.retrieval.service import retrieval_service


class TestRetrievalScope:
    def test_defaults(self) -> None:
        s = RetrievalScope(jurisdiction="za")
        assert s.jurisdiction == "za"
        assert s.as_of is None
        assert s.doc_types == ()
        assert s.tenant_id is None

    def test_frozen(self) -> None:
        s = RetrievalScope(jurisdiction="za")
        with pytest.raises(dataclasses.FrozenInstanceError):
            s.jurisdiction = "ng"  # type: ignore[misc]


class TestBaseFilter:
    def test_doc_type_filter_appended(self) -> None:
        with_doc = HybridSearchService._base_filter("za", None, ("ACT",))
        without = HybridSearchService._base_filter("za", None, ())
        assert "ANY(:doc_types)" in with_doc
        assert "ANY(:doc_types)" not in without

    def test_hard_filters_always_present(self) -> None:
        sql = HybridSearchService._base_filter("za", None, ("ACT",))
        assert "lower(s.jurisdiction) = :jurisdiction" in sql
        assert "c.in_force = true" in sql
        assert "c.as_at_date IS NULL OR c.as_at_date <= COALESCE(:as_of, now())" in sql


class TestSinglePath:
    @pytest.mark.asyncio
    async def test_search_scoped_matches_search(self, monkeypatch) -> None:
        """search_scoped is a pure adapter: identical kwargs to search()."""
        captured: dict = {}

        async def fake_search(self, **kwargs):
            captured.update(kwargs)
            return hs.HybridResult(hits=[], explain={})

        monkeypatch.setattr(HybridSearchService, "search", fake_search)
        svc = HybridSearchService(embedding_svc=None)
        scope = RetrievalScope(
            jurisdiction="ng",
            as_of="2026-01-01",
            doc_types=("ACT",),
            tenant_id="matter-42",
        )
        await svc.search_scoped("query", scope, per_leg_k=10, limit=5)
        assert captured["jurisdiction"] == "ng"
        assert captured["as_of"] == "2026-01-01"
        assert captured["doc_types"] == ("ACT",)
        assert captured["tenant_id"] == "matter-42"
        assert captured["per_leg_k"] == 10
        assert captured["limit"] == 5

    @pytest.mark.asyncio
    async def test_service_scope_wins_over_args(self, monkeypatch) -> None:
        """When both are given, scope.jurisdiction is authoritative."""
        captured: dict = {}

        async def fake_scoped(**kwargs):
            captured.update(kwargs)
            return hs.HybridResult(hits=[], explain={})

        class _FakeRerankResult:
            hits = []
            coverage = 0.0
            coverage_ok = False
            degraded = True
            reason = "no candidates"
            model = "test"
            rerank_ms = 0.0
            explain = {}

        async def fake_rerank(query, hits):
            return _FakeRerankResult()

        from app.services.retrieval import service as svc_mod

        monkeypatch.setattr(
            svc_mod.hybrid_search_service, "search_scoped", fake_scoped
        )
        monkeypatch.setattr(svc_mod.flash_reranker, "rerank", fake_rerank)

        result = await retrieval_service.retrieve_with_coverage(
            query="q",
            jurisdiction="za",
            scope=RetrievalScope(jurisdiction="ng"),
        )
        assert captured["scope"].jurisdiction == "ng"
        assert result.coverage_ok is False  # honest refusal on empty

    def test_one_path_for_both_jurisdictions(self) -> None:
        """No per-jurisdiction branches: both ids run the same function."""
        import inspect

        src = inspect.getsource(HybridSearchService.search)
        assert 'if jurisdiction == "za"' not in src
        assert 'if jurisdiction == "ng"' not in src
