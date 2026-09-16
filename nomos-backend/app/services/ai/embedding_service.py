"""
Embedding service for generating text embeddings.

Provider architecture (parallel to the LLM provider layer in
``app/services/ai/providers/`` — embeddings are a separate contract per
REDESIGN.md and IMPLEMENTATION_PLAN_15W.md, "one embedder interface"):

- ``VertexEmbeddingBackend``: real Vertex AI ``text-embedding-005``
  embeddings (768-dim, cosine). Requires GCP credentials; selected via
  ``EMBEDDING_PROVIDER=vertex``. (Distinct from ``providers.vertex_provider
  .VertexAIProvider``, which serves Gemini *chat* calls.)
- ``AzureOpenAIEmbeddingBackend``: Azure OpenAI embeddings
  (``text-embedding-3-small`` deployed in the Azure OpenAI resource),
  requested at ``dimensions=768`` so vectors stay schema-compatible with
  the Vertex corpus (same 768-dim column + HNSW index). Selected via
  ``EMBEDDING_PROVIDER=azure_openai``.
- ``MockEmbeddingBackend``: deterministic hash-based vectors for tests and
  offline development ONLY. Selected via ``EMBEDDING_PROVIDER=mock``.
  Vectors from this backend are NOT semantically meaningful and must never
  be used for retrieval quality evaluation or production upserts.

The facade ``EmbeddingService`` (and the module-level ``embedding_service``
instance) keeps the pre-existing API: ``generate_embeddings``, ``embed_chunk``
and ``embed_chunks``.
"""

import asyncio
import hashlib
import logging
import math
from typing import Protocol

from app.chunkers.za_chunker import LegalChunk
from app.core.config import settings
from app.services.ai.providers.config_helper import get_embedding_config

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    """Interface every embedding backend must satisfy."""

    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, returning one vector per input, same order."""
        ...


class MockEmbeddingBackend:
    """Deterministic hash-based embeddings. For tests/offline dev only."""

    def __init__(self, model_name: str, dimensions: int, batch_size: int | None = None):
        self._model_name = model_name
        self._dimensions = dimensions
        # batch_size accepted for backend-interface parity; hashing needs no batching.
        self._batch_size = batch_size
        logger.warning(
            "MockEmbeddingBackend active: vectors are hash-based and NOT "
            "semantically meaningful. Do not use for retrieval evaluation."
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _hash_embedding(self, text: str) -> list[float]:
        """Deterministic pseudo-embedding from successive MD5 rounds."""
        values: list[float] = []
        counter = 0
        while len(values) < self._dimensions:
            digest = hashlib.md5(f"{text}::{counter}".encode()).digest()
            for i in range(0, len(digest), 2):
                chunk = digest[i : i + 2]
                value = int.from_bytes(chunk, "big") / 65535.0 * 2.0 - 1.0
                values.append(value)
                if len(values) == self._dimensions:
                    break
            counter += 1
        # Normalize so cosine similarity is well-defined.
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [self._hash_embedding(text) for text in texts]


class VertexEmbeddingBackend:
    """Real Vertex AI text-embedding-005 embeddings (768-dim, cosine).

    Not to be confused with ``providers.vertex_provider.VertexAIProvider``
    (Gemini chat). Embeddings are a separate provider contract.
    """

    def __init__(
        self,
        model_name: str | None = None,
        dimensions: int | None = None,
        batch_size: int | None = None,
    ):
        self._model_name = model_name or settings.MODEL_EMBEDDING
        self._dimensions = dimensions or settings.EMBEDDING_DIMENSIONS
        self._batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        self._max_request_tokens = settings.EMBEDDING_MAX_REQUEST_TOKENS
        self._project = settings.GCP_PROJECT_ID
        self._location = settings.VERTEX_AI_LOCATION
        # Import lazily so the app can boot without GCP packages/creds when
        # the mock provider is selected.
        try:
            import vertexai
            from vertexai.language_models import TextEmbeddingModel
        except ImportError as exc:  # pragma: no cover - env-specific
            raise RuntimeError(
                "EMBEDDING_PROVIDER=vertex but the 'vertexai' package is not "
                "installed. Install project dependencies first."
            ) from exc
        # The SDK requires vertexai.init(project=...) before any call; the
        # project is NOT a get_embeddings() parameter.
        vertexai.init(project=self._project, location=self._location)
        self._model = TextEmbeddingModel.from_pretrained(self._model_name)
        logger.info(
            "VertexEmbeddingBackend initialized: model=%s project=%s location=%s dims=%d",
            self._model_name,
            self._project,
            self._location,
            self._dimensions,
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _embed_batch_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous Vertex call; executed in a worker thread."""
        from vertexai.language_models import TextEmbeddingInput

        task_type = "RETRIEVAL_DOCUMENT"  # corpus-side embeddings
        inputs = [TextEmbeddingInput(text=t, task_type=task_type) for t in texts]
        # 768 is a supported output_dimensionality for text-embedding-005.
        # Project/location come from vertexai.init() -- not call kwargs.
        result = self._model.get_embeddings(
            inputs, output_dimensionality=self._dimensions
        )
        vectors: list[list[float]] = []
        for i, embedding in enumerate(result):
            values = list(embedding.values)
            if len(values) != self._dimensions:
                raise RuntimeError(
                    f"Vertex returned {len(values)} dims at position {i}; "
                    f"expected {self._dimensions}."
                )
            vectors.append(values)
        return vectors

    def _pack_batches(self, texts: list[str]) -> list[list[str]]:
        """Pack texts into batches bounded by count AND estimated request tokens.

        Vertex caps each embedding *request* at 20k input tokens (model-level),
        so a naive fixed-size batch of long texts can exceed it. We estimate
        tokens as chars/4 (close enough for English legal text) and pack
        greedily under EMBEDDING_MAX_REQUEST_TOKENS, additionally capped by
        EMBEDDING_BATCH_SIZE items.
        """
        batches: list[list[str]] = []
        current: list[str] = []
        current_tokens = 0
        for text in texts:
            est = max(1, len(text) // 4)
            if current and (
                len(current) >= self._batch_size
                or current_tokens + est > self._max_request_tokens
            ):
                batches.append(current)
                current, current_tokens = [], 0
            if not current and est > self._max_request_tokens:
                logger.warning(
                    "Single text exceeds token budget (%d est > %d); "
                    "sending alone (may be rejected by the API)",
                    est,
                    self._max_request_tokens,
                )
            current.append(text)
            current_tokens += est
        if current:
            batches.append(current)
        return batches

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        done = 0
        for batch in self._pack_batches(texts):
            # Retries with capped exponential backoff for transient 429/5xx.
            # Quota (429) errors get longer waits: fresh projects have a
            # per-minute online-prediction quota, so the retry must outlast
            # the 60s window rather than the old 1+2+4+8s schedule.
            last_error: Exception | None = None
            batch_vectors: list[list[float]] | None = None
            for attempt in range(7):
                try:
                    batch_vectors = await asyncio.to_thread(self._embed_batch_sync, batch)
                    last_error = None
                    break
                except Exception as exc:  # noqa: BLE001 - retry any API error
                    last_error = exc
                    is_quota = "429" in str(exc) or "Quota exceeded" in str(exc)
                    wait = min(65.0, 15.0 * (2 ** (attempt // 2))) if is_quota else 2**attempt
                    logger.warning(
                        "Vertex embedding batch failed (attempt %d/7%s): %s -- retrying in %ds",
                        attempt + 1,
                        ", quota" if is_quota else "",
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
            if last_error is not None or batch_vectors is None:
                raise RuntimeError(
                    f"Vertex embedding failed after 7 attempts: {last_error}"
                ) from last_error
            vectors.extend(batch_vectors)
            done += len(batch)
            logger.info(
                "Embedded %d/%d texts (model=%s)",
                done,
                len(texts),
                self._model_name,
            )
        return vectors


class AzureOpenAIEmbeddingBackend:
    """Azure OpenAI embeddings (text-embedding-3-small) at 768 dims.

    The critical property: ``text-embedding-3-small`` accepts a
    ``dimensions`` parameter, so we request **768** to stay schema-compatible
    with the Vertex text-embedding-005 corpus (same ``vector(768)`` column and
    HNSW index — no migration, no re-embedding).

    Batching: Azure caps each request at 16k input tokens for
    text-embedding-3-small (2048 array elements); we reuse the same greedy
    char/4 token estimator as the Vertex backend under
    EMBEDDING_MAX_REQUEST_TOKENS, additionally capped by EMBEDDING_BATCH_SIZE.
    """

    # Azure hard cap per request for this model.
    _MAX_ITEMS_PER_REQUEST = 2048

    def __init__(
        self,
        model_name: str | None = None,
        dimensions: int | None = None,
        batch_size: int | None = None,
    ):
        self._model_name = model_name or "text-embedding-3-small"
        self._dimensions = dimensions or settings.EMBEDDING_DIMENSIONS
        self._batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        self._max_request_tokens = settings.EMBEDDING_MAX_REQUEST_TOKENS
        self._endpoint = settings.AZURE_OPENAI_ENDPOINT
        self._api_key = settings.AZURE_OPENAI_API_KEY
        self._api_version = settings.AZURE_OPENAI_API_VERSION
        if not self._endpoint or not self._api_key:
            raise ValueError(
                "EMBEDDING_PROVIDER=azure_openai requires AZURE_OPENAI_ENDPOINT "
                "and AZURE_OPENAI_API_KEY"
            )

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _client(self):
        """Lazy client construction (keeps import side-effect-free)."""
        try:
            from openai import AsyncAzureOpenAI
        except ImportError as exc:  # pragma: no cover - env-specific
            raise RuntimeError(
                "EMBEDDING_PROVIDER=azure_openai but the 'openai' package is "
                "not installed. Install project dependencies first."
            ) from exc
        return AsyncAzureOpenAI(
            api_key=self._api_key,
            api_version=self._api_version,
            azure_endpoint=self._endpoint,
            max_retries=0,  # we handle retries ourselves
        )

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._client()
        vectors: list[list[float]] = []
        done = 0
        for batch in self._pack_batches(texts):
            batch_vectors: list[list[float]] | None = None
            # Azure S0 free-tier rate limit is extremely tight. Each retry
            # attempt IS a request that resets the cooldown window, so we
            # must NOT retry rapidly. Strategy: try up to 5 times, but on
            # a 429, always wait 65s (just past the 60s retry-after).
            for attempt in range(5):
                try:
                    resp = await client.embeddings.create(
                        model=self._model_name,
                        input=batch,
                        dimensions=self._dimensions,
                    )
                    batch_vectors = [item.embedding for item in resp.data]
                    break
                except Exception as exc:  # noqa: BLE001 - retry any API error
                    is_rate = "429" in str(exc) or "rate" in str(exc).lower()
                    if is_rate:
                        wait = 20.0  # small batches can retry every 20s
                    else:
                        wait = min(2.0 ** attempt, 10.0)
                    logger.warning(
                        "Azure embedding batch failed (attempt %d/5%s): %s -- waiting %.0fs",
                        attempt + 1, " [rate-limit]" if is_rate else "",
                        exc, wait,
                    )
                    await asyncio.sleep(wait)
            if batch_vectors is None:
                raise RuntimeError(
                    f"Azure OpenAI embedding failed after 5 attempts"
                )
            if len(batch_vectors) != len(batch):
                raise RuntimeError(
                    f"Azure returned {len(batch_vectors)} vectors for {len(batch)} inputs"
                )
            vectors.extend(batch_vectors)
            done += len(batch)
            logger.info(
                "Embedded %d/%d texts (deployment=%s dims=%d)",
                done,
                len(texts),
                self._model_name,
                self._dimensions,
            )
        return vectors

    def _pack_batches(self, texts: list[str]) -> list[list[str]]:
        """Greedy packing under item-count and estimated-token caps.

        Mirrors the Vertex backend's estimator (chars/4) under
        EMBEDDING_MAX_REQUEST_TOKENS, capped by EMBEDDING_BATCH_SIZE items
        and Azure's 2048-items-per-request hard limit.
        """
        batches: list[list[str]] = []
        current: list[str] = []
        current_tokens = 0
        for text in texts:
            est = max(1, len(text) // 4)
            if current and (
                len(current) >= min(self._batch_size, self._MAX_ITEMS_PER_REQUEST)
                or current_tokens + est > self._max_request_tokens
            ):
                batches.append(current)
                current, current_tokens = [], 0
            current.append(text)
            current_tokens += est
        if current:
            batches.append(current)
        return batches


def get_embedding_provider() -> EmbeddingProvider:
    """Build the configured embedding provider.

    Selected via ``EMBEDDING_PROVIDER``:
    - ``vertex``: real text-embedding-005 (requires GCP creds at call time)
    - ``azure_openai``: Azure OpenAI text-embedding-3-small at 768 dims
      (cloud-neutral fallback; schema-compatible with the Vertex corpus)
    - ``mock``: deterministic hash vectors (tests/offline only)

    Model/dimension/batch config comes from ``config_helper`` so embedding
    settings live in the same place as every other service's.
    """
    provider = settings.EMBEDDING_PROVIDER.strip().lower()
    if provider == "vertex":
        return VertexEmbeddingBackend(**get_embedding_config())
    if provider == "azure_openai":
        return AzureOpenAIEmbeddingBackend(**get_embedding_config())
    if provider == "mock":
        return MockEmbeddingBackend(**get_embedding_config())
    raise ValueError(
        f"Unknown EMBEDDING_PROVIDER '{settings.EMBEDDING_PROVIDER}' "
        "(expected 'vertex', 'azure_openai' or 'mock')"
    )


class EmbeddingService:
    """Facade over the configured embedding provider (stable public API)."""

    def __init__(self, provider: EmbeddingProvider | None = None):
        self._provider = provider or get_embedding_provider()
        self.model_name = self._provider.model_name
        self.embedding_dimensions = self._provider.dimensions

    @property
    def provider(self) -> EmbeddingProvider:
        return self._provider

    async def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        return await self._provider.generate_embeddings(texts)

    async def embed_chunk(self, chunk: LegalChunk) -> LegalChunk:
        """Generate embedding for a single chunk and update the chunk object."""
        embeddings = await self.generate_embeddings([chunk.content])
        if embeddings:
            chunk.embedding = embeddings[0]
        return chunk

    async def embed_chunks(self, chunks: list[LegalChunk]) -> list[LegalChunk]:
        """Generate embeddings for a list of chunks, attaching in order."""
        if not chunks:
            return []
        texts = [chunk.content for chunk in chunks]
        embeddings = await self.generate_embeddings(texts)
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            chunk.embedding = embedding
        return chunks


class _LazyEmbeddingService:
    """Import-time placeholder that builds the real service on first use.

    Eagerly constructing EmbeddingService runs ``vertexai.init()`` and a live
    model-metadata call at import time, which makes every module that imports
    this one (test collection, offline tooling) fail whenever GCP is
    unreachable or denied. With the proxy, ``from app.services.ai import
    embedding_service`` is side-effect-free; the real provider is built on
    first attribute access or call.
    """

    _real: EmbeddingService | None = None

    def _materialize(self) -> EmbeddingService:
        if self._real is None:
            self._real = EmbeddingService()
        return self._real

    def __getattr__(self, name: str):
        return getattr(self._materialize(), name)

    def __setattr__(self, name: str, value):
        if name == "_real":
            object.__setattr__(self, name, value)
            return
        setattr(self._materialize(), name, value)


# Global instance for dependency injection (lazy; see _LazyEmbeddingService).
embedding_service = _LazyEmbeddingService()
