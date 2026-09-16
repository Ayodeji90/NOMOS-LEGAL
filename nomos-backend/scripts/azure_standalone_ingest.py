#!/usr/bin/env python3
"""Standalone ingest script — uses asyncpg directly (no SQLAlchemy ORM overhead),
with DNS resilience + rate-limit retry baked in. Writes one act at a time.

DNS fix: monkey-patches socket.getaddrinfo at import time so asyncpg's
internal resolution retries via Google DNS when the local resolver fails.

Usage:
    python scripts/azure_standalone_ingest.py bcea
    python scripts/azure_standalone_ingest.py companies_act
"""
# ---- DNS monkey-patch (MUST be first) ----
import socket
import subprocess
import time
import logging as _prelog

_prelog.basicConfig(level=_prelog.INFO, format="%(asctime)s %(levelname)s %(message)s")
_prelogger = _prelog.getLogger("dns_patch")

_orig_getaddrinfo = socket.getaddrinfo
_GOOGLE_DNS = "8.8.8.8"


def _resilient_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    """Retry DNS with Google DNS fallback."""
    for attempt in range(3):
        try:
            return _orig_getaddrinfo(host, port, family, type, proto, flags)
        except socket.gaierror:
            if attempt == 0:
                _prelogger.warning("Local DNS failed for %s, retrying...", host)
            time.sleep(2 * (attempt + 1))
    # Final fallback: use nslookup with Google DNS
    _prelogger.warning("All local DNS retries failed, trying Google DNS...")
    try:
        result = subprocess.run(
            ["nslookup", host, _GOOGLE_DNS],
            capture_output=True, text=True, timeout=15,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if "Address:" in line and _GOOGLE_DNS not in line:
                ip = line.split(":", 1)[1].strip()
                if ip and "." in ip and ip != _GOOGLE_DNS:
                    _prelogger.info("Google DNS resolved %s -> %s", host, ip)
                    return _orig_getaddrinfo(ip, port, family, type, proto, flags)
    except Exception as e:
        _prelogger.error("Google DNS fallback failed: %s", e)
    raise socket.gaierror(f"DNS resolution failed for {host} after all retries")


socket.getaddrinfo = _resilient_getaddrinfo
# ---- End DNS patch ----

import asyncio
import hashlib
import json
import logging
import os
import ssl
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logger = logging.getLogger("standalone_ingest")


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("act_key", choices=["bcea", "companies_act"])
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    pg_host = os.environ["PG_HOST"]
    pg_user = os.environ["PG_USER"]
    pg_pass = os.environ["PG_PASS"]
    pg_db = os.environ.get("PG_DB", "nomos")

    from app.core.config import settings
    from app.services.ingestion_service import ACT_CONFIGS, IngestionService
    from app.services.ai.embedding_service import embedding_service

    cfg = ACT_CONFIGS[args.act_key]
    raw_dir = Path(settings.INGESTION_RAW_DIR) / "acts"
    text_path = raw_dir / f"{args.act_key}_full.txt"

    if not text_path.exists():
        logger.error("File not found: %s", text_path)
        return 1

    logger.info("=== %s | provider=%s | batch_size=%d ===",
                args.act_key, settings.EMBEDDING_PROVIDER, args.batch_size)

    # 1. Parse + chunk (fast)
    svc = IngestionService()
    sections = await svc._parse_sections(args.act_key, text_path)
    logger.info("Parsed %d sections", len(sections))
    chunks = svc.chunker.chunk_sections(sections, act_name=cfg["act_name"])
    logger.info("Created %d chunks", len(chunks))
    texts = [c.content for c in chunks]

    # 2. Embed in batches
    batch_size = args.batch_size
    total_batches = (len(texts) + batch_size - 1) // batch_size
    all_embeddings = []

    for batch_idx in range(total_batches):
        batch_num = batch_idx + 1
        start = batch_idx * batch_size
        end = min(start + batch_size, len(texts))
        batch_texts = texts[start:end]

        logger.info("Embedding batch %d/%d (%d texts)...", batch_num, total_batches, len(batch_texts))
        for attempt in range(5):
            try:
                t0 = time.monotonic()
                vecs = await embedding_service.generate_embeddings(batch_texts)
                elapsed = time.monotonic() - t0
                all_embeddings.extend(vecs)
                logger.info("  Batch %d done in %.1fs: %d vectors", batch_num, elapsed, len(vecs))
                break
            except Exception as e:
                # Inner retry already waited 65s per attempt. On failure,
                # wait 3 min for Azure rate window to fully reset.
                wait = 180.0
                logger.warning("  Batch %d failed (attempt %d): %s — waiting %.0fs",
                               batch_num, attempt + 1, str(e)[:120], wait)
                await asyncio.sleep(wait)
        else:
            logger.error("FAILED batch %d after 5 retries", batch_num)
            return 1

        if batch_num < total_batches:
            # Azure S0 embedding: ~6 RPM for small batches (5 items).
            # Our test showed 15s gaps work reliably.
            logger.info("  Waiting 20s for rate pacing...")
            await asyncio.sleep(20)

    logger.info("All %d chunks embedded", len(all_embeddings))

    # 3. Write to DB via asyncpg
    import asyncpg

    conn = None
    for attempt in range(10):
        try:
            logger.info("Connecting to DB at %s (attempt %d)...", pg_host, attempt + 1)
            conn = await asyncpg.connect(
                host=pg_host,
                port=5432,
                user=pg_user,
                password=pg_pass,
                database=pg_db,
                ssl="require",
            )
            logger.info("DB connected")
            break
        except Exception as e:
            logger.warning("DB connect failed (attempt %d): %s", attempt + 1, str(e)[:200])
            await asyncio.sleep(5)
    else:
        logger.error("Could not connect to DB after 10 attempts")
        return 1

    try:
        # Check if source already exists
        row = await conn.fetchrow(
            "SELECT id FROM source WHERE source_id = $1", cfg["source_id"]
        )

        if row is None:
            source_id = await conn.fetchval(
                """INSERT INTO source (id, source_id, title, jurisdiction, document_type, authority_level, metadata_json)
                   VALUES (gen_random_uuid(), $1, $2, $3, $4, 0, $5) RETURNING id""",
                cfg["source_id"],
                cfg["title"],
                "za",
                (cfg["document_type"].value if hasattr(cfg["document_type"], "value") else str(cfg["document_type"])).lower(),
                json.dumps({"act_no": cfg["act_name"]}),
            )
            logger.info("Created source id=%s", source_id)
        else:
            source_id = row["id"]
            logger.info("Source exists id=%s", source_id)

        # Create version
        content_hash = hashlib.sha256(
            "".join(t + (c.heading or "") + (c.section_number or "")
                    for t, c in zip(texts, chunks)).encode()
        ).hexdigest()

        version_id = await conn.fetchval(
            """INSERT INTO version (id, source_id, version_id, as_at_date, status, content_hash, chunk_count, token_count, metadata_json)
               VALUES (gen_random_uuid(), $1, $2, $3, 'in_force', $4, $5, 0, '{}') RETURNING id""",
            source_id,
            cfg["version_id"],
            cfg["as_at_date"],
            content_hash,
            len(chunks),
        )
        logger.info("Created version id=%s", version_id)

        # Insert chunks
        CHUNK_BATCH = 50
        inserted = 0
        for i in range(0, len(chunks), CHUNK_BATCH):
            batch_chunks = chunks[i:i+CHUNK_BATCH]
            batch_embs = all_embeddings[i:i+CHUNK_BATCH]
            records = []
            for idx, (c, emb) in enumerate(zip(batch_chunks, batch_embs)):
                token_count = len(c.content.split())
                global_index = i + idx  # unique across the entire act
                records.append((
                    version_id,
                    cfg["as_at_date"],
                    cfg["version_id"],
                    global_index,
                    c.section_number,
                    None,  # subsection
                    c.heading,
                    c.content,
                    token_count,
                    str(emb),  # pgvector expects string representation
                    True,  # in_force
                    json.dumps({"document_type": (cfg["document_type"].value if hasattr(cfg["document_type"], "value") else str(cfg["document_type"]))}),
                ))
            await conn.executemany(
                """INSERT INTO chunk
                   (id, version_id, as_at_date, version_string, chunk_index, section_no, subsection, heading, text, token_count, embedding, in_force, metadata_json)
                   VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8, $9, $10::vector, $11, $12)""",
                records,
            )
            inserted += len(records)
            logger.info("  Inserted %d/%d chunks", inserted, len(chunks))

        logger.info("=== %s COMPLETE: %d chunks (source_id=%s, version_id=%s) ===",
                     args.act_key, inserted, source_id, version_id)
        return 0

    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
