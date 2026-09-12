# Week 15 — E2 canary fix process + retrieval cost lines (M6)

**Deliverables:** fix list with eval deltas (canary period) + retrieval's
contribution to the cost report. Scope: ZA (+NG prep); all other
jurisdictions out of prototype scope per plan §0A.

## 1. Canary bugfix process (E2 retrieval)

During canary (10% → 50% → 100% ZA over 3 days, plan W15/E1), every
retrieval-touching fix follows the Week 4 gate — no exceptions during canary:

1. **Reproduce with a trace.** Pull the request's per-query trace
   (timings, per-leg hits, boosts explain, rerank model/ms, coverage
   decision). No fix without a traced repro or a golden-set repro.
2. **Classify before touching code.**
   - *Data* (stale version, wrong in_force, missing asAt) → E4 lane;
     E2 verifies the hard filters held and files the corpus fix.
   - *Retrieval* (missed recall, bad fusion, boost misorder) → E2 fix.
   - *Rerank/coverage* (bad selection, wrong refusal) → E2 fix with E3
     consult if the prompt is implicated.
3. **Any change ships with an eval delta**: rerun
   `scripts/run_retrieval_eval.py` locally; the PR shows before/after on
   recall@10, MRR, refusal accuracy, false answers/refusals, and the CI gate
   (`.github/workflows/retrieval-eval.yml`) enforces the regression bars
   (`retrieval_tuning.json` → `regression_bars`).
4. **Rollback beats hotfix.** If a fix cannot be tested inside one canary
   window, E1 flips the rollback flag first; the fix lands through CI after.
   A red metric at 50% rolls back to 10%; at 100% rolls back to v1 path for
   the affected jurisdiction.
5. **Fix list.** Each canary fix is recorded here with its delta:

| Date | Symptom (trace) | Fix | Eval delta |
|---|---|---|---|
| — | (none yet — canary not started) | — | — |

## 2. Retrieval cost lines (E2's input to the M6 cost report)

Per-query retrieval cost drivers (ZA, current dev-tier scale):

| Line | Driver | Current measured/expected | Scaling behavior |
|---|---|---|---|
| Query embedding | 1 × text-embedding-005 call per query (768-dim) | ~$0.00002/query; ~550ms p50 round trip incl. DB legs | Linear with query volume |
| Dense leg | HNSW KNN k=50 on Cloud SQL | Negligible CPU; ~10-30ms | Sub-linear to corpus size (index); watch HNSW memory at GA scale |
| Lexical leg | GIN tsquery k=50 | ~5-15ms | Corpus-size dependent; cheap |
| Rerank | 1 × Gemini 2.5 Flash generate (50 candidates → JSON) | **Dominant cost + latency**: ~5-9s/call dev-tier; ~$0.001-0.002/query | Linear with query volume; provisioned throughput trades $ for p95 |
| Batch/agent queries | E3 agent loop may issue up to 3 retrievals/round | Multiplies embedding + leg costs ×N | Bounded by loop budget (max 3 rounds) |
| Index build (one-off per snapshot) | HNSW build on 619 chunks (2 Acts) | Seconds + ephemeral CPU | Grows super-linearly with corpus; batch off-peak at GA |
| Re-embeds (one-off per corpus change) | text-embedding-005 per chunk | ~$0.0001/chunk at snapshot refresh | Linear with changed chunks, not whole corpus (version diffing) |

**Cost snapshot for the report:**
- Retrieval per-query compute ≈ embedding + 2 SQL legs + 1 rerank call.
- At 10k queries/mo the rerank line dominates (~$10-20) — **provisioned
  throughput is the single highest-leverage spend** for the SLO (p95 < 8s
  total; retrieval+rerank < 1.5s retrieval-side budget per plan W10/W11).
- Storage/vector memory: 619 × 768 floats ≈ 1.9MB of vectors (trivial);
  HNSW index fits comfortably in Cloud SQL `db-g1-small` shared buffer at
  prototype scale. GA-scale recheck at >100k chunks (plan §9: path to
  AlloyDB if the vector index exceeds comfort).

**Scale risks (for the GA backlog):**
1. Rerank latency/cost at volume without provisioned throughput.
2. HNSW memory pressure when the corpus multiplies (more Acts, regs pilot).
3. Embedding dimension freeze (768) is load-bearing across index, ORM, and
   cached vectors — changing it is a corpus-wide re-embed, not a config flip.
