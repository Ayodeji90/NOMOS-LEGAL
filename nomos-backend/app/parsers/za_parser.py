#!/usr/bin/env python3
"""
South African legal corpus parser.
Handles section extraction and heading tree construction for ZA legislation.
"""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Section:
    """Represents a legal section."""

    id: str
    title: str
    content: str
    level: int  # Heading level (1 for chapter, 2 for section, etc.)
    parent_id: str | None = None


@dataclass
class HeadingTree:
    """Represents the hierarchical heading structure."""

    sections: list[Section]
    root_sections: list[Section]  # Top-level sections


class ZAParser:
    """Parser for South African legislation."""

    def __init__(self):
        # Common ZA section patterns from za-focus.js
        self.section_patterns = {
            "overtime": [r"section\s+10", r"s\s+10", r"sec\s+10"],
            "notice_period": [r"section\s+37", r"s\s+37", r"sec\s+37"],
            "annual_leave": [r"section\s+20", r"s\s+20", r"sec\s+20"],
            "sick_leave": [r"section\s+22", r"s\s+22", r"sec\s+22"],
            "family_responsibility_leave": [r"section\s+27", r"s\s+27", r"sec\s+27"],
            "maternity_leave": [r"section\s+25", r"s\s+25", r"sec\s+25"],
            "dismissal_procedure": [r"section\s+18[89]", r"s\s+18[89]", r"sec\s+18[89]"],
            "unfair_dismissal": [r"section\s+18[57]", r"s\s+18[57]", r"sec\s+18[57]"],
            "automatically_unfair": [r"section\s+187", r"s\s+187", r"sec\s+187"],
            "severance_pay": [r"section\s+41", r"s\s+41", r"sec\s+41"],
            "director_duties": [r"section\s+7[56]", r"s\s+7[56]", r"sec\s+7[56]"],
            "business_rescue": [r"section\s+129|131", r"s\s+129|131", r"sec\s+129|131"],
            "popia_processing": [r"section\s+1[12]", r"s\s+1[12]", r"sec\s+1[12]"],
            "popia_consent": [r"section\s+11", r"s\s+11", r"sec\s+11"],
            "popia_security": [r"section\s+19", r"s\s+19", r"sec\s+19"],
            "popia_breach": [r"section\s+22", r"s\s+22", r"sec\s+22"],
        }

        # Compile regex patterns
        self.compiled_patterns = {}
        for category, patterns in self.section_patterns.items():
            self.compiled_patterns[category] = [
                re.compile(pattern, re.IGNORECASE) for pattern in patterns
            ]

    def detect_section_number(self, text: str) -> str | None:
        """
        Detect section number from text using ZA patterns.
        Returns section identifier like '10', '37', etc.
        """
        text_lower = text.lower().strip()

        # Look for common section patterns
        section_matches = re.findall(r"section\s+(\d+[a-z]*)", text_lower)
        if section_matches:
            return section_matches[0]

        # Look for abbreviated forms
        sec_matches = re.findall(r"(?:s|sec)\.?\s*(\d+[a-z]*)", text_lower)
        if sec_matches:
            return sec_matches[0]

        return None

    def parse_heading_level(self, heading_text: str) -> int:
        """
        Determine heading level based on formatting.
        Returns integer level (1=highest/chapter, 2=section, etc.)
        """
        heading_text = heading_text.strip()

        # Chapter patterns (level 1)
        if re.match(r"^(chapter\s+[ivxlcdm]+|\d+)\.?\s*[A-Z]", heading_text, re.IGNORECASE):
            return 1

        # Part patterns (level 1 alternative)
        if re.match(r"^(part\s+[ivxlcdm]+|\d+)\.?\s*[A-Z]", heading_text, re.IGNORECASE):
            return 1

        # Section patterns (level 2)
        if re.match(r"^(section\s+\d+[a-z]*)\.?\s*[A-Z]", heading_text, re.IGNORECASE):
            return 2

        # Subsection patterns (level 3)
        if re.match(
            r"^(subsection\s+\(\d+\)|sub-section\s+\d+)\.?\s*[A-Z]", heading_text, re.IGNORECASE
        ):
            return 3

        # Paragraph patterns (level 4)
        if re.match(
            r"^(paragraph\s+\[[a-z]\]|para\s+\[[a-z]\])\.?\s*[A-Z]", heading_text, re.IGNORECASE
        ):
            return 4

        # Default to treating as content if no clear heading
        return 0

    def parse_file(self, file_path: Path) -> list[Section]:
        """
        Parse a single legal text file and extract sections.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        return self.parse_content(content, file_path.stem)

    def parse_content(self, content: str, source_id: str = "unknown") -> list[Section]:
        """
        Parse legal content and extract sections with heading hierarchy.
        """
        sections = []
        lines = content.split("\n")
        current_section = None
        current_content = []
        last_heading_level = 0

        for i, line in enumerate(lines):
            line = line.rstrip()
            if not line:
                if current_section:
                    current_content.append(line)
                continue

            # Check if this line is a heading
            heading_level = self.parse_heading_level(line)

            if heading_level > 0:
                # Save previous section if exists
                if current_section:
                    current_section.content = "\n".join(current_content).strip()
                    sections.append(current_section)

                # Start new section
                section_number = self.detect_section_number(line)
                section_id = (
                    f"{source_id}_section_{section_number}"
                    if section_number
                    else f"{source_id}_heading_{len(sections) + 1}"
                )

                current_section = Section(
                    id=section_id,
                    title=line.strip(),
                    content="",
                    level=heading_level,
                    parent_id=None,  # Will be set based on hierarchy
                )
                current_content = []
                last_heading_level = heading_level
            else:
                # Content line
                if current_section:
                    current_content.append(line)
                elif line.strip():  # Content without heading - treat as intro
                    # Create a preamble section
                    preamble_id = f"{source_id}_preamble"
                    preamble = Section(
                        id=preamble_id, title="Preamble", content=line.strip(), level=0
                    )
                    sections.append(preamble)

        # Don't forget the last section
        if current_section:
            current_section.content = "\n".join(current_content).strip()
            sections.append(current_section)

        # Establish parent-child relationships based on heading levels
        self._establish_hierarchy(sections)

        return sections

    def _establish_hierarchy(self, sections: list[Section]) -> None:
        """
        Establish parent-child relationships based on heading levels.
        """
        # Stack to keep track of potential parents by level
        level_stack = []  # Each element is (level, section_index)

        for i, section in enumerate(sections):
            # Pop from stack until we find a parent with lower level
            while level_stack and level_stack[-1][0] >= section.level:
                level_stack.pop()

            # If stack not empty, top element is the parent
            if level_stack:
                parent_index = level_stack[-1][1]
                section.parent_id = sections[parent_index].id

            # Push current section onto stack
            level_stack.append((section.level, i))

    def build_heading_tree(self, sections: list[Section]) -> HeadingTree:
        """
        Build a hierarchical tree from flat section list.
        """
        # Find root sections (those with no parent or level 0/1)
        root_sections = [s for s in sections if s.parent_id is None or s.level <= 1]

        return HeadingTree(sections=sections, root_sections=root_sections)

    def parse_directory(self, directory_path: Path) -> list[Section]:
        """
        Parse all legal text files in a directory.
        """
        all_sections = []

        if not directory_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory_path}")

        # Look for common legal text file extensions
        extensions = [".txt", ".xml", ".html", ".htm"]

        for ext in extensions:
            for file_path in directory_path.glob(f"*{ext}"):
                try:
                    sections = self.parse_file(file_path)
                    all_sections.extend(sections)
                except Exception as e:
                    print(f"Warning: Failed to parse {file_path}: {e}")

        return all_sections


def create_sample_manifest() -> dict:
    """Create a sample manifest for testing."""
    return {
        "jurisdiction": "za",
        "version": "1.0",
        "last_updated": "2026-09-10",
        "sections": [
            {"id": "za_section_10", "title": "Overtime working time", "act": "BCEA"},
            {"id": "za_section_37", "title": "Notice period", "act": "BCEA"},
            {"id": "za_section_20", "title": "Annual leave", "act": "BCEA"},
            {"id": "za_section_22", "title": "Sick leave", "act": "BCEA"},
            {"id": "za_section_27", "title": "Family responsibility leave", "act": "BCEA"},
            {"id": "za_section_25", "title": "Maternity leave", "act": "BCEA"},
            {"id": "za_section_188", "title": "Unfair dismissal procedures", "act": "LRA"},
            {"id": "za_section_185", "title": "Unfair dismissal definitions", "act": "LRA"},
            {"id": "za_section_187", "title": "Automatically unfair dismissal", "act": "LRA"},
            {"id": "za_section_41", "title": "Severance pay", "act": "LRA"},
            {
                "id": "za_section_76",
                "title": "Director duties - good faith",
                "act": "Companies Act",
            },
            {
                "id": "za_section_75",
                "title": "Director duties - care and skill",
                "act": "Companies Act",
            },
            {
                "id": "za_section_129",
                "title": "Business rescue proceedings",
                "act": "Companies Act",
            },
            {"id": "za_section_11", "title": "POPIA processing conditions", "act": "POPIA"},
            {"id": "za_section_19", "title": "POPIA security safeguards", "act": "POPIA"},
            {"id": "za_section_22_popia", "title": "POPIA breach notification", "act": "POPIA"},
        ],
    }


def main():
    """Example usage and testing."""
    import json

    # Create sample data directory for testing
    sample_data_dir = Path(
        "/home/machinemustlearn/WORKSPACE/NOMOS-LEGAL/nomos-backend/data/sample_za"
    )
    sample_data_dir.mkdir(parents=True, exist_ok=True)

    # Create a sample legal text file
    sample_content = """
CHAPTER 1
INTRODUCTION

This act establishes basic conditions of employment.

SECTION 10
OVERTIME WORKING TIME

(1) An employer may not require or permit an employee to work overtime except—
    (a) in accordance with an agreement; and
    (b) within the limits prescribed in subsection (2).

(2) An employer may not require or permit an employee to work overtime exceeding—
    (a) ten hours in any week; or
    (b) twelve hours in any day.

SECTION 37
NOTICE PERIOD

(1) Notice of termination of employment given by an employer must be—
    (a) at least one week, if the employee has been employed for six months or less;
    (b) at least two weeks, if the employee has been employed for more than six months but not more than one year;
    (c) at least four weeks, if the employee has been employed for more than one year.

SECTION 188
UNFAIR DISMISSAL PROCEDURES

(1) A dismissal is unfair if the employer fails to prove—
    (a) that the reason for the dismissal is a fair reason; and
    (b) that the dismissal was effected in accordance with a fair procedure.
"""

    sample_file = sample_data_dir / "bcea_sample.txt"
    with open(sample_file, "w") as f:
        f.write(sample_content)

    # Parse the sample file
    parser = ZAParser()
    sections = parser.parse_file(sample_file)

    # Build heading tree
    tree = parser.build_heading_tree(sections)

    # Create sample manifest
    manifest = create_sample_manifest()

    # Save manifest for testing
    manifest_file = sample_data_dir / "manifest.json"
    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2)

    # Create parsed directory and save parsed sections
    parsed_dir = sample_data_dir / "parsed"
    parsed_dir.mkdir(exist_ok=True)

    # Save sections as JSON for the manifest check
    sections_data = {
        "sections": [
            {
                "id": section.id,
                "title": section.title,
                "content": section.content[:200] + "..."
                if len(section.content) > 200
                else section.content,
                "level": section.level,
                "parent_id": section.parent_id,
            }
            for section in sections
        ]
    }

    parsed_file = parsed_dir / "sections.json"
    with open(parsed_file, "w") as f:
        json.dump(sections_data, f, indent=2)

    print(f"Parsed {len(sections)} sections from {sample_file}")
    print(f"Manifest saved to {manifest_file}")
    print(f"Parsed sections saved to {parsed_file}")

    # Test manifest check
    print("\n" + "=" * 50)
    print("Testing manifest check:")
    print("=" * 50)

    # Run manifest check
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            "/home/machinemustlearn/WORKSPACE/NOMOS-LEGAL/nomos-backend/scripts/manifest-check.py",
            str(manifest_file),
            str(parsed_dir),
        ],
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    return result.returncode == 0


if __name__ == "__main__":
    import sys

    success = main()
    sys.exit(0 if success else 1)
