"""Week 5 E2 tests: NG synonym dict v1 + post-fusion structural boosts.

Scope-locked per IMPLEMENTATION_PLAN_15W.md 0A: W5's GB/US dict work is
reassigned to ZA depth + NG prep, so these tests cover the NG dict and the
structural-boost module instead.
"""

from __future__ import annotations

import pytest

from app.services.retrieval.boosts import (
    DEFAULT_BOOST_WEIGHTS,
    StructuralBoosts,
)
from app.services.retrieval.hybrid_search import HybridHit
from app.services.retrieval.synonyms import (
    SynonymDictError,
    load_synonym_dict,
)

# ---------------------------------------------------------------------------
# NG synonym dict v1
# ---------------------------------------------------------------------------


class TestNGSynonymDict:
    def test_loads_and_is_valid_v1(self) -> None:
        d = load_synonym_dict("ng")
        assert d.jurisdiction == "ng"
        assert d.version == "1.0"
        assert d.term_count > 20, "NG dict should carry a real vocabulary"

    def test_act_aliases_resolve(self) -> None:
        d = load_synonym_dict("ng")
        assert d.lookup_act("cama").startswith("Companies and Allied Matters")
        assert d.lookup_act("labour_act").startswith("Labour Act")
        assert d.lookup_act("ndpa") == "Nigeria Data Protection Act 2023"

    def test_expansion_colloquial_to_statutory(self) -> None:
        d = load_synonym_dict("ng")
        aliases = d.expand_term("minimum_wage")
        assert "national minimum wage" in [a.lower() for a in aliases]

    def test_section_patterns_cover_labour_act(self) -> None:
        d = load_synonym_dict("ng")
        assert "section 18" in d.sections_for("annual_leave")
        assert "section 11" in d.sections_for("notice_period")

    def test_unknown_jurisdiction_raises(self) -> None:
        with pytest.raises(SynonymDictError):
            load_synonym_dict("gb")  # out of prototype scope on purpose

    def test_za_registry_still_works(self) -> None:
        d = load_synonym_dict("za")
        assert d.jurisdiction == "za"
        assert d.lookup_act("bcea") is not None


# ---------------------------------------------------------------------------
# Structural boosts
# ---------------------------------------------------------------------------


def _hit(chunk_id: str, rrf: float, act: str = "Basic Conditions of Employment Act 75 of 1997",
         section: str | None = None, source_id: str = "za-act-75-1997-bcea") -> HybridHit:
    return HybridHit(
        chunk_id=chunk_id,
        version_id="v1",
        source_id=source_id,
        source_title=f"{act} (consolidated)",
        act_name=act,
        section_no=section,
        heading=None,
        text="irrelevant text body",
        as_at_date=None,
        dense_rank=1,
        lexical_rank=1,
        rrf_score=rrf,
    )


class TestStructuralBoosts:
    def test_act_match_promotes_named_act(self) -> None:
        boosts = StructuralBoosts()
        lookup = {
            "bcea": "Basic Conditions of Employment Act 75 of 1997",
            "companies_act": "Companies Act 71 of 2008",
        }.get
        bcea = _hit("b1", rrf=0.030)
        cama = _hit("c1", rrf=0.031, act="Companies Act 71 of 2008",
                    source_id="za-act-71-2008-companies")
        result = boosts.apply([cama, bcea], "BCEA annual leave entitlement",
                              act_alias_lookup=lookup)
        assert result.hits[0].chunk_id == "b1"  # boosted past the higher-RRF hit
        assert result.explain["per_hit"]["b1"]["act_match"] > 0

    def test_section_match_promotes_cited_section(self) -> None:
        boosts = StructuralBoosts()
        s20 = _hit("h20", rrf=0.028, section="20")
        other = _hit("h7", rrf=0.030, section="7")
        result = boosts.apply([other, s20], "how much annual leave under section 20")
        assert result.hits[0].chunk_id == "h20"

    def test_never_adds_or_removes_hits(self) -> None:
        boosts = StructuralBoosts()
        hits = [_hit(f"h{i}", rrf=0.01 * (10 - i)) for i in range(10)]
        result = boosts.apply(hits, "completely unrelated query about nothing named")
        assert [h.chunk_id for h in result.hits] == [h.chunk_id for h in hits]
        assert result.explain["reordered"] == 0

    def test_authority_breaks_ties(self) -> None:
        boosts = StructuralBoosts()
        low = _hit("low", rrf=0.030, source_id="za-ancillary-1")
        high = _hit("high", rrf=0.030, source_id="za-act-75-1997-bcea")
        result = boosts.apply(
            [low, high],
            "annual leave",
            authority_levels={"za-act-75-1997-bcea": 8, "za-ancillary-1": 1},
        )
        assert result.hits[0].chunk_id == "high"

    def test_stable_tie_break_preserves_fused_order(self) -> None:
        boosts = StructuralBoosts()
        a = _hit("a", rrf=0.03)
        b = _hit("b", rrf=0.03)
        result = boosts.apply([a, b], "plain query")
        assert [h.chunk_id for h in result.hits] == ["a", "b"]

    def test_unknown_weight_rejected(self) -> None:
        with pytest.raises(ValueError):
            StructuralBoosts(weights={"made_up": 1.0})

    def test_weights_default_match_tuning_config(self) -> None:
        import json
        from pathlib import Path

        cfg = json.loads(
            (Path(__file__).resolve().parents[1] / "app/data/retrieval_tuning.json")
            .read_text(encoding="utf-8")
        )
        for key, val in cfg["boosts"].items():
            if key.startswith("_"):
                continue
            assert DEFAULT_BOOST_WEIGHTS[key] == val
