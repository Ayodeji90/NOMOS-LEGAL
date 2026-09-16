import time
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.flags import parse_v2_jurisdictions
from app.core.rate_limit import get_quota_manager, get_rate_limiter
from app.db.session import get_db
from app.schemas.verifier import VerifierInput
from app.schemas.writer import WriterInput
from app.services.ai.gates import gate_service
from app.services.ai.query_understanding import (
    QueryUnderstandingInput,
    understand_query,
)
from app.services.ai.verifier_service import verifier_service
from app.services.ai.writer_service import WriterService
from app.services.retrieval.service import retrieval_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/search", tags=["Search"])


def uses_v2_all() -> set:
    """Jurisdictions allowed on the v2 hybrid path (from flags)."""
    return parse_v2_jurisdictions(settings.RETRIEVAL_V2_JURISDICTIONS)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2500)
    jurisdiction: str = Field(default="za", pattern="^(za|ng)$")
    corpus_id: str | None = None
    note: str | None = None
    history: list[dict] | None = None


class SourceResponse(BaseModel):
    title: str
    url: str | None = None
    portion: str | None = None
    excerpt: str
    legal_citation: str | None = None
    section: str | None = None
    year: str | None = None
    jurisdiction: str | None = None


class StructuredAnswer(BaseModel):
    directAnswer: str
    legalBasis: list[dict]
    explanation: str
    gaps: str
    grounded: bool


class SearchResponse(BaseModel):
    query: str
    note: str
    top: list[dict]
    errors: list[dict]
    missReason: str | None = None
    sources: list[SourceResponse]
    structured: StructuredAnswer | dict
    answer: str
    grounded: bool
    provider: str
    suggestedJurisdiction: dict | None = None
    writer: dict | None = None


class RefusalResponse(BaseModel):
    query: str
    note: str
    top: list[dict]
    errors: list[dict]
    missReason: str
    sources: list[SourceResponse]
    structured: StructuredAnswer | dict
    answer: str
    grounded: bool
    provider: str
    suggestedJurisdiction: dict | None = None


async def enforce_rate_limits(request: Request) -> None:
    rate_limiter = get_rate_limiter()
    client_ip = rate_limiter.get_client_ip(request)

    results = await rate_limiter.check_multiple_windows(
        client_ip,
        [
            (settings.RATE_LIMIT_REQUESTS_PER_MINUTE, 60),
            (settings.RATE_LIMIT_REQUESTS_PER_HOUR, 3600),
        ],
    )

    for result in results:
        if not result.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": str(result.remaining),
                    "X-RateLimit-Reset": str(result.reset_at),
                    "Retry-After": str(result.retry_after or 60),
                },
            )


async def enforce_quotas(user_id: str) -> dict:
    quota_manager = get_quota_manager()
    quota_status = await quota_manager.get_quota_status(user_id)

    if quota_status["queries"]["used"] >= quota_status["queries"]["limit"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily query quota exceeded",
            headers={
                "X-Quota-Limit": str(quota_status["queries"]["limit"]),
                "X-Quota-Remaining": "0",
                "X-Quota-Reset": str(
                    int(
                        __import__("time").mktime(
                            __import__("time").strptime(
                                __import__("time").strftime("%Y-%m-%d 23:59:59"),
                                "%Y-%m-%d %H:%M:%S",
                            )
                        )
                    )
                ),
            },
        )

    return quota_status


@router.post("", response_model=SearchResponse | RefusalResponse)
async def search(
    request: Request,
    search_request: SearchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SearchResponse | RefusalResponse:
    start_time = time.time()
    await enforce_rate_limits(request)

    user_id = getattr(request.state, "user_id", None) or "anonymous"
    quota_status = await enforce_quotas(user_id)

    quota_manager = get_quota_manager()
    await quota_manager.consume_quota(user_id, "queries")

    # Week 5: Wire understanding pre-retrieval (live integration with Gemini Flash, cached 24h)
    # Build understanding input
    understanding_input = QueryUnderstandingInput(
        query=search_request.query,
        jurisdiction_hint=search_request.jurisdiction,
        history=search_request.history or [],
    )

    # Call understanding service (live for Week 5)
    understanding_result = await understand_query(understanding_input)

    # Log understanding JSON to traces (Week 2 deliverable maintained)
    logger.info(
        "understanding_completed",
        query=search_request.query[:100],
        jurisdiction=search_request.jurisdiction,
        understanding=understanding_result.model_dump() if understanding_result else None
    )

    # Week 3: Hybrid retrieval (dense+lexical, RRF) -> Flash rerank 50->8-12
    # -> coverage gate. retrieve_with_coverage returns the refusal verdict;
    # retrieval_metadata (per-leg ranks) rides in each excerpt dict.
    retrieval_start = time.time()
    retrieval_result = await retrieval_service.retrieve_with_coverage(
        query=search_request.query,
        jurisdiction=search_request.jurisdiction,
        understanding=understanding_result,  # Pass actual understanding for retrieval guidance
        limit=12,
    )
    excerpts = retrieval_result.excerpts
    retrieval_time = time.time() - retrieval_start

    # Coverage gate: below-threshold coverage means we answer honestly that
    # the corpus does not cover the question rather than writing from weak
    # evidence. Degraded rerank (reranker outage) also fails the gate closed
    # unless the fused excerpts themselves are present and the writer's own
    # grounding check keeps the answer honest.
    coverage_gate_failed = not retrieval_result.coverage_ok

    logger.info(
        "retrieval_completed",
        query=search_request.query[:50],
        jurisdiction=search_request.jurisdiction,
        excerpt_count=len(excerpts),
        coverage=round(retrieval_result.coverage, 3),
        coverage_ok=retrieval_result.coverage_ok,
        rerank_degraded=retrieval_result.degraded,
        retrieval_time_ms=round(retrieval_time * 1000, 2)
    )

    # Week 3: Run gates in log-only mode (not blocking yet)
    gates_start = time.time()
    should_refuse, failure_reasons, suggested_jurisdiction = await gate_service.check_all_gates(
        query=search_request.query,
        jurisdiction=search_request.jurisdiction,
        excerpts=excerpts
    )
    gates_time = time.time() - gates_start

    # Coverage gate (retrieval-side refusal): outside v2-allowed jurisdictions
    # or when rerank coverage is below threshold, honour the refusal contract.
    if coverage_gate_failed:
        logger.info(
            "coverage_gate_refusal",
            query=search_request.query[:50],
            coverage=round(retrieval_result.coverage, 3),
            threshold_reason=retrieval_result.reason,
        )
        return SearchResponse(
            query=search_request.query,
            note=search_request.note or "",
            top=[],
            errors=[],
            missReason=(
                "Retrieved excerpts do not sufficiently cover the question "
                "(coverage below jurisdiction threshold)"
                if not retrieval_result.degraded
                else "Retrieval reranker unavailable; fused excerpts insufficient"
            ),
            sources=[
                SourceResponse(
                    title=e.get("title"),
                    url=None,  # URL not available in current model, frontend handles None
                    portion=e.get("heading"),  # Frontend expects portion as heading/subsection
                    excerpt=e.get("sourceText", "")[:200] + "...",
                    legal_citation=e.get("citation"),
                    section=e.get("section"),  # Frontend expects section as section number
                    year=str(e.get("as_at_date")[:4]) if e.get("as_at_date") else None,
                    jurisdiction=e.get("jurisdiction")
                )
                for e in excerpts[:3]
            ],
            structured=StructuredAnswer(
                directAnswer="",
                legalBasis=[],
                explanation="The corpus does not contain enough on-point provisions.",
                gaps=retrieval_result.reason or "coverage below threshold",
                grounded=False,
            ),
            answer="",
            grounded=False,
            provider="nomos",
            suggestedJurisdiction=None,
        )

    # Log gate decisions (Week 3 deliverable: gate decisions visible in logs)
    logger.info(
        "gates_evaluated",
        query=search_request.query[:50],
        jurisdiction=search_request.jurisdiction,
        should_refuse=should_refuse,
        failure_count=len(failure_reasons),
        failure_reasons=failure_reasons,
        suggested_jurisdiction=suggested_jurisdiction,
        gates_time_ms=round(gates_time * 1000, 2)
    )

    # Week 3: Keep writer on new excerpts (now using real excerpts from retrieval)
    writer_service = WriterService()
    writer_input = WriterInput(
        query=search_request.query,
        jurisdiction=search_request.jurisdiction,
        excerpts=excerpts,  # NOW USING REAL EXCERPTS FROM RETRIEPIPELINE
        history=search_request.history or [],
        is_repair=False
    )

    try:
        writer_start = time.time()
        writer_output = await writer_service.write_answer(writer_input)
        writer_time = time.time() - writer_start

        logger.info(
            "writer_completed",
            query=search_request.query[:50],
            jurisdiction=search_request.jurisdiction,
            insufficient_context=writer_output.insufficientContext,
            answer_length=len(writer_output.directAnswer),
            writer_time_ms=round(writer_time * 1000, 2)
        )

        # If writer says insufficient context, return a refusal-like response
        if writer_output.insufficientContext:
            total_time = time.time() - start_time
            logger.info(
                "request_completed_insufficient_context",
                query=search_request.query[:50],
                total_time_ms=round(total_time * 1000, 2)
            )
            return SearchResponse(
                query=search_request.query,
                note=search_request.note or "",
                top=[],
                errors=[],
                missReason="Insufficient context - no relevant excerpts found in corpus",
                sources=[
                    SourceResponse(
                        title=excerpt.get("title"),
                        url=None,  # URL not available in current model, frontend handles None
                        portion=excerpt.get("heading"),  # Frontend expects portion as heading/subsection
                        excerpt=excerpt.get("sourceText", "")[:200] + "...",
                        legal_citation=excerpt.get("citation"),
                        section=excerpt.get("section"),  # Frontend expects section as section number
                        year=str(excerpt.get("as_at_date")[:4]) if excerpt.get("as_at_date") else None,
                        jurisdiction=excerpt.get("jurisdiction")
                    ) for excerpt in excerpts[:3]  # Top 3 sources
                ],
                structured=writer_output.model_dump(),
                answer="",
                grounded=False,
                provider="nomos",
                suggestedJurisdiction=None,
                writer=writer_output.model_dump() if hasattr(writer_output, 'model_dump') else None
            )

        # Week 4: Run verification on the writer's answer
        verifier_start = time.time()
        verifier_input = VerifierInput(
            query=search_request.query,
            answer=writer_output.directAnswer,
            excerpts=excerpts,
            jurisdiction=search_request.jurisdiction,
            is_repair=False
        )
        verifier_output = await verifier_service.verify(verifier_input)
        verifier_time = time.time() - verifier_start

        logger.info(
            "verification_completed",
            query=search_request.query[:50],
            jurisdiction=search_request.jurisdiction,
            grounded=verifier_output.grounded,
            citation_issues_count=len(verifier_output.citation_issues),
            section_issues_count=len(verifier_output.section_issues),
            verifier_time_ms=round(verifier_time * 1000, 2)
        )

        # Week 4: Handle verification results with one repair attempt
        if verifier_output.grounded:
            # Verification passed - return successful response
            total_time = time.time() - start_time
            logger.info(
                "request_completed",
                query=search_request.query[:50],
                jurisdiction=search_request.jurisdiction,
                total_time_ms=round(total_time * 1000, 2),
                grounded=True
            )
            return SearchResponse(
                query=search_request.query,
                note=search_request.note or "",
                top=[],
                errors=[],
                missReason=None,
                sources=[
                    SourceResponse(
                        title=excerpt.get("title"),
                        url=None,  # URL not available in current model, frontend handles None
                        portion=excerpt.get("heading"),  # Frontend expects portion as heading/subsection
                        excerpt=excerpt.get("sourceText", "")[:200] + "...",
                        legal_citation=excerpt.get("citation"),
                        section=excerpt.get("section"),  # Frontend expects section as section number
                        year=str(excerpt.get("as_at_date")[:4]) if excerpt.get("as_at_date") else None,
                        jurisdiction=excerpt.get("jurisdiction")
                    ) for excerpt in excerpts[:3]  # Top 3 sources
                ],
                structured=writer_output.model_dump(),
                answer=writer_output.directAnswer,
                grounded=True,
                provider="nomos",
                suggestedJurisdiction=suggested_jurisdiction if should_refuse else None,
                writer=writer_output.model_dump() if hasattr(writer_output, 'model_dump') else None
            )
        else:
            # Verification failed - check if we should attempt repair
            if verifier_output.should_repair and not writer_input.is_repair:
                # Attempt one repair
                logger.info(
                    "verification_failed_attempting_repair",
                    query=search_request.query[:50],
                    jurisdiction=search_request.jurisdiction,
                    failure_reasons=verifier_output.suggested_repairs
                )

                # Prepare repair input with verification failures
                repair_input = WriterInput(
                    query=search_request.query,
                    jurisdiction=search_request.jurisdiction,
                    excerpts=excerpts,
                    history=search_request.history or [],
                    is_repair=True,
                    verification_failures=verifier_output.suggested_repairs
                )

                try:
                    repair_start = time.time()
                    repair_output = await writer_service.write_answer(repair_input)
                    repair_time = time.time() - repair_start

                    logger.info(
                        "writer_repair_completed",
                        query=search_request.query[:50],
                        jurisdiction=search_request.jurisdiction,
                        insufficient_context=repair_output.insufficientContext,
                        answer_length=len(repair_output.directAnswer),
                        writer_time_ms=round(repair_time * 1000, 2)
                    )

                    if repair_output.insufficientContext:
                        # Repair also found insufficient context
                        total_time = time.time() - start_time
                        logger.info(
                            "request_completed_insufficient_context_after_repair",
                            query=search_request.query[:50],
                            total_time_ms=round(total_time * 1000, 2)
                        )
                        return SearchResponse(
                            query=search_request.query,
                            note=search_request.note or "",
                            top=[],
                            errors=[],
                            missReason="Insufficient context - no relevant excerpts found in corpus",
                            sources=[
                                SourceResponse(
                                    title=excerpt.get("title"),
                                    url=None,  # URL not available in current model, frontend handles None
                                    portion=excerpt.get("heading"),  # Frontend expects portion as heading/subsection
                                    excerpt=excerpt.get("sourceText", "")[:200] + "...",
                                    legal_citation=excerpt.get("citation"),
                                    section=excerpt.get("section"),  # Frontend expects section as section number
                                    year=str(excerpt.get("as_at_date")[:4]) if excerpt.get("as_at_date") else None,
                                    jurisdiction=excerpt.get("jurisdiction")
                                ) for excerpt in excerpts[:3]  # Top 3 sources
                            ],
                            structured=repair_output.model_dump(),
                            answer="",
                            grounded=False,
                            provider="nomos",
                            suggestedJurisdiction=None,
                            writer=repair_output.model_dump() if hasattr(repair_output, 'model_dump') else None
                        )
                    else:
                        # Run verification on repaired answer
                        verify_repair_start = time.time()
                        verify_repair_input = VerifierInput(
                            query=search_request.query,
                            answer=repair_output.directAnswer,
                            excerpts=excerpts,
                            jurisdiction=search_request.jurisdiction,
                            is_repair=True  # This is a repair attempt
                        )
                        verify_repair_output = await verifier_service.verify(verify_repair_input)
                        verify_repair_time = time.time() - verify_repair_start

                        logger.info(
                            "verification_repair_completed",
                            query=search_request.query[:50],
                            jurisdiction=search_request.jurisdiction,
                            grounded=verify_repair_output.grounded,
                            citation_issues_count=len(verify_repair_output.citation_issues),
                            section_issues_count=len(verify_repair_output.section_issues),
                            verifier_time_ms=round(verify_repair_time * 1000, 2)
                        )

                        total_time = time.time() - start_time
                        if verify_repair_output.grounded:
                            # Repair succeeded
                            logger.info(
                                "request_completed_after_repair",
                                query=search_request.query[:50],
                                jurisdiction=search_request.jurisdiction,
                                total_time_ms=round(total_time * 1000, 2),
                                grounded=True
                            )
                            return SearchResponse(
                                query=search_request.query,
                                note=search_request.note or "",
                                top=[],
                                errors=[],
                                missReason=None,
                                sources=[
                                    SourceResponse(
                                        title=excerpt.get("title"),
                                        url=None,  # URL not available in current model, frontend handles None
                                        portion=excerpt.get("heading"),  # Frontend expects portion as heading/subsection
                                        excerpt=excerpt.get("sourceText", "")[:200] + "...",
                                        legal_citation=excerpt.get("citation"),
                                        section=excerpt.get("section"),  # Frontend expects section as section number
                                        year=str(excerpt.get("as_at_date")[:4]) if excerpt.get("as_at_date") else None,
                                        jurisdiction=excerpt.get("jurisdiction")
                                    ) for excerpt in excerpts[:3]  # Top 3 sources
                                ],
                                structured=repair_output.model_dump(),
                                answer=repair_output.directAnswer,
                                grounded=True,
                                provider="nomos",
                                suggestedJurisdiction=suggested_jurisdiction if should_refuse else None,
                                writer=repair_output.model_dump() if hasattr(repair_output, 'model_dump') else None
                            )
                        else:
                            # Repair failed - return refusal after max attempts
                            logger.info(
                                "request_completed_verification_failed_max_repair",
                                query=search_request.query[:50],
                                jurisdiction=search_request.jurisdiction,
                                total_time_ms=round(total_time * 1000, 2),
                                grounded=False
                            )
                            return RefusalResponse(
                                query=search_request.query,
                                note=search_request.note or "",
                                top=[],
                                errors=[],
                                missReason="Answer failed verification after repair attempt",
                                sources=[
                                    SourceResponse(
                                        title=excerpt.get("title"),
                                        url=None,  # URL not available in current model, frontend handles None
                                        portion=excerpt.get("heading"),  # Frontend expects portion as heading/subsection
                                        excerpt=excerpt.get("sourceText", "")[:200] + "...",
                                        legal_citation=excerpt.get("citation"),
                                        section=excerpt.get("section"),  # Frontend expects section as section number
                                        year=str(excerpt.get("as_at_date")[:4]) if excerpt.get("as_at_date") else None,
                                        jurisdiction=excerpt.get("jurisdiction")
                                    ) for excerpt in excerpts[:3]  # Top 3 sources
                                ],
                                structured=verify_repair_output.model_dump(),  # Use verification output for structured info
                                answer="",  # Empty answer as per refusal
                                grounded=False,
                                provider="nomos",
                                suggestedJurisdiction=suggested_jurisdiction if should_refuse else None,
                                writer={"verification_failed": True, "repair_attempted": True}
                            )

                except Exception as e:
                    total_time = time.time() - start_time
                    logger.error(
                        "Writer repair service failed",
                        error=str(e),
                        query=search_request.query[:50],
                        total_time_ms=round(total_time * 1000, 2)
                    )
                    return SearchResponse(
                        query=search_request.query,
                        note=search_request.note or "",
                        top=[],
                        errors=[],
                        missReason="Writer repair service temporarily unavailable",
                        sources=[
                            SourceResponse(
                                title=excerpt.get("title"),
                                url=None,  # URL not available in current model, frontend handles None
                                portion=excerpt.get("heading"),  # Frontend expects portion as heading/subsection
                                excerpt=excerpt.get("sourceText", "")[:200] + "...",
                                legal_citation=excerpt.get("citation"),
                                section=excerpt.get("section"),  # Frontend expects section as section number
                                year=str(excerpt.get("as_at_date")[:4]) if excerpt.get("as_at_date") else None,
                                jurisdiction=excerpt.get("jurisdiction")
                            ) for excerpt in excerpts[:3]
                        ],
                        structured=StructuredAnswer(
                            directAnswer="Unable to generate answer due to service error.",
                            explanation="The writer service encountered an internal error during repair.",
                            legalBasis=[],
                            gaps="Service error prevented answer generation during repair attempt.",
                            grounded=False
                        ),
                        answer="Unable to generate answer due to service error.",
                        grounded=False,
                        provider="nomos",
                        suggestedJurisdiction=None,
                        writer={"error": "service_unavailable_during_repair"}
                    )
            else:
                # Either should not repair or already attempted repair - return refusal
                total_time = time.time() - start_time
                logger.info(
                    "request_completed_verification_failed_no_repair",
                    query=search_request.query[:50],
                    jurisdiction=search_request.jurisdiction,
                    total_time_ms=round(total_time * 1000, 2),
                    grounded=False,
                    should_repair=verifier_output.should_repair,
                    is_repair=writer_input.is_repair
                )
                return RefusalResponse(
                    query=search_request.query,
                    note=search_request.note or "",
                    top=[],
                    errors=[],
                    missReason="Answer failed verification checks",
                    sources=[
                        SourceResponse(
                            title=excerpt.get("title"),
                            url=None,  # URL not available in current model, frontend handles None
                            portion=excerpt.get("heading"),  # Frontend expects portion as heading/subsection
                            excerpt=excerpt.get("sourceText", "")[:200] + "...",
                            legal_citation=excerpt.get("citation"),
                            section=excerpt.get("section"),  # Frontend expects section as section number
                            year=str(excerpt.get("as_at_date")[:4]) if excerpt.get("as_at_date") else None,
                            jurisdiction=excerpt.get("jurisdiction")
                        ) for excerpt in excerpts[:3]  # Top 3 sources
                    ],
                    structured=verifier_output.model_dump(),  # Use verification output for structured info
                    answer="",  # Empty answer as per refusal
                    grounded=False,
                    provider="nomos",
                    suggestedJurisdiction=suggested_jurisdiction if should_refuse else None,
                    writer={"verification_failed": True, "repair_attempted": False}
                )

    except Exception as e:
        total_time = time.time() - start_time
        logger.error(
            "Writer service failed",
            error=str(e),
            query=search_request.query[:50],
            total_time_ms=round(total_time * 1000, 2)
        )
        return SearchResponse(
            query=search_request.query,
            note=search_request.note or "",
            top=[],
            errors=[],
            missReason="Writer service temporarily unavailable",
            sources=[
                SourceResponse(
                    title=excerpt.get("title"),
                    url=None,  # URL not available in current model, frontend handles None
                    portion=excerpt.get("heading"),  # Frontend expects portion as heading/subsection
                    excerpt=excerpt.get("sourceText", "")[:200] + "...",
                    legal_citation=excerpt.get("citation"),
                    section=excerpt.get("section"),  # Frontend expects section as section number
                    year=str(excerpt.get("as_at_date")[:4]) if excerpt.get("as_at_date") else None,
                    jurisdiction=excerpt.get("jurisdiction")
                ) for excerpt in excerpts[:3]
            ],
            structured=StructuredAnswer(
                directAnswer="Unable to generate answer due to service error.",
                explanation="The writer service encountered an internal error.",
                legalBasis=[],
                gaps="Service error prevented answer generation.",
                grounded=False
            ),
            answer="Unable to generate answer due to service error.",
            grounded=False,
            provider="nomos",
            suggestedJurisdiction=None,
            writer={"error": "service_unavailable"}
        )
