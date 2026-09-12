#!/usr/bin/env python3
"""Retrieval eval runner — Week 4 E2.

Runs the ZA golden set (eval/golden/za.json, maintained by E5 at repo root)
through the real retrieval pipeline (hybrid search -> Flash rerank -> coverage
gate) and reports the metrics E5's harness defines:

- recall@10 and MRR over expected sections (e.g. "BCEA s20" -> section_no 20
  in a BCEA source), scoped to the sections the corpus actually holds
- refusal correctness for must_refuse items (coverage gate must fire)
- coverage distribution for answerable items

Scoping honesty: 14 of the 25 answerable golden items target Acts not yet
ingested (LRA, POPIA, etc. — E4's lane). Those are reported separately as
"out_of_corpus" and excluded from recall scoring; otherwise the eval measures
our retrieval against books we do not own.

Output: JSON results file (baseline for the CI eval-delta gate) + stdout table.

Usage:
  python scripts/run_retrieval_eval.py [--golden PATH] [--out PATH] [--k 10]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

from app.services.retrieval.service import retrieval_service  # noqa: E402

logging.basicConfig(level=logging.WARNING)
logging.getLogger("app.services.retrieval.service").setLevel(logging.ERROR)

# Act short-name -> source_id prefix we ingested (keep in sync with ACT_CONFIGS).
HELD_ACTS = {
    "BCEA": "za-act-75-1997-bcea",
    "Companies Act": "za-act-71-2008-companies",
}


def parse_expected_section(ref: str) -> tuple[str, str] | None:
    """'BCEA s20' -> ('BCEA', '20'); None if not parseable.

    Requires the section part to start with a digit (guards against
    mid-word ' s' splits like 'no section marker').
    """
    parts = ref.strip().rsplit(" s", 1)
    if len(parts) != 2:
        return None
    act, sec = parts[0].strip(), parts[1].strip()
    if not sec[:1].isdigit():
        return None
    return (act, sec), None


def expected_section_id(ref: str) -> str:
    """Canonical section id used in recall sets: '<source_id>#<section_no>'."""
    parsed = parse_expected_section(ref)
    if parsed is None:
        return ref
    (act, sec), _ = parsed
    source_id = HELD_ACTS.get(act)
    if source_id is None:
        return f"unheld:{act}#{sec}"
    return f"{source_id}#{sec}"


def hit_section_ids(hit, expected_refs: list[str]) -> set[str]:
    """Which canonical section ids this hit satisfies."""
    ids = set()
    for ref in expected_refs:
        eid = expected_section_id(ref)
        if hit.source_id in eid and hit.section_no and eid.endswith(f"#{hit.section_no.lstrip('0') or '0'}"):
            ids.add(eid)
        elif hit.source_id in eid:
            # section-less chunks (schedules) cannot satisfy numbered refs
            pass
    return ids


async def eval_one(item: dict, k: int) -> dict:
    t0 = time.perf_counter()
    result = await retrieval_service.retrieve_with_coverage(
        query=item["question"], jurisdiction="za", limit=k
    )
    total_ms = (time.perf_counter() - t0) * 1000

    expected_refs = item.get("expected_sections", [])
    expected_in_corpus = [
        r for r in expected_refs if expected_section_id(r).startswith("za-")
    ]
    expected_out = [r for r in expected_refs if r not in expected_in_corpus]

    # Build ranked section-id list from returned excerpts (reranked order)
    ranked_ids: list[str] = []
    for ex in result.excerpts:
        meta = ex.get("retrieval_metadata", {})
        sid = meta.get("source_id", "")
        sec = str(ex.get("section") or "").lstrip("0") or "0"
        ranked_ids.append(f"{sid}#{sec}")

    expected_ids = [expected_section_id(r) for r in expected_in_corpus]

    # recall@k + first-hit rank (for MRR), restricted to in-corpus expectations
    topk = set(ranked_ids[:k])
    hits = [eid for eid in expected_ids if eid in topk]
    recall = len(hits) / len(expected_ids) if expected_ids else None
    first_rank = next(
        (i for i, rid in enumerate(ranked_ids, 1) if rid in set(expected_ids)), None
    )
    rr = 1.0 / first_rank if first_rank else 0.0

    # Refusal contract
    refused = not result.coverage_ok
    if item.get("must_refuse"):
        refusal_correct = refused
    else:
        refusal_correct = True  # tracked via false_refusals below, not blocking here

    return {
        "id": item["id"],
        "question": item["question"],
        "must_refuse": bool(item.get("must_refuse")),
        "refused": refused,
        "refusal_correct": refusal_correct,
        "coverage": round(result.coverage, 3),
        "degraded": result.degraded,
        "n_excerpts": len(result.excerpts),
        "recall": round(recall, 3) if recall is not None else None,
        "rr": round(rr, 3),
        "out_of_corpus_refs": expected_out,
        "total_ms": round(total_ms, 1),
        "_ranked_ids": ranked_ids[:k],
        "_expected_ids": expected_ids,
    }


def summarize(rows: list[dict], k: int) -> dict:
    # "In-corpus" answerable = every expected section held by the current corpus.
    # An answerable item whose expectations are all out-of-corpus (LRA, POPIA…
    # not yet ingested) SHOULD be refused by the coverage gate — that is the
    # honest-corpus contract working, not a false refusal.
    answerable_in = [
        r
        for r in rows
        if not r["must_refuse"] and r["_expected_ids"] and not r["refused"]
    ]
    refusals = [r for r in rows if r["must_refuse"]]
    recalls = [r["recall"] for r in answerable_in if r["recall"] is not None]
    rrs = [r["rr"] for r in answerable_in]
    false_refusals = [
        r["id"]
        for r in rows
        if not r["must_refuse"]
        and r["refused"]
        and r["_expected_ids"]  # had in-corpus expectations and still refused
    ]
    ooc_refused = [
        r["id"]
        for r in rows
        if not r["must_refuse"] and r["refused"] and not r["_expected_ids"]
    ]
    false_answers = [r["id"] for r in refusals if not r["refused"]]
    out_of_corpus = [r["id"] for r in rows if r["out_of_corpus_refs"]]

    return {
        "n_total": len(rows),
        "n_answerable_in_corpus": len(answerable_in),
        "n_must_refuse": len(refusals),
        f"recall_at_{k}": round(statistics.mean(recalls), 3) if recalls else None,
        "mrr": round(statistics.mean(rrs), 3) if rrs else None,
        "refusal_accuracy": (
            round(1 - len(false_answers) / len(refusals), 3) if refusals else None
        ),
        "false_answers": false_answers,
        "false_refusals": false_refusals,
        # Out-of-corpus questions refused by the coverage gate: correct and tracked.
        "n_ooc_answerable_refused": len(ooc_refused),
        "ooc_answerable_refused_ids": ooc_refused,
        "n_out_of_corpus_skipped": len(out_of_corpus),
        "out_of_corpus_ids": out_of_corpus,
        "mean_coverage_answerable": round(
            statistics.mean(r["coverage"] for r in answerable_in), 3
        )
        if answerable_in
        else None,
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default="../eval/golden/za.json")
    ap.add_argument("--out", default="eval/retrieval_results.json")
    ap.add_argument("--k", type=int, default=10)
    args = ap.parse_args()

    golden_path = Path(args.golden)
    if not golden_path.exists():
        print(f"golden set not found: {golden_path}", file=sys.stderr)
        return 2
    items = json.loads(golden_path.read_text())

    from app.db.session import db_manager

    if db_manager._engine is None:
        db_manager.initialize()

    rows = []
    for item in items:
        if item.get("jurisdiction") != "za":
            continue
        rows.append(await eval_one(item, args.k))
        r = rows[-1]
        flag = "REFUSE" if r["must_refuse"] else f"recall={r['recall']}"
        print(
            f"{r['id']:8} {flag:14} cov={r['coverage']:.2f} n={r['n_excerpts']:2} "
            f"{'DEGRADED ' if r['degraded'] else ''}{r['total_ms']:>8}ms"
        )

    summary = summarize(rows, args.k)
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "golden": str(golden_path),
        "k": args.k,
        "summary": summary,
        "rows": rows,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=1))
    print(f"\n=== summary (k={args.k}) ===")
    print(json.dumps(summary, indent=1))
    print(f"results -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
