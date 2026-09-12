# NOMOS v2 — 15-Week Per-Engineer Plan to Working Prototype
6 engineers, full-time. Single FastAPI app (Option B).
Static frontend + Word add-in unchanged. Response contract unchanged.

## Scope focus (locked)
Current target is South Africa only — willing ZA test users first, before any pivot. Nigeria is next after ZA is proven. GB, US federal, US states, CA, AU, IE, DE, NZ and all other listed countries/states are NOT in prototype scope and stay on the existing lexical path untouched. In the weekly breakdown below, read any non-ZA/NG corpus week as deferred to Phase 2: reassigned to ZA depth (more Acts, regulations pilot, golden-set volume, latency) and NG prep (source licensing, parser spike, manifest design) only.

## Engineer roles

E1 — Platform Lead / Backend Engineer
  Owns: FastAPI app, Cloud Run, Postgres, Redis, Firestore, CI/CD, flags, rollout, cost.
  Accountable for build order, gates, rollback.

E2 — Retrieval / Search Engineer
  Owns: chunk schema, pgvector + tsvector, RRF fusion, rerank interface, thresholds, latency.

E3 — AI / LLM Engineer
  Owns: query understanding, writer prompt, verifier (realism + NLI + currency), repair loop, agent loop.

E4 — Corpus / Ingestion Engineer
  Owns: parsers per jurisdiction, version diffing, ingestion job, GCS layout, manifests, gates.

E5 — Quality + Integration Engineer
  Owns: golden QA sets, eval harness, nightly job, frontend/Word compat, demo scripts.

E6 — App Security Engineer
  Owns: auth port, access gate, rate limits, CSP/CORS/SEO parity, secrets, abuse tests.

Capacity: 6 x 15 x 5 = 450 gross, ~360 assigned + ~90 buffer for bugfix/review/overrun.

---

## WEEK 1 — Scaffold + contracts

E1 — Platform Lead / Backend Engineer
  Tasks:
    1. Provision preview/staging/prod Cloud Run services.
    2. Provision Cloud SQL Postgres + pgvector, Redis, Firestore, Secret Manager, Artifact Registry.
    3. Scaffold FastAPI with /health, Pydantic Settings, asyncpg pool, Alembic init.
    4. Add NOMOS_RETRIEVAL_V2 per-jurisdiction flags.
    5. Set up CI (ruff, pytest, migration check).
  Deliverable: staging /health returns 200, migration 001 applies clean, CI green on empty app.

E2 — Retrieval / Search Engineer
  Tasks:
    1. Write chunk DDL + HNSW + GIN indexes.
    2. Implement RRF helper with unit tests.
    3. Build synonym-dict loader interface, port za-focus.js as za dict v1.
  Deliverable: DDL merged, RRF tests green, dict loader tested with BCEA/LRA/POPIA aliases.

E3 — AI / LLM Engineer
  Tasks:
    1. Freeze JSON contracts for understanding output, writer I/O, verifier verdict.
    2. Port ASK_SYSTEM + ZA addendum verbatim.
    3. Build Flash understanding stub behind flag (log-only).
  Deliverable: contracts doc merged, stub returns valid JSON on 5 sample queries.

E4 — Corpus / Ingestion Engineer
  Tasks:
    1. Create GCS layout: raw, parsed, versions, manifests per jurisdiction.
    2. Write manifest-check script.
    3. Start ZA + GB parsers (section regex + heading tree).
  Deliverable: layout live in bucket, script catches 1 missing smoke section on fixture.

E5 — Quality + Integration Engineer
  Tasks:
    1. Build eval skeleton (pytest, golden JSON schema, metric functions).
    2. Write first 30 golden QAs (20 ZA, 10 GB, incl 5 must-refuse).
    3. Write frontend contract test vs old workspace.js/taskpane.js shape.
  Deliverable: pytest runs, contract test asserts all 11 response keys.

E6 — App Security Engineer
  Tasks:
    1. Port auth (scrypt verify, timing-safe compare, nomos_session cookie, GIS verify).
    2. Port access gate (allowlist/waitlist).
    3. Port sanitize + injection rejection + UNTRUSTED wrapping.
    4. File CSP/CORS/SEO parity checklist from index.js.
  Deliverable: login/logout/allowlist tests green, checklist filed.

Joint gate: CI green, staging deploys. E1 envs unblock E2/E4.

---

## WEEK 2 — State out + first ingest (Milestone M0)

E1 — Platform Lead / Backend Engineer
  Tasks:
    1. Cut sessions to Firestore and limits/quotas to Redis in staging.
    2. Use real Cloud Run first-hop IP.
    3. Run revision-survival test + 20 rps smoke.
  Deliverable: redeploy keeps sessions, spoofed XFF cannot bypass limits.

E2 — Retrieval / Search Engineer
  Tasks:
    1. Pair with E4 to chunk, embed (text-embedding-005), and upsert BCEA + Companies Act 71/2008.
    2. Spot-check 10 sections for correct parent context.
  Deliverable: 2 Acts queryable in Postgres with headings embedded.

E3 — AI / LLM Engineer
  Tasks:
    1. Wire understanding stub pre-retrieval (log-only).
    2. Keep writer on old excerpts.
  Deliverable: every staging trace shows understanding JSON.

E4 — Corpus / Ingestion Engineer
  Tasks:
    1. Finish ZA chunker for the 2 pilot Acts.
    2. Snapshot ZA raw in GCS so hot path never hits live Laws.Africa quota.
  Deliverable: GCS snapshot + chunker tests green.

E5 — Quality + Integration Engineer
  Tasks:
    1. Expand golden set to 40.
    2. Run first manual eval (recall@10, MRR, leakage).
  Deliverable: first eval report committed in repo.

E6 — App Security Engineer
  Tasks:
    1. Write abuse suite (XFF spoof, replay, cross-instance quota).
    2. Verify admin/access endpoints parity.
  Deliverable: abuse tests green.

Joint gate M0: staging /search via new auth/limits. Tag proto-m0.

---

## WEEK 3 — ZA hybrid live in staging

E1 — Platform Lead / Backend Engineer
  Tasks:
    1. Shadow 10 percent of prod ZA queries to staging (compare only, no user impact).
  Deliverable: shadow diff log with latency + refusal delta.

E2 — Retrieval / Search Engineer
  Tasks:
    1. Ingest full ZA corpus.
    2. Ship hybrid query (tsvector + pgvector, RRF, hard jurisdiction + in-force filter).
    3. Ship Flash rerank 50 to 8-12, coverage threshold 0.5.
  Deliverable: juris=za returns hybrid excerpts, p95 retrieval+rerank under 1.5s staging.

E3 — AI / LLM Engineer
  Tasks:
    1. Wire writer to new excerpts.
    2. Keep mismatch + named-Act gates log-only.
  Deliverable: gate decisions visible in logs, no user-visible change.

E4 — Corpus / Ingestion Engineer
  Tasks:
    1. Ship ZA version diff + asAt stamping + amendment notes.
  Deliverable: every ZA excerpt carries asAt + version.

E5 — Quality + Integration Engineer
  Tasks:
    1. Grow ZA golden to 60.
    2. Tune synonyms (e.g. BCEA overtime s10).
  Deliverable: recall@10 reported with 5 fixed misses documented.

E6 — App Security Engineer
  Tasks:
    1. Ship per-query trace to Cloud Logging (timings, scores, verdicts, no bodies).
    2. Finalize quota 429 copy.
  Deliverable: trace viewable per request id.

Joint gate: ZA hybrid queryable in staging with traces.

---

## WEEK 4 — Verification lite + ZA canary (Milestone M1)

E1 — Platform Lead / Backend Engineer
  Tasks:
    1. Canary 10 percent ZA to v2 in prod with instant rollback flag.
    2. Watch SLOs (p95, 5xx, refusal shift).
  Deliverable: flag works, rollback under 5 min drilled.

E2 — Retrieval / Search Engineer
  Tasks:
    1. Tune thresholds from eval deltas.
    2. Require eval delta in every retrieval PR.
  Deliverable: threshold config file + tuning note.

E3 — AI / LLM Engineer
  Tasks:
    1. Ship blocking citation-realism (every [n] resolves).
    2. Ship section-realism (regex refs vs metadata).
    3. Add currency line + 1 repair retry. NLI stays log-only.
  Deliverable: invented-section fixture refused or repaired, currency line on all answers.

E4 — Corpus / Ingestion Engineer
  Tasks:
    1. Add ZA ingestion gate in CI (missing smoke section fails build).
  Deliverable: gate red on fixture, green on real corpus.

E5 — Quality + Integration Engineer
  Tasks:
    1. Make leakage + refusal tests blocking in CI.
    2. Write demo script v1 (5 answers + 2 refuses).
  Deliverable: CI fails on leaked fixture, demo runs end-to-end.

E6 — App Security Engineer
  Tasks:
    1. Run 50 rps staging soak, size connection pool.
  Deliverable: soak report, no pool exhaustion.

Joint gate M1: leakage 0, citation 100 percent on golden. Tag proto-m1-za.

---

## WEEK 5 — GB + US federal ingest

E1 — Platform Lead / Backend Engineer
  Tasks:
    1. Convert ingestion to Cloud Run job (GCS trigger, retry, idempotent upsert).
  Deliverable: job runtime per corpus logged.

E2 — Retrieval / Search Engineer
  Tasks:
    1. Build GB + US synonym dicts + structural boosts.
    2. Draft per-juris coverage thresholds.
  Deliverable: dicts merged, thresholds file extended.

E3 — AI / LLM Engineer
  Tasks:
    1. Turn understanding live for za, gb, us (Flash JSON, cached 24h by normalized query hash + jurisdiction).
  Deliverable: cache hit rate logged, 5 expansions spot-checked.

E4 — Corpus / Ingestion Engineer
  Tasks:
    1. Ship GB PGA parser full (1996-2024 scope).
    2. Ship US Code Title parser (2024 only).
  Deliverable: GB + US manifests pass gate.

E5 — Quality + Integration Engineer
  Tasks:
    1. Write GB 60 + US 60 golden (each 10 must-refuse + 5 cross-juris traps, e.g. BCEA on GB picker suggests ZA).
  Deliverable: traps refuse with suggestedJurisdiction.

E6 — App Security Engineer
  Tasks:
    1. Freeze suggestedJurisdiction UX contract with frontend.
  Deliverable: contract test green, no UI break.

Joint gate: 3 corpora queryable in staging.

---

## WEEK 6 — Honest jurisdiction + CI gates (Milestone M2)

E1 — Platform Lead / Backend Engineer
  Tasks:
    1. Promote gb, us canary to 100 percent if green.
    2. Publish cost snapshot 1 (Vertex by role, DB, Redis).
  Deliverable: cost report filed.

E2 — Retrieval / Search Engineer
  Tasks:
    1. Standardize coverage check per jurisdiction.
  Deliverable: coverage function + tests.

E3 — AI / LLM Engineer
  Tasks:
    1. Make mismatch + named-Act gates blocking (zero rows for named Act refuses naming it).
  Deliverable: 6 trap tests green.

E4 — Corpus / Ingestion Engineer
  Tasks:
    1. Backfill audit of asAt across 3 corpora.
  Deliverable: audit sheet, 0 null asAt.

E5 — Quality + Integration Engineer
  Tasks:
    1. Set CI to block on leakage above 0 or refusal regression. Recall stays informational.
  Deliverable: CI config merged, red-build demo recorded.

E6 — App Security Engineer
  Tasks:
    1. Run allowlist hygiene + API key rotation drill.
  Deliverable: drill log filed.

Joint gate M2: no silent wrong-country answers. Tag proto-m2-three-juris.

---

## WEEK 7 — Remaining countries CA, AU, IE, DE, NZ

E1 — Platform Lead / Backend Engineer
  Tasks:
    1. Parallelize ingestion job, log timing per corpus.
  Deliverable: ingest timings table.

E2 — Retrieval / Search Engineer
  Tasks:
    1. Pair with E4 on new parsers.
    2. Run DE multilingual embedding check behind interface (no fork without E1 sign-off).
  Deliverable: DE quality note + decision.

E3 — AI / LLM Engineer
  Tasks:
    1. Extend thresholds to new jurisdictions.
  Deliverable: thresholds file covers 8 countries.

E4 — Corpus / Ingestion Engineer
  Tasks:
    1. Ship 5 parsers (NZ first as template, then CA, AU, IE, DE last).
  Deliverable: 5 manifests pass gate.

E5 — Quality + Integration Engineer
  Tasks:
    1. Write 40 golden each for CA, AU, IE, DE, NZ.
  Deliverable: 200 new QAs merged.

E6 — App Security Engineer
  Tasks:
    1. Audit CSP, SEO, sitemap, robots parity for all public routes.
  Deliverable: audit checklist signed.

Joint gate: all 8 countries queryable in staging.

---

## WEEK 8 — US states bulk (19 states)

E1 — Platform Lead / Backend Engineer
  Tasks:
    1. Slim image (corpora out of image, DB is source of truth, GCS holds raw).
    2. Measure cold start before/after.
  Deliverable: image sizes + cold-start p95 recorded.

E2 — Retrieval / Search Engineer
  Tasks:
    1. Pair with E4 on unified state parser replacing shard-cache reader.
  Deliverable: unified parser tests green.

E3 — AI / LLM Engineer
  Tasks:
    1. Set state thresholds (shared default + overrides).
  Deliverable: state threshold config.

E4 — Corpus / Ingestion Engineer
  Tasks:
    1. Ingest 19 states (us-ak through us-wy), validate per-state meta.
  Deliverable: 19 states pass ingestion gate.

E5 — Quality + Integration Engineer
  Tasks:
    1. Write 15 golden per state (10 answer + 5 refuse/trap = 285 total).
    2. Run full-matrix script.
  Deliverable: set merged, matrix runs green.

E6 — App Security Engineer
  Tasks:
    1. Run per-state burst soak on limits.
  Deliverable: soak report.

Joint gate: 19 states queryable in staging.

---

## WEEK 9 — One retrieval path (Milestone M3)

E1 — Platform Lead / Backend Engineer
  Tasks:
    1. With E2, delete per-country reader branches from hot path (keep files flagged dead for reference).
  Deliverable: hot-path grep shows no retrieve-za/au imports.

E2 — Retrieval / Search Engineer
  Tasks:
    1. Ship single retrieve(scope) with jurisdiction, version, docType, tenantId.
  Deliverable: one code path serves all jurisdictions in traces.

E3 — AI / LLM Engineer
  Tasks:
    1. Verify coverage + writer wiring identical across jurisdictions.
  Deliverable: 3-jurisdiction spot check in traces.

E4 — Corpus / Ingestion Engineer
  Tasks:
    1. Re-verify every corpus_id manifest.
  Deliverable: all-green gate log.

E5 — Quality + Integration Engineer
  Tasks:
    1. Run full-matrix eval.
    2. Publish gap list (what each corpus does NOT hold) for trust page.
  Deliverable: gaps doc merged.

E6 — App Security Engineer
  Tasks:
    1. Reserve scope.tenantId in schema for future ACL (no enforcement yet).
  Deliverable: schema test green.

Joint gate M3: single path for all. Tag proto-m3-all-juris.

---

## WEEK 10 — Verification full part 1 (NLI blocking)

E1 — Platform Lead / Backend Engineer
  Tasks:
    1. Enforce per-step latency budgets (understanding 300ms, retrieval+rerank 1.5s, writer 4s, verifier 1.5s).
  Deliverable: budget alerts in traces.

E2 — Retrieval / Search Engineer
  Tasks:
    1. Calibrate Flash rerank scorer; decide on bge-reranker from W7 data.
  Deliverable: calibration note + decision.

E3 — AI / LLM Engineer
  Tasks:
    1. Promote NLI to blocking (atomic claims vs excerpt: entailed, not_entailed, not_found; not_found goes to gaps or delete + retry).
    2. Demote controlling-provision to suggestion + structural-override rules file.
  Deliverable: blended-Act and invented-section fixtures refused or repaired.

E4 — Corpus / Ingestion Engineer
  Tasks:
    1. Backfill audit of effectiveFrom and effectiveTo.
  Deliverable: 0 nulls.

E5 — Quality + Integration Engineer
  Tasks:
    1. Add faithfulness metrics to CI (citation 100 percent, invented 0, entailment tracked).
  Deliverable: CI metrics table green.

E6 — App Security Engineer
  Tasks:
    1. Ship client-doc injection suite (UNTRUSTED + patterns).
  Deliverable: suite green.

Joint gate: NLI blocking live in staging.

---

## WEEK 11 — Currency + repealed handling (Milestone M4)

E1 — Platform Lead / Backend Engineer
  Tasks:
    1. Tune p95 to budgets on staging.
  Deliverable: p95 report per step.

E2 — Retrieval / Search Engineer
  Tasks:
    1. Propose frozen thresholds.
  Deliverable: frozen config + eval delta.

E3 — AI / LLM Engineer
  Tasks:
    1. Finalize currency line (as at max asAt + commencement caveat).
    2. Handle repealed/pending (retrievable but marked, disclosed if cited).
  Deliverable: 3 fixtures show correct currency and status disclosure.

E4 — Corpus / Ingestion Engineer
  Tasks:
    1. Sign off asAt audit.
  Deliverable: audit green.

E5 — Quality + Integration Engineer
  Tasks:
    1. Run nightly full-pipeline green.
    2. Freeze thresholds (later changes need delta + E1 sign-off).
  Deliverable: nightly log + freeze note.

E6 — App Security Engineer
  Tasks:
    1. Write prompt and weight change-control process.
  Deliverable: process doc merged.

Joint gate M4: invented 0, entailment at target. Tag proto-m4-verified.

---

## WEEK 12 — Agent loop (max 3 rounds)

E1 — Platform Lead / Backend Engineer
  Tasks:
    1. Enforce loop budgets (3 rounds, 12 excerpts max, 2 writer calls incl repair).
  Deliverable: budget tests proving loop never exceeds.

E2 — Retrieval / Search Engineer
  Tasks:
    1. Ship multi-query batch + dedupe + missing-sub-question diagnostics interface.
  Deliverable: batch API + tests.

E3 — AI / LLM Engineer
  Tasks:
    1. Ship plan, retrieve, coverage, refine loop + compound decomposition (one retrieval per part, per-part cites, logged steps).
  Deliverable: 5 compound fixtures show 2-round gain in traces.

E4 — Corpus / Ingestion Engineer
  Tasks:
    1. Assist loop testing, no new corpora.
  Deliverable: test support + reviewed traces.

E5 — Quality + Integration Engineer
  Tasks:
    1. Build compound golden subset 30 (ZA/GB/US).
    2. Compare agent vs single-pass coverage gain vs latency.
  Deliverable: coverage-gain report justifying latency.

E6 — App Security Engineer
  Tasks:
    1. Cap expansions and tokens per role.
  Deliverable: cap tests green.

Joint gate: loop live in staging with step logs.

---

## WEEK 13 — Regulations and case pilot + nightly (Milestone M5)

E1 — Platform Lead / Backend Engineer
  Tasks:
    1. Schedule nightly eval job + alerts.
    2. Drill backup/PITR + rollback.
  Deliverable: 5-night green log + drill logs.

E2 — Retrieval / Search Engineer
  Tasks:
    1. Ship doc-type filter + court authority boosts.
  Deliverable: filter tests green.

E3 — AI / LLM Engineer
  Tasks:
    1. Handle regs and cases in writer/verifier (citation format, treatment disclosure).
  Deliverable: 5 pilot fixtures correct.

E4 — Corpus / Ingestion Engineer
  Tasks:
    1. Ingest pilot (1 ZA reg set + 1 GB SI set + 10-20 judgments with headnotes, paragraph chunks, manual treatment file).
  Deliverable: pilot queryable, gaps still disclosed where corpus lacks.

E5 — Quality + Integration Engineer
  Tasks:
    1. Build dashboard (log-based table acceptable) + regression alerts.
  Deliverable: dashboard path recorded in repo.

E6 — App Security Engineer
  Tasks:
    1. Review pool, replicas, backup access controls.
  Deliverable: review note filed.

Joint gate M5: agent + nightly green. Tag proto-m5-agent.

---

## WEEK 14 — Hardening + frontend and Word

E1 — Platform Lead / Backend Engineer
  Tasks:
    1. Write cutover plan (per-juris flags, snapshot pinning, rollback).
    2. Tune min-instance, autoscale, concurrency + rotation drill.
  Deliverable: runbook merged.

E2 — Retrieval / Search Engineer
  Tasks:
    1. Assist freeze (no new tuning without delta + E1 sign-off).
  Deliverable: freeze note signed.

E3 — AI / LLM Engineer
  Tasks:
    1. Freeze prompts with E2.
  Deliverable: freeze note signed.

E4 — Corpus / Ingestion Engineer
  Tasks:
    1. Freeze corpus + signed manifest with corpus_snapshot_id in every trace.
  Deliverable: snapshot id + manifest.

E5 — Quality + Integration Engineer
  Tasks:
    1. Full regression: public pages, workspace, login/enter/regions, go/ pages, admin/access, blog, sitemap/robots, manifest.xml, taskpane desktop + web.
  Deliverable: regression sheet all-green.

E6 — App Security Engineer
  Tasks:
    1. Verify noindex + htmlAttr parity with E5.
  Deliverable: parity checklist signed.

Joint gate: cutover approved.

---

## WEEK 15 — Canary + handover (Milestone M6)

E1 — Platform Lead / Backend Engineer
  Tasks:
    1. Canary 10/50/100 percent per jurisdiction over 3 days, rollback on breach.
  Deliverable: rollout log.

E2 — Retrieval / Search Engineer
  Tasks:
    1. Bugfix on canary only, each fix with eval delta.
  Deliverable: fix list with deltas.

E3 — AI / LLM Engineer
  Tasks:
    1. Bugfix on canary only.
  Deliverable: fix list with deltas.

E4 — Corpus / Ingestion Engineer
  Tasks:
    1. Bugfix on canary data issues only.
  Deliverable: fix list with deltas.

E5 — Quality + Integration Engineer
  Tasks:
    1. Publish 7-day SLO report + eval trend + final demo (8 answers + 4 refuses incl traps, currency, gaps).
  Deliverable: demo script + report.

E6 — App Security Engineer
  Tasks:
    1. Access review (allowlist, keys, service accounts least-privilege) + incident runbook.
  Deliverable: review signed + runbook merged.

All engineers:
  Tasks:
    1. Contribute to cost report (Vertex by role, embeddings, DB, Redis, Firestore, Storage, egress, logging) + scale risks + GA backlog.
  Deliverable: report + backlog filed.

Joint gate M6: prototype accepted, GA scope locked. Tag proto-m6.

---

## Staffing fallback

If headcount drops, protect ZA depth first: cut Nigeria prep, then regulations pilot, never cut eval gates or verification. Prototype stays ZA-only regardless of headcount; Nigeria never pulls ZA resources off its gates.
First blocker Monday W1: name reviewing lawyer (2 hours/week from W2) or W2 golden sets slip.
