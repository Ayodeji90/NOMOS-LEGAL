# NOMOS on Azure — Staging Deploy Runbook

**Goal:** run the full v2 stack on Azure (Container Apps + PostgreSQL Flexible + Azure OpenAI) using the provider-agnostic seam, within the ~$19 free-trial budget.

**Cost model (test windows):**
- Container Apps consumption: **$0** (free grant: 180k vCPU-s + 2M req/mo; scale-to-zero)
- PostgreSQL Flexible B1ms: **~$0.02/hour, $0 compute while stopped** → stop when idle
- Azure OpenAI gpt-4o-mini + text-embedding-3-small: **~$0.05–0.15 per full test session**
- ACR Basic: ~$0.17/day (the only always-on cost)
- **Full test cycle (deploy + ingest + ~50 queries) ≈ $0.30–0.50. Stop PG when done and it's pennies.**

**Code prerequisites (already merged):** `azure_openai` chat provider, `AzureOpenAIEmbeddingBackend` (768-dim, schema-compatible with the GCP corpus), `SESSION_STORE=postgres` + migration 005, `REDIS_FAIL_OPEN` flag, `openai` SDK in pyproject.

---

## 0. One-time setup

```bash
# Variables used throughout (copy-paste as-is)
RG=nomos-rg
LOC=eastus
PG_ADMIN=nomosadmin
PG_PASS='ChangeMe-Staging123!'        # single-quote it: no shell history expansion
ACR_NAME=nomosacr$RANDOM              # must be globally unique, alphanumeric
PG_SERVER=nomos-pg-$RANDOM            # must be globally unique
AOAI_NAME=nomos-aoai-$RANDOM
SUB=$(az account show --query id -o tsv)

az group create --name $RG --location $LOC
```

> **Free-trial note:** if your subscription is a Free/Student trial, some providers start unregistered. Register the ones we need (takes ~1 min each):
> ```bash
> az provider register --namespace Microsoft.ContainerInstance   # ACI backend for ACR tasks
> az provider register --namespace Microsoft.App                 # Container Apps
> az provider register --namespace Microsoft.OperationalInsights # CA logs workspace
> az provider register --namespace Microsoft.DBforPostgreSQL
> az provider register --namespace Microsoft.CognitiveServices
> # check: az provider list --query "[?namespace=='Microsoft.App'].registrationState" -o tsv
> ```

---

## 1. Azure OpenAI resource + deployments

```bash
az cognitiveservices account create \
  --name $AOAI_NAME --resource-group $RG --location $LOC \
  --kind OpenAI --sku S0 --yes

# Deployments (deployment name == MODEL_*_AZURE_OPENAI_MODEL in config):
az cognitiveservices account deployment create \
  --name $AOAI_NAME --resource-group $RG \
  --deployment-name nomos-gpt-4o-mini \
  --model-name gpt-4o-mini --model-version "2024-07-18" \
  --model-format OpenAI --sku-capacity 10 --sku-name Standard

az cognitiveservices account deployment create \
  --name $AOAI_NAME --resource-group $RG \
  --deployment-name text-embedding-3-small \
  --model-name text-embedding-3-small --model-version "1" \
  --model-format OpenAI --sku-capacity 10 --sku-name Standard

# Keys + endpoint (needed in step 3 env vars):
AOAI_ENDPOINT=$(az cognitiveservices account show \
  --name $AOAI_NAME --resource-group $RG --query properties.endpoint -o tsv)
AOAI_KEY=$(az cognitiveservices account keys list \
  --name $AOAI_NAME --resource-group $RG --query key1 -o tsv)
echo "endpoint=$AOAI_ENDPOINT"
```

> **If the gpt-4o-mini deployment fails with a capacity/quota error:** eastus is sometimes full for new subscriptions. Retry in `swedencentral` (delete the resource, recreate there — the resource **must** be in the region that has capacity; Container Apps and PG can stay in eastus).

---

## 2. PostgreSQL Flexible Server (pgvector)

```bash
az postgres flexible-server create \
  --name $PG_SERVER --resource-group $RG --location $LOC \
  --admin-user $PG_ADMIN --admin-password "$PG_PASS" \
  --sku-name Standard_B1ms --tier Burstable \
  --storage-size 32 --version 15 \
  --public-access None

# pgvector support:
az postgres flexible-server parameter set \
  --resource-group $RG --server-name $PG_SERVER \
  --name azure.extensions --value vector

# Database + a schema-scoped app user:
az postgres flexible-server db create \
  --resource-group $RG --server-name $PG_SERVER --database-name nomos

# Firewall: allow only your current IP for migrations/ingest (service connector
# handles Container Apps -> PG later):
MY_IP=$(curl -s ifconfig.me)
az postgres flexible-server firewall-rule create \
  --resource-group $RG --server-name $PG_SERVER \
  --name my-ip --start-ip-address $MY_IP --end-ip-address $MY_IP
```

**Connection string for local migrate/ingest (step 4):**

```
postgresql+asyncpg://$PG_ADMIN:$PG_PASS@$PG_SERVER.postgres.database.azure.com:5432/nomos?sslmode=require
```

---

## 3. Container Apps environment + app

```bash
# ACR + build (from the repo root, nomos-backend/ contains the Dockerfile):
az acr create --name $ACR_NAME --resource-group $RG --sku Basic
az acr build \
  --registry $ACR_NAME --image nomos-backend:azure-staging \
  --file nomos-backend/Dockerfile nomos-backend/

# CA environment (consumption; Log Analytics auto-created):
az containerapp env create \
  --name nomos-env --resource-group $RG --location $LOC
```

```bash
az containerapp create \
  --name nomos-backend-staging \
  --resource-group $RG \
  --environment nomos-env \
  --image $ACR_NAME.azurecr.io/nomos-backend:azure-staging \
  --target-port 8000 \
  --ingress external \
  --min-replicas 0 --max-replicas 3 \
  --secrets aoai-key=$AOAI_KEY pg-pass="$PG_PASS" \
  --env-vars \
    ENVIRONMENT=staging \
    DATABASE_URL="postgresql+asyncpg://$PG_ADMIN:$PG_PASS@$PG_SERVER.postgres.database.azure.com:5432/nomos?sslmode=require" \
    REDIS_FAIL_OPEN=1 \
    AZURE_OPENAI_ENDPOINT=$AOAI_ENDPOINT \
    AZURE_OPENAI_API_KEY=secretref:aoai-key \
    AZURE_OPENAI_API_VERSION=2024-10-21 \
    QUERY_UNDERSTANDING_PROVIDER=azure_openai \
    WRITER_PROVIDER=azure_openai \
    VERIFIER_PROVIDER=azure_openai \
    EMBEDDING_PROVIDER=azure_openai \
    SESSION_STORE=postgres \
    GCP_PROJECT_ID=unused \
    FIRESTORE_PROJECT_ID=unused \
    SECRET_KEY=staging-secret-change-me-min-32-chars!! \
    LOG_LEVEL=INFO
```

> **Note on provider env vars:** config reads `QUERY_UNDERSTANDING_PROVIDER` etc. via the provider seam; rerank follows query-understanding's provider (see `rerank.py`). `SESSION_STORE=postgres` uses migration 005's table.

---

## 4. Migrate + ingest (from this machine, one-time per fresh DB)

```bash
# App user (least privilege; the app can use admin too but shouldn't):
psql "postgresql://$PG_ADMIN:$PG_PASS@$PG_SERVER.postgres.database.azure.com:5432/nomos?sslmode=require" \
  -c "CREATE ROLE nomos_user LOGIN PASSWORD '$PG_PASS';"
psql "..." -c "GRANT ALL ON SCHEMA public TO nomos_user;"   # or run everything as admin

# From nomos-backend/ with the venv active:
DATABASE_URL="postgresql+asyncpg://$PG_ADMIN:$PG_PASS@$PG_SERVER.postgres.database.azure.com:5432/nomos?sslmode=require" \
  alembic upgrade head

# Ingest (real Azure embeddings; ~630 chunks, pennies):
DATABASE_URL="postgresql+asyncpg://$PG_ADMIN:$PG_PASS@$PG_SERVER.postgres.database.azure.com:5432/nomos?sslmode=require" \
  .venv/bin/python scripts/cleanup_and_reingest.py --jurisdiction za

# NG sample:
DATABASE_URL="postgresql+asyncpg://$PG_ADMIN:$PG_PASS@$PG_SERVER.postgres.database.azure.com:5432/nomos?sslmode=require" \
  .venv/bin/python scripts/ingest_ng_sample.py
```

---

## 5. Test

```bash
APP_URL=$(az containerapp show --name nomos-backend-staging \
  --resource-group $RG --query properties.configuration.ingress.fqdn -o tsv)
echo $APP_URL

curl -s https://$APP_URL/health | jq .
# expect: {"status":"healthy","checks":{"database":"ok","redis":"fail-open (ok)"}}

curl -s -X POST https://$APP_URL/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"What are the overtime rules under the BCEA?","jurisdiction":"za"}' | jq .
# expect: hits from BCEA sections + coverage >= 0.5 (or an honest refusal)

curl -s -X POST https://$APP_URL/api/v1/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"What is the notice period for dismissal under the Labour Act?","jurisdiction":"ng"}' | jq .
```

**Expected costs after this runbook:** ACR (~$0.17/day) + PG while running (~$0.02/h). **Stop PG between sessions:**

```bash
az postgres flexible-server stop  --resource-group $RG --name $PG_SERVER
az postgres flexible-server start --resource-group $RG --name $PG_SERVER
```

---

## 6. Tear-down (when testing is done)

```bash
az group delete --name $RG --yes --no-wait   # removes everything in one shot
```

---

## Known caveats (honest list)

1. **Free-trial subscriptions can't always create Azure OpenAI resources** — if `az cognitiveservices account create` fails with a policy/quota error, the account may need an upgrade to Pay-As-You-Go (still free-grant eligible for CA). Check: `az provider list --query "[?namespace=='Microsoft.CognitiveServices']"`.
2. **`text-embedding-3-small` at 768 dims is NOT vector-identical to Vertex text-embedding-005** — same schema (768 dims, cosine) but different vector space. **Do not mix** embeddings from both providers in one table: pick one provider per corpus and stay consistent (the ingest scripts embed query + corpus with the same configured backend, so this only matters if you re-ingest with a different provider than you query with).
3. **Redis is intentionally absent** (`REDIS_FAIL_OPEN=1`): rate limits/quotas fail open per instance. Remove the flag (and add a real Redis) before any production exposure.
4. **`sslmode=require`** in the PG URL is mandatory — Flexible Server rejects non-TLS by default; asyncpg honours the query param.
5. **First cold start** of the Container App takes ~30–60s (scale-from-zero + DB connect); subsequent requests are fast.
