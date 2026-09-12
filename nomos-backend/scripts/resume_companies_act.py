#!/usr/bin/env python3
"""Resume only the failed Companies Act ingest (BCEA already done)."""

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, ".")

from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

assert settings.EMBEDDING_PROVIDER == "vertex", "EMBEDDING_PROVIDER must be vertex"


async def main() -> int:
    from app.services.ingestion_service import IngestionService

    svc = IngestionService()
    text_path = (
        Path(settings.INGESTION_RAW_DIR) / "acts" / "companies_act_full.txt"
    )
    result = await svc.ingest_act("companies_act", text_path)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") == "ingested" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
