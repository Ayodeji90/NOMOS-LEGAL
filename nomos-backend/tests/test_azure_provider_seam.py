"""Tests for the Azure OpenAI provider seam (Week: Azure staging path).

Covers:
- factory registration + per-service model resolution (azure_openai)
- AzureOpenAIProvider chat/JSON behaviour against a mocked AsyncAzureOpenAI
- embedding-provider selection for EMBEDDING_PROVIDER=azure_openai
- AzureOpenAIEmbeddingBackend: 768-dim contract, batching, retries
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.services.ai.embedding_service import (
    AzureOpenAIEmbeddingBackend,
    get_embedding_provider,
)
from app.services.ai.providers.azure_openai_provider import AzureOpenAIProvider
from app.services.ai.providers.config_helper import get_model_name_for_service
from app.services.ai.providers.factory import ProviderFactory


@pytest.fixture
def azure_creds(monkeypatch):
    """Set fake Azure credentials for direct backend construction."""
    monkeypatch.setattr(settings, "AZURE_OPENAI_ENDPOINT", "https://r.openai.azure.com")
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", "test-key")

# ---------------------------------------------------------------------------
# Provider seam resolution
# ---------------------------------------------------------------------------


def test_factory_creates_azure_openai_provider():
    provider = ProviderFactory.create(
        "azure_openai",
        "nomos-gpt-4o-mini",
        endpoint="https://res.openai.azure.com",
        api_key="k",
    )
    assert isinstance(provider, AzureOpenAIProvider)
    assert provider.provider_name == "azure_openai"
    assert provider._model_name == "nomos-gpt-4o-mini"


def test_model_names_for_azure_openai_per_service():
    for service in ("query_understanding", "writer", "verifier"):
        assert (
            get_model_name_for_service(service, "azure_openai") == "nomos-gpt-4o-mini"
        )


# ---------------------------------------------------------------------------
# Chat provider behaviour (mocked SDK)
# ---------------------------------------------------------------------------


def _fake_chat_response(content: str):
    choice = SimpleNamespace(message=SimpleNamespace(content=content))
    return SimpleNamespace(choices=[choice])


def test_missing_credentials_raises_on_client_build():
    provider = AzureOpenAIProvider(
        "nomos-gpt-4o-mini", endpoint=None, api_key=None, api_version="2024-10-21"
    )
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="credentials missing"):
            provider._get_client()


async def test_generate_json_roundtrip():
    provider = AzureOpenAIProvider(
        "nomos-gpt-4o-mini", endpoint="https://r.openai.azure.com", api_key="k"
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_fake_chat_response('```json\n{"intent": "law_lookup"}\n```')
    )
    with patch.object(provider, "_get_client", return_value=client):
        out = await provider.generate_json("sys", "user")
    assert out == {"intent": "law_lookup"}
    # Azure contract: model kwarg is the deployment name; JSON mode requested.
    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "nomos-gpt-4o-mini"
    assert kwargs["response_format"] == {"type": "json_object"}


async def test_generate_text_returns_content():
    provider = AzureOpenAIProvider(
        "nomos-gpt-4o-mini", endpoint="https://r.openai.azure.com", api_key="k"
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_fake_chat_response("plain answer")
    )
    with patch.object(provider, "_get_client", return_value=client):
        assert await provider.generate_text("s", "u") == "plain answer"


async def test_generate_json_invalid_json_raises():
    provider = AzureOpenAIProvider(
        "nomos-gpt-4o-mini", endpoint="https://r.openai.azure.com", api_key="k"
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(
        return_value=_fake_chat_response("no json here")
    )
    with patch.object(provider, "_get_client", return_value=client):
        with pytest.raises(ValueError, match="no JSON"):
            await provider.generate_json("s", "u")


# ---------------------------------------------------------------------------
# Embedding backend selection + contract
# ---------------------------------------------------------------------------


def test_embedding_provider_selection_azure(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "azure_openai")
    monkeypatch.setattr(settings, "AZURE_OPENAI_ENDPOINT", "https://r.openai.azure.com")
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", "k")
    backend = get_embedding_provider()
    assert isinstance(backend, AzureOpenAIEmbeddingBackend)


def test_embedding_backend_requires_credentials(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_PROVIDER", "azure_openai")
    monkeypatch.setattr(settings, "AZURE_OPENAI_ENDPOINT", None)
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", None)
    with pytest.raises(ValueError, match="AZURE_OPENAI_ENDPOINT"):
        get_embedding_provider()


def test_embedding_backend_defaults_to_768_dims(monkeypatch, azure_creds):
    monkeypatch.setattr(settings, "AZURE_OPENAI_ENDPOINT", "https://r.openai.azure.com")
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", "k")
    backend = AzureOpenAIEmbeddingBackend()
    # Schema-compatibility contract: matches EMBEDDING_DIMENSIONS (vector(768)).
    assert backend.dimensions == settings.EMBEDDING_DIMENSIONS == 768
    assert backend.model_name == "text-embedding-3-small"


def test_pack_batches_respects_item_and_token_caps(azure_creds):
    backend = AzureOpenAIEmbeddingBackend(
        model_name="text-embedding-3-small", dimensions=768, batch_size=3
    )
    texts = [f"text-{i}" for i in range(7)]
    batches = backend._pack_batches(texts)
    assert all(len(b) <= 3 for b in batches)
    assert [len(b) for b in batches] == [3, 3, 1]
    assert sum(batches, []) == texts


async def test_generate_embeddings_uses_dimensions_and_batches(azure_creds):
    backend = AzureOpenAIEmbeddingBackend(
        model_name="text-embedding-3-small", dimensions=768, batch_size=2
    )

    async def fake_create(**kwargs):
        assert kwargs["dimensions"] == 768
        assert len(kwargs["input"]) <= 2
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1] * 768) for _ in kwargs["input"]]
        )

    client = MagicMock()
    client.embeddings.create = AsyncMock(side_effect=fake_create)
    with patch.object(backend, "_client", return_value=client):
        vectors = await backend.generate_embeddings(["a", "b", "c"])
    assert len(vectors) == 3
    assert all(len(v) == 768 for v in vectors)
    assert client.embeddings.create.await_count == 2  # batch_size=2 -> 2 calls


async def test_generate_embeddings_retries_on_rate_limit(azure_creds):
    backend = AzureOpenAIEmbeddingBackend(dimensions=768, batch_size=10)
    calls = {"n": 0}

    async def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("429 rate limited")
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.2] * 768)])

    client = MagicMock()
    client.embeddings.create = AsyncMock(side_effect=flaky)
    with patch.object(backend, "_client", return_value=client), patch.object(
        asyncio, "sleep", new=AsyncMock()
    ):
        vectors = await backend.generate_embeddings(["one text"])
    assert len(vectors) == 1 and len(vectors[0]) == 768
    assert calls["n"] == 3


async def test_generate_embeddings_empty_input_is_noop(azure_creds):
    backend = AzureOpenAIEmbeddingBackend(dimensions=768)
    assert await backend.generate_embeddings([]) == []
