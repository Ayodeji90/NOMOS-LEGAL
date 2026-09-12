"""
Ingestion service: parse -> chunk -> embed -> upsert for the ZA corpus.

Week-2 pipeline (real sources, real embeddings):

- Sources are the typeset Government Gazette texts produced by
  ``scripts/fetch_za_acts.py`` (see data/gcs-layout/raw/za/acts/manifest.json
  for provenance and sha256 checksums). The fabricated sample XMLs from the
  earlier attempt are quarantined and are never ingested.
- ``.txt`` gazette texts are parsed with ``app.parsers.gazette_parser``
  (heading + numbered-marker state machine); legacy ``.xml`` inputs fall back
  to ``app.parsers.za_parser``.
- Embeddings come from the configured provider (``EMBEDDING_PROVIDER``):
  Vertex AI text-embedding-005 in production, deterministic mock for tests.
- Upserts are idempotent per (source, version): the content hash (sha256 of
  the parsed section stream) decides whether to skip, replace chunks, or
  create a new version.

Every chunk's text carries the parent context prepend
``"[Act N of Y] Section N Heading: body"`` so embeddings and lexical matches
both benefit from the heading/act context.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chunkers.za_chunker import LegalChunk, ZAChunker
from app.core.config import settings
from app.db.session import db_manager
from app.models import (
    Chunk,
    DocumentType,
    Jurisdiction,
    Source,
    SourceStatus,
    Version,
)
from app.parsers import gazette_parser
from app.parsers.za_parser import Section, ZAParser
from app.services.ai.embedding_service import embedding_service

logger = logging.getLogger(__name__)

# Canonical corpus entries. provenance lives in the acts manifests written
# by scripts/fetch_za_acts.py and scripts/fetch_ng_acts.py; only what ingestion needs is repeated here.
ACT_CONFIGS: dict[str, dict] = {
    "bcea": {
        "title": "Basic Conditions of Employment Act",
        "act_name": "Basic Conditions of Employment Act 75 of 1997",
        "source_id": "za-act-75-1997-bcea",
        "version_id": "1998-12-01",  # commencement
        "as_at_date": datetime(1998, 12, 1),
        "document_type": DocumentType.ACT,
    },
    "companies_act": {
        "title": "Companies Act",
        "act_name": "Companies Act 71 of 2008",
        "source_id": "za-act-71-2008-companies",
        "version_id": "2011-05-01",  # commencement
        "as_at_date": datetime(2011, 5, 1),
        "document_type": DocumentType.ACT,
    },
    # NG (Nigerian) corpus entries
    "labour_act_ng": {
        "title": "Labour Act",
        "act_name": "Labour Act",
        "source_id": "ng-act-labour-act",
        "version_id": "2004-03-31",  # commencement
        "as_at_date": datetime(2004, 3, 31),
        "document_type": DocumentType.ACT,
    },
    "cam_a_ng": {
        "title": "Companies and Allied Matters Act",
        "act_name": "Companies and Allied Matters Act",
        "source_id": "ng-act-cam-a",
        "version_id": "2004-03-31",  # commencement
        "as_at_date": datetime(2004, 3, 31),
        "document_type": DocumentType.ACT,
    },
    "employee_compensation_act_ng": {
        "title": "Employee Compensation Act",
        "act_name": "Employee Compensation Act",
        "source_id": "ng-act-employee-compensation",
        "version_id": "2004-03-31",  # commencement
        "as_at_date": datetime(2004, 3, 31),
        "document_type": DocumentType.ACT,
    },
}


def _sha256_chunks(chunks: list[LegalChunk]) -> str:
    """Deterministic hash over the exact chunk stream to be stored.

    Hashing the *chunk* stream (content + section_no + heading + order), not
    just the parsed sections, means any change upstream (parser fix, chunker
    format change, context-prepend fix) flips the hash and triggers a clean
    re-embed + replace on the next ingestion run.
    """
    import hashlib

    h = hashlib.sha256()
    for c in chunks:
        h.update(c.id.encode("utf-8"))
        h.update(b"\x00")
        h.update(c.section_number.encode("utf-8"))
        h.update(b"\x00")
        h.update(c.heading.encode("utf-8"))
        h.update(b"\x00")
        h.update(c.content.encode("utf-8"))
        h.update(b"\x1e")  # record separator
    return h.hexdigest()


class IngestionService:
    """Ingest ZA legal acts into the NOMOS database (idempotent)."""

    def __init__(self, embedding_service_override=None):
        self.gazette_parser = gazette_parser
        self.legacy_parser = ZAParser()
        self.chunker = ZAChunker(
            max_chunk_size=settings.INGESTION_CHUNK_MAX_TOKENS * 4  # ~chars
        )
        self.embedding_service = embedding_service_override or embedding_service
        if db_manager._engine is None:
            db_manager.initialize()
        logger.info("IngestionService initialized")

    # ------------------------------------------------------------------
    # Source / version helpers
    # ------------------------------------------------------------------
    async def _get_or_create_source(
        self,
        session: AsyncSession,
        jurisdiction: Jurisdiction,
        source_id: str,
        title: str,
        document_type: DocumentType,
        metadata: dict | None = None,
    ) -> Source:
        stmt = select(Source).where(
            Source.jurisdiction == jurisdiction,
            Source.source_id == source_id,
        )
        try:
            source = (await session.execute(stmt)).scalar_one_or_none()
        except Exception as e:
            logger.error("Error in _get_or_create_source: %s", e)
            logger.error("Jurisdiction: %s, value: %s", jurisdiction, jurisdiction.value)
            raise
        if source is None:
            source = Source(
                jurisdiction=jurisdiction.value,  # Use the enum value, not the enum object
                source_id=source_id,
                title=title,
                document_type=document_type,
                authority_level=1,  # national legislation
                metadata_json=metadata or {},
            )
            session.add(source)
            await session.flush()
            logger.info("Created source: %s (%s)", title, source_id)
        else:
            logger.info("Found existing source: %s (%s)", title, source_id)
        return source

    async def _upsert_version(
        self,
        session: AsyncSession,
        source: Source,
        version_id: str,
        as_at_date: datetime,
        content_hash: str,
        amendment_note: str | None = None,
        metadata: dict | None = None,
    ) -> tuple[Version, bool]:
        """Return (version, changed).

        - version missing          -> create, changed=True
        - hash equal               -> reuse, changed=False (skip re-embed)
        - hash differs             -> update hash/note in place and replace
                                      chunks (single in-force lineage)
        """
        stmt = select(Version).where(
            Version.source_id == source.id,
            Version.version_id == version_id,
        )
        version = (await session.execute(stmt)).scalar_one_or_none()
        if version is None:
            version = Version(
                source_id=source.id,
                version_id=version_id,
                as_at_date=as_at_date,
                status=SourceStatus.IN_FORCE,
                amendment_note=amendment_note,
                content_hash=content_hash,
                metadata_json=metadata or {},
            )
            session.add(version)
            await session.flush()
            logger.info("Created version %s for %s", version_id, source.title)
            return version, True
        if version.content_hash == content_hash:
            logger.info(
                "Version %s for %s unchanged (hash match) -- skip",
                version_id,
                source.title,
            )
            return version, False
        logger.info(
            "Version %s for %s content changed -- replacing chunks",
            version_id,
            source.title,
        )
        version.content_hash = content_hash
        if metadata:
            version.metadata_json = {**(version.metadata_json or {}), **metadata}
        await session.flush()
        return version, True

    # ------------------------------------------------------------------
    # Chunk storage
    # ------------------------------------------------------------------
    async def _replace_chunks(
        self,
        session: AsyncSession,
        version: Version,
        chunks: list[LegalChunk],
    ) -> int:
        await session.execute(delete(Chunk).where(Chunk.version_id == version.id))

        chunk_objects = []
        for i, chunk in enumerate(chunks):
            chunk_objects.append(
                Chunk(
                    version_id=version.id,
                    as_at_date=version.as_at_date,
                    version_string=version.version_id,
                    chunk_index=i,
                    section_no=chunk.section_number,
                    heading=chunk.heading,
                    text=chunk.content,
                    token_count=len(chunk.content.split()),
                    embedding=chunk.embedding,
                    in_force=True,
                    metadata_json={
                        **(chunk.metadata or {}),
                        "act_name": chunk.act_name,
                    },
                )
            )
        session.add_all(chunk_objects)
        await session.flush()

        version.chunk_count = len(chunk_objects)
        version.token_count = sum(c.token_count for c in chunk_objects)
        logger.info("Stored %d chunks for version %s", len(chunk_objects), version.version_id)
        return len(chunk_objects)

    # ------------------------------------------------------------------
    # Per-act pipeline
    # ------------------------------------------------------------------
    async def _parse_sections(self, act_key: str, path: Path) -> list[Section]:
        if path.suffix.lower() == ".txt":
            # Determine jurisdiction from act_key
            if act_key.startswith("ng") or act_key in ["labour_act_ng", "cam_a_ng", "employee_compensation_act_ng"]:
                # Use NG parser for NG acts
                from app.parsers.ng_parser import NGParser
                parser = NGParser()
                sections = parser.parse_file(path)
                logger.info("Parsed %d sections from NG text %s", len(sections), path.name)
                return sections
            else:
                # Use gazette parser for ZA acts
                sections = self.gazette_parser.parse_file(act_key, path)
                logger.info("Parsed %d units from gazette text %s", len(sections), path.name)
                return sections
        # legacy XML/HTML path via the original line parser
        sections = self.legacy_parser.parse_file(path)
        logger.info("Parsed %d sections (legacy parser) from %s", len(sections), path.name)
        return sections

    async def ingest_act(self, act_key: str, xml_file_path: Path) -> dict:
        """Parse, chunk, embed and upsert one act. Returns a summary dict."""
        cfg = ACT_CONFIGS[act_key]
        logger.info("Ingesting %s from %s", act_key, xml_file_path.name)

        sections = await self._parse_sections(act_key, xml_file_path)
        if not sections:
            raise RuntimeError(f"No sections parsed from {xml_file_path}")

        legal_chunks = self.chunker.chunk_sections(sections, act_name=cfg["act_name"])
        logger.info("Created %d chunks for %s", len(legal_chunks), act_key)
        content_hash = _sha256_chunks(legal_chunks)

        # Embed BEFORE opening the write transaction: a Vertex call can take
        # minutes and must not hold a DB transaction open.
        embedded_chunks = await self.embedding_service.embed_chunks(legal_chunks)

        # Determine jurisdiction based on act_key
        jurisdiction = Jurisdiction.NG if act_key.startswith("ng") or act_key in ["labour_act_ng", "cam_a_ng", "employee_compensation_act_ng"] else Jurisdiction.ZA

        async with db_manager.session() as session:
            source = await self._get_or_create_source(
                session=session,
                jurisdiction=jurisdiction,
                source_id=cfg["source_id"],
                title=cfg["title"],
                document_type=cfg["document_type"],
                metadata={
                    "act_no": cfg["act_name"],
                    "imported_at": datetime.utcnow().isoformat(),
                },
            )
            version, changed = await self._upsert_version(
                session=session,
                source=source,
                version_id=cfg["version_id"],
                as_at_date=cfg["as_at_date"],
                content_hash=content_hash,
                amendment_note="As-gazetted import (see acts manifest)",
                metadata={
                    "content_sha256": content_hash,
                    "source_pdf": xml_file_path.with_suffix(".pdf").name,
                },
            )
            if not changed:
                await session.commit()
                return {
                    "status": "skipped",
                    "reason": "content hash unchanged",
                    "source_id": str(source.id),
                    "version_id": str(version.id),
                    "chunk_count": version.chunk_count,
                }

            chunk_count = await self._replace_chunks(
                session=session, version=version, chunks=embedded_chunks
            )
            await session.commit()
            logger.info("Ingestion completed for %s: %d chunks", cfg["title"], chunk_count)
            return {
                "status": "ingested",
                "source_id": str(source.id),
                "version_id": str(version.id),
                "chunk_count": chunk_count,
                "content_sha256": content_hash,
            }

    # ------------------------------------------------------------------
    # Batch entry point (used by ingest_za_acts.py CLI)
    # ------------------------------------------------------------------
    async def ingest_bcea_and_companies_act(self) -> dict:
        """Ingest both BCEA and Companies Act 71/2008."""
        raw_dir = Path(settings.INGESTION_RAW_DIR)
        acts_dir = raw_dir / "acts"

        results: dict = {}
        for act_key in ACT_CONFIGS:
            text_path = acts_dir / f"{act_key}_full.txt"
            try:
                if not text_path.exists():
                    raise FileNotFoundError(
                        f"{text_path} not found -- run scripts/fetch_za_acts.py first"
                    )
                summary = await self.ingest_act(act_key, text_path)
                results[act_key] = {"status": summary["status"], **summary}
            except Exception as exc:  # noqa: BLE001 - report per-act failures
                logger.error("%s ingestion failed: %s", act_key, exc)
                results[act_key] = {"status": "failed", "error": str(exc)}

        successful = [
            k
            for k, v in results.items()
            if k in ACT_CONFIGS and v["status"] in ("ingested", "skipped")
        ]
        results["summary"] = {
            "total_acts_processed": len(ACT_CONFIGS),
            "successful_acts": len(successful),
            "failed_acts": len(ACT_CONFIGS) - len(successful),
            "total_chunks": sum(
                v.get("chunk_count", 0) for k, v in results.items() if k in ACT_CONFIGS
            ),
        }
        logger.info("Ingestion summary: %s", results["summary"])
        return results

    # ------------------------------------------------------------------
    # Spot-check: deterministic sample + parent-context verification
    # ------------------------------------------------------------------
    async def spot_check_sections(self, limit: int = 10, act_key: str | None = None) -> list[dict]:
        """Deterministically sample chunks and verify parent context.

        Selection is stable across runs: per act, chunks are ordered by
        chunk_index and evenly spaced samples are taken. For each sample we
        verify the ``[Act] Section N Heading:`` prepend against the stored
        heading/section_no, i.e. that the embedding text carries the right
        parent context.
        """
        logger.info("Spot-check: %d sections (act=%s)", limit, act_key or "all")

        async with db_manager.session() as session:
            from sqlalchemy import text as sql_text

            query = sql_text(
                """
                SELECT
                    c.id,
                    c.heading,
                    c.text,
                    c.section_no,
                    c.chunk_index,
                    v.version_id,
                    s.title AS source_title,
                    s.source_id,
                    s.metadata_json->>'act_no' AS act_no,
                    s.jurisdiction,
                    (c.embedding IS NOT NULL) AS has_embedding
                FROM chunk c
                JOIN version v ON c.version_id = v.id
                JOIN source s ON v.source_id = s.id
                WHERE s.jurisdiction IN ('za', 'ng') AND c.in_force = true
                ORDER BY s.source_id, c.chunk_index
                """
            )
            rows = (await session.execute(query)).fetchall()

        # group by act
        per_act: dict[str, list] = {}
        for row in rows:
            per_act.setdefault(row.source_id, []).append(row)
        if act_key:
            cfg = ACT_CONFIGS.get(act_key)
            if cfg and cfg["source_id"] in per_act:
                per_act = {cfg["source_id"]: per_act[cfg["source_id"]]}

        n_acts = max(len(per_act), 1)
        per_act_limit = max(limit // n_acts, 1)
        check_results: list[dict] = []

        for source_id, act_rows in sorted(per_act.items()):
            total = len(act_rows)
            if total == 0:
                continue
            step = max(total / per_act_limit, 1)
            picks = sorted({int(k * step) for k in range(per_act_limit)})
            for idx in picks:
                if idx >= total:
                    idx = total - 1
                row = act_rows[idx]
                (
                    chunk_id,
                    heading,
                    text,
                    section_no,
                    chunk_index,
                    version_id,
                    source_title,
                    _sid,
                    act_no,
                    jurisdiction,
                    has_embedding,
                ) = row

                # Expected context per the chunker's prepend format:
                # "[Act N of Y] [Section N ]Heading: body". Section/heading
                # parts are omitted when absent (preamble/schedule rows).
                expected_parts = []
                if act_no:
                    expected_parts.append(act_no)
                if section_no and section_no != "unknown":
                    expected_parts.append(f"Section {section_no}")
                if heading:
                    expected_parts.append(heading)
                expected_context = " ".join(expected_parts)
                has_context = (
                    bool(text) and bool(expected_context) and text.startswith(expected_context)
                )

                check_results.append(
                    {
                        "chunk_id": str(chunk_id),
                        "source_title": source_title,
                        "source_id": source_id,
                        "jurisdiction": jurisdiction,
                        "chunk_index": chunk_index,
                        "section_no": section_no,
                        "heading": heading,
                        "version_id": version_id,
                        "has_embedding": bool(has_embedding),
                        "has_correct_context": has_context,
                        "expected_context": expected_context,
                        "actual_preview": (
                            text[:200] + "..." if text and len(text) > 200 else text
                        ),
                    }
                )

        logger.info("Spot-check done: %d sections checked", len(check_results))
        return check_results


if __name__ == "__main__":  # pragma: no cover - manual CLI
    logging.basicConfig(level=logging.INFO)
    svc = IngestionService()
    print(asyncio.run(svc.ingest_bcea_and_companies_act()))
