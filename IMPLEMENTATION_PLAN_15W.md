# NOMOS v2 — 15-Week Implementation Plan to Working Prototype
6 engineers, full-time. Target: shippable prototype, not full GA.

Companion docs: REDESIGN.md, ARCHITECTURE.md, REDESIGN-PYTHON.md
Current stack: juris-backend-src (Node/Express, index.js ~2256 lines), per-jurisdiction lexical retrieval, Gemini writer, in-memory state.
Target stack: single FastAPI app (Option B) on Cloud Run + Postgres pgvector + Redis + Firestore + Vertex AI. Static frontend + Word add-in unchanged.

## 0A. Scope focus (locked)
Current target is South Africa only. We have willing test users in ZA waiting to use it before any pivot. Nigeria is next after ZA is proven. GB, US federal, US states (19), CA, AU, IE, DE, NZ and all other listed countries/states are explicitly NOT in prototype scope — they stay on the existing lexical path untouched, and any multi-jurisdiction weeks in older drafts of this plan are deferred to post-prototype (Phase 2). No engineer is assigned to non-ZA/NG corpora during the 15 weeks except to keep existing paths from regressing.

## 0. Definitions

Working prototype means:
  1. Web + Word add-in ask flow works against the v2 API with a compatible response contract (provider, answer, structured, sources, results, matchCount, grounded, jurisdiction, corpus_id, writer, suggestedJurisdiction, errors).
  2. South Africa served by one hybrid retrieval path. Nigeria corpus prep runs in parallel from W7 but goes live only after ZA prototype acceptance. All other jurisdictions stay on the existing lexical path untouched for the prototype.
  3. Refusal-first behavior preserved and measurable: wrong-jurisdiction leakage = 0 in eval, must-refuse questions refuse, every [n] resolves, every section ref exists in cited excerpt, currency line present.
  4. Point-in-time corpus: every excerpt carries version + asAt + inForce; answer states law as at max asAt.
  5. Eval harness runs in CI + nightly: recall@10, MRR, leakage rate, refusal correctness, citation validity, invented-section rate, entailment rate.
  6. Bounded agent loop (max 3 rounds) with sub-question decomposition + coverage check + one repair retry.
  7. State out of instance: sessions survive revision, rate limits enforceable under autoscale, quotas per authenticated identity.
  8. Deployable with rollback flag per jurisdiction, corpus snapshot id, per-query trace.

Out of scope for prototype (explicitly deferred to Phase 2/GA):
  GB, US federal, US states, CA, AU, IE, DE, NZ and every other non-ZA/NG jurisdiction (no re-chunk, no new parsers, no golden sets); full Nigeria launch (prep only); regulations/SIs beyond a ZA pilot set, full case-law corpus + citator (pilot only), matter-level ACLs / multi-tenant workspaces, self-hosted open-weight LLMs, multi-region + data residency, full billing/usage attribution.

## 1. Team (6 engineers)

  E1 Platform lead: FastAPI, Cloud Run, Postgres/AlloyDB, Redis, Firestore, CI/CD, observability, cost. Owns build order + flags + rollout.
  E2 Retrieval engineer: chunking, pgvector + tsvector, RRF fusion, rerank interface, thresholds, latency.
  E3 AI engineer: query understanding, writer prompt, verifier (realism + NLI + currency), repair loop, agent loop.
  E4 Corpus engineer: parsers per jurisdiction, version diffing, ingestion job, manifests, GCS layout.
  E5 Quality + integration engineer: golden QA sets, eval harness + nightly job, frontend/Word compat, demo scripts.
  E6 App security engineer: auth port (scrypt, sessions), access gate, rate limits, CSP/CORS/SEO parity, secrets, abuse tests.

No dedicated PM in this plan. E1 runs standup + cuts scope. Budget 0.5 day/week E1 for coordination (already in estimates).

Total capacity: 6 x 15 x 5 = 450 person-days gross. Net build assumes ~380 after meetings, review, bugfix buffer. Plan below uses ~360 assigned + ~90 buffer/contingency.

## 2. Milestones and gates

  M0 (end W2): skeleton API + state out of instance + chunk schema frozen + 30 golden QAs. Gate: staging /search answers ZA from old path through new auth/limits; sessions survive redeploy; chunker unit tests pass.
  M1 (end W4): ZA on hybrid retrieval in staging, verification lite blocking. Gate: ZA recall@10 reported, leakage 0, citation resolve 100 percent on golden set, canary flag exists.
  M2 (end W6): GB + US federal on hybrid, query understanding + jurisdiction gate live. Gate: cross-jurisdiction eval shows 0 leakage, named-Act honest refusal works, eval in CI blocking on leakage + refusal.
  M3 (end W9): all remaining countries + 19 US states ingested, one retrieval path for all. Gate: ingestion gate passes for every corpus_id, every jurisdictions.json smoke section present.
  M4 (end W11): verification full (NLI blocking) + currency + repair loop. Gate: invented-section rate 0, entailment pass rate target met, repair path tested.
  M5 (end W13): agent loop + eval nightly + pilot regulations/case law. Gate: multi-round retrieval improves coverage on compound-question subset, nightly job green 5 nights straight.
  M6 (end W15): prototype hardening, canary to production, demo + handover. Gate: SLOs met for 7 days (see section 7), rollback tested, cost snapshot signed off.

No milestone ships if its gate fails. Cut scope, never cut the gate.

## 3. Technical decisions frozen in W1 (no revisits without E1 sign-off)

  1. Single FastAPI app (Option B). Node kept only as static-file reference until cutover; no split-brain deploys.
  2. One database: Cloud SQL Postgres with pgvector (start) with path to AlloyDB if vector index exceeds comfort. pg_trgm + tsvector for sparse. HNSW for vectors. SQLAlchemy + asyncpg, Alembic from day one.
  3. Embedding: text-embedding-005 via Vertex AI through one embedder interface. No open-weights embedding in prototype.
  4. Rerank: Gemini Flash scoring batched (top-50 to top-10) behind a rerank interface. Open cross-encoder (bge-reranker) only if latency/quality forces it; needs E1 approval.
  5. Models per role via one llm.py: Flash for query understanding/rerank/NLI, Pro for writer, Claude fallback behind writer interface. Env-driven model names.
  6. Chunk = section or subsection, never across sections. Parent context prepended (Act + sectionNo + heading). Headings + short title embedded with text. Cases (pilot only) chunk per paragraph with headnote attached.
  7. Hard filters pre-fusion: jurisdiction + in-force version. Soft boosts post-fusion: act/section match, authority level, doc type.
  8. Sessions in Firestore, limits/quotas in Redis, users/keys hashed in Postgres. Real client IP = Cloud Run X-Forwarded-For first hop. Never trust client headers.
  9. Verification is blocking in the hot path (except NLI log-only until M4). One repair retry max. Still failing goes to refuse.
  10. Logging: per-query trace (timings, scores, verdicts, refusal reasons) always; full prompts/answers sampled only. Never log document bodies.

## 4. Week-by-week build

### W1 — Scaffold + contracts (all hands)
  E1: GCP projects/envs, Cloud Run service, Cloud SQL + pgvector, Redis, Firestore, Secret Manager, Artifact Registry, preview + staging + prod services, NOMOS_RETRIEVAL_V2 per-jurisdiction flags, /health + /search compat skeleton, asyncpg pool, Alembic init, CI (ruff, pytest, migration check).
  E2: chunk schema + SQL DDL + indexes (HNSW, GIN tsvector), RRF helper, synonym-dict loader interface (port za-focus.js as first dict).
  E3: freeze JSON contracts: query-understanding output, writer input/output (insufficientContext, directAnswer, explanation, gaps, followUps), verifier verdict; port ASK_SYSTEM wording + ZA addendum.
  E4: GCS layout (raw/, parsed/, versions/, manifests/), per-jurisdiction parser interface, ZA + GB parser start, manifest-check script.
  E5: eval harness skeleton (pytest, golden JSON schema, metrics: recall@10, MRR, leakage, refusal correctness, citation validity), first 30 golden QAs (20 ZA, 10 GB, incl. 5 must-refuse), frontend contract test (old workspace.js + taskpane.js against new /search shape).
  E6: port auth (scrypt verify, timing-safe compare, nomos_session cookie, Google GIS verify), access gate (allowlist/waitlist), Redis rate limits, sanitize + injection rejection + UNTRUSTED wrapping parity, CSP/CORS/SEO parity checklist from index.js.
  Exit: M0 prep. Daily E1/E4 sync on parser vs chunker interface.

### W2 — State out + first ingest (M0)
  E1: sessions/quota/limits cutover in staging, revision-survival test, load smoke (20 rps).
  E2+E4: ZA chunk + embed batch (first 2 Acts end-to-end: BCEA + Companies Act 71 of 2008) to prove pipeline chunk to upsert to query.
  E3: query-understanding stub (rules + Flash call) behind flag, log-only.
  E5: golden set to 40, eval runs manually, frontend compat green.
  E6: abuse tests (spoofed XFF, session replay, quota bypass across instances), admin/access endpoints parity.
  Gate M0. Tag: proto-m0.

### W3 — ZA hybrid live in staging
  E2: full ZA ingest, hybrid query (tsvector + pgvector, RRF, hard jurisdiction/in-force filter), Flash rerank top-50 to 8-12, coverage threshold 0.5 initial.
  E3: jurisdiction-mismatch + named-Act gates log-only, writer wired to new excerpts.
  E4: version diffing (previous vs new ZA snapshot, amendment notes), asAt stamping.
  E5: ZA golden to 60, report recall@10/MRR/leakage, tune stopwords/synonyms.
  E6: per-query trace logging to Cloud Logging, quota UX (429 copy + headers).
  E1: shadow traffic ZA (duplicate 10 percent prod queries to staging, compare, no user impact).

### W4 — Verification lite + ZA canary (M1)
  E3: blocking citation-realism + section-realism + currency line + one repair retry; NLI runs log-only.
  E2: threshold tuning from eval deltas (every retrieval PR includes eval delta).
  E5: refusal + leakage tests blocking in CI; canary checklist; demo script v1 (5 answers + 2 refuses).
  E1+E6: canary 10 percent ZA to v2 in prod with instant rollback; SLO watch (p95 latency, 5xx, refusal rate shift).
  Gate M1. Tag: proto-m1-za.

### W5 — GB + US federal
  E4: GB PGA parser full (1996-2024 scope), US Code Title parser (2024 titles only), ingestion gates per corpus_id.
  E2: per-jurisdiction synonym dicts (GB, US), structural boosts per doc type.
  E3: query understanding live for za,gb,us (Flash JSON, cached by normalized query hash, TTL 24h, jurisdiction-aware key).
  E5: golden sets GB 60, US 60 (each incl. 10 must-refuse + 5 cross-jurisdiction traps, e.g. BCEA asked on GB picker must suggest ZA).
  E6: suggestedJurisdiction UX contract frozen with frontend.

### W6 — Honest jurisdiction + CI gates (M2)
  E3: mismatch + named-Act gates blocking (no silent wrong-country answers, no silent cross-Act keeps).
  E5: CI now blocks on leakage > 0 or refusal-correctness regression; recall informational.
  E1: promote gb,us to canary then 100 percent if green; cost snapshot #1 (Vertex calls by role, DB size, Redis tier).
  Gate M2. Tag: proto-m2-three-juris.

### W7 — Remaining countries (CA, AU, IE, DE, NZ)
  E4: five parsers in parallel with E2 pairing (CA/AU/IE share common-law structure; DE needs separate section regex + multilingual embedding check; NZ smallest, first to prove template).
  E2: multilingual retrieval check on DE (if text-embedding-005 underperforms on DE queries, spike alternative behind embedder interface, no hot-path fork without E1 approval).
  E5: 40 golden QAs each for CA/AU/IE/DE/NZ (leaner than ZA/GB/US, focused on top Acts + refuses).
  E6: CSP/SEO/sitemap/robots parity audit for all public routes carried over.
  E1: ingestion as Cloud Run job (GCS trigger), retry + idempotent upsert, per-corpus timing logs.

### W8 — US states bulk ingest
  E4+E2: 19 state corpora (us-ak through us-wy) through unified parser; per_code shard handling replaces bespoke retrieve-us-state.js shard cache; meta.json per state validated (counts vs manifest).
  E5: 15 golden QAs per state (285 total, lean: 10 answer + 5 refuse/trap each); ingestion gate per state (missing smoke section fails build).
  E1: image/build slimming (corpora no longer shipped in image; DB is source of truth; GCS holds raw); cold-start check.
  E6: quota/limits per-state soak (burst test per corpus_id).

### W9 — One retrieval path for all (M3)
  E1+E2: delete per-country reader branches from hot path (keep files for reference, flagged dead); single retrieve() with scope param (jurisdiction, version, doc type) for future ACL use.
  E3: coverage check standardized (on-point threshold per jurisdiction from eval, not global vibe).
  E5: full-matrix eval run (all jurisdictions), leakage + refusal gates green; publish coverage-gap list (what each corpus does NOT hold) for trust page.
  Gate M3. Tag: proto-m3-all-juris.

### W10 — Verification full part 1
  E3: NLI entailment promoted to blocking (atomic claims vs cited excerpt: entailed/not_entailed/not_found; not_found goes to gaps or delete + retry); controlling-provision language demoted to suggestion with verify-before-relying caveat unless structural rule (Constitution override etc. from small reviewable rules file).
  E2: rerank quality pass (Flash scorer calibration; decision on bge-reranker spike from W7 data).
  E5: faithfulness metrics in CI (citation validity, invented-section rate must be 0, entailment rate tracked); golden adversarial cases (invented-section traps, blended-Act traps).
  E4: asAt/effectiveFrom/effectiveTo backfill audit across all corpora.
  E6: client-document injection suite (UNTRUSTED wrapping + rejection patterns, no behavior change without test).

### W11 — Verification full part 2 + currency (M4)
  E3: currency disclosure final (law stated as at max asAt + commencement caveat), repealed/pending-section handling (retrievable but marked, writer must disclose if cited).
  E5: full pipeline nightly run green; threshold freeze for prototype (any later change needs eval delta).
  E1: latency pass (p95 budget per step: understanding ~300ms, retrieval + rerank < 1.5s, writer < 4s, verifier < 1.5s; total p95 < 8s on staging).
  Gate M4. Tag: proto-m4-verified.

### W12 — Agent loop
  E3: bounded loop (plan to max 3 rounds: retrieve to coverage_ok else diagnose missing sub-question, new queries, continue; compound questions decompose to one retrieval per part, merge with per-part cites); per-round steps logged for UI (searched N variants, found basis for X, still missing Y).
  E2: support multi-query retrieval batching + dedupe; coverage diagnostics interface.
  E5: compound-question golden subset (30 across ZA/GB/US), agent-vs-single-pass comparison (coverage gain must justify latency).
  E1: timeouts + budgets enforced (max 3 rounds, max 12 excerpts to writer, max 2 writer calls incl. repair).
  E6: agent abuse caps (max expansions per request, max tokens per role).

### W13 — Regulations/case pilot + nightly eval (M5)
  E4: pilot ingest (1 ZA regulation set + 1 GB SI set + 10-20 landmark judgments with headnotes, paragraph chunks, court/authorityLevel/treatment manual file); distinct doc-type filters; judgments-off-licence gaps still disclosed where corpus lacks them.
  E5: nightly Cloud Run eval job + Scheduler, regression alerts, dashboard (even a simple log-based table is fine for prototype).
  E1+E6: read-replica / connection-pool review, backup + PITR drill, rollback drill.
  Gate M5. Tag: proto-m5-agent.

### W14 — Hardening + Word + web
  E5+E6: full frontend regression (public pages, workspace, login/enter/regions, go/ region pages, admin/access, blog, sitemap, robots, manifest.xml, taskpane on Word desktop + web), no-HTML-injection audit (htmlAttr parity), noindex rules parity (app/login/enter/regions/go/request-access/admin/word-addin).
  E1: production cutover plan (flag per jurisdiction, corpus snapshot pinning, instant rollback), min-instance + autoscale + concurrency tuning, Secret Manager rotation drill.
  E2+E3: final threshold + prompt freeze; prompt + weight changes require eval delta + E1 sign-off.
  E4: corpus freeze for prototype + signed manifest (corpus_snapshot_id recorded in every trace).

### W15 — Canary, SLOs, handover (M6)
  All: 10 percent to 50 percent to 100 percent per jurisdiction over 3 days, rollback on any gate breach.
  E5: 7-day SLO report + eval trend + demo script final (8 answers + 4 refuses incl. cross-jurisdiction traps + currency + gaps).
  E1: cost report (Vertex by role, embeddings batch, DB, Redis, Firestore, Storage, egress, logging) + scale risks + GA backlog.
  E6: access review (allowlist hygiene, admin keys, service accounts least-privilege), incident runbook (retrieval down, Vertex quota, Laws.Africa fallback if still used as source, DB failover).
  Gate M6. Tag: proto-m6. Decision: prototype accepted, GA scope locked.

## 5. Staffing by week (X = full week, x = half week)

  W1:  E1 X, E2 X, E3 X, E4 X, E5 X, E6 X (scaffold)
  W2:  E1 X, E2 X, E3 x, E4 X, E5 X, E6 X (M0)
  W3:  E1 x, E2 X, E3 X, E4 X, E5 X, E6 x (ZA hybrid)
  W4:  E1 X, E2 X, E3 X, E4 x, E5 X, E6 X (M1 canary)
  W5:  E1 x, E2 X, E3 X, E4 X, E5 X, E6 x (GB+US)
  W6:  E1 X, E2 x, E3 X, E4 x, E5 X, E6 X (M2 gates)
  W7:  E1 X, E2 X, E3 x, E4 X, E5 X, E6 x (5 countries)
  W8:  E1 x, E2 X, E3 x, E4 X, E5 X, E6 x (US states)
  W9:  E1 X, E2 X, E3 X, E4 X, E5 X, E6 x (M3 unify)
  W10: E1 x, E2 X, E3 X, E4 X, E5 X, E6 X (NLI blocking)
  W11: E1 X, E2 x, E3 X, E4 X, E5 X, E6 x (M4 currency)
  W12: E1 X, E2 X, E3 X, E4 x, E5 X, E6 X (agent)
  W13: E1 X, E2 x, E3 X, E4 X, E5 X, E6 x (M5 pilot+nightly)
  W14: E1 X, E2 x, E3 x, E4 x, E5 X, E6 X (hardening)
  W15: E1 X, E2 x, E3 x, E4 x, E5 X, E6 X (M6 ship)

  Person-days assigned: ~360. Unassigned buffer: ~90 for bugfix, review, lawyer QA time, overruns. If headcount drops to 5, cut DE pilot + NZ to lexical fallback and keep gates; if drops to 4, cut to ZA+GB+US only for prototype and move M3 to GA.

## 6. Deliverables per milestone (acceptance criteria)

  M0: FastAPI staging answers ZA via old path through new auth/limits; sessions survive revision; chunker unit tests green; 40 golden QAs in repo; CI runs ruff + pytest.
  M1: ZA hybrid in staging behind flag; recall@10 + MRR reported; leakage 0; citation-resolve 100 percent; section-realism blocking; currency line present; 10 percent canary flag exists with rollback.
  M2: za,gb,us on v2; mismatch + named-Act gates blocking; CI blocks on leakage/refusal; cost snapshot #1 published.
  M3: every corpus_id ingested via pipeline; single retrieve() in hot path; ingestion gate green for all; full-matrix eval published with gap list.
  M4: NLI blocking with repair-then-refuse; invented-section 0; entailment tracked; p95 budgets met on staging.
  M5: agent loop max 3 rounds live; compound subset shows coverage gain; nightly eval green 5 nights; pilot regs/cases queryable with doc-type filter.
  M6: production canary 10/50/100 clean; 7-day SLOs met; corpus snapshot pinned; runbook + cost report + GA backlog signed.

## 7. Prototype SLOs (M6 gate)

  Availability 99.5 percent (staging) / 99.9 percent target prod path; p95 /search < 8s, p50 < 4s; 5xx < 0.5 percent.
  Quality: leakage 0, must-refuse correctness 100 percent, citation validity 100 percent, invented-section 0, entailment pass >= 95 percent on golden set, recall@10 ZA >= 0.85 / GB >= 0.8 / others reported (no fake bar).
  Ops: rollback < 5 min via flag; PITR tested; revision redeploy keeps sessions/limits.

## 8. Risks + mitigations

  1. Per-jurisdiction parsers explode (especially US states + DE). Mitigation: E4+E2 pairing, template-first (NZ proves template), time-box DE multilingual spike in W7, fallback to lexical for a jurisdiction rather than slip M3.
  2. Embedding/re-embed cost + HNSW build time on 19 states. Mitigation: batch jobs off-peak, HNSW build once per snapshot, snapshot pinning, cost snapshot at M2/M6.
  3. Golden QA quality bottlenecks on lawyer time. Mitigation: E5 drafts, single reviewing lawyer 2h/week from W2, adversarial traps prioritized over volume, 40-per-country minimums for non-core jurisdictions.
  4. Flash rerank/NLI quality insufficient. Mitigation: interfaces swappable, bge-reranker spike pre-approved as experiment, thresholds per jurisdiction, NLI log-only until proven.
  5. Laws.Africa dependency/quota for ZA raw. Mitigation: snapshot + cache raw in GCS in W2, pipeline never hits live API in hot path after M1.
  6. Scope creep (regs/case law/ACLs). Mitigation: pilot-only rule, scope param reserved in schema, GA backlog owned by E1.

## 9. Cost lines to track (beyond LLM tokens)

  Vertex generate-content by role (writer dominates), embeddings batch + re-embeds, Cloud SQL (instance + storage + vector index memory), Redis tier, Firestore sessions, GCS storage + ops, egress (answers + docs), Cloud Logging ingestion, Artifact Registry + CI runners, GPU only if reranker self-hosted (avoid in prototype).

## 10. Week 1 ticket list (start Monday)

  E1-01 FastAPI skeleton + compat /search schema + flags; E1-02 GCP envs + secrets + CI.
  E2-01 chunk DDL + RRF + dict loader; E2-02 ZA/GB chunker tests.
  E3-01 contract freeze doc + ASK_SYSTEM port; E3-02 understanding stub.
  E4-01 GCS layout + manifest script; E4-02 ZA+GB parser start.
  E5-01 eval skeleton + 30 QAs; E5-02 frontend contract test.
  E6-01 auth/access port; E6-02 limits + trace + parity checklist.

First standup question: who owns the reviewing-lawyer slot for golden sets. Without that name, W2 slips.
