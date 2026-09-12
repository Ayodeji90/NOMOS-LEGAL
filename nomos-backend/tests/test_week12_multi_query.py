"""Week 12 E2 tests: multi-query batch + dedupe + coverage diagnostics."""

from __future__ import annotations

import asyncio

import pytest

from app.services.retrieval.hybrid_search import (
    HybridHit,
    HybridResult,
    RetrievalScope,
)
from app.services.retrieval.multi_query import (
    BatchRetrievalResult,
    MultiQueryRetriever,
    PartResult,
)


def _hit(cid: str, act: str = "BCEA", section: str | None = None) -> HybridHit:
    return HybridHit(
        chunk_id=cid,
        version_id="v",
        source_id="za-act-75-1997-bcea",
        source_title=act,
        act_name=act,
        section_no=section,
        heading=None,
        text="t",
        as_at_date=None,
        dense_rank=1,
        lexical_rank=1,
        rrf_score=0.03,
    )


def _fake_search_svc(per_query: dict[str, list[HybridHit]], fail_on: set[str] | None = None):
    fail_on = fail_on or set()

    class _Fake:
        async def search_scoped(self, query, scope, per_leg_k=50, limit=None):
            if query in fail_on:
                raise RuntimeError("boom")
            return HybridResult(hits=list(per_query.get(query, [])), explain={})

    return _Fake()


class TestBatch:
    @pytest.mark.asyncio
    async def test_parts_run_and_merge(self) -> None:
        svc = MultiQueryRetriever(
            _fake_search_svc({
                "part a": [_hit("a1"), _hit("a2"), _hit("a3")],
                "part b": [_hit("b1"), _hit("b2"), _hit("b3")],
            })
        )
        result = await svc.retrieve_batch(
            ["part a", "part b"], RetrievalScope(jurisdiction="za")
        )
        assert len(result.parts) == 2
        assert {h.chunk_id for h in result.hits} == {"a1", "a2", "a3", "b1", "b2", "b3"}
        assert result.explain["missing_part_indexes"] == []

    @pytest.mark.asyncio
    async def test_dedupe_keeps_best_rank_and_provenance(self) -> None:
        shared = _hit("shared")
        svc = MultiQueryRetriever(
            _fake_search_svc({
                "first": [_hit("x1"), shared],
                "second": [shared, _hit("y1"), _hit("y2"), _hit("y3")],
            })
        )
        result = await svc.retrieve_batch(
            ["first", "second"], RetrievalScope(jurisdiction="za")
        )
        ids = [h.chunk_id for h in result.hits]
        assert ids.count("shared") == 1
        # shared ranked 2nd in "first" -> its best rank beats the 1st-place
        # y1? No: y1 rank 2 in second, shared rank 2 in first; tie broken by
        # part index (first < second) -> shared before y1.
        assert ids.index("shared") < ids.index("y1")
        assert sorted(result.chunk_parts["shared"]) == [0, 1]

    @pytest.mark.asyncio
    async def test_missing_part_diagnosed(self) -> None:
        svc = MultiQueryRetriever(
            _fake_search_svc({
                "rich part": [_hit(f"r{i}") for i in range(5)],
                "thin part": [_hit("t1")],  # below DEFAULT_MIN_HITS_PER_PART
            })
        )
        result = await svc.retrieve_batch(
            ["rich part", "thin part"], RetrievalScope(jurisdiction="za")
        )
        assert result.missing_parts[0].index == 1
        assert result.explain["missing_part_indexes"] == [1]
        assert result.parts[0].covered is True

    @pytest.mark.asyncio
    async def test_part_failure_isolated(self) -> None:
        svc = MultiQueryRetriever(
            _fake_search_svc(
                {"good": [_hit("g1"), _hit("g2"), _hit("g3")]},
                fail_on={"bad"},
            )
        )
        result = await svc.retrieve_batch(
            ["good", "bad"], RetrievalScope(jurisdiction="za")
        )
        assert result.parts[1].error is not None
        assert result.parts[1].covered is False
        assert [h.chunk_id for h in result.hits] == ["g1", "g2", "g3"]

    @pytest.mark.asyncio
    async def test_max_total_caps_merge(self) -> None:
        svc = MultiQueryRetriever(
            _fake_search_svc({
                "a": [_hit(f"a{i}") for i in range(10)],
                "b": [_hit(f"b{i}") for i in range(10)],
            })
        )
        result = await svc.retrieve_batch(
            ["a", "b"], RetrievalScope(jurisdiction="za"), max_total=8
        )
        assert len(result.hits) == 8

    @pytest.mark.asyncio
    async def test_empty_queries(self) -> None:
        result = await MultiQueryRetriever(_fake_search_svc({})).retrieve_batch(
            [], RetrievalScope(jurisdiction="za")
        )
        assert isinstance(result, BatchRetrievalResult)
        assert result.hits == []

    @pytest.mark.asyncio
    async def test_parts_actually_parallel(self) -> None:
        """Parts run concurrently (gather), not sequentially."""
        started = []

        class _Slow:
            async def search_scoped(self, query, scope, per_leg_k=50, limit=None):
                started.append(query)
                await asyncio.sleep(0.05)
                return HybridResult(hits=[], explain={})

        svc = MultiQueryRetriever(_Slow())
        await asyncio.wait_for(
            svc.retrieve_batch(["a", "b", "c"], RetrievalScope(jurisdiction="za")),
            timeout=0.14,  # 3 sequential 50ms sleeps would exceed this
        )
        assert len(started) == 3


class TestPartResult:
    def test_covered_threshold(self) -> None:
        ok = PartResult(query="q", index=0, fused_hits=3)
        thin = PartResult(query="q", index=1, fused_hits=2)
        failed = PartResult(query="q", index=2, error="x", fused_hits=0)
        assert ok.covered and not thin.covered and not failed.covered
