#!/usr/bin/env python3
"""
Manifest check script for NOMOS corpus ingestion.
Validates that all expected sections are present in the corpus.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

def load_manifest(manifest_path: Path) -> Dict:
    """Load manifest JSON file."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    
    with open(manifest_path, 'r') as f:
        return json.load(f)

def extract_sections_from_parsed(parsed_dir: Path) -> Set[str]:
    """Extract all section identifiers from parsed files."""
    sections = set()
    
    if not parsed_dir.exists():
        return sections
    
    # Look for sections.json file first
    sections_file = parsed_dir / "sections.json"
    if sections_file.exists():
        try:
            with open(sections_file, 'r') as f:
                data = json.load(f)
                
            if isinstance(data, dict) and 'sections' in data:
                for section in data['sections']:
                    if isinstance(section, dict) and 'id' in section:
                        sections.add(section['id'])
            elif isinstance(data, list):
                for section in data:
                    if isinstance(section, dict) and 'id' in section:
                        sections.add(section['id'])
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not parse {sections_file}: {e}")
    
    # Also check individual parsed files
    for parsed_file in parsed_dir.glob("*.json"):
        if parsed_file.name == "sections.json":
            continue  # Already processed
            
        try:
            with open(parsed_file, 'r') as f:
                data = json.load(f)
                
            # Extract section information based on structure
            if isinstance(data, dict):
                # Handle different possible structures
                if 'sections' in data:
                    for section in data['sections']:
                        if isinstance(section, dict) and 'id' in section:
                            sections.add(section['id'])
                        elif isinstance(section, str):
                            sections.add(section)
                elif 'section_id' in data:
                    sections.add(data['section_id'])
                elif 'id' in data and 'section' in data['id'].lower():
                    sections.add(data['id'])
                    
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not parse {parsed_file}: {e}")
            continue
    
    return sections

def extract_manifest_sections(manifest: Dict) -> Set[str]:
    """Extract section identifiers from manifest."""
    sections = set()
    
    if 'sections' in manifest:
        for section in manifest['sections']:
            if isinstance(section, dict) and 'id' in section:
                sections.add(section['id'])
            elif isinstance(section, str):
                sections.add(section)
    
    return sections

def check_sections(manifest: Dict, parsed_sections: Set[str]) -> Tuple[List[str], List[str]]:
    """
    Check manifest against parsed sections.
    Returns (missing_sections, extra_sections)
    """
    manifest_sections = extract_manifest_sections(manifest)
    
    missing = sorted(list(manifest_sections - parsed_sections))
    extra = sorted(list(parsed_sections - manifest_sections))
    
    return missing, extra

def main():
    if len(sys.argv) != 3:
        print("Usage: python manifest-check.py <manifest_path> <parsed_dir>")
        sys.exit(1)
    
    manifest_path = Path(sys.argv[1])
    parsed_dir = Path(sys.argv[2])
    
    try:
        manifest = load_manifest(manifest_path)
        parsed_sections = extract_sections_from_parsed(parsed_dir)
        missing, extra = check_sections(manifest, parsed_sections)
        
        print(f"Manifest: {manifest_path}")
        print(f"Parsed directory: {parsed_dir}")
        manifest_sections = extract_manifest_sections(manifest)
        print(f"Manifest sections: {len(manifest_sections)}")
        print(f"Parsed sections: {len(parsed_sections)}")
        
        if missing:
            print(f"\nMISSING SECTIONS ({len(missing)}):")
            for section in missing:
                print(f"  - {section}")
        else:
            print("\n✅ No missing sections!")
            
        if extra:
            print(f"\nEXTRA SECTIONS ({len(extra)}):")
            for section in extra:
                print(f"  + {section}")
        else:
            print("\n✅ No extra sections!")
        
        # Exit with error code if there are missing sections (for CI gate)
        if missing:
            print(f"\n❌ Manifest check FAILED: {len(missing)} missing sections")
            sys.exit(1)
        else:
            print("\n✅ Manifest check PASSED")
            sys.exit(0)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
