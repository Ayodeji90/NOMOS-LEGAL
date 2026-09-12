"""
Per-query trace logging to Cloud Logging.

Week 3 E6: Per-query trace logging (timings, scores, verdicts, refusal reasons).
This system logs detailed trace information for each query to Cloud Logging for observability.
"""
import logging

import structlog
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.config import settings

logger = structlog.get_logger(__name__)


@dataclass
class QueryTrace:
    """Trace data for a single query."""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    query: str = ""
    jurisdiction: str = ""
    user_id: str | None = None
    session_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # Timing information
    understanding_ms: float = 0.0
    retrieval_ms: float = 0.0
    rerank_ms: float = 0.0
    writer_ms: float = 0.0
    verifier_ms: float = 0.0
    total_ms: float = 0.0

    # Retrieval information
    dense_hits: int = 0
    lexical_hits: int = 0
    fused_hits: int = 0
    excerpts_returned: int = 0

    # Quality information
    coverage: float = 0.0
    coverage_ok: bool = False
    refusal_reason: str | None = None
    suggested_jurisdiction: str | None = None

    # Additional metadata
    corpus_snapshot_id: str | None = None
    retrieval_path: str = "v2"  # v1 (lexical) or v2 (hybrid)
    error: str | None = None


class TraceLogger:
    """Manages per-query trace logging to Cloud Logging."""

    def __init__(self):
        self.enabled = settings.ENABLE_QUERY_TRACING
        self.sample_rate = settings.TRACE_SAMPLE_RATE
        self.logger = logger.bind(service="TraceLogger")
        self.logger.info(
            "Trace logger initialized",
            enabled=self.enabled,
            sample_rate=self.sample_rate,
        )

    @contextmanager
    def trace_query(
        self,
        query: str,
        jurisdiction: str,
        user_id: str | None = None,
        session_id: str | None = None,
    ):
        """
        Context manager to trace a query execution.

        Usage:
            with trace_logger.trace_query(query, jurisdiction, user_id) as trace:
                # Execute query
                trace.understanding_ms = 100
                trace.retrieval_ms = 500
                # ...
        """
        # Check if tracing is enabled and sampled
        if not self.enabled or (self.sample_rate < 1.0 and hash(query) % 100 > int(self.sample_rate * 100)):
            # Return a dummy trace that won't be logged
            dummy_trace = QueryTrace()
            yield dummy_trace
            return

        trace = QueryTrace(
            query=query[:500],  # Truncate long queries
            jurisdiction=jurisdiction,
            user_id=user_id,
            session_id=session_id,
        )

        start_time = time.time()
        try:
            yield trace
        finally:
            trace.total_ms = (time.time() - start_time) * 1000
            self.log_trace(trace)

    def log_trace(self, trace: QueryTrace):
        """Log trace data to Cloud Logging."""
        if not self.enabled:
            return

        # In production, this would send to Cloud Logging
        # For now, we'll log locally
        log_data = {
            "trace_id": trace.trace_id,
            "query": trace.query,
            "jurisdiction": trace.jurisdiction,
            "user_id": trace.user_id,
            "session_id": trace.session_id,
            "timestamp": trace.timestamp,
            "timing": {
                "understanding_ms": trace.understanding_ms,
                "retrieval_ms": trace.retrieval_ms,
                "rerank_ms": trace.rerank_ms,
                "writer_ms": trace.writer_ms,
                "verifier_ms": trace.verifier_ms,
                "total_ms": trace.total_ms,
            },
            "retrieval": {
                "dense_hits": trace.dense_hits,
                "lexical_hits": trace.lexical_hits,
                "fused_hits": trace.fused_hits,
                "excerpts_returned": trace.excerpts_returned,
            },
            "quality": {
                "coverage": trace.coverage,
                "coverage_ok": trace.coverage_ok,
                "refusal_reason": trace.refusal_reason,
                "suggested_jurisdiction": trace.suggested_jurisdiction,
            },
            "metadata": {
                "corpus_snapshot_id": trace.corpus_snapshot_id,
                "retrieval_path": trace.retrieval_path,
                "error": trace.error,
            },
        }

        if trace.error:
            self.logger.error("Query trace (error)", **log_data)
        elif trace.refusal_reason:
            self.logger.warning("Query trace (refused)", **log_data)
        else:
            self.logger.info("Query trace", **log_data)

    def log_refusal(
        self,
        query: str,
        jurisdiction: str,
        reason: str,
        suggested_jurisdiction: str | None = None,
        user_id: str | None = None,
    ):
        """Log a query refusal."""
        trace = QueryTrace(
            query=query[:500],
            jurisdiction=jurisdiction,
            user_id=user_id,
            refusal_reason=reason,
            suggested_jurisdiction=suggested_jurisdiction,
        )
        self.log_trace(trace)

    def log_error(
        self,
        query: str,
        jurisdiction: str,
        error: str,
        user_id: str | None = None,
    ):
        """Log a query error."""
        trace = QueryTrace(
            query=query[:500],
            jurisdiction=jurisdiction,
            user_id=user_id,
            error=error,
        )
        self.log_trace(trace)


# Global instance
trace_logger = TraceLogger()


def get_trace_logger() -> TraceLogger:
    """Get the global trace logger instance."""
    return trace_logger
