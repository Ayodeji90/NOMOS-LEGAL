#!/usr/bin/env python3
"""
Demo script showing the BCEA & Companies Act embedding pipeline.
This demonstrates the complete flow without requiring a live database:
1. Parse XML files using ZAParser
2. Create chunks with parent context prepended using ZAChunker
3. Generate mock embeddings using EmbeddingService
4. Show that chunks are ready for upserting to PostgreSQL
"""

import asyncio
import logging
from pathlib import Path
from typing import List

# Add the app directory to Python path
import sys
sys.path.append(str(Path(__file__).parent))

from app.parsers.za_parser import ZAParser
from app.chunkers.za_chunker import ZAChunker, LegalChunk
from app.services.ai.embedding_service import embedding_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def demo_pipeline():
    """Demonstrate the complete embedding pipeline."""
    logger.info("=" * 70)
    logger.info("NOMOS v2 - BCEA & Companies Act Embedding Pipeline Demo")
    logger.info("Week 2 Task: Pair with E4 to chunk, embed, and prepare for upsert")
    logger.info("=" * 70)

    # Initialize services
    parser = ZAParser()
    chunker = ZAChunker()

    logger.info("Pipeline components initialized:")
    logger.info("  ✅ ZAParser (section extraction + heading tree)")
    logger.info("  ✅ ZAChunker (context prepending: Act + Section + Heading)")
    logger.info("  ✅ EmbeddingService (mock Vertex AI text-embedding-005)")
    logger.info("")

    # Process BCEA
    logger.info("📄 Processing Basic Conditions of Employment Act (BCEA)...")
    bcea_path = Path("/home/machinemustlearn/WORKSPACE/NOMOS-LEGAL/nomos-backend/data/gcs-layout/raw/za/bcea_full.xml")
    bcea_sections = parser.parse_file(bcea_path)
    logger.info(f"   Parsed {len(bcea_sections)} sections from BCEA")

    bcea_chunks = chunker.chunk_sections(bcea_sections)
    logger.info(f"   Created {len(bcea_chunks)} chunks from BCEA sections")

    # Generate embeddings for BCEA chunks
    logger.info("   Generating embeddings for BCEA chunks...")
    bcea_embedded_chunks = await embedding_service.embed_chunks(bcea_chunks)
    logger.info(f"   Generated {len(bcea_embedded_chunks)} embeddings for BCEA")

    # Show sample BCEA chunk with context
    if bcea_embedded_chunks:
        sample_chunk = bcea_embedded_chunks[0]
        logger.info(f"   Sample BCEA chunk:")
        logger.info(f"     ID: {sample_chunk.id}")
        logger.info(f"     Act: {sample_chunk.act_name}")
        logger.info(f"     Section: {sample_chunk.section_number}")
        logger.info(f"     Heading: {sample_chunk.heading}")
        logger.info(f"     Content preview: {sample_chunk.content[:100]}...")
        logger.info(f"     Embedding dimensions: {len(sample_chunk.embedding) if sample_chunk.embedding else 0}")
    logger.info("")

    # Process Companies Act
    logger.info("📄 Processing Companies Act 71/2008...")
    companies_act_path = Path("/home/machinemustlearn/WORKSPACE/NOMOS-LEGAL/nomos-backend/data/gcs-layout/raw/za/companies_act_full.xml")
    companies_act_sections = parser.parse_file(companies_act_path)
    logger.info(f"   Parsed {len(companies_act_sections)} sections from Companies Act")

    companies_act_chunks = chunker.chunk_sections(companies_act_sections)
    logger.info(f"   Created {len(companies_act_chunks)} chunks from Companies Act sections")

    # Generate embeddings for Companies Act chunks
    logger.info("   Generating embeddings for Companies Act chunks...")
    companies_act_embedded_chunks = await embedding_service.embed_chunks(companies_act_chunks)
    logger.info(f"   Generated {len(companies_act_embedded_chunks)} embeddings for Companies Act")

    # Show sample Companies Act chunk with context
    if companies_act_embedded_chunks:
        sample_chunk = companies_act_embedded_chunks[0]
        logger.info(f"   Sample Companies Act chunk:")
        logger.info(f"     ID: {sample_chunk.id}")
        logger.info(f"     Act: {sample_chunk.act_name}")
        logger.info(f"     Section: {sample_chunk.section_number}")
        logger.info(f"     Heading: {sample_chunk.heading}")
        logger.info(f"     Content preview: {sample_chunk.content[:100]}...")
        logger.info(f"     Embedding dimensions: {len(sample_chunk.embedding) if sample_chunk.embedding else 0}")
    logger.info("")

    # Summary
    total_sections = len(bcea_sections) + len(companies_act_sections)
    total_chunks = len(bcea_embedded_chunks) + len(companies_act_embedded_chunks)

    logger.info("📊 PIPELINE SUMMARY")
    logger.info("-" * 40)
    logger.info(f"Total sections parsed: {total_sections}")
    logger.info(f"Total chunks created: {total_chunks}")
    logger.info(f"Total embeddings generated: {total_chunks}")
    logger.info("")
    logger.info("🔍 CONTEXT PREPPENDING VERIFICATION")
    logger.info("-" * 40)

    # Verify a few chunks have correct context
    verification_chunks = []
    if bcea_embedded_chunks:
        verification_chunks.append(bcea_embedded_chunks[0])
    if companies_act_embedded_chunks:
        verification_chunks.append(companies_act_embedded_chunks[0])

    correct_context_count = 0
    for chunk in verification_chunks:
        expected_parts = []
        if chunk.act_name:
            expected_parts.append(chunk.act_name)
        if chunk.section_number:
            expected_parts.append(f"Section {chunk.section_number}")
        if chunk.heading:
            expected_parts.append(chunk.heading)

        expected_context = " ".join(expected_parts)
        has_correct_context = chunk.content.startswith(expected_context + ": ") if expected_context else False

        if has_correct_context:
            correct_context_count += 1
            status = "✅ CORRECT"
        else:
            status = "❌ INCORRECT"

        logger.info(f"   [{status}] {chunk.act_name} Section {chunk.section_number}: {chunk.heading}")
        if not has_correct_context:
            logger.info(f"     Expected start: {expected_context}")
            logger.info(f"     Actual start:   {chunk.content[:80]}...")

    logger.info("")
    logger.info(f"Context verification: {correct_context_count}/{len(verification_chunks)} chunks correct")

    # Final assessment
    logger.info("")
    logger.info("🎯 DELIVERABLE ASSESSMENT")
    logger.info("-" * 40)

    pipeline_success = (
        len(bcea_sections) > 0 and
        len(companies_act_sections) > 0 and
        len(bcea_embedded_chunks) == len(bcea_sections) and
        len(companies_act_embedded_chunks) == len(companies_act_sections) and
        correct_context_count >= len(verification_chunks) * 0.8  # Allow 20% tolerance
    )

    if pipeline_success:
        logger.info("✅ PIPELINE SUCCESS")
        logger.info("   BCEA and Companies Act processed successfully")
        logger.info("   Chunks created with parent context prepended")
        logger.info("   Embeddings generated (mock Vertex AI text-embedding-005)")
        logger.info("   Ready for upserting to PostgreSQL with pgvector")
        logger.info("")
        logger.info("📋 NEXT STEPS FOR PRODUCTION:")
        logger.info("   1. Configure live PostgreSQL connection")
        logger.info("   2. Replace mock embedding service with Vertex AI integration")
        logger.info("   3. Run actual ingestion to store chunks with embeddings")
        logger.info("   4. Verify 10 sections have correct parent context (spot-check)")
        return True
    else:
        logger.info("❌ PIPELINE ISSUES DETECTED")
        logger.info("   Please review the logs above for specific problems")
        return False


if __name__ == "__main__":
    # Run the async demo function
    success = asyncio.run(demo_pipeline())
    exit(0 if success else 1)