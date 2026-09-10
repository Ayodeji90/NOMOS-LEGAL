# NOMOS v2 — Architecture Diagrams (Mermaid)

Companion to [REDESIGN.md](REDESIGN.md). These diagrams render on GitHub, GitLab, and any Mermaid Live viewer (paste the block into https://mermaid.live).

---

## 1. Core query flow — plan, retrieve, verify, answer

```mermaid
flowchart TD
    Q["User question<br/>(web or Word add-in)"] --> AUTH["Auth + rate limit<br/>Firestore sessions, Redis limits"]
    AUTH --> QU["Query understanding<br/>Gemini Flash<br/>jurisdiction check, question type,<br/>3-5 expanded queries"]

    QU -->|"named Act not in<br/>selected jurisdiction"| REFJ["Refuse: suggest jurisdiction<br/>or named Act not held"]
    QU --> MISMATCH{"Picker vs query<br/>jurisdiction match?"}
    MISMATCH -->|"no"| REFJ
    MISMATCH -->|"yes"| RET

    subgraph AGENT["Agent loop - max 3 rounds"]
        RET["Hybrid retrieval<br/>BM25 + dense vectors fused by RRF<br/>filters: jurisdiction, in-force, version"] --> RER["Rerank<br/>cross-encoder, top 50 to top 8-12"]
        RER --> COV{"Coverage check:<br/>anything on point?"}
        COV -->|"no, rounds left"| REFINE["Diagnose missing sub-question<br/>generate new queries"] --> RET
    end

    COV -->|"no, rounds exhausted"| REF1["Refuse: no supported legal answer<br/>explain what was searched"]
    COV -->|"yes"| WRITE

    WRITE["Writer LLM<br/>excerpts only, structured answer:<br/>directAnswer, legalBasis, explanation, gaps"] --> VER

    subgraph VERIF["Grounding verification"]
        VER["Citation realism:<br/>every [n] resolves; every section ref<br/>like s 145 exists in excerpt metadata"] --> NLI["Claim entailment:<br/>each atomic claim entailed<br/>by its cited excerpt"]
        NLI --> CUR["Currency disclosure:<br/>law stated as at max asAt date"]
    end

    VER -->|"fail"| REPAIR["One bounded repair retry<br/>failure reasons injected"] --> VER
    REPAIR -->|"still failing"| REF2["Refuse rather than ship<br/>an unverified answer"]
    VER -->|"pass"| OUT["Response + full trace:<br/>answer, excerpts, confidence,<br/>per-step timings logged"]
```

---

## 2. GCP system architecture

```mermaid
flowchart LR
    subgraph CLIENTS["Clients"]
        WEB["Web app<br/>public static site"]
        ADDIN["Word add-in"]
    end

    subgraph RUN["Cloud Run - Node/Express, kept"]
        IDX["index.js<br/>routing, CSP, SEO, auth gate"]
        Q["query.js<br/>understanding + expansion"]
        RET2["retrieve.js<br/>hybrid search"]
        RR["rerank.js"]
        AG["agent.js<br/>plan-retrieve-verify loop"]
        AW["ai-write.js<br/>writer LLM"]
        GR["grounding.js<br/>citation + entailment checks"]
    end

    subgraph DATA["Data layer"]
        PG[("Cloud SQL / AlloyDB<br/>Postgres: pgvector + tsvector<br/>sources, versions, chunks, users, keys")]
        FS[("Firestore<br/>sessions")]
        REDIS[("Memorystore Redis<br/>rate limits, quotas")]
        GCS[("Cloud Storage<br/>raw source documents")]
    end

    subgraph MODELS["Vertex AI"]
        FLASH["Gemini Flash<br/>query understanding, rerank, NLI"]
        PRO["Gemini Pro<br/>writer, Claude fallback"]
        EMB["text-embedding-005<br/>embeddings"]
    end

    WEB --> IDX
    ADDIN --> IDX
    IDX --> Q --> AG
    AG --> RET2 --> RR
    AG --> AW --> GR
    Q --> FLASH
    RR --> FLASH
    GR --> FLASH
    AW --> PRO
    RET2 --> PG
    EMB -.->|"used by ingest"| PG
    IDX --> FS
    IDX --> REDIS
    GR --> OUT3["Response + trace<br/>Cloud Logging"]
```

---

## 3. Ingestion pipeline (CI-gated, Cloud Run job)

```mermaid
flowchart LR
    SRC["GCS raw sources<br/>Acts, regulations, case law<br/>per jurisdiction"] --> PARSE["Parse + normalize<br/>per-jurisdiction HTML rules"]
    PARSE --> STRUCT["Structure detection<br/>section tree, headings, provisos"]
    STRUCT --> VER["Version diffing<br/>against previous version<br/>emits amendment + commencement notes"]
    VER --> CHUNK["Structure-aware chunking<br/>one chunk = section or subsection<br/>headings embedded with text"]
    CHUNK --> EMU["Embed<br/>text-embedding-005"]
    EMU --> UP["Upsert Postgres<br/>pgvector + tsvector + metadata<br/>inForce, asAt, authorityLevel"]
    UP --> GATE{"Ingestion gate:<br/>smoke sections present?<br/>counts match manifest?"}
    GATE -->|"fail"| FAIL["Block deploy,<br/>report missing sources"]
    GATE -->|"pass"| LIVE["Corpus live<br/>every excerpt stamped with version + asAt"]
```

---

## 4. Grounding verification detail

```mermaid
flowchart TD
    ANS["Writer draft with [n] citations"] --> C1{"All [n] resolve to<br/>retrieved excerpts?"}
    C1 -->|"no"| F["Fail: fabricated citation"]
    C1 -->|"yes"| C2{"Every section ref in prose<br/>s 145, s 37(1) - exists in<br/>that excerpt's sectionNo / text?"}
    C2 -->|"no"| F
    C2 -->|"yes"| C3["NLI: split into atomic claims,<br/>check each against cited excerpt"]
    C3 --> C4{"All claims<br/>entailed?"}
    C4 -->|"not_entailed"| F
    C4 -->|"not_found"| MOVE["Move claim to gaps section"]
    C4 -->|"entailed"| C5["Append currency line:<br/>law stated as at date<br/>+ controlling-provision caveat"]
    MOVE --> C5
    C5 --> PASS["Verified answer"]
    F --> REP["One repair retry with<br/>failure reasons in prompt"]
    REP --> ANS
    REP -->|"second failure"| REFUSE["Refuse + show excerpts found"]
```

---

## 5. Build order

```mermaid
flowchart LR
    P1["Phase 1<br/>State out of instance:<br/>Firestore + Redis + real IP"] --> P2["Phase 2<br/>Re-chunk + embed into Postgres,<br/>hybrid retrieval everywhere"]
    P2 --> P3["Phase 3<br/>Query understanding,<br/>honest jurisdiction + Act filters"]
    P3 --> P4["Phase 4<br/>Verification v2:<br/>section realism, NLI, currency"]
    P4 --> P5["Phase 5<br/>Eval harness + CI gates"]
    P5 --> P6["Phase 6<br/>Agent loop,<br/>regulations + case law sources"]
```
