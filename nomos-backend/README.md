# NOMOS v2 Backend

Python FastAPI backend for NOMOS Legal AI - replacing the Node/Express backend with a proper AI/RAG architecture.

## Architecture

- **Framework**: FastAPI (async, typed, OpenAPI)
- **Database**: PostgreSQL + pgvector (Cloud SQL / AlloyDB)
- **Cache/Rate Limits**: Redis (Memorystore)
- **Sessions**: Firestore
- **AI/ML**: Vertex AI (Gemini Flash/Pro, text-embedding-005)
- **Container**: Cloud Run
- **CI/CD**: GitHub Actions

## Quick Start (Local Development)

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local development without Docker)

### Using Docker Compose (Recommended)

```bash
cd nomos-backend
cp .env.example .env
docker compose up --build
```

This starts:
- PostgreSQL with pgvector on port 5432
- Redis on port 6379
- Firestore emulator on port 8081
- Backend API on port 8080 with hot reload

### Verify It's Working

```bash
# Health checks
curl http://localhost:8080/health
curl http://localhost:8080/ready
curl http://localhost:8080/live

# API docs (development only)
open http://localhost:8080/docs
```

### Local Development Without Docker

```bash
cd nomos-backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Start PostgreSQL and Redis separately, then:
cp .env.example .env
# Edit .env with your local DB/Redis URLs

alembic upgrade head
uvicorn app.main:app --reload --port 8080
```

## Project Structure

```
nomos-backend/
├── app/
│   ├── api/v1/           # API routes (auth, search, draft, review, improve)
│   ├── core/             # Core modules (config, auth, redis, firestore, rate_limit)
│   ├── db/               # Database (session, init, base)
│   ├── models/           # SQLAlchemy models
│   ├── services/         # Business logic (to be added)
│   ├── schemas/          # Pydantic schemas (to be added)
│   └── utils/            # Utilities (to be added)
├── tests/                # Pytest tests
├── alembic/              # Database migrations
├── scripts/              # SQL scripts
├── docker-compose.yml    # Local development stack
├── Dockerfile.dev        # Multi-stage Dockerfile
├── pyproject.toml        # Dependencies & tool config
└── .env.example          # Environment template
```

## API Endpoints

All endpoints prefixed with `/api/v1`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/register` | POST | Register new user |
| `/auth/login` | POST | Login (OAuth2 password flow) |
| `/auth/refresh` | POST | Refresh access token |
| `/auth/logout` | POST | Logout |
| `/auth/me` | GET | Current user profile |
| `/auth/api-keys` | GET/POST/DELETE | Manage API keys |
| `/search` | POST | Legal search (grounded) |
| `/draft` | POST | Draft documents |
| `/review` | POST | Review documents |
| `/improve` | POST | Improve documents |

## Configuration

All configuration via environment variables (see `.env.example`). Key settings:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL async connection string |
| `REDIS_URL` | Redis connection string |
| `FIRESTORE_PROJECT_ID` | GCP project for Firestore |
| `GCP_PROJECT_ID` | GCP project for Vertex AI |
| `VERTEX_AI_LOCATION` | Vertex AI region |
| `SECRET_KEY` | JWT signing key (32+ chars) |
| `ENVIRONMENT` | `development` / `production` |

## Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=app --cov-report=html

# Specific test file
pytest tests/test_auth.py -v
```

## Code Quality

```bash
# Lint
ruff check app tests

# Format
ruff format app tests

# Type check
mypy app

# All checks (run in CI)
ruff check app tests && ruff format --check app tests && mypy app && pytest
```

## Deployment

### Cloud Run (Production)

```bash
# Build and push
gcloud builds submit --tag gcr.io/PROJECT_ID/nomos-backend

# Deploy
gcloud run deploy nomos-backend \
  --image gcr.io/PROJECT_ID/nomos-backend \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars=ENVIRONMENT=production,...
```

### Required GCP Services
- Cloud Run
- Cloud SQL (PostgreSQL) or AlloyDB with pgvector
- Memorystore (Redis)
- Firestore
- Vertex AI
- Secret Manager
- Cloud Storage
- Artifact Registry

## Phase Status

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ Complete | Platform, data, local dev, auth, rate limits, API skeleton |
| 2 | ⬜ Pending | Corpus model & ingestion for ZA |
| 3 | ⬜ Pending | Hybrid retrieval, query understanding |
| 4 | ⬜ Pending | Writer, grounding v2, verification |
| 5 | ⬜ Pending | Eval harness, CI gates |
| 6 | ⬜ Pending | Product integration, Word add-in |

## License

Proprietary - NOMOS Legal AI