#!/usr/bin/env python3
"""
Test script for NG Parser.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.parsers.ng_parser import NGParser

def test_ng_parser():
    """Test the NG parser on the sample Labour Act file."""
    print("🧪 Testing NG Parser")
    print("=" * 40)

    # Initialize parser
    parser = NGParser()
    print("✅ NG Parser initialized")

    # Define path to sample file (relative to nomos-backend directory)
    sample_file = Path("data/gcs-layout/raw/ng/acts/labour_act_sample.txt")
    if not sample_file.exists():
        print(f"�Sample file not found: {sample_file}")
        return False

    print(f"📄 Parsing file: {sample_file}")

    try:
        # Parse the file
        sections = parser.parse_file(sample_file)
        print(f"✅ Successfully parsed {len(sections)} sections")

        # Display first few sections
        print("\n📋 First 5 sections:")
        for i, section in enumerate(sections[:5], 1):
            print(f"{i}. ID: {section.id}")
            print(f"   Title: {section.title}")
            print(f"   Level: {section.level}")
            print(f"   Content preview: {section.content[:100]}...")
            print()

        # Check for expected sections
        if len(sections) > 0:
            print("✅ Parser produced sections without errors")
            return True
        else:
            print("❌ Parser produced no sections")
            return False

    except Exception as e:
        print(f"❌ Error parsing file: {e}")
        return False

if __name__ == "__main__":
    success = test_ng_parser()
    sys.exit(0 if success else 1)