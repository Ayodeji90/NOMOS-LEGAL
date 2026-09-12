"""Unit tests for eval.metrics (synthetic data, no model or DB needed)."""

from eval.metrics import (
    citation_validity,
    extract_citations,
    extract_section_refs,
    jurisdiction_leakage,
    mrr,
    recall_at_k,
    refusal_report,
    section_realism,
)


def test_extract_citations():
    assert extract_citations("Rule [1] then exception [2] and again [1].") == [1, 2]
    assert extract_citations("No cites here.") == []


def test_citation_validity_ok():
    assert citation_validity("Lead with [1], support with [2].", 2) == {
        "valid": True,
        "dangling": [],
    }


def test_citation_validity_dangling():
    out = citation_validity("Invented support [3].", 2)
    assert out == {"valid": False, "dangling": [3]}


def test_extract_section_refs():
    assert "76" in extract_section_refs("duties under section 76 of the Act")
    assert "145" in extract_section_refs("see s 145 for overtime")


def test_section_realism_ok():
    excerpts = [
        {
            "sectionNo": "76",
            "subsection": "(2)",
            "text": "A director must act in good faith s. 76",
        }
    ]
    assert section_realism("Duties arise under section 76.", excerpts)["ok"]


def test_section_realism_invented():
    excerpts = [
        {"sectionNo": "76", "subsection": "", "text": "Standards of directors conduct"}
    ]
    out = section_realism("Liability follows under section 145.", excerpts)
    assert not out["ok"] and out["unverified"] == ["145"]


def test_recall_at_k():
    assert recall_at_k(["a", "b", "c"], ["b", "c", "z"], k=10) == 2 / 3
    assert recall_at_k(["a"], ["a"], k=10) == 1.0
    assert recall_at_k([], [], k=10) == 1.0


def test_mrr():
    assert mrr(["x", "b", "c"], ["b"]) == 1 / 2
    assert mrr(["x"], ["b"]) == 0.0


def test_jurisdiction_leakage_none():
    out = jurisdiction_leakage([{"jurisdiction": "za"}], "za")
    assert out == {"rate": 0.0, "leaked": []}


def test_jurisdiction_leakage_hard_fail():
    out = jurisdiction_leakage([{"jurisdiction": "za"}, {"jurisdiction": "gb"}], "za")
    assert out["rate"] == 0.5 and len(out["leaked"]) == 1


def test_refusal_report():
    cases = [
        {"id": "a", "must_refuse": True, "refused": True},
        {"id": "b", "must_refuse": True, "refused": False},
        {"id": "c", "must_refuse": False, "refused": False},
        {"id": "d", "must_refuse": False, "refused": True},
    ]
    out = refusal_report(cases)
    assert out["accuracy"] == 0.5
    assert out["false_answers"] == ["b"]
    assert out["false_refusals"] == ["d"]
