"""Helper functions for provider configuration.

This module provides utilities for getting the correct model name and configuration
for a service based on the selected provider.
"""

from app.core.config import settings


def get_model_name_for_service(service: str, provider: str) -> str:
    """Get the model name for a service based on the provider.

    Args:
        service: Service name ('query_understanding', 'writer', 'verifier', 'rerank')
        provider: Provider name ('vertex', 'anthropic', 'openai', 'azure_openai')

    Returns:
        Model name for the service and provider combination
    """
    service_upper = service.upper()
    provider_upper = provider.upper()

    env_var = f"{service_upper}_{provider_upper}_MODEL"

    return getattr(settings, env_var, "gemini-1.5-flash")


def get_provider_config(provider: str) -> dict:
    """Get provider-specific configuration.

    Args:
        provider: Provider name ('vertex', 'anthropic', 'openai')

    Returns:
        Dictionary of provider-specific configuration
    """
    config = {}

    if provider == "vertex":
        config["project_id"] = settings.GCP_PROJECT_ID
        config["location"] = settings.VERTEX_AI_LOCATION
    elif provider == "anthropic":
        config["api_key"] = settings.ANTHROPIC_API_KEY
    elif provider == "openai":
        config["api_key"] = settings.OPENAI_API_KEY
    elif provider == "azure_openai":
        config["endpoint"] = settings.AZURE_OPENAI_ENDPOINT
        config["api_key"] = settings.AZURE_OPENAI_API_KEY
        config["api_version"] = settings.AZURE_OPENAI_API_VERSION

    return config


def get_embedding_config() -> dict:
    """Get embedding-service configuration (model, dimensions, batch size).

    Embeddings are a separate provider contract from chat LLM calls (see
    REDESIGN.md -- "one embedder interface"), so this helper mirrors
    ``get_model_name_for_service`` for the embedding backend instead of
    reusing the chat-model lookup.

    Returns:
        Keyword arguments for the configured embedding backend.
    """
    # The Azure backend's model_name is the Azure DEPLOYMENT name, which is
    # configured separately from the Vertex model id.
    model = (
        settings.AZURE_OPENAI_EMBEDDING_MODEL
        if settings.EMBEDDING_PROVIDER.strip().lower() == "azure_openai"
        else settings.MODEL_EMBEDDING
    )
    return {
        "model_name": model,
        "dimensions": settings.EMBEDDING_DIMENSIONS,
        "batch_size": settings.EMBEDDING_BATCH_SIZE,
    }
