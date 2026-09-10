# NOMOS v2 — Implementation Plan (Python, GCP)

Goal: get a **working, lawyer-facing product** out of this rebuild, not a research repo.
The target is a real answer pipeline you can put in front of users: hybrid retrieval, honest jurisdiction handling, structured grounded answers, verification that refuses when it should, and enough operations to run it safely on GCP.

This plan assumes the **Python backend approach in REDESIGN-PYTHON.md** and the **architecture in REDESIGN.md + ARCHITECTURE.md**.

---

## 1. What “working product” means here

A working v2 is **not** every nice-to-have in the design. It is the smallest system that can:

1. Authenticate users and gate the API honestly.
2. Take a legal question, understand it, and refuse when the jurisdiction/Act is wrong or not held.
3. Retrieve real law through hybrid search, not keyword-only matching.
4. Write a structured grounded answer from retrieved excerpts only.
5. Verify that answer before returning it, and refuse when verification fails.
6. Return the answer plus enough trace to debug and improve it.
7. Run on GCP without per-instance in-memory state and without spoofable rate limits.
8. Be testable from the start, because legal correctness must be measured, not hoped for.

Everything else — full agent loop, regulations, case law, multi-round research, fancy UI polish — is **phase 6 or later**, not the thing that makes v2 usable.

---

## 2. Big picture shape of the build

Two reasonable deployment shapes:

- **Option A — keep the existing frontend shell, replace the backend.**  
  Frontend/Word add-in/static site stay where they are; the Node backend is replaced by a Python FastAPI backend that serves the same product API. This is the fastest path to a working product if the current frontend and Word add-in are worth keeping.

- **Option B — Python end to end for the product backend.**  
  Same as A, but you also move the public-site serving, auth gate, and SEO routes into FastAPI instead of keeping any Express code. Cleaner long term, slightly more front-loaded work.

For a rebuild aimed at a working product soon, **start with Option A and treat Option B as a later simplification**. Do not let a full frontend question block the backend work. The important rebuild is the AI/RAG spine.

---

## 3. Workstreams

There are five workstreams, not one linear path:

1. **Platform and data foundation.** GCP project shape, managed Postgres with pgvector, Redis, Firestore or Postgres sessions, Secrets Manager, networking, CI, container build, local dev story.
2. **Corpus and retrieval.** Versioned source model, structure-aware chunking, embeddings, hybrid search, reranking, the query understanding layer, honest jurisdiction/Act handling.
3. **Answering and verification.** Writer, grounding checks, citation realism, section realism, entailment, currency disclosure, repair loop, refusal paths.
4. **Product API and integration.** Search, draft, review endpoints, Word add-in contract, existing frontend compatibility, error and refusal shapes, observability.
5. **Quality and operations.** Tests, golden QA sets, eval harness, ingestion pipeline, deploy pipeline, cost and logging discipline.

A working product can ship before the agent loop and before case law. It cannot ship before retrieval, verification, auth, and a tested API contract.

---

## 4. Phase plan with dependencies and estimates

Estimates are **calendar-day ranges for a small competent team**, not promises. They assume focused work, existing GCP project access, and the design already decided. Where hands are listed, one “hand” is one reasonably experienced engineer working full time on this. If the team has stronger infra or stronger ML people, shift effort between phases but not the order.

### Phase 0 — Scope lock and starting state (1–3 days, 1 hand)

Do this before code.

**Tasks:**
- Decide Option A vs Option B for now and write it down.
- Decide jurisdiction start set for v2. Recommended: **one deep jurisdiction first**, likely South Africa, plus one or two others only if the corpus is ready. Trying to launch many jurisdictions in phase 1 is the fastest way to ship a shallow product.
- Decide the v2 corpus currency model: versioned, in-force filtering, as-at stamps. Confirm where the source texts will come from and what is legal to use.
- Freeze the v2 API response shape for search/draft/review/refuse, including the trace fields.
- List the existing frontend and Word add-in endpoints the new backend must satisfy.
- Write the non-functional requirements: latency targets, refusal correctness, logging boundaries, cost guardrails.

**Output:**
- A one-page scope note plus the frozen API contract and jurisdiction set.

**Dependency:** none.  
**Everything else depends on this.**

---

### Phase 1 — Platform, data, and local dev (5–10 days, 1–2 hands)

This is the unglamorous phase that determines whether the rest moves fast or stalls.

**Tasks:**
- Stand up the GCP pieces needed for dev and early prod:
  - Cloud SQL or AlloyDB PostgreSQL with pgvector
  - Memorystore Redis
  - Firestore or decide Postgres sessions
  - Secret Manager
  - Cloud Storage buckets for sources, ingestion artifacts, eval data
  - Cloud Run service account shape and least-privilege plan
- Build the local dev story:
  - Docker Compose or equivalent for Postgres + pgvector + Redis + optional Firestore emulator
  - `.env` + Pydantic Settings shape
  - connection pooling and async DB driver chosen
  - migrations tool chosen and initialized (Alembic)
- Put CI in place early:
  - lint/format (ruff)
  - tests (pytest + pytest-asyncio)
  - container build check
  - basic security checks (no secrets in repo, no world-open DB)
- Define the shared library layout:
  - config, db, redis, auth,llm, retrieve, reranking, grounding, models, eval, ingestion

**Output:**
- A developer can spin up the stack locally, run tests, and deploy a hello-world FastAPI service to Cloud Run with real config from Secret Manager.

**Dependency:** Phase 0.  
**Phase 2–5 depend on this.**

---

### Phase 2 — Auth, sessions, rate limits, and API skeleton (4–8 days, 1–2 hands)

This makes the system operable and honest before it is smart.

**Tasks:**
- Auth and users:
  - password hashing with scrypt, timing-safe compare
  - API keys hashed in Postgres
  - invite-only or gated access flow as required
  - session storage in Firestore or Postgres
- Shared limits:
  - per-IP, per-session, per-user rate limits in Redis
  - use Cloud Run real client IP via `X-Forwarded-For` first hop
  - writer/daily and per-endpoint quotas if you want them now
- FastAPI product skeleton:
  - health, readiness, liveness
  - auth-gated routes for search, draft, review, improve as applicable
  - refusal and error response shapes
  - request validation with Pydantic
- Basic observability:
  - request logs with minimal necessary metadata
  - per-request trace id
  - no full prompt logging by default

**Output:**
- A gated API that can authenticate, limit, and refuse safely, even before it can answer legal questions well.

**Dependency:** Phase 1.  
**Phase 3–4 depend on this.**

---

### Phase 3 — Corpus model and ingestion for the lead jurisdiction(s) (8–15 days, 1–2 hands, plus legal/source work that is not pure engineering)

This is where the product gets real law in it. The engineering is one part; the source work is often the long pole.

**Tasks:**
- Define the versioned source model:
  - sources, versions, in-force flags, as-at stamps, repealed/pending status
  - chunk model: jurisdiction, source, version, act, section/subsection, heading, text, embedding, tokens, in-force, effective dates
- Build structure-aware chunking for the lead jurisdiction(s):
  - parse and normalize source HTML/text
  - detect section tree, headings, provisos, defined terms
  - chunk by section/subsection, not fixed windows
  - embed headings/short titles with text
- Build the embedding and upsert path:
  - batch embed with `text-embedding-005` through the Google SDK
  - upsert chunks and create pgvector index
  - tsvector / full-text setup for sparse search
- Build the ingestion job:
  - Cloud Run job or scheduled job
  - re-ingest path that can replace corpus safely
  - manifest/smoke check so a bad corpus cannot silently go live
- Put one or two lead jurisdictions into the system with real coverage, even if thin.

**Output:**
- A pipeline that can take source law, version it, chunk it, embed it, and make it retrievable through hybrid search.

**Dependency:** Phase 1–2.  
**Phase 4 depends on this.**  
**Independent of Phase 5.**

---

### Phase 4 — Hybrid retrieval, query understanding, and honest jurisdiction handling (7–12 days, 1–2 hands)

This is the core intelligence of the product.

**Tasks:**
- Hybrid retrieval:
  - sparse search via Postgres full text / tsvector with legal synonym expansion
  - dense search via pgvector
  - reciprocal rank fusion over the two ranked lists
  - metadata filtering: jurisdiction, in-force, version, doc type, authority level where applicable
  - hard filters before fusion so wrong jurisdiction never enters results
- Query understanding:
  - Gemini Flash structured output for jurisdiction confirmation, question type, expanded queries, named Acts, intent category
  - cache by query hash where appropriate
- Jurisdiction mismatch handling:
  - picker vs query mismatch detected before retrieval
  - named Act not held in the selected jurisdiction = honest refusal with suggestion
  - synonym/expansion dictionary per jurisdiction, versioned in repo
- Rerank:
  - Gemini Flash relevance scoring from top-50 to top 8–12, or a swappable rerank interface
  - coverage check threshold, tuned later from eval
- Make retrieval testable:
  - retrieve-by-query tests
  - jurisdiction leakage tests
  - refusal-on-no-match tests

**Output:**
- A retrieval path that finds paraphrased legal questions and refuses honestly when the law is not there.

**Dependency:** Phase 3.  
**Phase 5 depends on this.**

---

### Phase 5 — Writer, grounding v2, and refuse-during-verification (7–12 days, 1–2 hands)

This is what makes the product safe enough to put near lawyers.

**Tasks:**
- Writer:
  - structured answer shape: direct answer, legal basis, explanation, gaps
  - excerpts-only constraint in the prompt
  - citation numbering tied to retrieved excerpts
  - currency stamp from excerpt as-at dates
- Grounding v2:
  - citation realism: every `[n]` resolves to a retrieved excerpt
  - section realism: every statutory reference in prose is checked against chunk metadata/text
  - entailment-style check: claims compared to cited excerpt via Flash structured output
  - currency disclosure in the answer template
  - controlling provision demoted from confident claim to “most relevant retrieved — verify” unless backed by a small rules file
- Repair loop:
  - one bounded retry on verification failure with failure reasons in the prompt
  - still failing → refuse
- Refusal UX:
  - no supported answer found → explain what was searched
  - jurisdiction mismatch → suggest correct jurisdiction/Act
  - named Act not held → honest refusal
- Make verification testable:
  - fabricated citation tests
  - invented section tests
  - entailment and refusal tests
  - whole-pipeline tests against small golden cases

**Output:**
- A system that can write grounded answers and refuse when it should, with checks that are real enough to trust more than the current heuristic version.

**Dependency:** Phase 4.  
**Phase 6 depends on this.**

---

### Phase 6 — Product integration, Word add-in fit, and UI/frontend alignment (5–10 days, 1–2 hands, depends on how much frontend is reused)

This gets the backend in front of users through the existing surfaces.

**Tasks:**
- Adapt the existing frontend/Word add-in to the new API contract where needed.
- Align request/response shapes, error shapes, and refusal text.
- Make sure the main user paths work end to end:
  - question → understanding → retrieval → answer/refusal
  - drafted review/document review flow if kept
  - session and rate-limit behavior visible to users
- Add the trace/explanation surface the product can show users if desired.
- Decide what to keep from the existing public site and what to move into FastAPI.

**Output:**
- A usable product path through the existing or lightly adapted frontend.

**Dependency:** Phase 2–5.  
**Can ship a usable product with Phases 1–6 if scope is disciplined.**

---

### Phase 7 — Ingestion automation, eval harness, and CI gates (6–12 days, 1–2 hands, can overlap later parts of Phase 6)

This is what turns the system from “works in dev” into “improveable and deployable.”

**Tasks:**
- Golden QA sets:
  - start with one jurisdiction, enough cases to be meaningful
  - include should-retrieve, should-refuse, and ambiguous cases
- Eval harness:
  - retrieval metrics: recall, MRR, jurisdiction leakage, refusal correctness
  - faithfulness metrics: citation validity, invented-section rate, entailment outcomes
  - run the real pipeline, not a mock
- CI gates:
  - regression checks that can block deploys
  - at minimum: critical refusal correctness and fabricated-citation checks
- Ingestion automation:
  - scheduled or triggered re-ingest
  - corpus version and as-at reporting
  - cost and failure visibility for ingestion runs

**Output:**
- A system you can change without flying blind.

**Dependency:** Phase 3–5.  
**Strongly recommended before broad user rollout.**

---

### Phase 8 — Optional agent loop, expanded sources, and polish (10–20+ days, 1–2 hands, not required for first working product)

Only enter this once the core pipeline is working and measured.

**Tasks:**
- Bounded multi-round retrieval loop with coverage diagnosis.
- Sub-question decomposition for compound questions.
- Regulations/SIs and case law sources where available, with authority metadata.
- Better reranking path if needed.
- UX polish for trace, citations, and gaps.

**Output:**
- A stronger researcher product, not the thing that makes v2 usable.

**Dependency:** Phase 5–7.

---

## 5. Combined effort view

If the scope is disciplined — one deep jurisdiction first, no full agent loop in v1, existing frontend reused where possible — the critical path is roughly:

- Phase 0: 1–3 days
- Phase 1: 5–10 days
- Phase 2: 4–8 days
- Phase 3: 8–15 days
- Phase 4: 7–12 days
- Phase 5: 7–12 days
- Phase 6: 5–10 days
- Phase 7: 6–12 days

That is a **working-product critical path in the low-double-digit to ~60–90 day range**, depending heavily on:
- how much existing frontend is reused,
- how ready the lead corpus is,
- how much legal/source work is needed,
- how much infra is already in place,
- and how strictly you resist adding agent loop, case law, and multi-jurisdiction breadth too early.

In hands:
- **One strong full-stack/mixed engineer** can drive this, but the realistic pace will be slower and riskier because ingestion, retrieval, verification, infra, and eval all need care.
- **Two focused hands** is a much better fit: one on platform + retrieval + ingestion, one on product API + verification + eval/integration. That is the shape most likely to produce a working product without stalling.
- **Three hands** helps if you want frontend adaptation, eval authoring, and ingestion parallelism to move together.

The biggest schedule risks are not the LLM calls. They are:
- corpus readiness and legal/source availability,
- structure-aware parsing for each jurisdiction,
- refusal correctness and verification getting real rather than cosmetic,
- and scope creep into agent loop, case law, and many jurisdictions before the base works.

---

## 6. What can ship first

If you want value sooner, ship in this order of usefulness:

1. Honest auth, rate limits, real IP, and refusal paths — makes the system safe to expose.
2. One jurisdiction retrievable through hybrid search with verification and refusal — makes the system useful.
3. One clean product endpoint and one frontend path — makes it usable.
4. Golden QA + eval gates — makes it improvable.
5. Agent loop and more sources — makes it stronger.

---

## 7. What to avoid during the build

- Do not start with many jurisdictions. Start deep, not broad.
- Do not build the agent loop before the single-query pipeline is verified.
- Do not treat verification as a post-launch nice-to-have.
- Do not put per-instance state back in.
- Do not trust client headers for rate limiting.
- Do not log full prompts/answers by default.
- Do not skip tests because legal AI “should just work.”

---

## 8. Decision points to resolve before Phase 1

- Reuse existing frontend/Word add-in or rebuild the UI later?
- One jurisdiction or a small set for first launch?
- Postgres sessions or Firestore sessions?
- AlloyDB or Cloud SQL for pgvector?
- Flash-only for cheap passes now, and reranker switched later?
- What source material is actually available and licensable for the lead jurisdiction?

Resolve those and the rest of the plan becomes mostly execution.

---

## 9. Suggested next step

If you want, I can turn this into:
- a **task-level breakdown** for Phases 1–5 with owned deliverables and acceptance criteria, or
- a **first-sprint build plan** that gets the platform + auth + hybrid retrieval skeleton working locally and on Cloud Run, which is the fastest way to validate the rebuild before committing to the full schedule.
