# NOMOS v2 — AI & RAG System Design

Renderable diagrams live in [ARCHITECTURE.md](ARCHITECTURE.md) (Mermaid — renders on GitHub/GitLab or mermaid.live).

**Goal:** an effective, lawyer-trustworthy legal RAG system on GCP that fixes the flaws found in the current implementation (lexical-only retrieval, heuristic "controlling provision" claims, invented-section hallucinations, cross-Act leakage, silent jurisdiction fallback, stale corpora, per-instance state) while keeping NOMOS's genuine differentiator: **refusal-first grounding**.

**Design stance:** hybrid retrieval done properly, an agent loop that verifies before it answers, point-in-time corpora, and evaluation as a first-class citizen. Keep the current Express/Cloud Run shell — this is a spine replacement, not a rewrite of the product surface.

---

## 1. The core loop (what a query goes through)

```
User question
   │
   ▼
[1] Query Understanding ──► jurisdiction? question type? legal-terms expansion?
   │                        generate 3–5 search variants
   ▼
[2] Hybrid Retrieval ─────► BM25 + dense vectors, fused (RRF), top ~50
   │                        filters: jurisdiction, in-force, doc type
   ▼
[3] Rerank ───────────────► cross-encoder, top 50 → top 8–12 passages
   │
   ▼
[4] Coverage Check ───────► is anything actually on point?  ──no──► REFUSE
   │                                                      (offer nearest jurisdiction)
   ▼
[5] Answer Synthesis ─────► writer LLM, excerpts only, structured answer
   │                        (directAnswer / legalBasis / explanation / gaps)
   ▼
[6] Grounding Verification ► independent checks: citations real? sections real?
   │                        statements entailed by excerpts? currency flagged?
   ▼  fail → one bounded repair retry → else refuse
[7] Response + Trace ─────► answer, excerpts, confidence, per-step timings/log
```

This is a **plan → retrieve → verify → answer** loop. The agent wrapper (section 7) repeats steps 2–4 when coverage is poor instead of answering from weak evidence.

---

## 2. Corpus & ingestion layer (fixes flaws #1, #6, #7)

### 2.1 Source model — "document" becomes versioned

Every instrument (Act, regulation, SI, code, case) is stored as **point-in-time versions**, never a flat snapshot:

```
sources/
  └─ za/acts/2008/71/                     # Companies Act 71 of 2008
      ├─ manifest.json                    # title, short title, publication, status
      ├─ versions/
      │    ├─ 2011-05-01.json            # text as in force from this date
      │    └─ 2023-12-01.json            # latest consolidated text
      └─ amendments.json                  # what changed, commencement dates
```

- **`inForce` is a first-class filter.** Retrieval defaults to the latest in-force version and stamps every excerpt with `asAt: <date>`. Answers state "as amended up to <date>".
- **Repealed/pending sections are retrievable but marked** — the writer must disclose status if cited. (Today the corpus is a frozen snapshot presented as current law.)
- **New source types:** regulations/SIs, and case law (judgments with headnotes + paragraph-level chunks). Cases carry `court`, `authorityLevel` (Constitutional Court > SCA > High Court…), `treatment` (followed/distinguished/overruled — even a manual citator file beats nothing).

### 2.2 Structure-aware chunking

Legal text is hierarchical; fixed-size chunks destroy meaning. Chunk along the statute tree, never across it:

```
chunk = { jurisdiction, sourceId, version, actTitle, sectionNo, subsection,
          heading, text, embedding, tokens, inForce, effectiveFrom, effectiveTo }
```

- One chunk = **section or subsection**; long sections split at sub-subsection/proviso boundaries with parent context prepended (`"Companies Act 71 of 2008 s 159(2) — Accountability and transparency:"`).
- Headings + short-title are embedded **together with the text** — this alone fixes a large share of the current lexical-miss problem.
- Cases chunk per paragraph with the catchwords/headnote attached to each.
- `draft-reference/` (will templates etc.) keeps its own store but gains the same versioning.

### 2.3 Ingestion pipeline (Cloud Run job, triggered from Cloud Storage)

```
GCS bucket (raw sources: PDF/HTML/JSON) 
  → parse (normalize HTML per jurisdiction) 
  → structure detection (section regex + heading tree)
  → version diffing (against previous version; emits amendment notes)
  → chunk + embed (batch, Vertex AI embedding API)
  → upsert to Postgres/AlloyDB (pgvector)
  → manifest check (every source resolvable, in-force flags set)
  → report (source counts, chunk counts, orphaned citations)
```

**Ingestion gate:** a corpus deploy fails CI if any section referenced by `jurisdictions.json` or the smoke tests is missing — the same way the current `NOMOS_SMOKE` hooks work, but offline.

---

## 3. Retrieval layer (fixes flaw #1 — the big one)

### 3.1 Hybrid search, three signals

| Signal | Engine | Catches |
|---|---|---|
| Sparse (BM25, with legal synonym expansion) | Postgres `tsvector` + custom dictionary (or ParadeDB) | exact statutory phrases, section numbers, defined terms ("BCEA", "summary dismissal") |
| Dense (embeddings) | pgvector, HNSW index | paraphrase ("can I fire without notice?" ↔ "termination without notice") |
| Structural boosts | SQL metadata | in-force, jurisdiction, doc type, authority level, act/section match |

- **Embedding model:** `text-embedding-005` (Vertex AI) — one API, no model hosting. If multilingual coverage (DE/IE) becomes important, switch to a multilingual model behind the same interface (`embedder.js` is the only caller).
- **Fusion:** Reciprocal Rank Fusion over the two ranked lists, then metadata filters applied **pre-fusion** (hard filter: wrong jurisdiction never enters; soft boosts after).
- **Why Postgres/AlloyDB, not a dedicated vector DB:** the metadata filtering (jurisdiction × in-force × version × doc type) is the hard part of legal retrieval, and that lives naturally in SQL. One database, ACID upserts on re-ingest, no second system to operate. (This is the lesson from the Legora/Elastic choice inverted at our scale: they need horizontal scale across firms; we need correctness across versions.)

### 3.2 Query understanding (before retrieval)

A cheap LLM step (Gemini Flash, ~300ms, cached) that returns JSON:

```json
{ "jurisdiction": "za",              // explicit picker wins; this infers/confirms
  "questionType": "threshold",        // definition | procedure | threshold | exception | comparison
  "expandedQueries": [                 // 3–5 search variants
    "notice period termination of employment BCEA section 37",
    "minimum notice period dismissal common law contract"
  ],
  "namedActs": ["Basic Conditions of Employment Act"],
  "intent": "employee_notice" }
```

- **Legal synonym dictionary per jurisdiction** (curated, versioned in repo): "sack/fire/dismiss", "redundancy/retrenchment", "notice period/minimum notice". Cheap, auditable, and it plugs the dense model's domain gaps.
- **Jurisdiction inference fixes flaw #5:** if the picker says ZA but the query mentions "Employment Rights Act 1996" (UK), the mismatch handler fires **before** retrieval — no more silent wrong-country answers. If the query names a live jurisdiction not selected, respond with `suggestedJurisdiction` (existing pattern, now driven by data, not regex).
- **Named-Act filter becomes honest:** if the user names an Act and retrieval returns no rows for it → refuse with "no excerpts from <Act> matched" instead of silently keeping other Acts' excerpts (fixes flaw #4).

### 3.3 Rerank

- **Cross-encoder** over top-50: start with Gemini Flash scoring relevance 0–10 in batches (cheap, zero hosting); if latency/quality demands, graduate to an open cross-encoder (bge-reranker-v2-m3) on a small Cloud Run GPU instance behind the same interface.
- Output: top 8–12 passages with scores. **Coverage check** (step 4): if no passage exceeds a calibrated on-point threshold → refuse. Thresholds tuned per jurisdiction from the eval harness, not vibes.
- The ZA BM25+RRF pipeline is retired — it becomes a special case of this general pipeline. `retrieve-za.js` logic is superseded; `za-focus.js` concept survives as the ZA synonym/expansion dictionary.

---

## 4. Grounding & verification layer (keep the philosophy, close the holes)

`grounding.js`'s refusal-first stance is NOMOS's best asset — v2 keeps and hardens it:

1. **Citation realism (fixes flaw #3):** every `[n]` must map to a retrieved excerpt **and** every statutory reference inside the prose (`s 145`, "section 145(2)(b)") must exist in that excerpt's text or metadata. The verifier regexes section references out of the answer and checks them against `sectionNo`/`subsection` fields — invented sections are caught even when the Act name is real.
2. **Entailment check (new):** split the answer into atomic claims; run a cheap NLI pass (Gemini Flash, structured output: `entailed / not_entailed / not_found` per claim vs the cited excerpt). `not_found` claims are either deleted (retry) or moved to `gaps`. This is the automated version of what a checking lawyer does.
3. **"Controlling provision" demoted from claim to suggestion (fixes flaw #2):** the answer says "The most relevant retrieved provision is [1] — verify the full section before relying on this" unless the provision's authority is structural (e.g., Constitution overrides, later statute prevails) — those cases come from a small, reviewable rules file, not keyword scores.
4. **Currency disclosure:** every excerpt carries `asAt`; the answer template appends "Law stated as at <max asAt date>. Verify commencement of recent amendments."
5. **Repair loop:** on verification failure → one bounded retry with the failure reasons injected into the writer prompt → still failing → refuse. (Two attempts max; latency is bounded.)
6. **Untrusted inputs:** client documents keep the existing `UNTRUSTED_CLIENT_DOCUMENT_START/END` wrapping + injection-pattern rejection, unchanged.

Writer prompt structure (same four-part answer as today: `directAnswer / legalBasis / explanation / gaps`) — this is good UX and stays.

---

## 5. Agent loop (step 7 of the core loop) — "Researcher"

A single, inspectable loop (not a free-roaming agent):

```
plan(question) → for up to 3 rounds:
    retrieve(query variants) → coverage_ok? 
        no → refine: what's missing? (which sub-question has no support)
             new queries → continue
answer once coverage_ok or rounds exhausted (answer with explicit gaps)
verify → repair → deliver
```

- Each round is logged as a step the UI can show ("Searched 4 variants · found statutory basis for X · still missing Y → searching case law").
- Sub-questions: compound questions ("Can I dismiss and what's my severance?") decompose into one retrieval per part; answers merge with per-part citations.
- **Human sign-off posture (the Legora pattern, honestly implemented):** the system produces drafts with citations and a verification trace; the lawyer approves. No action-taking beyond draft generation.

This maps directly onto what Legora does well (plan → investigate multiple angles → verify against primary sources → rank by authority) but is smaller, self-hosted on GCP, and keeps refusal-first behavior.

---

## 6. Models & serving (GCP-native, swappable)

| Role | Model (start) | Notes |
|---|---|---|
| Query understanding / expansion | Gemini Flash (Vertex AI) | JSON mode, cached by query hash |
| Embeddings | `text-embedding-005` | 768-dim, batch upsert |
| Rerank | Gemini Flash scoring (→ bge-reranker later) | top-50 → top-10 |
| Writer | Gemini Pro (Claude as fallback) | existing `ai-write.js` multi-provider pattern kept |
| Verifier (NLI + citation checks) | Gemini Flash | structured output, cheap |

- All model calls go through one `llm.js` interface with **per-role model config** (env-driven) — the Legora "multi-model with redundancy" idea, minimal version.
- **Per-instance state is gone (fixes flaws #8, #9):** sessions → Firestore; rate limits & quotas → Memorystore (Redis) keyed by authenticated session/user + real client IP from Cloud Run's `X-Forwarded-For` first hop (Cloud Run guarantees this — the spoofable header chain goes away); API keys hashed in Postgres.
- **Auth stays** (scrypt, timing-safe compares, invite-only) — it's the good part of the current code.

---

## 7. Evaluation harness (the piece that makes the rest trustworthy)

No legal RAG works without measurement. `eval/` in the repo:

1. **Golden QA sets** per jurisdiction: 100+ questions each with (a) the source sections a competent lawyer would cite, (b) expected refusals for out-of-coverage questions. ZA first (deepest corpus), then US federal, UK.
2. **Retrieval metrics in CI:** recall@10, MRR, jurisdiction leakage rate (wrong-country excerpts returned = hard fail), refusal correctness (should-refuse questions that got answered = hard fail).
3. **Faithfulness metrics:** citation validity rate (all `[n]` resolve), invented-section rate, claim-entailment rate — run the full pipeline on the golden set nightly on Cloud Run job; regressions block deploys.
4. **Threshold tuning:** coverage cutoffs and boost weights are tuned against these sets, stored as config, and every change to retrieval must show eval deltas in the PR.

This is what today's code has zero of, and it's the difference between "plausible demo" and "tool a lawyer signs their name under."

---

## 8. Target architecture on GCP (one diagram)

```
                        ┌──────────────────────────── Cloud Run (Node/Express, kept) ───────────────────────────┐
Browser / Word add-in → │ index.js (routing, CSP, SEO — kept)                                                   │
                        │   ├─ auth.js → Firestore (sessions), Postgres (users/keys)                            │
                        │   ├─ limits.js → Memorystore Redis (rate, quotas)                                     │
                        │   ├─ query.js    → Gemini Flash (understanding, expansion, jurisdiction check)        │
                        │   ├─ retrieve.js → AlloyDB/Cloud SQL Postgres (pgvector + tsvector, metadata filters) │
                        │   ├─ rerank.js   → Gemini Flash scorer (swappable)                                    │
                        │   ├─ agent.js    → plan/retrieve rounds, sub-questions, coverage loop                 │
                        │   ├─ ai-write.js → Gemini Pro writer (structured answer)                              │
                        │   └─ grounding.js→ citation realism + NLI entailment + currency disclosure            │
                        └──────────────┬──────────────────────────────────────┬─────────────────────────────────┘
                                       │                                      │
                     Ingestion job (Cloud Run jobs, CI-gated)              Observability
                     GCS raw sources → parse → version → chunk →           Cloud Logging (per-query traces:
                     embed → upsert Postgres → eval gate                   retrieval scores, verification
                                                                           verdicts, refusal reasons)
```

**What to build, in order (each ships value alone):**

| Phase | Deliverable | Flaws killed |
|---|---|---|
| 1 | State out of instance: Firestore sessions, Redis limits, real IP | #8, #9 |
| 2 | Structure-aware re-chunk + embeddings into Postgres; hybrid retrieval for **all** jurisdictions | #1 |
| 3 | Query understanding + honest jurisdiction/named-Act handling | #5, #4 |
| 4 | Verification v2: section-reference realism + NLI entailment + currency disclosure | #3, #2, #7 (disclosure) |
| 5 | Eval harness + CI gates | makes 1–4 provable |
| 6 | Agent loop (multi-round retrieval, sub-questions) + regulations/case-law sources | #6 |

Phases 1–3 are weeks, not months, and they convert the current system from "keyword demo" to "real legal RAG" — worth doing regardless of the fix-vs-rebuild decision, because the product surface (`index.js`, `public/`, auth, the Word add-in) survives intact.

---

## 9. Explicitly out of scope (v2)

- Multi-tenant firm workspaces / matter-level ACLs (Legora's enterprise core) — single-product ACLs only, but `retrieve()` takes a `scope` parameter now so it's a schema change later, not a rewrite.
- Self-hosted open-weight LLMs — API models with a provider interface; revisit on cost.
- Full citator (CaseMap/Lexis-grade treatment graphs) — manual `treatment` files per case first, vendor data later if licensed.
