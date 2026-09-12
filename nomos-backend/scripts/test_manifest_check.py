#!/usr/bin/env python3
"""
Test script to demonstrate manifest-check catching exactly one missing section.
"""

import json
import tempfile
import os
import sys
import subprocess
from pathlib import Path

def create_test_scenario():
    """Create a test scenario with exactly one missing section."""
    
    # Create temporary directory for test
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Create manifest with 5 sections including one "smoke section"
        manifest = {
            "jurisdiction": "za",
            "version": "1.0",
            "last_updated": "2026-09-10",
            "sections": [
                {"id": "za_section_10", "title": "Overtime working time", "act": "BCEA"},
                {"id": "za_section_20", "title": "Annual leave", "act": "BCEA"},
                {"id": "za_section_37", "title": "Notice period", "act": "BCEA"},
                {"id": "za_section_101", "title": "SMOKE SECTION - Critical compliance check", "act": "BCEA"},  # This will be missing
                {"id": "za_section_41", "title": "Severance pay", "act": "LRA"}
            ]
        }
        
        # Save manifest
        manifest_file = temp_path / "manifest.json"
        with open(manifest_file, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        # Create parsed directory with 4 out of 5 sections (missing the smoke section)
        parsed_dir = temp_path / "parsed"
        parsed_dir.mkdir()
        
        # Create parsed sections data (missing za_section_101)
        sections_data = {
            "sections": [
                {
                    "id": "za_section_10",
                    "title": "Overtime working time",
                    "content": "(1) An employer may not require or permit an employee to work overtime except...",
                    "level": 2,
                    "parent_id": None
                },
                {
                    "id": "za_section_20",
                    "title": "Annual leave",
                    "content": "An employee is entitled to annual leave...",
                    "level": 2,
                    "parent_id": None
                },
                {
                    "id": "za_section_37",
                    "title": "Notice period",
                    "content": "Notice of termination of employment given by an employer must be...",
                    "level": 2,
                    "parent_id": None
                },
                {
                    "id": "za_section_41",
                    "title": "Severance pay",
                    "content": "An employer must pay severance pay...",
                    "level": 2,
                    "parent_id": None
                }
                # Note: za_section_101 (SMOKE SECTION) is intentionally missing
            ]
        }
        
        # Save parsed sections
        parsed_file = parsed_dir / "sections.json"
        with open(parsed_file, 'w') as f:
            json.dump(sections_data, f, indent=2)
        
        # Test manifest check
        print("Testing manifest-check with exactly one missing section...")
        print(f"Manifest file: {manifest_file}")
        print(f"Parsed directory: {parsed_dir}")
        print()
        
        # Run manifest check via subprocess
        result = subprocess.run([
            sys.executable, 
            "/home/machinemustlearn/WORKSPACE/NOMOS-LEGAL/nomos-backend/scripts/manifest-check.py",
            str(manifest_file),
            str(parsed_dir)
        ], capture_output=True, text=True)
        
        print("OUTPUT:")
        print(result.stdout)
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        print(f"Return code: {result.returncode}")
        
        # Check if exactly one missing section was detected
        if "MISSING SECTIONS (1):" in result.stdout and "za_section_101" in result.stdout:
            print("\n✅ SUCCESS: Manifest-check correctly caught exactly 1 missing smoke section!")
            return True
        else:
            print("\n❌ FAILURE: Did not detect exactly one missing section as expected")
            return False

if __name__ == "__main__":
    success = create_test_scenario()
    sys.exit(0 if success else 1)
