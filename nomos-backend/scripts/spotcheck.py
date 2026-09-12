#!/usr/bin/env python3
"""Spot-check sampled chunks for parent context + real embeddings."""

import asyncio
import json
import sys

sys.path.insert(0, ".")

from app.services.ingestion_service import IngestionService


async def main() -> int:
    svc = IngestionService()
    results = await svc.spot_check_sections(limit=10)
    ok = sum(1 for r in results if r["has_correct_context"] and r["has_embedding"])
    print(
        json.dumps(
            [
                {
                    k: r[k]
                    for k in (
                        "source_id",
                        "section_no",
                        "heading",
                        "has_correct_context",
                        "has_embedding",
                    )
                }
                for r in results
            ],
            indent=1,
        )
    )
    print(f"PASSED {ok}/{len(results)}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
