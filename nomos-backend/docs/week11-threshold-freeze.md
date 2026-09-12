# Week 11 — Retrieval threshold freeze (E2) + Week 14 sign-off

**Deliverable (W11):** frozen config + eval delta. **Deliverable (W14):**
freeze note signed — no new tuning without delta + E1 sign-off.

## What is frozen

`app/data/retrieval_tuning.json` version **3.0-frozen** (`"frozen": true`):

| Knob | Frozen value |
|---|---|
| `per_leg_k` | 50 |
| `rrf_k` / weights | 60 / dense 1.0, lexical 1.0 |
| `tsquery_mode` | or_fallback (min lexeme 2, max 24) |
| `rerank.model` | gemini-2.5-flash, temp 0, 1024 tok |
| `rerank.timeout` | 11.0s × (1 + 1 retry) |
| `rerank.keep` | 8–12 from a 50-candidate pool |
| `coverage_thresholds` | za **0.5**, ng **0.4** (NG pre-tuned before NG go-live) |
| `boosts` | act 0.15 / section 0.10 / authority 0.05 (max level 10) |
| Prompt variant | v2-keep-definitional |

Also frozen by reference (see `docs/week10-rerank-calibration.md`): the
bge-reranker decision (not adopted; documented revisit triggers).

## Verification delta (frozen-config run)

Baseline (Week 4, tuning v2): recall@10 **1.0** · MRR **0.955** · refusal
**1.0** · 0 false answers · 0 in-corpus false refusals · 0 degraded ·
mean answerable coverage 0.891.

Frozen-config run (v3, full new path — structural boosts, standardized
coverage gate, scope path; `eval/frozen_thresholds_results.json`, n=30):

| Metric | Baseline v2 | Frozen v3 | Bar | |
|---|---|---|---|---|
| recall@10 | 1.0 | **1.0** | ≥ 1.0 | ✅ |
| MRR | 0.955 | **0.955** | ≥ 0.9 | ✅ |
| refusal accuracy | 1.0 | **1.0** | = 1.0 | ✅ |
| false answers | 0 | **0** | 0 | ✅ |
| in-corpus false refusals | 0 | **0** | 0 | ✅ |
| degraded reranks | 0 | **0** | — | ✅ |
| mean coverage (answerable) | 0.891 | **0.909** | — | +0.018 |

No regression from the W5–W13 additions; the +0.018 coverage lift is
consistent with structural boosts feeding the reranker a better-ordered
pool. NG positive/negative controls: in-corpus question answers (coverage
1.0), out-of-sample question honestly refuses at the 0.4 gate.

## Unfreeze process (from the freeze onward)

1. Open an issue with the hypothesis + golden-set evidence for the change.
2. PR updates `retrieval_tuning.json` (bump `version`, set `frozen: false`
   in the PR branch), includes **before/after eval deltas** on the full
   golden set, and passes the CI regression bars.
3. **E1 sign-off required** (plan W14). E5 review for metric integrity.
4. Re-freeze with a new dated version once the delta lands clean.

Signed (Week 14): E2 — retrieval thresholds frozen at v3.0-frozen; no
prototype-branch tuning changes without the process above.
