"""Reciprocal Rank Fusion (RRF) for hybrid retrieval.

Fuses ranked result lists (e.g. sparse BM25/tsvector leg + dense HNSW leg)
into a single ranking. The fused score of a document ``d`` is:

    score(d) = sum over lists L of  weight_L / (rrf_k + rank_L(d))

where ``rank_L(d)`` is the 1-based position of ``d`` in list ``L``. This is
the formulation of Cormack, Clarke & Buettcher (2009); ``rrf_k = 60`` damps
the influence of top ranks and is the community default
(settings.RETRIEVAL_RRF_K).

Design notes:
- Pure functions: no I/O, no ORM, no DB. Trivially unit-testable.
- Generic over any hashable item id; callers keep their own payloads and
  re-attach them after fusion (keeps this module dependency-free).
- Per-list weights: an item absent from a list gets no contribution from
  that list (its weight is never applied to a rank it does not have).
- A list where the same id appears twice counts only its best (lowest) rank.
- Ties in fused score are broken deterministically: best-rank asc, then id
  asc, so results are reproducible across runs and processes.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Generic, TypeVar

ID = TypeVar("ID", bound=Hashable)

#: Default damping constant (matches settings.RETRIEVAL_RRF_K).
DEFAULT_RRF_K = 60


@dataclass(frozen=True)
class FusedResult(Generic[ID]):
    """A fused result: the item id, its RRF score, and rank provenance."""

    id: ID
    score: float
    #: list index -> 1-based rank of this item in that list (present lists only)
    ranks: dict[int, int] = field(default_factory=dict)


def rrf_score(
    ranks: Iterable[int],
    k: int = DEFAULT_RRF_K,
    weights: Iterable[float] | None = None,
) -> float:
    """Compute the RRF score for one item given its per-list ranks.

    Args:
        ranks: 1-based ranks of the item in each list it appears in.
            Order must align with ``weights`` when weights are given.
        k: damping constant (>= 1). Higher flattens rank differences.
        weights: optional per-entry weights (defaults to 1.0 per entry).

    Returns:
        sum(weight_i / (k + rank_i))

    Raises:
        ValueError: if ``k < 1``, any rank < 1, or weights/ranks misalign.
    """
    if k < 1:
        raise ValueError(f"rrf k must be >= 1, got {k}")
    ranks_list = list(ranks)  # materialise once; ranks may be a generator
    weight_list = list(weights) if weights is not None else None
    if weight_list is not None and len(weight_list) != len(ranks_list):
        raise ValueError(
            f"weights length ({len(weight_list)}) must match ranks length ({len(ranks_list)})"
        )
    total = 0.0
    for i, rank in enumerate(ranks_list):
        if rank < 1:
            raise ValueError(f"ranks must be 1-based (got {rank})")
        weight = weight_list[i] if weight_list is not None else 1.0
        total += weight / (k + rank)
    return total


def fuse_ranked_lists(
    ranked_lists: Sequence[Sequence[ID]],
    k: int = DEFAULT_RRF_K,
    weights: Sequence[float] | None = None,
    limit: int | None = None,
) -> list[FusedResult[ID]]:
    """Fuse multiple ranked lists into one ranking via RRF.

    Args:
        ranked_lists: ordered lists of item ids (best first). A list may
            contain duplicate ids; only the best rank of an id counts.
        k: RRF damping constant (default 60).
        weights: per-list weights aligned with ``ranked_lists`` (default
            1.0 each). Lists with weight 0 are skipped entirely. Negative
            weights are rejected.
        limit: optional cap on returned results (applied after sort).

    Returns:
        FusedResult list sorted by score desc, then deterministically:
        best-rank asc, then id asc (stable/reproducible).

    Raises:
        ValueError: if ``k < 1``, weights misalign, or a weight is negative.
    """
    if k < 1:
        raise ValueError(f"rrf k must be >= 1, got {k}")
    if weights is not None and len(weights) != len(ranked_lists):
        raise ValueError(
            f"weights length ({len(weights)}) must match ranked_lists length ({len(ranked_lists)})"
        )
    if weights is not None and any(w < 0 for w in weights):
        raise ValueError("rrf weights must be non-negative")

    weight_by_list = list(weights) if weights is not None else None

    # id -> {list_index: best_rank}
    participation: dict[ID, dict[int, int]] = {}
    for list_index, lst in enumerate(ranked_lists):
        if weight_by_list is not None and weight_by_list[list_index] == 0:
            continue  # zero-weight lists contribute nothing
        best_rank_in_list: dict[ID, int] = {}
        for pos, item in enumerate(lst, start=1):
            prev = best_rank_in_list.get(item)
            if prev is None or pos < prev:
                best_rank_in_list[item] = pos
        for item, rank in best_rank_in_list.items():
            slot = participation.setdefault(item, {})
            prev = slot.get(list_index)
            if prev is None or rank < prev:
                slot[list_index] = rank

    fused: list[FusedResult[ID]] = []
    for item, ranks_map in participation.items():
        score = 0.0
        for list_index, rank in ranks_map.items():
            weight = weight_by_list[list_index] if weight_by_list is not None else 1.0
            score += weight / (k + rank)
        fused.append(FusedResult(id=item, score=score, ranks=dict(ranks_map)))

    # Deterministic ordering: score desc, best rank asc, id asc.
    fused.sort(key=lambda r: (-r.score, min(r.ranks.values()), str(r.id)))
    return fused[:limit] if limit is not None else fused
