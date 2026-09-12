"""Structural boosts: post-fusion soft ranking adjustments.

Week 5 E2 (re-scoped from GB/US to ZA depth + NG prep). Plan §3.7 freezes the
retrieval design: hard filters pre-fusion (jurisdiction, in-force, currency),
SOFT boosts post-fusion (act/section match, authority level, doc type). These
boosts never add or remove hits — they only reorder fused candidates — so they
cannot break the honesty contract: the coverage gate and refusal behavior stay
exactly as tuned in Week 4.

Boost model: each hit's fused RRF score is adjusted by additive bonuses in
``[0, max_boost]`` per feature:

- Act match:      the query (or a resolved act alias from the jurisdiction's
                  synonym dict) names an act the hit belongs to.
- Section match:  the query cites a section number the hit carries
                  (e.g. "section 20", "s 20", "sec 20").
- Authority:      higher ``source.authority_level`` ranks first within ties
                  (principal Acts outrank ancillary instruments).

Weights come from ``retrieval_tuning.json`` (``boosts`` key) so every change
ships with an eval delta, per the Week 4 gate. The module is pure: no DB, no
LLM, trivially unit-testable.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.services.retrieval.hybrid_search import HybridHit

logger = logging.getLogger(__name__)

# Section-citation pattern: "section 20", "s20", "s 20", "sec. 20", "§ 20".
# Captures the bare section number ("20", "20A", "20(1)").
_SECTION_PATTERN = re.compile(
    r"\b(?:section|sect?|ss|§)\s*(\d+[A-Za-z]?(?:\(\d+\))?)\b",
    re.IGNORECASE,
)

DEFAULT_BOOST_WEIGHTS: dict[str, float] = {
    "act_match": 0.15,
    "section_match": 0.10,
    "authority": 0.05,
    "authority_max_level": 10.0,
}


@dataclass
class BoostResult:
    """Reordered hits plus an explain trace for observability."""

    hits: list[HybridHit]
    explain: dict[str, Any] = field(default_factory=dict)


class StructuralBoosts:
    """Applies post-fusion structural boosts to fused hybrid hits."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._weights = dict(DEFAULT_BOOST_WEIGHTS)
        if weights:
            unknown = set(weights) - set(self._weights)
            if unknown:
                raise ValueError(f"unknown boost weights: {sorted(unknown)}")
            self._weights.update({k: float(v) for k, v in weights.items()})

    # -- feature extraction ------------------------------------------------

    @staticmethod
    def _query_section_refs(query: str) -> set[str]:
        """Bare section numbers cited in the query (e.g. {'20', '20(1)'})."""
        return {m.group(1).lower() for m in _SECTION_PATTERN.finditer(query or "")}

    def _act_aliases(self, query: str, act_alias_lookup: Any) -> set[str]:
        """Normalized act names the query names, via the synonym dict aliases.

        ``act_alias_lookup`` is ``SynonymDict.lookup_act`` or None. A match is
        when the SHORT ALIAS (e.g. "bcea", "labour act") or the full title
        itself appears in the query; the resolved full title is what we match
        against the hit's act name / source title.
        """
        names: set[str] = set()
        q = (query or "").lower()
        if act_alias_lookup is not None:
            for alias in ("bcea", "lra", "eea", "cama", "popia", "cpa", "pisa",
                          "ndpa", "labour_act", "companies_act", "constitution",
                          "land_use_act", "fccpa"):
                full = act_alias_lookup(alias)
                if not full:
                    continue
                alias_text = alias.replace("_", " ")
                if alias_text in q or full.lower() in q:
                    names.add(full.lower())
        return names

    # -- scoring -----------------------------------------------------------

    def apply(
        self,
        hits: list[HybridHit],
        query: str,
        act_alias_lookup: Any = None,
        authority_levels: dict[str, int] | None = None,
    ) -> BoostResult:
        """Reorder ``hits`` by fused score + structural bonuses.

        Args:
            hits: fused hybrid hits (already RRF-ordered).
            query: raw user query.
            act_alias_lookup: optional ``SynonymDict.lookup_act`` callable for
                act-alias resolution (pass the jurisdiction's loaded dict).
            authority_levels: optional ``source_id -> authority_level`` map;
                absent sources get level 0 (no bonus).

        Returns:
            BoostResult with a stable-sorted copy of hits and an explain dict
            (per-hit bonuses) for the retrieval trace.
        """
        section_refs = self._query_section_refs(query)
        act_names = self._act_aliases(query, act_alias_lookup)
        levels = authority_levels or {}

        scored: list[tuple[float, int, HybridHit, dict[str, Any]]] = []
        per_hit: dict[str, dict[str, Any]] = {}
        w = self._weights

        for idx, h in enumerate(hits):
            bonuses: dict[str, float] = {}

            act_l = (h.act_name or "").lower()
            title_l = (h.source_title or "").lower()
            if act_names and any(
                name in act_l or name in title_l for name in act_names
            ):
                bonuses["act_match"] = w["act_match"]

            if h.section_no and h.section_no.lower() in section_refs:
                bonuses["section_match"] = w["section_match"]

            level = float(levels.get(h.source_id, 0))
            if level > 0 and w["authority"] > 0:
                bonuses["authority"] = w["authority"] * min(
                    1.0, level / max(1.0, w["authority_max_level"])
                )

            boost = sum(bonuses.values())
            # Stable ordering: original fused order breaks exact ties, so
            # equal-scored hits never shuffle (deterministic traces).
            scored.append((-(h.rrf_score + boost), idx, h, bonuses))
            if bonuses:
                per_hit[h.chunk_id] = {
                    **bonuses,
                    "total_boost": round(boost, 4),
                }

        scored.sort(key=lambda t: (t[0], t[1]))
        ordered = [t[2] for t in scored]

        moved = sum(
            1 for i, t in enumerate(scored) if t[1] != i
        )
        explain: dict[str, Any] = {
            "boosted_hits": len(per_hit),
            "reordered": moved,
            "weights": dict(w),
            "per_hit": per_hit,
        }
        if moved:
            logger.info("structural boosts reordered %d/%d hits", moved, len(hits))
        return BoostResult(hits=ordered, explain=explain)


# Module-level singleton (mirrors hybrid_search_service convention).
structural_boosts = StructuralBoosts()
