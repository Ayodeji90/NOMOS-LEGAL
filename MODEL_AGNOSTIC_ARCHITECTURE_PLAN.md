# NOMOS v2 - Model-Agnostic AI Services Architecture Plan
## Multi-Provider LLM Support Strategy

**Date**: 2026-09-11  
**Status**: Planning Phase  
**Objective**: Enable easy switching between LLM providers (Gemini, Claude, OpenAI, etc.) via configuration/API

---

## 🎯 Problem Statement

**Current State**:
- All AI services (writer, verifier, query_understanding) tightly coupled to Vertex AI/Gemini
- Hard-coded model names in each service
- No easy way to switch providers without code changes
- Single point of failure if Vertex AI has issues
- No ability to A/B test models or use different models for different tasks

**Desired State**:
- Provider-agnostic interface for all AI services
- Configuration-driven model selection per service
- Easy switching via environment variables or API
- Fallback mechanisms between providers
- Support for multiple providers: Vertex AI (Gemini), Anthropic (Claude), OpenAI (GPT), etc.
- Model-specific prompt adaptations handled automatically

---

## 🏗️ Architecture Design

### 1. Provider Abstraction Layer

```
app/services/ai/providers/
├── __init__.py
├── base.py              # Abstract base class for all providers
├── vertex_provider.py    # Vertex AI (Gemini) implementation
├── anthropic_provider.py # Anthropic (Claude) implementation
├── openai_provider.py   # OpenAI (GPT) implementation
└── factory.py           # Provider factory for instantiation
```

**Base Provider Interface**:
```python
class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs
    ) -> dict:
        """Generate JSON output from LLM."""
        pass
    
    @abstractmethod
    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        **kwargs
    ) -> str:
        """Generate text output from LLM."""
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier."""
        pass
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Current model name."""
        pass
```

### 2. Configuration Structure

**Environment Variables**:
```bash
# Provider selection per service
QUERY_UNDERSTANDING_PROVIDER=vertex
WRITER_PROVIDER=anthropic
VERIFIER_PROVIDER=openai

# Model selection per provider
QUERY_UNDERSTANDING_VERTEX_MODEL=gemini-1.5-flash
WRITER_ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
VERIFIER_OPENAI_MODEL=gpt-4o-mini

# Fallback providers
QUERY_UNDERSTANDING_FALLBACK_PROVIDER=openai
WRITER_FALLBACK_PROVIDER=vertex

# API keys (if not using default auth)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

**Configuration Schema** (`app/core/config.py`):
```python
class Settings(BaseSettings):
    # Provider selection
    QUERY undertanding_PROVIDER: str = "vertex"
    WRITER_PROVIDER: str = "vertex"
    VERIFIER_PROVIDER: str = "vertex"
    
    # Model names per provider
    QUERY_UNDERSTANDING_VERTEX_MODEL: str = "gemini-1.5-flash"
    QUERY_UNDERSTANDING_ANTHROPIC_MODEL: str = "claude-3-haiku-20240307"
    QUERY_UNDERSTANDING_OPENAI_MODEL: str = "gpt-4o-mini"
    
    WRITER_VERTEX_MODEL: str = "gemini-1.5-pro"
    WRITER_ANTHROPIC_MODEL: str = "claude-3-5-sonnet-20241022"
    WRITER_OPENAI_MODEL: str = "gpt-4o"
    
    VERIFIER_VERTEX_MODEL: str = "gemini-1.5-flash"
    VERIFIER_ANTHROPIC_MODEL: str = "claude-3-haiku-20240307"
    VERIFIER_OPENAI_MODEL: str = "gpt-4o-mini"
    
    # Fallback providers
    QUERY_UNDERSTANDING_FALLBACK_PROVIDER: str = "openai"
    WRITER_FALLBACK_PROVIDER: str = "vertex"
    VERIFIER_FALLBACK_PROVIDER: str = "openai"
    
    # API keys for non-GCP providers
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
```

### 3. Provider Factory

**Factory Pattern**:
```python
class ProviderFactory:
    """Factory for creating LLM provider instances."""
    
    _providers = {
        "vertex": VertexAIProvider,
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
    }
    
    @classmethod
    def create(
        cls,
        provider_name: str,
        model_name: str,
        **kwargs
    ) -> BaseLLMProvider:
        """Create provider instance."""
        provider_class = cls._providers.get(provider_name.lower())
        if not provider_class:
            raise ValueError(f"Unknown provider: {provider_name}")
        return provider_class(model_name=model_name, **kwargs)
    
    @classmethod
    def create_with_fallback(
        cls,
        primary_provider: str,
        fallback_provider: str,
        model_name: str,
        **kwargs
    ) -> BaseLLMProvider:
        """Create provider with fallback support."""
        return FallbackProvider(
            primary=cls.create(primary_provider, model_name, **kwargs),
            fallback=cls.create(fallback_provider, model_name, **kwargs),
        )
```

### 4. Fallback Provider

**Automatic Fallback**:
```python
class FallbackProvider(BaseLLMProvider):
    """Provider that automatically falls back to secondary on failure."""
    
    def __init__(self, primary: BaseLLMProvider, fallback: BaseLLMProvider):
        self._primary = primary
        self._fallback = fallback
    
    async def generate_json(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        try:
            return await self._primary.generate_json(system_prompt, user_prompt, **kwargs)
        except Exception as e:
            logger.warning(f"Primary provider failed: {e}, trying fallback")
            return await self._fallback.generate_json(system_prompt, user_prompt, **kwargs)
```

### 5. Service Integration

**Refactored Services**:
```python
# app/services/ai/query_understanding.py
class QueryUnderstandingService:
    def __init__(self):
        self._provider = ProviderFactory.create(
            provider_name=settings.QUERY_UNDERSTANDING_PROVIDER,
            model_name=getattr(
                settings,
                f"QUERY_UNDERSTANDING_{settings.QUERY_UNDERSTANDING_PROVIDER.upper()}_MODEL"
            ),
        )
    
    async def understand(self, query_input: QueryUnderstandingInput) -> QueryUnderstandingOutput:
        response = await self._provider.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=settings.QUERY_UNDERSTANDING_TEMPERATURE,
            max_tokens=settings.QUERY_UNDERSTANDING_MAX_TOKENS,
        )
        # ... process response
```

### 6. Prompt Adaptation Layer

**Model-Specific Prompts**:
```python
class PromptAdapter:
    """Adapts prompts for different models."""
    
    @staticmethod
    def for_vertex(prompt: str) -> str:
        """Adapt prompt for Vertex AI/Gemini."""
        return prompt
    
    @staticmethod
    def for_anthropic(prompt: str) -> str:
        """Adapt prompt for Anthropic/Claude."""
        # Claude prefers XML-style tags
        return f"<system>{prompt}</system>"
    
    @staticmethod
    def for_openai(prompt: str) -> str:
        """Adapt prompt for OpenAI/GPT."""
        # GPT uses different system message format
        return prompt
```

### 7. API Endpoint for Model Switching

**Runtime Model Switching**:
```python
# app/api/v1/endpoints/models.py
@router.post("/switch-model")
async def switch_model(
    service: str,  # "query_understanding", "writer", "verifier"
    provider: str,  # "vertex", "anthropic", "openai"
    model: str,    # model name
    current_user: User = Depends(get_current_user),
):
    """Switch model for a specific service at runtime."""
    if not current_user.is_admin:
        raise HTTPException(403, "Admin only")
    
    # Update in-memory configuration
    model_switcher.switch_service_model(service, provider, model)
    
    # Persist to database for persistence across restarts
    await save_model_config(service, provider, model)
    
    return {"status": "success", "service": service, "provider": provider, "model": model}
```

---

## 📋 Implementation Plan

### Phase 1: Foundation (Week 6)
- [ ] Create `app/services/ai/providers/` directory structure
- [ ] Implement `BaseLLMProvider` abstract class
- [ ] Implement `VertexAIProvider` (refactor existing code)
- [ ] Implement `AnthropicProvider` (Claude via API)
- [ ] Implement `OpenAIProvider` (GPT via API)
- [ ] Implement `ProviderFactory`
- [ ] Add configuration schema for multi-provider support

### Phase 2: Service Refactoring (Week 6)
- [ ] Refactor `QueryUnderstandingService` to use provider abstraction
- [ ] Refactor `WriterService` to use provider abstraction
- [ ] Refactor `VerifierService` to use provider abstraction
- [ ] Add prompt adaptation layer
- [ ] Update tests to work with multiple providers

### Phase 3: Fallback & Monitoring (Week 7)
- [ ] Implement `FallbackProvider`
- [ ] Add provider health checks
- [ ] Add metrics for provider performance (latency, cost, error rate)
- [ ] Add automatic fallback on repeated failures
- [ ] Add logging for provider switching events

### Phase 4: Runtime Switching (Week 7)
- [ ] Implement model switcher service
- [ ] Add API endpoint for runtime model switching
- [ ] Add database persistence for model configuration
- [ ] Add admin UI for model management
- [ ] Add A/B testing framework for model comparison

### Phase 5: Optimization (Week 8)
- [ ] Implement request batching for cost optimization
- [ ] Add model-specific caching strategies
- [ ] Add cost tracking per provider
- [ ] Add performance benchmarking tools
- [ ] Add model recommendation engine

---

## 🎯 Provider Support Matrix

| Provider | Status | Models Supported | Auth Method | Cost (per 1M tokens) |
|----------|--------|------------------|-------------|----------------------|
| Vertex AI | ✅ Current | gemini-1.5-flash, gemini-1.5-pro | GCP ADC | $0.075 (Flash), $3.50 (Pro) |
| Anthropic | 🚧 Planned | claude-3-haiku, claude-3-sonnet, claude-3-opus | API Key | $0.25 (Haiku), $3.00 (Sonnet), $15.00 (Opus) |
| OpenAI | 🚧 Planned | gpt-4o-mini, gpt-4o, gpt-4-turbo | API Key | $0.15 (4o-mini), $2.50 (4o), $10.00 (4-turbo) |

---

## 💡 Use Cases

### 1. Cost Optimization
- Use cheaper models (gemini-1.5-flash, gpt-4o-mini) for query understanding
- Use higher-quality models (claude-3-opus, gpt-4o) for writer
- Use fast models (gemini-1.5-flash) for verifier

### 2. Redundancy
- Configure fallback provider in case of outages
- Automatic switching on repeated failures
- Health checks to detect provider issues

### 3. A/B Testing
- Compare model quality for same task
- Measure latency and cost differences
- Choose optimal model per use case

### 4. Regional Compliance
- Use different providers for different regions
- Data residency requirements
- Regulatory compliance

### 5. Rapid Experimentation
- Test new models without code changes
- Easy rollback if issues occur
- Gradual rollout with monitoring

---

## 🔒 Security Considerations

### API Key Management
- Store API keys in Secret Manager (GCP)
- Rotate keys regularly
- Audit key usage
- Restrict key permissions

### Data Privacy
- Ensure no data leaks between providers
- Check provider data retention policies
- Implement data encryption in transit
- Log all provider API calls

### Rate Limiting
- Implement per-provider rate limits
- Queue requests when limits exceeded
- Monitor quota usage
- Alert on approaching limits

---

## 📊 Monitoring & Observability

### Metrics to Track
- **Per Provider**:
  - Request count
  - Success rate
  - Average latency
  - P95/P99 latency
  - Cost per request
  - Error rate by error type

- **Per Service**:
  - Which provider used for each request
  - Fallback trigger count
  - Model switch events
  - Quality metrics (citation validity, entailment rate)

### Dashboards
- Provider health dashboard
- Cost breakdown by provider
- Latency comparison
- Error rate tracking
- Model usage statistics

---

## 🚀 Migration Strategy

### Step 1: Add Abstraction (Non-Breaking)
- Keep existing Gemini implementation as default
- Add provider layer alongside existing code
- Test with Gemini through new abstraction
- Verify no performance regression

### Step 2: Add Alternative Providers
- Implement Anthropic provider
- Implement OpenAI provider
- Test with sample queries
- Compare output quality

### Step 3: Enable Configuration
- Add environment variables
- Update documentation
- Test provider switching
- Verify fallback works

### Step 4: Gradual Rollout
- Start with query understanding (lowest risk)
- Monitor metrics closely
- Roll out to writer
- Roll out to verifier
- Full rollout

### Step 5: Remove Old Code
- Deprecate direct Gemini calls
- Migrate all services to abstraction
- Remove old code after validation period
- Update all documentation

---

## ✅ Success Criteria

- [ ] All AI services use provider abstraction
- [ ] Can switch providers via environment variables
- [ ] Can switch providers via API endpoint
- [ ] Fallback mechanism works automatically
- [ ] No performance regression with abstraction
- [ ] Comprehensive monitoring in place
- [ ] Documentation updated
- [ ] Tests pass for all providers
- [ ] Cost tracking implemented
- [ ] Security audit passed

---

## 📝 Next Steps

1. **Review this plan** with the team
2. **Approve provider list** (which providers to support initially)
3. **Prioritize phases** (can we do all phases or focus on specific ones?)
4. **Assign tasks** to team members
5. **Set timeline** for implementation
6. **Begin Phase 1** implementation

---

## 🤔 Open Questions

1. Should we support local models (Ollama, vLLM) for offline/testing?
2. Should we implement request routing based on query complexity?
3. Should we add model fine-tuning support?
4. Should we implement token counting for accurate cost tracking?
5. Should we add provider-specific prompt templates?
