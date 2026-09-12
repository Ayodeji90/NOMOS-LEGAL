# NOMOS v2 — Python AI/RAG Build Plan (GCP)

Companion to [REDESIGN.md](REDESIGN.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

**Decision:** use **Python** for every AI/RAG/ML layer. Keep the existing frontend/mobile/www shell where you want, but the backend serving the product API becomes Python (FastAPI) and the vector/search/ingestion/verification jobs become Python. Python is the right choice here because the libraries you want (embeddings, reranking, BM25, structured output, vector search, evaluation harnesses) are strongest and most mature in Python, and GCP's managed AI + data services integrate cleanly with it.

This doc is the honest, engineer-facing answer to:

1. What we are building (architecture)
2. What libraries and infrastructure we will use
3. Where the money actually goes beyond LLM tokens
4. What GCP it deploys on
5. What to start caring about as users scale

---

## 1. The build in plain language

For each user question, the system does this:

1. **Understand the question.** A cheap model call figures out: which jurisdiction, what kind of legal question, and writes 3–5 search variants plus lists any Acts the user named.
2. **Check for jurisdiction mismatch before retrieving.** If the selected jurisdiction does not match what the question implies, or a named Act is not held in that jurisdiction, the system refuses honestly and suggests the right jurisdiction or says the Act is not held.
3. **Retrieve.** A hybrid search over the law: keyword search plus embedding search, combined, filtered to the right jurisdiction, in-force version, and document type. Then a reranking model picks the 8–12 best passages.
4. **Check coverage.** If nothing on point was found and the agent still has rounds left, it diagnoses what is missing and searches again, up to 3 rounds. If still nothing, it refuses and explains what it searched.
5. **Write the answer.** A stronger model writes a structured answer using only the retrieved excerpts, citing them by number, and includes a gaps section for anything it could not support.
6. **Verify the answer.** Independent checks confirm every citation is real, every section reference exists in the cited excerpt, each factual claim is supported by the cited text, and the currency date is disclosed. If a check fails, one repair attempt is made; if it still fails, the system refuses rather than publish a weakly supported answer.
7. **Return the answer plus a trace.** The response includes the answer, the excerpts, the steps taken, the timings, and the verification result.

The agent part is not a free-roaming agent. It is a bounded loop that plans, retrieves more when coverage is poor, and verifies before it answers.

---

## 2. Architecture (Python map)

```
User / Word add-in
  │
  ▼
FastAPI backend (Cloud Run)            Python AI/RAG service
  ├─ routes, auth, CSP, SEO, rate limits      ├─ query understanding (Gemini Flash)
  ├─ sessions (Firestore)                      ├─ hybrid retrieval (Postgres pgvector + text search)
  ├─ users / API keys (Postgres)               ├─ reranking (Gemini Flash or open reranker)
  ├─ quotas and rate limits (Redis)            ├─ writer (Gemini Pro, Claude fallback)
  └─ task endpoints (search, draft, review)    └─ verifier (citation realism + entailment + currency)
                                               │
Ingestion and evaluation (separate Cloud Run jobs)
  ├─ parse and normalize sources (per jurisdiction)
  ├─ detect structure and version differences
  ├─ structure-aware chunking
  ├─ embeddings (text-embedding-005)
  ├─ upsert into Postgres with pgvector
  └─ eval harness runs golden QA sets nightly
```

Where the Python code lives is a choice. Two practical shapes:

- **Option A — split:** Node/Express keeps the frontend shell and auth gate, and a separate Python service owns the AI/RAG endpoints. Good when you want a clean boundary and independent deploys.
- **Option B — single FastAPI app:** replace the Express app with FastAPI and put routes, auth/limits glue, and AI/RAG all in Python. Simpler to operate for a small team.

For a rebuild targeting correctness and a small team, Option B is usually easier to own end to end. Keep the static frontend, Word add-in, and public marketing pages as they are; they talk to the API over HTTP.

---

## 3. Python libraries and dependencies

This is the stack. Pick the managed path first; choose OSS/self-host only when managed cost or control forces it.

### Web and API

- **FastAPI** — the backend framework. Async, typed with Pydantic, Swagger/OpenAPI out of the box, easy to containerize for Cloud Run.
- **Uvicorn** — ASGI server for local dev and container start.
- **Pydantic + Pydantic Settings** — request/response models, env config, structured model I/O.
- **HTTPX** — outbound HTTP to model APIs and internal service calls; support for timeouts, retries, and tracing.

### Data

- **PostgreSQL with pgvector** on **AlloyDB** or **Cloud SQL** — the main store. Chunks, versions, sources, users, keys, and the vector index. pgvector gives you HNSW vector search plus full SQL for jurisdiction/in-force/version/doc-type filtering. This is the core architectural choice: one database for structured legal metadata and vectors, not two systems.
- **SQLAlchemy** (with **asyncpg**) — ORM/connection layer. Use async drivers so the API can serve concurrent requests without blocking on DB I/O.
- **psycopg2-binary / psycopg** — fallback or sync path if needed.
- **Alembic** — database migrations. Point-in-time versioned schema will change; you want migration history from day one.
- **Redis (Google Memorystore)** — rate limits, quotas, short-lived caches. For local dev use fakeredis.

### Sessions and identity

- **Firestore** (Google Cloud Firestore in Datastore mode or native) for sessions if you want managed NoSQL. The existing session model (timing-safe compare, scrypt) is good; move the storage from in-memory/node Firebase client to Python with the Firestore client.
- If you prefer SQL for everything, session storage can live in Postgres too; the tradeoff is latency and scaling shape. Either is fine for v2. Start with Firestore for sessions if you want the least ops, or Postgres if you want a single data plane.

### Auth and secrets

- **scrypt** (Python `hashlib.scrypt` or passlib) for password storage with timing-safe comparison.
- API keys hashed in Postgres.
- Cloud Run IAM for service-to-service calls; service account JSON only in the runtime environment, never checked into repo.

### Search and retrieval

- **pgvector** for dense search.
- **Postgres full text (`tsvector`)** for sparse/BM25-style search. For stronger BM25 tuning you can use **ParadeDB** (a Postgres extension) or stick with Postgres GIN+tsearch and a legal synonym dictionary. For v2, Postgres full text plus a curated per-jurisdiction synonym list is the pragmatic start.
- **Cross-encoder reranking:** start with **Gemini Flash scoring** as the reranker interface (cheap, zero hosting). Later, if latency or quality demands it, add an open cross-encoder such as ** BGE reranker** (via Hugging Face `transformers` or the Sentence Transformers reranker interface) hosted on a small Cloud Run GPU instance, behind the same rerank interface.

### Embeddings

- **Google Generative AI Python SDK (`google-generativeai`)** for `text-embedding-005` through Vertex AI. This is the managed embedding call. Start here; swap the embedder implementation later without touching retrieval if you need multilingual or open weights.

### Models

- **Gemini Flash** for query understanding, expansion, reranking, and verifier/NLI passes. Cheap, fast, structured output.
- **Gemini Pro** for the writer. Keep the multi-provider pattern if you used one; Claude as fallback behind the same writer interface is fine.
- All model calls go through one small `llm.py` style module with per-role model config driven by env. That keeps you able to change models per task without rewriting retrieval or verification.

### Files, sources, and parsing

- **Google Cloud Storage client** for raw source documents and corpus archives.
- Per-jurisdiction HTML parsing: Python HTML parsing (e.g. `lxml` or `BeautifulSoup`) with jurisdiction-specific normalization rules. The structure detection (section tree, headings, provisos) is custom code per jurisdiction; this is the main engineering per jurisdiction, not a library.

### Evaluation and quality

- **pytest + pytest-asyncio** for unit and integration tests. Legal RAG needs this from the start.
- **ruff** for lint/format in CI.
- Golden QA sets stored in the repo; an evaluation job runs the full pipeline against them and reports retrieval and faithfulness metrics. The eval harness is mostly Python: call the real pipeline, compare retrieved sections and refusals to expected, emit metrics.

### Optional, only if needed

- **Celery + Redis** or **Cloud Tasks** for long ingestion jobs if you outgrow Cloud Run jobs. Start with Cloud Run jobs triggered from GCS or Cloud Scheduler.
- **LangChain** only if you want a wrapper around prompt chains; it is not required and often adds weight. For this design, plain Python with explicit prompt functions is cleaner and easier to verify. If you do use it, `langchain-core` plus the Google integration, not the full framework by default.

---

## 4. Where the money goes, besides LLM tokens

LLM credits are the obvious line, but in a legal RAG system the other costs matter and are often larger than people expect. The main paid things are:

### Model usage

- **Vertex AI generate content calls** for query understanding, reranking, writer, verifier. Gemini Flash is cheap per call; the writer and any long verification passes are where the cost sits.
- **Vertex AI embeddings** for `text-embedding-005`. Cheap per embedding, but ingestion is a batch cost, and re-embeds on corpus refresh are a recurring batch cost.
- **Model choice matters a lot.** Flash-heavy design keeps cost low; using Pro for every step would multiply it. The design uses the right model for the right job on purpose.

### Data storage and search

- **AlloyDB or Cloud SQL for Postgres with pgvector.** Cost scales with instance size, storage, and connections. Vector indexes and larger corpora push storage and memory. This is usually the steady baseline cost.
- **Firestore** for sessions if you use it. Small per-session cost that grows with active users.
- **Memorystore Redis.** A fixed hourly cost per tier; pick the smallest tier that meets your rate-limit and cache needs.

### Storage and ingress/egress

- **Cloud Storage** for raw sources, parsed documents, corpus archives, and evaluation data. Cheap; the cost is around storage volume and operations.
- **Network egress.** Every answer that leaves GCP to a browser or Word add-in costs egress. Many small API responses are not expensive; large document uploads/downloads and high volume are. Cross-region traffic and external egress are where surprises show up.
- **Ingestion ingress.** If you pull source documents from external sites or vendors, that traffic can matter.

### Compute

- **Cloud Run** for the API and for ingestion/eval jobs. Cloud Run bills per vCPU-second and memory-second and per request concurrency. For a steady API, you can keep a minimum instance count warm to avoid cold starts; that adds a small constant cost.
- **GPU Cloud Run** only if you self-host a reranker or embedder. Avoid at first; add only if the managed model path is too expensive or too slow for your quality bar.

### Ops and tooling

- CloudLogging/Cloud Monitoring ingestion and storage if you log every query trace. Query-level traces are valuable, but they are also a cost line; sample or summarize when volume grows.
- Secret Manager, Artifact Registry, and CI runners if you use them. Usually small relative to model and data costs.

**Rough intuition for early stage:** the biggest variable cost is model calls, the biggest fixed cost is the managed database and Redis, and the biggest scale risk is egress plus logging volume plus embedding/hybrid-search workload on the database. You can run a useful v2 on a fairly small GCP footprint if you keep the model path Flash-heavy and do not log every token.

---

## 5. GCP infrastructure requirements

This is the target shape on GCP.

### Core services

- **Cloud Run** for the FastAPI backend and for ingestion/eval jobs. Cloud Run gives you autoscaling, request-based scaling, and containerized deploys. It is the right host for a request-serving API and for batch jobs.
- **AlloyDB** or **Cloud SQL PostgreSQL with pgvector** for the data and vector store. AlloyDB is the stronger Postgres path for vector workloads and read scaling; Cloud SQL is the simpler managed Postgres path. Pick based on expected vector index size, read load, and how much operational simplicity you want.
- **Memorystore for Redis** for rate limiting and short-lived caches.
- **Firestore** for sessions, if you keep sessions out of Postgres.
- **Cloud Storage** for raw sources, ingestion inputs/outputs, corpus archives, and eval data.
- **Vertex AI** for Gemini model calls and embeddings.
- **Cloud Logging + Cloud Monitoring** for traces, metrics, and alerts.
- **Secret Manager** for keys and service account credentials.
- **Cloud Scheduler** for nightly eval jobs and corpus refresh triggers, if used.
- **Cloud Tasks** or **Cloud Run jobs** for longer ingestion pipelines, depending on job length and retry needs.

### Networking and access

- Cloud Run service with public ingress controlled by IAM or by an allowed origin path if you want to front it with another entry point.
- If you later add an internal-only service, use Serverless VPC Access or private Cloud Run with VPC connectivity to reach AlloyDB/Cloud SQL and Memorystore without public exposure.
- Real client IP for rate limiting: Cloud Run provides the true client IP via `X-Forwarded-For` first hop. Use that instead of trusting client headers. This fixes the current spoofable rate-limiting problem.

### Security baseline

- Least-privilege service accounts per workload: the API service account, the ingestion job service account, the eval job service account.
- Secrets in Secret Manager, not env files in the repo.
- DB access through Cloud SQL/AlloyDB authorized networks or private IP, not world-open.
- Schema migrations via Alembic applied in the deploy pipeline, not by hand.

### Baseline sizing intuition

- Small launch: one Cloud Run service for the API, one small Postgres instance with pgvector, one small Redis tier, Firestore for sessions, Vertex AI for models, and Cloud Storage for sources. That is enough for a working v2 and a small user base.
- The pieces that grow first are the Postgres/vector workload and model calls. Redis and Firestore grow more slowly. Compute grows with concurrency and job load.

---

## 6. Scaling considerations, in order of when they start to matter

### First, correctness and cost discipline

Before scale, make sure the system is correct and not leaking money:

- Every retrieval is jurisdiction-filtered and version-filtered; wrong-jurisdiction excerpts never make it into answers.
- Verification is real and not skippable in the hot path.
- Model calls are role-appropriate: Flash for cheap passes, Pro for writing.
- Logging does not capture more than you need. If you log full prompts and full answers for every request, cost and compliance both get worse quickly.

### Second, the database and vector index

As corpora grow and user volume grows:

- pgvector index maintenance, index size, and query latency become the main retrieval concern. HNSW index build time and memory usage matter when you re-ingest.
- Connection pooling matters on Cloud Run because every instance can open DB connections; use a pooler or connection pooling to avoid exhausting Postgres connections under autoscaling.
- Backups, point-in-time recovery, and migration discipline matter more once the corpus is real and versioned.
- If retrieval load gets heavy, read replicas or AlloyDB read scaling matter before you add application complexity.

### Third, model cost and latency

- Rate limiting and quotas become real money controls, not just abuse controls.
- Caching query understanding and repeated retrieval for similar questions saves money and latency. Cache by semantic or normalized query hash, with a short TTL and jurisdiction/version awareness.
- As volume grows, the writer and verifier calls dominate cost. Keep the writer prompt tight, keep verification lean, and avoid rerunning the whole pipeline for changes that do not need it.
- If Flash becomes a bottleneck or a cost/quality tradeoff appears, consider a small open-weight reranker on GPU Cloud Run only for that step.

### Fourth, ingestion and corpus operations

- Corpus refreshes are batch work that can spike DB and embedding usage. Schedule them, not ad hoc.
- Versioned corpora mean re-embeds and re-uploads on amendments. That cost is real and should be modeled before you promise frequent updates.
- Structure detection per jurisdiction is ongoing engineering, not a one-time thing. Budget for per-jurisdiction parsing work whenever you add a new source type or jurisdiction.

### Fifth, multi-region and resilience

- If you serve lawyers across regions, latency and data residency matter. You may need regional deployment or at least regional endpoints for model and database access.
- Session and cache affinity are not required, but rate-limiting state and session state need to be shared, which is why they live in Redis/Firestore/Postgres rather than in instance memory.
- Backups, deploy rollbacks, and evaluated corpus state matter before you have lawyers depending on the product.

### Sixth, the things people forget until they are painful

- **Observability before scale.** Per-query traces, retrieval scores, verification outcomes, refusal reasons, and timings are what let you improve the system and diagnose bad answers. Build this early, then sample later.
- **Evaluation as a gate.** Golden QA sets and nightly metrics are what keep retrieval and grounding from silently regressing. Without them, you only find problems when a lawyer tells you.
- **Cost attribution.** If you grow into multiple teams or matters, you eventually want per-query or per-matter cost tracking. Design the trace to carry enough metadata to attribute cost later.
- **Abuse and quota shapes.** Invite-only and per-user/per-session quotas are good; make them real in Redis and tied to authenticated identity, not to spoofable headers.
- **Content and liability posture.** Legal answers expose you to correctness and disclaimer expectations. Keep refusal paths honest, keep currency disclosure real, and keep a clear line between cited primary sources and generated explanation.

---

## 7. What to build first, translated to Python

Same build order as REDESIGN.md, but with the Python shape made explicit:

1. **State out of instances.** FastAPI app with sessions in Firestore, rate limits and quotas in Redis, real client IP from Cloud Run, passwords hashed with scrypt, API keys hashed in Postgres. Env config via Pydantic Settings, secrets via Secret Manager. Tests and CI from day one.
2. **Versioned corpus and hybrid retrieval.** Postgres with pgvector, SQLAlchemy/asyncpg, Alembic migrations, structure-aware chunking, embeddings through the Google SDK, hybrid search over tsvector plus pgvector with RRF and metadata filters, reranking through the model interface.
3. **Query understanding and honest jurisdiction/Act handling.** Gemini Flash in JSON mode, jurisdiction mismatch checked before retrieval, named-Act filtering that refuses honestly when no matching excerpts exist.
4. **Verification v2.** Citation realism, section-reference realism against chunk metadata, NLI-style entailment via Flash structured output, currency disclosure, one bounded repair retry, then refuse.
5. **Eval harness.** Golden QA sets, nightly Cloud Run job, retrieval and faithfulness metrics, regression checks before deploy.
6. **Agent loop plus expanded sources.** Bounded multi-round retrieval, sub-question decomposition, plus regulations and case law sources with authority metadata where available.

---

## 8. What is intentionally not in v2

- A full enterprise multi-tenant workspace with matter-level ACLs.
- Self-hosted open-weight LLMs as the default, though the model interface supports swapping if cost or residency requires it.
- A full citator with comprehensive treatment graphs; start with per-case metadata and manual treatment notes, not a Lexis-grade system.

---

## 9. Bottom line

Yes, this still deploys cleanly on GCP. The architecture is Cloud Run + managed Postgres with pgvector + Redis + optional Firestore + Vertex AI + Cloud Storage, with the heavy AI work in Python. Beyond LLM tokens, your main costs are database and vector search, Redis and sessions, storage and network egress, logging volume, and model calls by role. As you scale, the first things to plan for are shared state for limits and sessions, database and vector index scale, model cost control via caching and right-sized models, corpus refresh operations, and evaluation-driven quality control.

The honest reason to use Python here is not fashion. It is that the retrieval, embedding, reranking, structured-output, and evaluation pieces you actually need are easiest to build, test, and operate in Python on GCP, and the legal correctness story depends on being able to test and verify the pipeline rather than on any particular framework.
