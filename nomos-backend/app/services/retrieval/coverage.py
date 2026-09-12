"""Standardized coverage gate: one jurisdiction-aware source of truth.

Week 6 E2 (re-scoped from M2's three-jurisdiction gate to ZA+NG). Before this
module the coverage threshold lived in two places (FlashReranker's constructor
hardcoding ``"za"``, and the tuning config) with a fallback in a third; the NG
corpus would have been silently judged by the ZA bar. Plan §3.9 makes the
honesty contract blocking in the hot path, so the gate must be unambiguous.

Contract:
- ``threshold_for(jurisdiction)``: the bar for answering vs refusing.
  Cascade: ``retrieval_tuning.json`` ``coverage_thresholds`` (tuned values,
  Week 4 eval delta applies) -> jurisdiction global default from
  ``jurisdiction_thresholds.json`` (house fallback for unconfigured ids,
  matching ``JurisdictionThresholds``) -> 1.0 (impossible bar, fail closed)
  when even the fallback lookup is unavailable.
- ``evaluate(jurisdiction, coverage, degraded, n_hits)``: the single gate
  decision used by the pipeline (rerank -> service -> endpoint). Fails
  CLOSED: missing jurisdiction, degraded rerank with no hits, or malformed
  coverage all refuse.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TUNING_PATH = Path(__file__).resolve().parents[2] / "data" / "retrieval_tuning.json"

# Last-resort floor if both config files are unreadable. Matches the Week 3
# plan default so behavior cannot silently loosen.
_ABSOLUTE_FLOOR = 0.5


@dataclass
class CoverageDecision:
    """The gate verdict the pipeline and endpoint consume."""

    coverage: float
    threshold: float
    coverage_ok: bool
    reason: str
    explain: dict[str, Any] = field(default_factory=dict)


class CoverageGate:
    """Jurisdiction-aware coverage evaluation (fail-closed)."""

    def __init__(self, tuning_path: str | Path | None = None) -> None:
        self._path = Path(tuning_path) if tuning_path else _TUNING_PATH
        self._thresholds: dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            raw = data.get("coverage_thresholds", {})
            self._thresholds = {
                k.lower(): float(v)
                for k, v in raw.items()
                if not k.startswith("_") and isinstance(v, (int, float))
            }
        except (OSError, ValueError, TypeError) as exc:
            logger.error("coverage thresholds unavailable (%s); using floor", exc)
            self._thresholds = {}

    def reload(self) -> None:
        """Re-read the tuning config (tests and hot config updates)."""
        self._load()

    def threshold_for(self, jurisdiction: str) -> float:
        """Coverage bar for a jurisdiction id (e.g. 'za', 'ng')."""
        key = (jurisdiction or "").strip().lower()
        if key in self._thresholds:
            return self._thresholds[key]
        if key:
            # Unknown jurisdiction: global default from the thresholds file
            # is more honest than the ZA-specific bar.
            try:
                from app.services.ai.thresholds import thresholds

                gd = thresholds.get_threshold(key, "coverage_threshold")
                if isinstance(gd, (int, float)):
                    return float(gd)
            except Exception:  # pragma: no cover - defensive
                pass
            logger.warning("no coverage threshold for %r; failing closed", key)
            return 1.0  # impossible bar -> always refuse (fail closed)
        return _ABSOLUTE_FLOOR

    def evaluate(
        self,
        jurisdiction: str,
        coverage: float,
        *,
        degraded: bool = False,
        n_hits: int = 0,
    ) -> CoverageDecision:
        """Single gate decision for the pipeline. Fails closed.

        Rules:
        - unknown/missing jurisdiction -> refuse;
        - degraded rerank with zero hits -> refuse;
        - malformed coverage (non-finite) -> refuse;
        - otherwise coverage >= threshold answers, below refuses.
        """
        threshold = self.threshold_for(jurisdiction)
        reasons: list[str] = []

        cov = coverage
        if cov is None or cov != cov or cov in (float("inf"), float("-inf")):
            reasons.append("malformed coverage value")
            cov = 0.0

        jur = (jurisdiction or "").strip().lower()
        if not jur:
            reasons.append("missing jurisdiction")

        if degraded and n_hits == 0:
            reasons.append("degraded rerank with no candidates")

        ok = not reasons and cov >= threshold
        if ok:
            reason = "coverage meets threshold"
        else:
            reason = "; ".join(reasons) or (
                f"coverage {cov:.2f} below threshold {threshold:.2f}"
            )

        return CoverageDecision(
            coverage=cov,
            threshold=threshold,
            coverage_ok=ok,
            reason=reason,
            explain={
                "jurisdiction": jur or None,
                "n_hits": n_hits,
                "degraded": degraded,
            },
        )


# Module-level singleton (mirrors flash_reranker convention).
coverage_gate = CoverageGate()
