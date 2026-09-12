"""
Cloud Run job for corpus ingestion.

Week 7 E1: Ingestion as Cloud Run job with GCS trigger, retry + idempotent upsert,
per-corpus timing logs.

This job is triggered when new source files are uploaded to GCS, processes them
through the ingestion pipeline, and upserts to the database.
"""
import asyncio
import logging

import structlog
import time
from datetime import datetime
from typing import Any

from app.core.config import settings
from app.db.session import db_manager
from app.services.ingestion_service import IngestionService

logger = structlog.get_logger(__name__)


class IngestionJob:
    """Cloud Run job for corpus ingestion with retry and idempotency."""

    def __init__(self):
        self.ingestion_service = IngestionService()
        self.logger = logger.bind(service="IngestionJob")

    async def process_corpus(
        self,
        corpus_id: str,
        gcs_path: str,
        jurisdiction: str,
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ) -> dict[str, Any]:
        """
        Process a corpus from GCS with retry logic.

        Args:
            corpus_id: Unique identifier for the corpus (e.g., "za-2024-01")
            gcs_path: GCS path to the raw corpus files
            jurisdiction: Jurisdiction code (e.g., "za", "ng")
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds

        Returns:
            Dict with processing results and timing information
        """
        start_time = time.time()
        self.logger.info(
            "Starting corpus ingestion",
            corpus_id=corpus_id,
            gcs_path=gcs_path,
            jurisdiction=jurisdiction,
        )

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    self.logger.info(
                        f"Retry attempt {attempt}/{max_retries}",
                        corpus_id=corpus_id,
                        delay=retry_delay,
                    )
                    await asyncio.sleep(retry_delay)

                # Initialize database connection
                db_manager.initialize()

                # Process corpus
                result = await self.ingestion_service.ingest_corpus(
                    corpus_id=corpus_id,
                    gcs_path=gcs_path,
                    jurisdiction=jurisdiction,
                )

                total_time = time.time() - start_time
                self.logger.info(
                    "Corpus ingestion completed successfully",
                    corpus_id=corpus_id,
                    attempt=attempt + 1,
                    total_time=round(total_time, 2),
                    sections_processed=result.get("sections_processed", 0),
                    chunks_created=result.get("chunks_created", 0),
                )

                return {
                    "success": True,
                    "corpus_id": corpus_id,
                    "jurisdiction": jurisdiction,
                    "attempt": attempt + 1,
                    "total_time_seconds": round(total_time, 2),
                    "sections_processed": result.get("sections_processed", 0),
                    "chunks_created": result.get("chunks_created", 0),
                    "embeddings_generated": result.get("embeddings_generated", 0),
                    "timing": result.get("timing", {}),
                    "completed_at": datetime.now().isoformat(),
                }

            except Exception as e:
                last_error = e
                self.logger.error(
                    "Corpus ingestion failed",
                    corpus_id=corpus_id,
                    attempt=attempt + 1,
                    error=str(e),
                    exc_info=True,
                )

        # All retries exhausted
        total_time = time.time() - start_time
        return {
            "success": False,
            "corpus_id": corpus_id,
            "jurisdiction": jurisdiction,
            "attempts": max_retries + 1,
            "total_time_seconds": round(total_time, 2),
            "error": str(last_error),
            "error_type": type(last_error).__name__,
            "failed_at": datetime.now().isoformat(),
        }

    async def process_multiple_corpora(
        self, corpora: list[dict[str, str]], max_concurrent: int = 3
    ) -> dict[str, Any]:
        """
        Process multiple corpora concurrently with controlled concurrency.

        Args:
            corpora: List of dicts with corpus_id, gcs_path, jurisdiction
            max_concurrent: Maximum number of concurrent processing jobs

        Returns:
            Dict with overall results and per-corpus details
        """
        start_time = time.time()
        self.logger.info(
            "Starting multi-corpus ingestion",
            total_corpora=len(corpora),
            max_concurrent=max_concurrent,
        )

        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(corpus: dict[str, str]) -> dict[str, Any]:
            async with semaphore:
                return await self.process_corpus(
                    corpus_id=corpus["corpus_id"],
                    gcs_path=corpus["gcs_path"],
                    jurisdiction=corpus["jurisdiction"],
                )

        results = await asyncio.gather(
            *[process_with_semaphore(corpus) for corpus in corpora],
            return_exceptions=True,
        )

        total_time = time.time() - start_time
        successful = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
        failed = len(results) - successful

        self.logger.info(
            "Multi-corpus ingestion completed",
            total_corpora=len(corpora),
            successful=successful,
            failed=failed,
            total_time=round(total_time, 2),
        )

        return {
            "total_corpora": len(corpora),
            "successful": successful,
            "failed": failed,
            "total_time_seconds": round(total_time, 2),
            "results": [r if isinstance(r, dict) else {"error": str(r)} for r in results],
            "completed_at": datetime.now().isoformat(),
        }


# Global instance
ingestion_job = IngestionJob()


async def main():
    """Main entry point for Cloud Run job."""
    import sys

    # Parse command line arguments
    if len(sys.argv) < 4:
        print("Usage: python -m app.services.ingestion_job <corpus_id> <gcs_path> <jurisdiction>")
        sys.exit(1)

    corpus_id = sys.argv[1]
    gcs_path = sys.argv[2]
    jurisdiction = sys.argv[3]

    job = IngestionJob()
    result = await job.process_corpus(corpus_id, gcs_path, jurisdiction)

    if result["success"]:
        print(f"✅ Ingestion completed: {result}")
        sys.exit(0)
    else:
        print(f"❌ Ingestion failed: {result}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
