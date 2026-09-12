# Week 4 — Retrieval threshold tuning note (E2)

**Deliverable:** threshold config + tuning note (per `IMPLEMENTATION_PLAN_15W_DETAILED.md`, Week 4 E2).
**Config:** `nomos-backend/app/data/retrieval_tuning.json` · **Runner:** `nomos-backend/scripts/run_retrieval_eval.py` · **Baseline results:** `nomos-backend/eval/retrieval_results.json`

## Method

Ran the 30-item ZA golden set (E5's `eval/golden/za.json`) through the real
pipeline (hybrid search → Flash rerank → coverage gate) and scored each item
against its expected sections (`"BCEA s20"` → `source_id + section_no` match),
plus the refusal contract for the 5 must-refuse items. Every knob change was
re-run through the same runner; deltas below are measured, not vibes.

**Corpus scoping:** the golden set targets 10 Acts; we hold BCEA + Companies
Act 71/2008. 14 answerable items target Acts not yet ingested (E4's lane).
The eval classifies these separately: refusing them is the **honest-corpus
contract working** (the coverage gate fires because the corpus genuinely
lacks the material) — they are tracked as `n_ooc_answerable_refused`, not as
false refusals. When E4 ingests more Acts, these graduate into the scored set
automatically via the config's `HELD_ACTS` map.

## Baseline → tuned deltas

| knob | before | after | why | measured delta |
|---|---|---|---|---|
| rerank system prompt | "prefer provisions that directly regulate" | + "keep definitional sections the question depends on" | za-018 (business rescue) failed: s128 (definitions) is required to apply s129 but the reranker judged it boilerplate and dropped it → recall 0.955 | recall@10 **0.955 → 1.0**, no other item regressed |
| rerank watchdog | 8s | 11s | raw Flash calls measured 5.4–9.0s under dev-tier quota; the 8s watchdog killed healthy 9s calls → spurious degradations → false refusals (za-019, za-001) | false refusals **2 → 0** across runs; degraded reranks **3/30 → 0/30** |
| timeout retries | 0 | 1 | tail spikes >8s are transient (observed ~15% of calls); one immediate retry absorbs them | stabilized the two deltas above |
| coverage threshold (za) | 0.35 (E5 default) | 0.5 | plan-specified Week 3 value; tuned-run data supports it: answerable in-corpus mean coverage **0.891**, observed minimum 0.7 — 0.5 keeps headroom above the floor while still refusing thin questions | refusal accuracy stays **1.0** (5/5 must-refuse refused; 14/14 out-of-corpus refused); zero false refusals at 0.5 |

Knobs evaluated and **left unchanged** (no eval delta from varying them):
`per_leg_k` 50 (already saturates both legs at 50/50), `rrf_k` 60,
`rrf_weights` 1.0/1.0, `max_output_tokens` 1024.

## Tuned baseline (the number every retrieval PR must now beat)

```
recall@10        1.000   (11/11 in-corpus answerable items)
mrr              0.955
refusal accuracy 1.000   (5/5 must-refuse)
false answers    0
false refusals   0       (in-corpus)
mean coverage    0.891   (answerable, in-corpus)
ooc refused      14/14   (out-of-corpus questions correctly refused)
degraded reranks 0/30
```

## Regression bars (CI eval-delta gate)

Enforced by `.github/workflows/retrieval-eval.yml` when a PR touches
retrieval code or the tuning config:

- `recall@10 >= 1.0` (hard)
- `mrr >= 0.9` (0.05 drift allowed pending golden-set growth)
- `refusal accuracy == 1.0`, `false answers == 0`, in-corpus `false refusals == 0` (hard)

## Known cost, on the record

The 11s watchdog + 1 retry raises the worst-case refusal latency (~2×11s +
overhead ≈ 24s before degradation) for questions the corpus can't answer.
That is the correct trade for the honesty contract (refuse, never answer
thin), and it only hits must-refuse/out-of-corpus traffic — answerable
in-corpus p50 is ~5.4s, dominated by the Flash call itself (dev-tier quota,
no provisioned throughput; see Week 3 latency harness).

## Follow-ups for the threshold owner (E5 joint, Week 5+)

1. Grow the golden set: 11 scored items is thin; bars tighten once ≥100.
2. When E4 lands LRA/POPIA/etc., re-baseline — the 14 out-of-corpus items
   enter scoring and the recall bar should stay at 1.0.
3. Entailment/citation metrics are E3's Week 4 lane; the runner emits
   `n_excerpts` + reranked order per item so their verifier eval can reuse it.
