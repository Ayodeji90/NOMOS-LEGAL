# Week 10 — Flash rerank calibration + reranker decision (E2)

**Deliverable:** calibration note + reranker decision (plan W10 E2: "calibrate
Flash scorer; decide on bge-reranker"). Re-scoped: bge-reranker decision made
on ZA+NG evidence (W7/W8 non-ZA corpus weeks were reassigned per the locked
scope).

## Calibration evidence (measured, not assumed)

| Source | Measurement |
|---|---|
| Week 4 raw-call probes | Flash rerank calls measured **5.4–9.0s** under dev-tier Vertex quota; the original 8s watchdog killed healthy 9s calls → 2 false refusals |
| Week 4 fix | Watchdog 8s → **11s** + 1 retry → **0/30 degraded** on the golden set |
| Golden-set run (`eval/retrieval_results.json`, n=30) | Pipeline `total_ms` p50 **5.4s**, p90 **21.0s**, max 35.6s; **0 degraded reranks**; answerable in-corpus coverage **min 0.70 / mean 0.89**; refusal accuracy **1.0** |
| Week 3 latency harness | Retrieval-only (embed + both legs + fuse) **~550ms p50** — the entire excess over the 1.5s retrieval budget is the rerank network call |

**Quality calibration finding:** the Flash scorer's raw coverage numbers run
high (in-corpus mean 0.89, observed minimum 0.70). The 0.5 ZA threshold has
real headroom — it has never produced a false answer *or* an in-corpus false
refusal across 30 golden items + all Week 3/4 probes. No re-centering is
warranted; the threshold is the honest gate, not a quality knob to chase.

## Decision: keep Flash rerank; bge-reranker NOT adopted for the prototype

**Rationale:**

1. **The failure mode is quota-tier latency, not scorer quality.** Recall@10
   is 1.0, MRR 0.955, refusals 1.0, 0 degraded — the scorer is not the
   problem. Swapping rerankers does not touch the p95 offender (network LLM
   latency on a fresh-project quota), it only changes which model is slow.
2. **Self-hosting cost is real; the benefit is hypothetical.** bge-reranker
   means a GPU-bearing service (Cloud Run GPU or GKE), a new deployment,
   embedding-model sync between query and reranker input, and an ops surface —
   against a scorer that is currently 0-for-0 on errors and
   misrefusals on the golden set.
3. **The plan's own escape hatch stays open.** §3.4 pre-approves the
   bge-reranker spike *if latency/quality forces it*. Documented trigger:
   **if after provisioned Vertex throughput the rerank p95 still exceeds 1.5s,
   or false refusals/false answers appear on a doubled golden set, E2 opens
   the spike with E1 sign-off.** Until then: no.
4. **Interim latency mitigation (no new infra):** provisioned throughput on
   the Vertex endpoint (owner/cost conversation from Week 3), and E3's agent
   loop calling `retrieve_batch` + one merged rerank instead of N rerank
   calls.

## Frozen knobs this locks (feeding W11/W14)

- `rerank.timeout_seconds: 11.0`, `timeout_retries: 1` (measured p99)
- `rerank.min_keep: 8, max_keep: 12`, `candidate_pool: 50`
- `coverage_thresholds.za: 0.5` (never regressed; headroom confirmed)
- Prompt variant `v2-keep-definitional` (Week 4 recall fix)

Any change to the above requires an eval delta + E1 sign-off (Week 4 gate).
