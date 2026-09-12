#!/usr/bin/env python3
"""
Audit script for Week 6: Verify asAt field is correctly set for ZA and NG chunks.
This script checks that every chunk has a non-null asAt date and that it matches
the version's asAt date.
"""

import sys
import asyncio
sys.path.append('.')

from app.db.session import db_manager
from app.models import Chunk, Version, Source
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime

async def audit_asat():
    """Audit asAt field for ZA and NG chunks."""
    print("🔍 Auditing asAt field for ZA and NG chunks")
    print("=" * 60)

    # Initialize database (synchronous call)
    try:
        db_manager.initialize()
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        return False

    async with db_manager.session() as session:
        try:
            # Query for chunks with their version and source information for ZA and NG
            stmt = select(
                Chunk.id,
                Chunk.as_at_date,
                Chunk.version_string,
                Chunk.version_id,
                Version.as_at_date.label('version_as_at'),
                Version.version_id.label('version_id'),
                Source.jurisdiction,
                Source.title
            ).join(
                Version, Chunk.version_id == Version.id
            ).join(
                Source, Version.source_id == Source.id
            ).where(
                Source.jurisdiction.in_(['za', 'ng'])
            ).order_by(
                Source.jurisdiction, Chunk.id
            )

            result = await session.execute(stmt)
            rows = result.fetchall()

            if not rows:
                print("❌ No chunks found for ZA or NG jurisdictions. Please run ingestion first.")
                return False

            print(f"📊 Found {len(rows)} chunks to audit:")
            print()

            all_correct = True
            za_count = 0
            ng_count = 0
            za_correct = 0
            ng_correct = 0

            for i, row in enumerate(rows, 1):
                (chunk_id, chunk_as_at, chunk_version_string, chunk_version_id,
                 version_as_at, version_version_id, jurisdiction, source_title) = row

                # Count by jurisdiction
                if jurisdiction == 'za':
                    za_count += 1
                elif jurisdiction == 'ng':
                    ng_count += 1

                # Check that chunk's as_at_date is not null
                if chunk_as_at is None:
                    print(f"{i:3d}. ❌ FAIL [{jurisdiction.upper()}] {source_title}")
                    print(f"     Chunk ID: {chunk_id}")
                    print(f"     as_at_date is NULL")
                    all_correct = False
                    continue

                # Check that chunk's as_at_date matches version's as_at_date
                as_at_match = chunk_as_at == version_as_at

                # Check that chunk's version_string matches version's version_id
                version_match = chunk_version_string == version_version_id

                # Overall check
                is_correct = as_at_match and version_match

                if jurisdiction == 'za' and is_correct:
                    za_correct += 1
                elif jurisdiction == 'ng' and is_correct:
                    ng_correct += 1

                status = "✅ PASS" if is_correct else "❌ FAIL"
                print(f"{i:3d}. {status} [{jurisdiction.upper()}] {source_title}")
                print(f"     Chunk ID: {chunk_id}")
                print(f"     Chunk asAt: {chunk_as_at}")
                print(f"     Version asAt: {version_as_at} (match: {as_at_match})")
                print(f"     Chunk version: {chunk_version_string}")
                print(f"     Version ID: {version_version_id} (match: {version_match})")
                print()

                if not is_correct:
                    all_correct = False

            print("=" * 60)
            print("📋 SUMMARY:")
            print(f"   ZA chunks: {za_count} total, {za_correct} correct")
            print(f"   NG chunks: {ng_count} total, {ng_correct} correct")
            print()

            if all_correct:
                print("🎉 SUCCESS: All chunks have correct asAt and version!")
                print("   Week 6 audit PASSED")
                return True
            else:
                print("❌ FAILURE: Some chunks have incorrect asAt or version")
                print("   Week 6 audit FAILED")
                return False

        except SQLAlchemyError as e:
            print(f"� Database error during audit: {e}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error during audit: {e}")
            return False

if __name__ == "__main__":
    success = asyncio.run(audit_asat())
    sys.exit(0 if success else 1)