#!/usr/bin/env python3
"""
Verification script for Week 3 tasks: ZA version diff + asAt stamping + amendment notes
This script verifies that every ZA excerpt carries asAt + version.
"""

import sys
import asyncio
sys.path.append('.')

from app.db.session import db_manager
from app.models import Chunk, Version, Source
from sqlalchemy import select

async def verify_week3():
    """Verify that every ZA chunk carries asAt + version"""
    print("🔍 Verifying Week 3: ZA version diff + asAt stamping + amendment notes")
    print("=" * 80)

    # Initialize database (synchronous call)
    db_manager.initialize()
    print("✅ Database initialized")

    async with db_manager.session() as session:
        # Query for ZA chunks with their version information
        stmt = select(
            Chunk.id,
            Chunk.as_at_date,
            Chunk.version_string,
            Chunk.version_id,
            Version.as_at_date.label('version_as_at'),
            Version.version_id.label('version_version_id'),
            Version.amendment_note,
            Source.title
        ).join(
            Version, Chunk.version_id == Version.id
        ).join(
            Source, Version.source_id == Source.id
        ).where(
            Source.jurisdiction == 'za'
        ).limit(10)

        result = await session.execute(stmt)
        rows = result.fetchall()

        if not rows:
            print("❌ No ZA chunks found. Please run ingestion first.")
            return False

        print(f"📊 Found {len(rows)} ZA chunks to verify:")
        print()

        all_correct = True
        for i, row in enumerate(rows, 1):
            (chunk_id, chunk_as_at, chunk_version_string, chunk_version_id,
             version_as_at, version_version_id, amendment_note, source_title) = row

            # Check that chunk's as_at_date matches version's as_at_date
            as_at_match = chunk_as_at == version_as_at

            # Check that chunk's version_string matches version's version_id
            version_match = chunk_version_string == version_version_id

            # Check that both match
            is_correct = as_at_match and version_match

            status = "✅ PASS" if is_correct else "❌ FAIL"
            print(f"{i:2d}. {status} {source_title}")
            print(f"    Chunk ID: {chunk_id}")
            print(f"    Chunk asAt: {chunk_as_at}")
            print(f"    Version asAt: {version_as_at} (match: {as_at_match})")
            print(f"    Chunk version: {chunk_version_string}")
            print(f"    Version ID: {version_version_id} (match: {version_match})")
            if amendment_note:
                print(f"    Amendment note: {amendment_note}")
            print()

            if not is_correct:
                all_correct = False

        print("=" * 80)
        if all_correct:
            print("🎉 SUCCESS: All ZA chunks carry correct asAt + version!")
            print("   DELIVERABLE ACHIEVED: 'every ZA excerpt carries asAt + version'")
            return True
        else:
            print("❌ FAILURE: Some chunks have incorrect asAt or version")
            return False

if __name__ == "__main__":
    success = asyncio.run(verify_week3())
    sys.exit(0 if success else 1)