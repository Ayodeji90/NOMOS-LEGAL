"""Week 13 E2 tests: doc-type filter + authority boosts (ZA pilot, M5).

Scope-locked: the pilot is 1 ZA regulation set; GB SI set is out of prototype
scope. The filter SQL landed with the Week 9 scope work; these tests pin the
pilot contract.
"""

from __future__ import annotations

import inspect

import pytest

from app.services.retrieval.boosts import StructuralBoosts
from app.services.retrieval.hybrid_search import (
    HybridHit,
    HybridSearchService,
    RetrievalScope,
)


class TestDocTypeFilter:
    def test_filter_targets_source_document_type(self) -> None:
        sql = HybridSearchService._base_filter("za", None, ("regulation",))
        assert "lower(s.document_type) = ANY(:doc_types)" in sql
        # Must be a HARD filter: inside the shared WHERE, applied to both legs.
        assert sql.index("lower(s.document_type)") > sql.index("WHERE")

    def test_filter_applies_to_both_legs(self) -> None:
        dense_src = inspect.getsource(HybridSearchService._dense_leg)
        lex_src = inspect.getsource(HybridSearchService._lexical_leg)
        assert "doc_types" in dense_src and "_base_filter(jurisdiction, as_of, doc_types)" in dense_src
        assert "doc_types" in lex_src and "_base_filter(jurisdiction, as_of, doc_types)" in lex_src

    def test_legs_lowercase_doc_types(self) -> None:
        for src in (
            inspect.getsource(HybridSearchService._dense_leg),
            inspect.getsource(HybridSearchService._lexical_leg),
        ):
            assert '[d.lower() for d in doc_types]' in src

    def test_scope_carries_doc_types(self) -> None:
        scope = RetrievalScope(jurisdiction="za", doc_types=("ACT", "REGULATION"))
        assert scope.doc_types == ("ACT", "REGULATION")


class TestAuthorityBoostPilot:
    def _hit(self, cid: str, source_id: str, rrf: float) -> HybridHit:
        return HybridHit(
            chunk_id=cid, version_id="v", source_id=source_id,
            source_title="t", act_name="a", section_no=None, heading=None,
            text="t", as_at_date=None, dense_rank=1, lexical_rank=1,
            rrf_score=rrf,
        )

    def test_principal_act_outranks_regulation_on_tie(self) -> None:
        """Court/authority boosts: principal Act beats ancillary instrument."""
        boosts = StructuralBoosts()
        reg = self._hit("reg", "za-si-1", rrf=0.030)
        act = self._hit("act", "za-act-75-1997-bcea", rrf=0.030)
        result = boosts.apply(
            [reg, act], "notice period",
            authority_levels={"za-act-75-1997-bcea": 8, "za-si-1": 2},
        )
        assert result.hits[0].chunk_id == "act"

    def test_hit_metadata_carried_through(self) -> None:
        """document_type/authority_level flow from SQL rows to hits."""
        h = HybridHit(
            chunk_id="c", version_id="v", source_id="s", source_title="t",
            act_name="a", section_no=None, heading=None, text="t",
            as_at_date=None, dense_rank=1, lexical_rank=1, rrf_score=0.1,
            document_type="REGULATION", authority_level=3,
        )
        assert h.document_type == "REGULATION"
        assert h.authority_level == 3


@pytest.mark.asyncio
async def test_doc_type_filter_live_db() -> None:
    """Live ZA check: ACT-only filter returns hits; bogus type returns none.

    Skips (does not fail) when running against the CI/test schema, which has
    the DDL but no ingested corpus; run locally against the dev DB to execute.
    """
    import pytest
    from sqlalchemy import text

    from app.db.session import db_manager

    db_manager.initialize()
    svc = HybridSearchService()

    async with db_manager.session() as session:
        n = await session.execute(
            text(
                "SELECT COUNT(*) FROM chunk c "
                "JOIN version v ON c.version_id = v.id "
                "JOIN source s ON v.source_id = s.id "
                "WHERE lower(s.jurisdiction) = 'za'"
            )
        )
        if (n.scalar() or 0) == 0:
            pytest.skip("no ZA corpus in this database (CI test schema)")

        from app.services.ai.embedding_service import embedding_service

        qvec = (
            await embedding_service.generate_embeddings(["annual leave entitlement"])
        )[0]

        act_rows = await svc._dense_leg(
            session, qvec, "za", None, 10, doc_types=("ACT",)
        )
        none_rows = await svc._dense_leg(
            session, qvec, "za", None, 10, doc_types=("REGULATION",)
        )
        assert len(act_rows) > 0, "ZA ACT corpus should hit"
        assert len(none_rows) == 0, "no REGULATION sources exist yet (pilot pending)"
