"""Week 4 unit tests: eval runner parsing + classification logic."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_retrieval_eval import (  # noqa: E402
    HELD_ACTS,
    expected_section_id,
    summarize,
)

# ---------------------------------------------------------------------------
# Section-ref parsing / corpus scoping
# ---------------------------------------------------------------------------


class TestSectionParsing:
    def test_bcea_ref_maps_to_source(self):
        assert expected_section_id("BCEA s20") == "za-act-75-1997-bcea#20"

    def test_companies_ref_maps_to_source(self):
        assert (
            expected_section_id("Companies Act s129")
            == "za-act-71-2008-companies#129"
        )

    def test_unheld_act_marked(self):
        eid = expected_section_id("LRA s64")
        assert eid.startswith("unheld:")
        assert "#64" in eid

    def test_unparseable_ref_passthrough(self):
        assert expected_section_id("no section marker") == "no section marker"

    def test_held_acts_complete(self):
        assert set(HELD_ACTS) == {"BCEA", "Companies Act"}


# ---------------------------------------------------------------------------
# Summarize classification (the honest-corpus contract)
# ---------------------------------------------------------------------------


def _row(rid, *, must_refuse=False, refused=False, expected=None, ooc=False,
         recall=None, rr=0.0, coverage=0.5):
    return {
        "id": rid,
        "must_refuse": must_refuse,
        "refused": refused,
        "recall": recall,
        "rr": rr,
        "coverage": coverage,
        "out_of_corpus_refs": ["LRA s64"] if ooc else [],
        "_expected_ids": expected or [],
        "_ranked_ids": [],
    }


class TestSummarizeClassification:
    def test_ooc_refusal_not_false_refusal(self):
        """An answerable question outside the corpus SHOULD be refused."""
        rows = [
            _row("a", expected=["za-x#1"], recall=1.0, rr=1.0, coverage=0.9),
            _row("b", expected=[], ooc=True, refused=True, coverage=0.0),
        ]
        s = summarize(rows, k=10)
        assert s["false_refusals"] == []
        assert s["n_ooc_answerable_refused"] == 1
        assert s["ooc_answerable_refused_ids"] == ["b"]

    def test_in_corpus_refusal_is_false_refusal(self):
        rows = [
            _row("a", expected=["za-x#1"], refused=True),  # had expectations, refused
        ]
        s = summarize(rows, k=10)
        assert s["false_refusals"] == ["a"]

    def test_must_refuse_wrongly_answered(self):
        rows = [
            _row("trap", must_refuse=True, refused=False),
        ]
        s = summarize(rows, k=10)
        assert s["false_answers"] == ["trap"]
        assert s["refusal_accuracy"] == 0.0

    def test_perfect_scores(self):
        rows = [
            _row(f"a{i}", expected=[f"za-x#{i}"], recall=1.0, rr=1.0, coverage=0.9)
            for i in range(3)
        ] + [_row(f"r{i}", must_refuse=True, refused=True) for i in range(2)]
        s = summarize(rows, k=10)
        assert s["recall_at_10"] == 1.0
        assert s["mrr"] == 1.0
        assert s["refusal_accuracy"] == 1.0
        assert s["false_answers"] == []
        assert s["false_refusals"] == []

    def test_recall_none_excluded_from_mean(self):
        """Items with only out-of-corpus expectations contribute no recall."""
        rows = [
            _row("a", expected=["za-x#1"], recall=1.0, rr=1.0),
            _row("b", expected=[], ooc=True, refused=True),
        ]
        s = summarize(rows, k=10)
        assert s["recall_at_10"] == 1.0  # only 'a' scored


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
