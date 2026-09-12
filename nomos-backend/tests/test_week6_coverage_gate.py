"""Week 6 E2 tests: standardized jurisdiction-aware coverage gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.retrieval.coverage import CoverageGate, coverage_gate


class TestThresholdCascade:
    def test_tuned_jurisdictions_from_tuning_config(self) -> None:
        # Tuning config is the source of truth for configured jurisdictions.
        cfg = json.loads(
            (Path(__file__).resolve().parents[1] / "app/data/retrieval_tuning.json")
            .read_text(encoding="utf-8")
        )
        for jur, expected in cfg["coverage_thresholds"].items():
            if jur.startswith("_"):
                continue
            assert coverage_gate.threshold_for(jur) == pytest.approx(expected)

    def test_case_insensitive(self) -> None:
        assert coverage_gate.threshold_for("ZA") == coverage_gate.threshold_for("za")

    def test_unknown_uses_global_default(self) -> None:
        # Unconfigured ids get the house global default (0.35), not the ZA bar.
        assert coverage_gate.threshold_for("zz") == pytest.approx(0.35)

    def test_blank_id_gets_floor(self) -> None:
        assert coverage_gate.threshold_for("") == pytest.approx(0.5)

    def test_corrupt_tuning_degrades_to_jurisdiction_file(self, tmp_path: Path) -> None:
        bad = tmp_path / "tuning.json"
        bad.write_text("{not json", encoding="utf-8")
        gate = CoverageGate(tuning_path=bad)
        # Tuning config unreadable -> cascade falls back to the jurisdiction
        # thresholds file, which still holds za=0.5 (graceful degradation).
        assert gate.threshold_for("za") == pytest.approx(0.5)
        # And the gate itself keeps working.
        assert gate.evaluate("za", 0.49).coverage_ok is False
        assert gate.evaluate("za", 0.51).coverage_ok is True


class TestEvaluate:
    def test_pass_at_threshold_boundary(self) -> None:
        d = coverage_gate.evaluate("ng", 0.40)
        assert d.coverage_ok is True

    def test_refuse_below_threshold(self) -> None:
        d = coverage_gate.evaluate("za", 0.49)
        assert d.coverage_ok is False
        assert "below threshold" in d.reason

    def test_degraded_no_hits_refuses_even_with_high_coverage(self) -> None:
        d = coverage_gate.evaluate("za", 0.9, degraded=True, n_hits=0)
        assert d.coverage_ok is False
        assert "degraded" in d.reason

    def test_degraded_with_hits_lets_coverage_decide(self) -> None:
        d = coverage_gate.evaluate("za", 0.9, degraded=True, n_hits=8)
        assert d.coverage_ok is True

    def test_nan_and_inf_refuse(self) -> None:
        for bad in (float("nan"), float("inf")):
            d = coverage_gate.evaluate("za", bad)
            assert d.coverage_ok is False

    def test_missing_jurisdiction_refuses(self) -> None:
        d = coverage_gate.evaluate("", 0.9)
        assert d.coverage_ok is False
        assert "missing jurisdiction" in d.reason

    def test_explain_carries_context(self) -> None:
        d = coverage_gate.evaluate("ng", 0.2, degraded=False, n_hits=3)
        assert d.explain == {"jurisdiction": "ng", "n_hits": 3, "degraded": False}
