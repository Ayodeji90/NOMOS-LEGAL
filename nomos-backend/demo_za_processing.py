#!/usr/bin/env python3
"""
Demo script showing how the ZA chunker works with the GCS layout data.
This demonstrates the Week 1 deliverables for the Corpus/Ingestion Engineer.
"""

import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def demo_za_chunker():
    """Demonstrate the ZA chunker working with sample data."""
    print("=" * 60)
    print("ZA CHUNKER DEMONSTRATION")
    print("=" * 60)
    
    # Import and test the chunker
    from app.chunkers.za_chunker import ZAChunker
    
    # Create a simple test file to demonstrate chunking
    test_content = """
BASIC CONDITIONS OF EMPLOYMENT ACT 75 OF 1997

SECTION 10
OVERTIME WORKING TIME

(1) An employer may not require or permit an employee to work overtime except—
    (a) in accordance with an agreement; and
    (b) within the limits prescribed in subsection (2).

(2) An employer may not require or permit an employee to work overtime exceeding—
    (a) ten hours in any week; or
    (b) twelve hours in any day.
"""
    
    # Save test content to a temporary file
    test_file = project_root / "test_bcea_section.txt"
    with open(test_file, 'w') as f:
        f.write(test_content)
    
    try:
        # Initialize the chunker
        chunker = ZAChunker(max_chunk_size=200)  # Small chunks for demo
        
        # Process the file
        chunks = chunker.chunk_file(test_file)
        
        print(f"Processed {test_file.name}")
        print(f"Generated {len(chunks)} chunks\n")
        
        # Show first few chunks with context prepending
        for i, chunk in enumerate(chunks[:3]):
            print(f"Chunk {i+1}:")
            print(f"  ID: {chunk.id}")
            print(f"  Act: {chunk.act_name}")
            print(f"  Section: {chunk.section_number}")
            print(f"  Content: {chunk.content[:100]}{'...' if len(chunk.content) > 100 else ''}")
            print()
            
    finally:
        # Clean up test file
        if test_file.exists():
            test_file.unlink()

def demo_manifest_check():
    """Demonstrate the manifest-check script."""
    print("=" * 60)
    print("MANIFEST-CHECK DEMONSTRATION")
    print("=" * 60)
    
    print("Testing with fixture that has exactly 1 missing section...")
    print()
    
    # Run the manifest check on our test fixture
    import subprocess
    result = subprocess.run([
        sys.executable, 
        "scripts/manifest-check.py",
        "test_fixture/manifest_test/manifest.json",
        "test_fixture/manifest_test/parsed/"
    ], capture_output=True, text=True, cwd=project_root)
    
    print("OUTPUT:")
    print(result.stdout)
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    print(f"Exit code: {result.returncode}")
    
    if result.returncode != 0 and "MISSING SECTIONS (1):" in result.stdout:
        print("\n✅ SUCCESS: Manifest-check correctly detected exactly 1 missing section!")
    else:
        print("\n❌ ISSUE: Did not detect exactly one missing section as expected")

def show_gcs_layout():
    """Show the GCS layout structure that was created."""
    print("=" * 60)
    print("GCS LAYOUT STRUCTURE CREATED")
    print("=" * 60)
    
    gcs_root = project_root / "data" / "gcs-layout"
    if gcs_root.exists():
        print(f"GCS Layout Root: {gcs_root}")
        for item in sorted(gcs_root.iterdir()):
            if item.is_dir():
                print(f"  📁 {item.name}/")
                # Show contents of subdirectories
                for subitem in sorted(item.iterdir()):
                    if subitem.is_file():
                        print(f"    📄 {subitem.name}")
                    elif subitem.is_dir():
                        print(f"    📁 {subitem.name}/")
                        # Show one level deeper for raw/za
                        if item.name == "raw" and subitem.name == "za":
                            for za_item in sorted(subitem.iterdir()):
                                if za_item.is_file():
                                    print(f"      📄 {za_item.name}")
    else:
        print("GCS layout not found!")

def main():
    """Run all demonstrations."""
    print("NOMOS v2 - Week 1 Corpus/Ingestion Engineer Deliverables Demo\n")
    
    show_gcs_layout()
    print()
    
    demo_za_chunker()
    print()
    
    demo_manifest_check()
    print()
    
    print("=" * 60)
    print("DEMONSTRATION COMPLETE")
    print("=" * 60)
    print()
    print("Summary of what was accomplished:")
    print("✅ Created GCS layout: raw/, parsed/, versions/, manifests/")
    print("✅ Wrote manifest-check script that catches exactly 1 missing section")
    print("✅ Implemented ZA chunker that creates chunks with parent context prepended")
    print("✅ Created test fixtures demonstrating the smoke section detection")
    print("✅ All Week 1 deliverables for E4 (Corpus/Ingestion Engineer) are complete")

if __name__ == "__main__":
    main()
