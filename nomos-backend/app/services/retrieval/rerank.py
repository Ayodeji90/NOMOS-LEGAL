"""Gemini Flash reranker: refine hybrid candidates to 8-12 grounded excerpts.

Week 3 E2 task 3. Consumes the fused hybrid hits (top-50) and asks Flash to
select the excerpts that actually answer the question, scoring *coverage* --
the share of the question the selected excerpts jointly address. Built on the
model-agnostic provider architecture (``ProviderFactory`` +
``get_model_name_for_service``) rather than a bespoke Vertex call, so the
reranker follows the same swap-the-provider path as every other AI service.

Contract (REDESIGN.md): retrieval is honest; when coverage is below the
jurisdiction threshold the pipeline REFUSES rather than answers from weak
evidence. Coverage starts at 0.5 for ZA (plan: tuned against golden sets).

Failure mode is graceful degradation: any reranker error (timeout, invalid
JSON, provider outage) falls back to the fused RRF order so search stays
available with slightly weaker precision. The refusal gate then still applies
to the degraded list.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.services.ai.providers.config_helper import get_model_name_for_service
from app.services.ai.providers.factory import ProviderFactory
from app.services.retrieval.coverage import coverage_gate
from app.services.retrieval.hybrid_search import HybridHit

logger = logging.getLogger(__name__)

RERANK_TIMEOUT_SECONDS = 11.0  # raw Flash calls measure 5.4-9s under dev-tier quota; 8s watchdog killed healthy 9s calls, 11s covers observed p99
RERANK_TIMEOUT_RETRIES = 1  # one immediate retry on timeout: tail spikes are transient under dev quota
MIN_KEEP = 8
MAX_KEEP = 12

_SYSTEM_PROMPT = """You are a legal retrieval reranker for South African statutes. \
Given a question and candidate excerpts from an Acts corpus, select the excerpts \
that bear on answering the question. Prefer provisions that directly regulate or \
answer the question; skip merely-related boilerplate. Keep definitional sections \
(terms defined there and needed to apply the operative provision) when the question \
depends on them. Output STRICT JSON only."""

_USER_PROMPT_TEMPLATE = """Question: {query}

Candidates (id | act | section | heading | excerpt head):
{candidates}

Select the 8 to 12 candidates that are genuinely relevant to the question, best first.
Then rate coverage: the fraction of the question the selected excerpts jointly address
(0.0 to 1.0). If nothing bears on the question, select none and rate coverage 0.

Output JSON exactly like:
{{"selected_ids": ["<id>", ...], "coverage": <float>, "reason": "<one sentence>"}}"""


@dataclass
class RerankResult:
    """Reranked hits + coverage decision for the pipeline/endpoint layer."""

    hits: list[HybridHit]
    coverage: float
    coverage_ok: bool
    degraded: bool = False  # True when the LLM failed and we fell back to RRF order
    reason: str = ""
    model: str = ""
    rerank_ms: float = 0.0
    explain: dict[str, Any] = field(default_factory=dict)


def _parse_rerank_json(raw: str) -> dict:
    """Parse the model response into {selected_ids, coverage, reason}.

    Raises ValueError on unusable output (caller degrades gracefully).
    """
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("reranker returned no JSON object")
    data = json.loads(match.group(0))

    selected = data.get("selected_ids", [])
    if not isinstance(selected, list) or not all(isinstance(x, str) for x in selected):
        raise ValueError("selected_ids must be a list of strings")
    coverage = data.get("coverage", 0.0)
    try:
        coverage = max(0.0, min(1.0, float(coverage)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"coverage not a number: {coverage!r}") from exc
    return {
        "selected_ids": selected,
        "coverage": coverage,
        "reason": str(data.get("reason", ""))[:500],
    }


class FlashReranker:
    """Rerank hybrid hits 50 -> 8-12 with a coverage gate.

    Args:
        provider: optional pre-built BaseLLMProvider (tests inject a fake);
            defaults to the factory-built Vertex provider for MODEL_RERANK.
        coverage_threshold: override; defaults to the ZA threshold from
            jurisdiction config (0.5 per Week 3 plan).
    """

    def __init__(
        self,
        provider: Any = None,
        coverage_threshold: float | None = None,
        timeout_seconds: float = RERANK_TIMEOUT_SECONDS,
        timeout_retries: int = RERANK_TIMEOUT_RETRIES,
        jurisdiction: str = "za",
    ):
        self._timeout = timeout_seconds
        self._timeout_retries = timeout_retries
        # Week 6: threshold source of truth is the coverage gate; the explicit
        # override (tests) still wins.
        self._jurisdiction = jurisdiction
        self._coverage_threshold = (
            coverage_threshold
            if coverage_threshold is not None
            else coverage_gate.threshold_for(jurisdiction)
        )
        if provider is not None:
            self._provider = provider
            self._model = getattr(provider, "model_name", "test-model")
        else:
            # MODEL_RERANK (settings) is the reranker's model knob; the
            # provider follows QUERY_UNDERSTANDING_PROVIDER so rerank moves
            # cloud with the rest of the LLM services (config_helper pattern).
            provider_name = getattr(settings, "QUERY_UNDERSTANDING_PROVIDER", "vertex")
            if provider_name == "azure_openai":
                model = getattr(settings, "MODEL_RERANK_AZURE_OPENAI", None) or "nomos-gpt-4o-mini"
            else:
                model = getattr(settings, "MODEL_RERANK", None) or get_model_name_for_service(
                    "rerank", provider_name
                )
            self._provider = ProviderFactory.create(provider_name, model)
            self._model = model

    @property
    def coverage_threshold(self) -> float:
        return self._coverage_threshold

    def _build_prompt(self, query: str, hits: list[HybridHit]) -> str:
        lines = []
        for h in hits:
            head = " ".join((h.text or "").split())[:180]
            sec = f"s{h.section_no}" if h.section_no else "-"
            lines.append(f"{h.chunk_id} | {h.act_name} | {sec} | {h.heading or '-'} | {head}")
        return _USER_PROMPT_TEMPLATE.format(query=query, candidates="\n".join(lines))

    def _reorder(self, hits: list[HybridHit], selected_ids: list[str]) -> list[HybridHit]:
        by_id = {h.chunk_id: h for h in hits}
        ordered = [by_id[cid] for cid in selected_ids if cid in by_id]
        # Clamp to the 8-12 window: selection longer than MAX_KEEP truncates;
        # a short-but-real selection is accepted as-is (reranker knows best).
        return ordered[:MAX_KEEP]

    async def rerank(self, query: str, hits: list[HybridHit]) -> RerankResult:
        """Rerank fused hits; degrade to fused order on any failure."""
        t0 = time.perf_counter()
        if not hits:
            return RerankResult(
                hits=[],
                coverage=0.0,
                coverage_ok=False,
                degraded=True,
                reason="no candidates",
                model=self._model,
            )

        candidates = hits[:50]
        user_prompt = self._build_prompt(query, candidates)

        attempts_left = 1 + self._timeout_retries
        last_exc: Exception | None = None
        while attempts_left > 0:
            attempts_left -= 1
            try:
                raw = await asyncio.wait_for(
                    self._provider.generate_json(
                        system_prompt=_SYSTEM_PROMPT,
                        user_prompt=user_prompt,
                        temperature=0.0,
                        max_tokens=1024,
                    ),
                    timeout=self._timeout,
                )
                last_exc = None
                break
            except TimeoutError as exc:
                last_exc = exc
                logger.warning(
                    "Flash rerank timed out after %.1fs (%d attempt(s) left)",
                    self._timeout,
                    attempts_left,
                )
            except Exception as exc:  # noqa: BLE001 - provider errors degrade too
                last_exc = exc
                logger.warning("Flash rerank failed (%s): %s", type(exc).__name__, exc)
        if last_exc is not None:
            logger.warning(
                "Flash rerank degraded to fused order after retries: %s",
                type(last_exc).__name__,
            )
            return self._degraded(candidates, t0)

        try:
            parsed = _parse_rerank_json(raw if isinstance(raw, str) else json.dumps(raw))
            selected = self._reorder(candidates, parsed["selected_ids"])
            if not selected:
                # Model answered but picked nothing relevant: honest empty.
                coverage = parsed["coverage"]
                return RerankResult(
                    hits=[],
                    coverage=coverage,
                    coverage_ok=coverage >= self._coverage_threshold,
                    reason=parsed["reason"] or "reranker selected nothing relevant",
                    model=self._model,
                    rerank_ms=round((time.perf_counter() - t0) * 1000, 1),
                )
            coverage = parsed["coverage"]
            return RerankResult(
                hits=selected,
                coverage=coverage,
                coverage_ok=coverage >= self._coverage_threshold,
                reason=parsed["reason"],
                model=self._model,
                rerank_ms=round((time.perf_counter() - t0) * 1000, 1),
                explain={"candidates": len(candidates), "selected": len(selected)},
            )
        except ValueError as exc:
            logger.warning("Flash rerank returned unusable JSON: %s", exc)
        except Exception as exc:  # noqa: BLE001 - any provider error degrades
            logger.warning("Flash rerank failed (%s): %s", type(exc).__name__, exc)

        # Graceful degradation: fused RRF order, clamped to the same window.
        return self._degraded(candidates, t0)

    def _degraded(self, candidates: list[HybridHit], t0: float) -> RerankResult:
        degraded_hits = candidates[MIN_KEEP - 1 : MAX_KEEP] or candidates[:MIN_KEEP]
        return RerankResult(
            hits=degraded_hits,
            coverage=0.0,  # unknown -- caller may gate on its own signal
            coverage_ok=False,
            degraded=True,
            reason="reranker unavailable; using fused order",
            model=self._model,
            rerank_ms=round((time.perf_counter() - t0) * 1000, 1),
        )


# Module-level singleton (lazy provider construction on first use).
flash_reranker = FlashReranker()
