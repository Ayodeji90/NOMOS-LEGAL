from functools import lru_cache
from pathlib import Path

from pydantic import Field, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    APP_NAME: str = "nomos-backend"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    API_PREFIX: str = "/api/v1"

    # Environment detection
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def is_staging(self) -> bool:
        return self.ENVIRONMENT == "staging"

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def use_real_firestore(self) -> bool:
        """Use real Firestore in staging/prod, emulator in dev"""
        return self.is_staging or self.is_production

    @property
    def use_real_redis(self) -> bool:
        """Use real Redis in staging/prod, fakeredis in dev"""
        return self.is_staging or self.is_production

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    WORKERS: int = 1

    # Database (Cloud SQL / AlloyDB PostgreSQL with pgvector)
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/nomos",
        description="Async PostgreSQL connection string with pgvector",
    )
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 3600

    # Redis (Memorystore)
    REDIS_URL: RedisDsn = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string for rate limits, quotas, caches",
    )
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_SOCKET_TIMEOUT: int = 5
    REDIS_SOCKET_CONNECT_TIMEOUT: int = 5

    # Firestore (sessions)
    FIRESTORE_PROJECT_ID: str | None = Field(
        default=None,
        description="GCP project ID for Firestore. If None, uses default credentials.",
    )
    FIRESTORE_DATABASE: str = "(default)"
    SESSION_TTL_DAYS: int = 30

    # Google Cloud / Vertex AI
    GCP_PROJECT_ID: str | None = Field(default=None, description="GCP project ID")
    GCP_REGION: str = "us-central1"
    VERTEX_AI_LOCATION: str = "us-central1"

    # Provider selection per service (model-agnostic architecture)
    QUERY_UNDERSTANDING_PROVIDER: str = Field(
        default="vertex",
        description="LLM provider for query understanding: 'vertex', 'anthropic', 'openai'",
    )
    WRITER_PROVIDER: str = Field(
        default="vertex", description="LLM provider for writer: 'vertex', 'anthropic', 'openai'"
    )
    VERIFIER_PROVIDER: str = Field(
        default="vertex", description="LLM provider for verifier: 'vertex', 'anthropic', 'openai'"
    )

    # Model names per provider for query understanding
    QUERY_UNDERSTANDING_VERTEX_MODEL: str = "gemini-2.5-flash"
    QUERY_UNDERSTANDING_ANTHROPIC_MODEL: str = "claude-3-haiku-20240307"
    QUERY_UNDERSTANDING_OPENAI_MODEL: str = "gpt-4o-mini"

    # Model names per provider for writer
    WRITER_VERTEX_MODEL: str = "gemini-2.5-flash"
    WRITER_ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"
    WRITER_OPENAI_MODEL: str = "gpt-4o"

    # Model names per provider for verifier
    VERIFIER_VERTEX_MODEL: str = "gemini-2.5-flash"
    VERIFIER_ANTHROPIC_MODEL: str = "claude-3-haiku-20240307"
    VERIFIER_OPENAI_MODEL: str = "gpt-4o-mini"

    # Fallback providers
    QUERY_UNDERSTANDING_FALLBACK_PROVIDER: str = Field(
        default="openai", description="Fallback provider for query understanding"
    )
    WRITER_FALLBACK_PROVIDER: str = Field(
        default="vertex", description="Fallback provider for writer"
    )
    VERIFIER_FALLBACK_PROVIDER: str = Field(
        default="openai", description="Fallback provider for verifier"
    )

    # API keys for non-GCP providers
    ANTHROPIC_API_KEY: str | None = Field(
        default=None, description="Anthropic API key (if not using default auth)"
    )
    OPENAI_API_KEY: str | None = Field(
        default=None, description="OpenAI API key (if not using default auth)"
    )

    # Legacy model configuration (for backward compatibility)
    MODEL_QUERY_UNDERSTANDING: str = "gemini-2.5-flash"
    MODEL_EMBEDDING: str = "text-embedding-005"
    MODEL_RERANK: str = "gemini-2.5-flash"
    MODEL_WRITER: str = "gemini-2.5-flash"
    MODEL_VERIFIER: str = "gemini-2.5-flash"
    MODEL_FALLBACK_WRITER: str = "claude-3-5-sonnet-20241022"

    # Model parameters
    QUERY_UNDERSTANDING_TEMPERATURE: float = 0.1
    QUERY_UNDERSTANDING_MAX_TOKENS: int = 1024
    RERANK_TEMPERATURE: float = 0.0
    RERANK_MAX_TOKENS: int = 512
    WRITER_TEMPERATURE: float = 0.2
    WRITER_MAX_TOKENS: int = 4096
    VERIFIER_TEMPERATURE: float = 0.0
    VERIFIER_MAX_TOKENS: int = 2048

    # Embedding
    EMBEDDING_DIMENSIONS: int = 768
    EMBEDDING_BATCH_SIZE: int = 100
    EMBEDDING_MAX_REQUEST_TOKENS: int = 18000
    EMBEDDING_PROVIDER: str = Field(
        default="mock",
        description="Embedding backend: 'vertex' (real text-embedding-005) or 'mock' (hash-based, tests only)",
    )

    # Retrieval
    RETRIEVAL_TOP_K_SPARSE: int = 50
    RETRIEVAL_TOP_K_DENSE: int = 50
    RETRIEVAL_RRF_K: int = 60
    RERANK_TOP_K: int = 12
    COVERAGE_THRESHOLD: float = 0.35

    # Rate limiting
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 30
    RATE_LIMIT_REQUESTS_PER_HOUR: int = 500
    RATE_LIMIT_BURST: int = 10
    QUOTA_DAILY_QUERIES: int = 100
    QUOTA_DAILY_WRITER_CALLS: int = 20

    # Auth
    SECRET_KEY: str = Field(
        default="dev-secret-change-in-production",
        description="Secret key for JWT signing",
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    SCRYPT_N: int = 16384
    SCRYPT_R: int = 8
    SCRYPT_P: int = 1

    # API Keys
    API_KEY_PREFIX: str = "nomos_"
    API_KEY_HASH_ROUNDS: int = 12

    # CORS
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="Allowed CORS origins",
    )
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    # Cloud Storage
    GCS_BUCKET_SOURCES: str | None = Field(
        default=None, description="GCS bucket for raw legal sources"
    )
    GCS_BUCKET_CORPUS: str | None = Field(
        default=None, description="GCS bucket for corpus archives"
    )
    GCS_BUCKET_EVAL: str | None = Field(default=None, description="GCS bucket for evaluation data")

    # Ingestion
    INGESTION_CHUNK_MAX_TOKENS: int = 512
    INGESTION_CHUNK_OVERLAP_TOKENS: int = 50
    INGESTION_RAW_DIR: Path = Field(
        default=Path("data/gcs-layout/raw/za"),
        description="Directory holding raw ZA source documents (replaces hardcoded paths)",
    )

    # Evaluation
    EVAL_GOLDEN_SET_PATH: str = "eval/golden_sets/za.jsonl"
    EVAL_NIGHTLY_ENABLED: bool = True

    # Feature flags
    FLAG_AGENT_LOOP_ENABLED: bool = False
    FLAG_CASE_LAW_ENABLED: bool = False
    FLAG_REGULATIONS_ENABLED: bool = False
    FLAG_VERIFICATION_REPAIR_ENABLED: bool = True

    # Retrieval rollout: comma-separated jurisdiction ids on the v2 hybrid
    # path (e.g. "za"). Prototype scope is ZA-only (Nigeria next);
    # unlisted jurisdictions stay on the legacy path.
    RETRIEVAL_V2_JURISDICTIONS: str = "za"

    # Observability
    ENABLE_REQUEST_LOGGING: bool = True
    ENABLE_QUERY_TRACING: bool = True
    TRACE_SAMPLE_RATE: float = 1.0
    LOG_PROMPTS: bool = False
    LOG_RESPONSES: bool = False

    # South Africa specific
    ZA_JURISDICTION_ID: str = "za"
    ZA_JURISDICTION_NAME: str = "South Africa"
    ZA_SYNONYM_DICT_PATH: str = "app/data/za_synonyms.json"

    # Nigeria specific (Week 5 E2: NG prep alongside ZA scope)
    NG_JURISDICTION_ID: str = "ng"
    NG_JURISDICTION_NAME: str = "Nigeria"
    NG_SYNONYM_DICT_PATH: str = "app/data/ng_synonyms.json"

    # Shadow traffic (Week 3 E1)
    SHADOW_TRAFFIC_SAMPLE_RATE: float = 0.1
    SHADOW_TRAFFIC_STAGING_URL: str | None = Field(
        default=None,
        description="Staging URL for shadow traffic duplication",
    )

    # Canary deployment (Week 4 E1)
    CANARY_PERCENTAGE: int = 0
    ROLLBACK_MODE: bool = False

    # Access gate (Week 1 E6)
    ACCESS_ALLOWLIST: list[str] = Field(default_factory=list)
    WAITLIST_ENABLED: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
