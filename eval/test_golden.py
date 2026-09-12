"""Golden-set integrity tests: schema conformance + W1 counts.

Scope: ZA-only prototype (Nigeria next). GB sets are deferred to
Phase 2, so this asserts za.json holds 30 items: 25 answerable +
5 must-refuse (2 cross-jurisdiction traps, 1 invented-act trap,
1 case-law gap, 1 coverage gap).
"""

import json
from pathlib import Path

from eval.validate_golden import REFUSAL_REASONS, validate

GOLDEN = Path(__file__).parent / "golden" / "za.json"


def load():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_golden_validates_clean():
    assert validate(load()) == []


def test_counts():
    items = load()
    assert len(items) == 30
    refused = [i for i in items if i["must_refuse"]]
    answerable = [i for i in items if not i["must_refuse"]]
    assert len(answerable) == 25
    assert len(refused) == 5


def test_ids_unique_and_ordered():
    ids = [i["id"] for i in load()]
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)


def test_refusal_reasons_cover_all_traps():
    reasons = {i["refusal_reason"] for i in load() if i["must_refuse"]}
    assert reasons == REFUSAL_REASONS


def test_cross_jurisdiction_traps_suggest():
    traps = [i for i in load() if i.get("refusal_reason") == "wrong-jurisdiction"]
    assert len(traps) == 2
    for t in traps:
        assert t.get("suggested_jurisdiction") in {"gb", "us"}


def test_answerable_items_have_targets():
    for i in load():
        if not i["must_refuse"]:
            assert i["expected_sections"], i["id"]
            assert i["expected_acts"], i["id"]
            assert i["jurisdiction"] == "za"
            assert i["corpus_id"] == "legislation-za"
