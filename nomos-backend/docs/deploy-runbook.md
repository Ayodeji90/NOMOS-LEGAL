# NOMOS Staging — Cloud Run Deploy Runbook (Cloud Shell edition)

Status as of 2026-09-14: service `nomos-backend-staging` deploys but is **unhealthy**
(database + Redis failed) and the corpus is **not yet ingested** into Cloud SQL.
This runbook fixes both, end to end, from Cloud Shell.

**What was already verified from the dev machine:**
- Cloud SQL `nomos-postgres`: PG 15.19, pgvector ON, all 7 tables present,
  migration level `004`, **0 source rows / 0 chunk rows** (empty corpus).
- Code fix landed: `REDIS_FAIL_OPEN` staging flag (rate limit + quotas fail
  open while Redis is unreachable; default off = prod unchanged) + unit tests.

---

## 0. BLOCKER FIRST — Billing

All billable APIs (Vertex AI embeddings/LLM) currently fail with:

```
google.api_core.exceptions.PermissionDenied: 403 Lightning dunning decision is deny
for project: projects/88191897416
```

Billing **is linked** (account `015B66-4D259F-8A123B`) but the account is in
**dunning** — a payment was declined. Nothing in this runbook's AI steps will
work until the account owner fixes it:

1. Console → **Billing** → account `015B66-4D259F-8A123B` → **Payment method**
   → update/replace the card (or settle any outstanding balance).
2. After payment succeeds, re-check: `gcloud billing projects describe project-a98ee197-e936-490c-adb`
   and run a probe from Cloud Shell:
   ```bash
   gcloud ai models list --region=us-central1 2>&1 | head -3
   ```
   (A 403 here means billing is still holding.)

Cloud Run / Cloud SQL / Build are unaffected — you can do steps 2–3 while
waiting, but ingestion (step 4) and real search (step 5) need billing cleared.

---

## 1. Sync the repo in Cloud Shell

```bash
cd ~/NOMOS-LEGAL && git pull --ff-only origin main
```

---

## 2. Deploy the fixed service (copy-paste block)

The database fix is the **Unix socket URL** — the instance is already attached
via `--set-cloudsql-instances`, which mounts the socket inside the container.
No public IP, no connector code needed. Redis is skipped for now via the new
`REDIS_FAIL_OPEN=1` flag (health will still show redis failed — that is
expected and documented at the bottom).

```bash
PROJECT=project-a98ee197-e936-490c-adb
REGION=us-central1
SVC=nomos-backend-staging
CONN="${PROJECT}:${REGION}:nomos-postgres"
DBPASS='SetYourSecurePassword123!'

gcloud run deploy "$SVC" \
  --image="us-central1-docker.pkg.dev/${PROJECT}/nomos-backend-repo/nomos-backend-staging:latest" \
  --region="$REGION" --platform=managed \
  --allow-unauthenticated \
  --cpu=2 --memory=4Gi --max-instances=10 --min-instances=0 \
  --timeout=300 --concurrency=80 \
  --set-cloudsql-instances="$CONN" \
  --set-env-vars="ENVIRONMENT=staging" \
  --set-env-vars="DATABASE_URL=postgresql+asyncpg://nomos_user:${DBPASS}@/nomos?host=/cloudsql/${CONN}" \
  --set-env-vars="REDIS_URL=redis://localhost:6379/0" \
  --set-env-vars="REDIS_FAIL_OPEN=1" \
  --set-env-vars="FIRESTORE_PROJECT_ID=${PROJECT}" \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT}" \
  --set-env-vars="VERTEX_AI_LOCATION=${REGION}" \
  --set-env-vars="SECRET_KEY=$(openssl rand -hex 32)" \
  --set-env-vars="EMBEDDING_PROVIDER=vertex" \
  --set-env-vars="LOG_LEVEL=INFO"
```

Key changes vs the last attempt:
- `DATABASE_URL` = asyncpg **unix-socket** URL (works because the type is now
  `str` after commit `a350246`, and the socket exists because of
  `--set-cloudsql-instances`).
- `EMBEDDING_PROVIDER=vertex` (was `mock` — that would poison retrieval).
- `REDIS_FAIL_OPEN=1` so search works while Redis/Memorystore is unreachable.
- `SECRET_KEY` randomized once (note it somewhere stable; re-deploys that
  rotate it will invalidate existing tokens).

Note: the service account deploy uses needs the image built from **current
main**. If the image is stale, build first:

```bash
gcloud builds submit ../NOMOS-LEGAL/nomos-backend \
  --tag="us-central1-docker.pkg.dev/${PROJECT}/nomos-backend-repo/nomos-backend-staging:latest"
```

(Adjust the path to wherever the repo lives in Cloud Shell; run from the repo
root: `gcloud builds submit nomos-backend --tag=...`.)

---

## 3. IAM for Vertex AI (runtime service account)

```bash
PROJECT_NUMBER=88191897416
SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA}" --role="roles/aiplatform.user"
```

Also confirm Cloud SQL client (needed for the socket mount):

```bash
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${SA}" --role="roles/cloudsql.client"
```

This is a shared project — binding `roles/aiplatform.user` on the **default
compute SA** only (not on user accounts) is the least-privilege way to let the
staging service call Vertex. Flag it to the owner in standup.

---

## 4. Ingest the corpus (Cloud Shell, one block)

Cloud Shell already has the cloud SQL proxy binary available via
`cloud_sql_proxy` (or use the baked-in connector). Simplest reliable path:
download v1 proxy, ingest, then verify.

```bash
PROJECT=project-a98ee197-e936-490c-adb
CONN="${PROJECT}:us-central1:nomos-postgres"
DBPASS='SetYourSecurePassword123!'

# 1) proxy up on 5439
wget -q https://dl.google.com/cloudsql/cloud_sql_proxy.linux.amd64 -O /tmp/cloud_sql_proxy
chmod +x /tmp/cloud_sql_proxy
/tmp/cloud_sql_proxy -instances="${CONN}"=tcp:5439 >/tmp/csql_proxy.log 2>&1 &
sleep 5

# 2) ingest ZA (BCEA + Companies Act, real text-embedding-005 vectors)
cd ~/NOMOS-LEGAL/nomos-backend
export DATABASE_URL="postgresql+asyncpg://nomos_user:${DBPASS}@127.0.0.1:5439/nomos"
export EMBEDDING_PROVIDER=vertex
python3 scripts/cleanup_and_reingest.py 2>&1 | tail -20

# 3) ingest NG sample
python3 scripts/ingest_ng_sample.py 2>&1 | tail -5

# 4) verify counts
python3 - <<'EOF'
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect("postgres://nomos_user:SetYourSecurePassword123!@127.0.0.1:5439/nomos")
    for q in ["SELECT count(*) FROM source",
              "SELECT jurisdiction, count(*) FROM source GROUP BY 1",
              "SELECT count(*) FROM chunk",
              "SELECT count(*) FROM chunk WHERE embedding IS NOT NULL"]:
        print(q, "->", await c.fetchval(q))
    await c.close()
asyncio.run(main())
EOF

# 5) proxy down
kill %1
```

Expected: 619 ZA chunks (BCEA 122 + Companies Act 497) + NG sample chunks,
every chunk with a non-null embedding. If you see `403 Lightning dunning`,
billing isn't cleared yet — go back to step 0.

Tip: run the two ingest scripts inside `tmux` in Cloud Shell so an idle
disconnect doesn't kill a 619-chunk embedding run mid-way.

---

## 5. Test end-to-end

```bash
SVC_URL="https://nomos-backend-staging-88191897416.us-central1.run.app"

# Health: database should flip to "ok". Redis will still say "failed" —
# expected with REDIS_FAIL_OPEN=1 and no reachable Memorystore.
curl -s "${SVC_URL}/health" ; echo

# Real search (v2 hybrid path: dense+lexical RRF -> Flash rerank -> coverage gate).
# NOTE: the correct endpoint is /api/v1/search (POST) — not /search.
curl -s -X POST "${SVC_URL}/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{"query":"What are the overtime rules under BCEA?","jurisdiction":"za"}' \
  | python3 -m json.tool | head -50
```

Expected shapes:
- **Answer**: `grounded: true`, `sources[]` with BCEA section excerpts,
  `structured.legalBasis[]` citations like `BCEA s 20`.
- **Honest refusal**: `missReason` set, `grounded: false` — e.g. ask about LRA
  or POPIA provisions; those Acts aren't ingested yet, and the gate refuses
  rather than hallucinating. This is the intended behavior.

If search 502s/500s: check logs
```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=nomos-backend-staging" \
  --limit=50 --format="table(timestamp,severity,textPayload)"
```

---

## Known limitations after this runbook

1. **Redis failed in /health** — cosmetic for testing (REDIS_FAIL_OPEN keeps
   search up). Real fix = Serverless VPC connector to the existing Memorystore
   (creation previously failed with an internal error — retry later), or a
   private-IP retry. Until then, rate-limit state is per-instance and quotas
   are unenforced.
2. **Rerank latency** — dev-tier Vertex quota = ~5-6s per Flash rerank call;
   p95 total ~7s. Known, documented in `docs/week10-rerank-calibration.md`.
   Not a deploy blocker.
3. **Corpus coverage** — only BCEA + Companies Act 71/2008 (ZA) + NG Labour
   Act sample. Many legit questions will honestly refuse until E4 ingests
   more Acts.
