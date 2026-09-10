# NOMOS v2 — 15-Week Per-Engineer Tasks + Weekly Deliverables
6 engineers full-time. Goal: working prototype. Single FastAPI app (Option B).
Roles frozen: E1 Platform lead, E2 Retrieval, E3 AI/LLM, E4 Corpus/ingestion, E5 Quality+integration, E6 App security.
Each week lists: goal, tasks per engineer, each engineer's deliverable (acceptance criteria), joint exit gate. Dependencies noted.

## W1 — Scaffold + contracts
Goal: repo builds, envs exist, contracts frozen, parsers started.
E1: GCP projects (preview/staging/prod), Cloud Run services, Cloud SQL+pgvector, Redis, Firestore, Secret Manager, Artifact Registry, CI (ruff/pytest/migration check), FastAPI skeleton /health, NOMOS_RETRIEVAL_V2 flags, asyncpg pool, Alembic init. Deliverable: staging /health 200, migration 001 applies clean, CI green on empty app.
E2: chunk DDL + indexes (HNSW, GIN tsvector), RRF helper + unit tests, synonym-dict loader interface (port za-focus.js as za dict v1). Deliverable: DDL merged, RRF unit test green, dict loader tested with BCEA/LRA/POPIA aliases.
E3: freeze JSON contracts (understanding output, writer I/O, verifier verdict), port ASK_SYSTEM + ZA addendum verbatim, Flash understanding stub behind flag log-only. Deliverable: contracts doc merged, stub returns valid JSON on 5 sample queries.
E4: GCS layout (raw/parsed/versions/manifests per juris) + manifest-check script, ZA + GB parser start (section regex + heading tree). Deliverable: layout in bucket, manifest script detects 1 missing smoke section on fixture.
E5: eval skeleton (pytest, golden JSON schema, metrics funcs) + 30 golden QAs (20 ZA/10 GB incl 5 must-refuse) + frontend contract test vs old workspace.js/taskpane.js shape. Deliverable: pytest runs, contract test asserts all 11 response keys.
E6: port auth (scrypt verify, timing-safe, nomos_session cookie, GIS verify), access gate (allowlist/waitlist), Redis limits skeleton, sanitize + injection + UNTRUSTED parity, CSP/CORS/SEO parity checklist from index.js. Deliverable: login/logout/allowlist tests green, parity checklist filed.
Gate: M0 prep. CI green, staging deploy ok. Depends on: E1 envs unblock E2/E4.

## W2 — State out + first ingest (M0)
Goal: sessions/limits survive revision; first ZA Acts embedded end-to-end.
E1: sessions (Firestore) + limits/quotas (Redis) cutover in staging, real Cloud Run first-hop IP, revision-survival test, 20 rps smoke. Deliverable: redeploy keeps sessions, spoofed XFF test fails to bypass.
E2+E4: ZA chunk->embed->upsert for BCEA + Companies Act 71/2008 (structure-aware chunker, headings embedded, text-embedding-005 batch). Deliverable: 2 Acts queryable in Postgres, chunk spot-check (10 sections correct parent context).
E3: understanding stub wired pre-retrieval log-only, writer still on old excerpts. Deliverable: traces show understanding JSON on every staging query.
E5: golden set to 40, manual eval run with recall@10/MRR/leakage printed. Deliverable: first eval report in repo.
E6: abuse suite (XFF spoof, replay, cross-instance quota), admin/access parity. Deliverable: abuse tests green.
Gate M0: staging /search via new auth/limits; tag proto-m0.

## W3 — ZA hybrid live in staging
Goal: full ZA on hybrid behind flag.
E1: shadow 10% prod ZA queries to staging (compare only). Deliverable: shadow diff log (latency + refusal delta).
E2: full ZA ingest, hybrid query (tsvector+pgvector RRF, hard jurisdiction+in-force filter), Flash rerank 50->8-12, coverage threshold 0.5. Deliverable: /search?juris=za returns hybrid excerpts, p95 retrieval+rerank < 1.5s staging.
E3: mismatch + named-Act gates log-only, writer on new excerpts. Deliverable: gate decisions logged, no user-visible change.
E4: ZA version diff + asAt stamping, amendment notes. Deliverable: every ZA excerpt carries asAt+version.
E5: ZA golden to 60, synonym tuning (stopwords, BCEA overtime s10 etc.). Deliverable: recall@10 reported, 5 fixed misses documented.
E6: per-query trace to Cloud Logging (timings/scores/verdicts, no bodies), quota 429 copy. Deliverable: trace viewable per request id.
Gate: ZA hybrid queryable in staging with traces.

## W4 — Verification lite + ZA canary (M1)
Goal: blocking realism checks, ZA canary in prod.
E1: canary 10% ZA to v2 with instant rollback flag, SLO watch. Deliverable: flag works, rollback < 5 min drilled.
E2: threshold tuning from eval deltas (every retrieval PR includes delta). Deliverable: threshold config file + tuning note.
E3: blocking citation-realism (every [n] resolves) + section-realism (regex refs vs metadata) + currency line + 1 repair retry; NLI log-only. Deliverable: invented-section fixture refused/repaired, currency line present on all answers.
E4: ingestion gate in CI for ZA (missing smoke section fails build). Deliverable: gate red on fixture, green on real.
E5: leakage + refusal tests blocking in CI, demo script v1 (5 answers + 2 refuses). Deliverable: CI red on leaked fixture, demo runs.
E6: load + session soak (50 rps staging, pool sizing). Deliverable: soak report, no pool exhaustion.
Gate M1: tag proto-m1-za. Leakage 0, citation 100% on golden.

## W5 — GB + US federal ingest
Goal: 3 jurisdictions on v2 path.
E1: ingestion as Cloud Run job (GCS trigger, retry, idempotent upsert). Deliverable: job runs ZA in < X min logged.
E2: GB + US synonym dicts + structural boosts, per-juris coverage thresholds draft. Deliverable: dicts merged, thresholds file.
E3: understanding live for za,gb,us (Flash JSON, cached normalized-query hash 24h jurisdiction-aware). Deliverable: cache hit rate logged, 5 expansions spot-checked.
E4: GB PGA parser full (1996-2024), US Code Title parser (2024 only), per-corpus gates. Deliverable: GB+US manifests pass gate.
E5: golden GB 60 + US 60 (each 10 must-refuse + 5 cross-juris traps e.g. BCEA on GB picker -> suggest ZA). Deliverable: traps refuse with suggestedJurisdiction.
E6: suggestedJurisdiction UX contract frozen with frontend (no UI break). Deliverable: contract test green.
Gate: 3 corpora queryable in staging.

## W6 — Honest jurisdiction + CI gates (M2)
Goal: no silent wrong-country answers; gates block regressions.
E1: promote gb,us canary -> 100% if green; cost snapshot #1. Deliverable: cost report (Vertex by role, DB, Redis).
E2: coverage check standardized per jurisdiction. Deliverable: coverage func + tests.
E3: mismatch + named-Act gates blocking (zero rows for named Act -> refuse naming it). Deliverable: 6 trap tests green.
E4: backfill audit asAt across 3 corpora. Deliverable: audit sheet, 0 null asAt.
E5: CI blocks on leakage>0 or refusal regression; recall informational. Deliverable: CI config merged, red-build demo.
E6: allowlist hygiene + API key rotation drill. Deliverable: drill log.
Gate M2: tag proto-m2-three-juris.

## W7 — Remaining countries CA/AU/IE/DE/NZ
Goal: 8-country coverage in staging.
E1: job parallelism + timing logs per corpus. Deliverable: ingest timings table.
E2: pair with E4 on parsers; DE multilingual check (embedding quality spike behind interface, no fork without E1 sign-off). Deliverable: DE quality note + decision.
E3: light support (thresholds per new juris). Deliverable: thresholds extended.
E4: 5 parsers (NZ first as template, then CA/AU/IE, DE last). Deliverable: 5 manifests pass gate.
E5: 40 golden each (top Acts + refuses). Deliverable: 200 new QAs merged.
E6: CSP/SEO/sitemap/robots parity audit. Deliverable: audit checklist signed.
Gate: all 8 queryable in staging.

## W8 — US states bulk (19 states)
Goal: all states ingested via unified path.
E1: build slimming (corpora out of image, DB source of truth, GCS raw), cold-start check. Deliverable: image size before/after + cold-start p95.
E2+E4: unified state parser replacing shard-cache reader; per-state meta validated. Deliverable: 19 states pass ingestion gate.
E3: state thresholds (shared default + overrides). Deliverable: config.
E5: 15 golden per state (10 answer + 5 refuse/trap = 285). Deliverable: set merged, full-matrix script runs.
E6: per-state burst soak. Deliverable: soak report.
Gate: 19 states queryable in staging.

## W9 — One retrieval path (M3)
Goal: delete per-country branches from hot path.
E1+E2: single retrieve(scope={jurisdiction,version,docType,tenantId}) for all; old readers flagged dead, kept for reference. Deliverable: hot-path grep shows no retrieve-za/au/etc import.
E3: coverage + writer wiring unchanged across juris. Deliverable: 3-juris spot check identical code path in trace.
E4: manifest re-verify all corpus_ids. Deliverable: all-green gate log.
E5: full-matrix eval + published gap list (what each corpus does NOT hold) for trust page. Deliverable: gaps doc merged.
E6: scope param reserved for tenant ACL (no enforcement yet, schema only). Deliverable: schema test.
Gate M3: tag proto-m3-all-juris.

## W10 — Verification full part 1 (NLI blocking)
Goal: entailment enforced.
E1: latency budget enforcement per step (understanding 300ms, retrieval+rerank 1.5s, writer 4s, verifier 1.5s). Deliverable: budget alerts in trace.
E2: rerank calibration (Flash scorer; bge decision from W7 data). Deliverable: calibration note + decision.
E3: NLI blocking (atomic claims vs excerpt: entailed/not_entailed/not_found; not_found -> gaps or delete+retry); controlling-provision demoted to suggestion + rules file for structural overrides. Deliverable: adversarial fixtures (blended-Act, invented-section) refused/repaired.
E4: effectiveFrom/To backfill audit. Deliverable: 0 nulls.
E5: faithfulness metrics in CI (citation 100%, invented 0, entailment tracked). Deliverable: CI metrics table.
E6: client-doc injection suite (UNTRUSTED + patterns). Deliverable: suite green.
Gate: NLI blocking live in staging.

## W11 — Currency + repealed handling (M4)
Goal: honest currency on every answer.
E1: p95 tuning to budgets on staging. Deliverable: p95 report per step.
E2: threshold freeze proposal. Deliverable: frozen config + eval delta.
E3: currency line final (as at max asAt + commencement caveat); repealed/pending marked + disclosed if cited. Deliverable: 3 fixture answers show correct lines.
E4: asAt audit sign-off. Deliverable: audit green.
E5: nightly full-pipeline run green; freeze thresholds (later changes need delta + E1 sign-off). Deliverable: nightly log.
E6: prompt/weight change control doc. Deliverable: process merged.
Gate M4: tag proto-m4-verified. Invented 0, entailment >= target.

## W12 — Agent loop (max 3 rounds)
Goal: bounded multi-round retrieval.
E1: timeouts/budgets (3 rounds, 12 excerpts max, 2 writer calls incl repair). Deliverable: budget tests (loop never exceeds).
E2: multi-query batch + dedupe + diagnostics interface (missing sub-question). Deliverable: batch API + tests.
E3: plan->retrieve->coverage->refine loop + compound decomposition (one retrieval per part, per-part cites, logged steps: searched N, found X, missing Y). Deliverable: 5 compound fixtures show 2-round gain in trace.
E4: support (no new corpora). Deliverable: idle/assist on loop testing.
E5: compound golden subset 30 (ZA/GB/US), agent vs single-pass comparison. Deliverable: coverage-gain report justifying latency.
E6: agent abuse caps (expansions/tokens per role). Deliverable: cap tests.
Gate: loop live in staging with step logs.

## W13 — Regs/case pilot + nightly (M5)
Goal: new doc types + reliable nightly signal.
E1+E6: nightly eval job + Scheduler + alerts + backup/PITR + rollback drills. Deliverable: 5-night green log, drill logs.
E2: doc-type filter + authority boosts (court levels). Deliverable: filter tests.
E3: writer/verifier handling for regs/cases (citation format, treatment disclosure). Deliverable: 5 pilot fixtures correct.
E4: pilot ingest (1 ZA reg set + 1 GB SI set + 10-20 judgments with headnotes, paragraph chunks, manual treatment file). Deliverable: pilot queryable, gaps still disclosed where corpus lacks.
E5: dashboard (log-based table ok) + regression alerts. Deliverable: dashboard link/screenshot path in repo.
Gate M5: tag proto-m5-agent.

## W14 — Hardening + frontend/Word
Goal: no regressions, cutover ready.
E1: cutover plan (per-juris flags, snapshot pinning, rollback), min-instance/autoscale tuning, rotation drill. Deliverable: runbook merged.
E2+E3: prompt + threshold freeze (changes need delta + E1 sign-off). Deliverable: freeze note.
E4: corpus freeze + signed manifest (corpus_snapshot_id in every trace). Deliverable: snapshot id + manifest.
E5+E6: full regression (public pages, workspace, login/enter/regions, go/ pages, admin/access, blog, sitemap/robots, manifest.xml, taskpane desktop+web), noindex + htmlAttr parity. Deliverable: regression sheet all-green.
Gate: cutover approved.

## W15 — Canary + handover (M6)
Goal: prototype live, measured, handed over.
E1: canary 10/50/100% per jurisdiction over 3 days, rollback on breach. Deliverable: rollout log.
E2+E3+E4: bugfix on canary, no new features. Deliverable: fix list with eval deltas.
E5: 7-day SLO report + eval trend + final demo (8 answers + 4 refuses incl traps/currency/gaps). Deliverable: demo script + report.
E6: access review (allowlist, keys, service accounts least-privilege) + incident runbook. Deliverable: review signed.
All: cost report (Vertex by role, embeddings, DB, Redis, Firestore, Storage, egress, logging) + scale risks + GA backlog. Deliverable: report + backlog filed.
Gate M6: tag proto-m6. Prototype accepted, GA scope locked.

Staffing totals: ~360 assigned person-days + ~90 buffer. If headcount drops to 5, cut DE pilot + NZ to lexical fallback; if 4, cut to ZA+GB+US for prototype and move M3 to GA. First blocker to resolve Monday W1: name reviewing lawyer (2h/week from W2) or W2 golden sets slip.
