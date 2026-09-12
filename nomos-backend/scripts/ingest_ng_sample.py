#!/usr/bin/env python3
"""
Script to ingest NG sample data (Labour Act) into NOMOS database.
This script demonstrates the NG pipeline:
1. Parse the sample file using NGParser
2. Create chunks with parent context prepended using ZAChunker (reusing for now)
3. Generate embeddings using the configured provider
4. Store chunks with embeddings in PostgreSQL
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add the app directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from app.services.ingestion_service import IngestionService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Main ingestion function for NG sample data."""
    logger.info("=" * 60)
    logger.info("NOMOS v2 - NG Sample Data Ingestion")
    logger.info("Processing Nigerian Labour Act sample")
    logger.info("=" * 60)

    # Initialize ingestion service
    ingestion_service = IngestionService()

    try:
        # Define the NG sample file path
        sample_file = Path("data/gcs-layout/raw/ng/acts/labour_act_sample.txt")

        if not sample_file.exists():
            logger.error(f"Sample file not found: {sample_file}")
            return False

        # Ingest the NG sample using our ingestion service
        # We'll treat this as a custom ingestion for NG
        logger.info("Step 1: Ingesting NG Labour Act sample...")

        # Since we don't have a specific act_key in ACT_CONFIGS for this sample,
        # we'll create a custom ingestion process
        from app.parsers.ng_parser import NGParser
        from app.chunkers.za_chunker import ZAChunker
        from app.services.ai.embedding_service import embedding_service
        from app.db.session import db_manager
        from app.models import Jurisdiction, Source, DocumentType, Version
        from sqlalchemy import select
        from datetime import datetime

        # Initialize database
        if db_manager._engine is None:
            db_manager.initialize()

        # Parse the file
        parser = NGParser()
        sections = parser.parse_file(sample_file)
        logger.info(f"Parsed {len(sections)} sections from NG sample")

        if not sections:
            logger.error("No sections parsed from sample file")
            return False

        # Create chunks using ZAChunker (we can reuse it for now)
        chunker = ZAChunker(max_chunk_size=500)
        legal_chunks = chunker.chunk_sections(sections, act_name="Labour Act")
        logger.info(f"Created {len(legal_chunks)} chunks from NG sample")

        if not legal_chunks:
            logger.error("No chunks created from sections")
            return False

        # Generate embeddings
        embedded_chunks = await embedding_service.embed_chunks(legal_chunks)
        logger.info(f"Generated embeddings for {len(embedded_chunks)} chunks")

        # Store in database
        async with db_manager.session() as session:
            # Get or create source for NG Labour Act
            from app.services.ingestion_service import IngestionService as IngestionServiceClass
            temp_service = IngestionServiceClass()
            source = await temp_service._get_or_create_source(
                session=session,
                jurisdiction=Jurisdiction.NG,  # Pass the enum object like ZA does
                source_id="ng-act-labour-act-sample",
                title="Labour Act (Sample)",
                document_type=DocumentType.ACT,
                metadata={"imported_at": datetime.utcnow().isoformat()},
            )

            # Create version
            version, changed = await temp_service._upsert_version(
                session=session,
                source=source,
                version_id="2004-03-31",  # Using the date from our ACT_CONFIGS
                as_at_date=datetime(2004, 3, 31),
                content_hash="sample-hash-placeholder",  # In real scenario, this would be computed
                amendment_note="Sample import for testing NG ingestion",
                metadata={"sample": True},
            )

            if not changed and version.chunk_count > 0:
                logger.info("NG sample data already ingested, skipping storage")
                await session.commit()
            else:
                # Store the chunks
                from app.models import Chunk
                chunk_objects = []
                for i, chunk in enumerate(embedded_chunks):
                    chunk_objects.append(
                        Chunk(
                            version_id=version.id,
                            as_at_date=version.as_at_date,
                            version_string=version.version_id,
                            chunk_index=i,
                            section_no=str(i),  # Simplified for sample
                            heading=f"Section {i+1}",  # Simplified for sample
                            text=chunk.content,
                            token_count=len(chunk.content.split()),
                            embedding=chunk.embedding,
                            in_force=True,
                            metadata_json={
                                **(chunk.metadata or {}),
                                "act_name": "Labour Act (Sample)",
                            },
                        )
                    )
                session.add_all(chunk_objects)
                version.chunk_count = len(chunk_objects)
                version.token_count = sum(c.token_count for c in chunk_objects)
                await session.commit()

                logger.info(f"Ingestion completed for NG sample: {len(chunk_objects)} chunks stored")

        logger.info("=" * 60)
        logger.info("NG SAMPLE INGESTION COMPLETED SUCCESSFULLY")
        logger.info("=" * 60)
        return True

    except Exception as e:
        logger.error(f"❌ NG sample ingestion failed with error: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    # Run the async main function
    success = asyncio.run(main())
    sys.exit(0 if success else 1)