#!/usr/bin/env python3
"""
United Kingdom legal corpus parser.
Handles section extraction and heading tree construction for UK legislation.
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


class GBParser:
    """Parser for United Kingdom legislation."""

    def __init__(self):
        # UK-specific section patterns
        self.section_patterns = {
            # Employment Rights Act 1996 patterns
            "unfair_dismissal": [r"section\s+9[45]", r"s\s+9[45]", r"sec\s+9[45]"],
            "redundancy_payment": [r"section\s+13[56]", r"s\s+13[56]", r"sec\s+13[56]"],
            "notice_period": [r"section\s+86", r"s\s+86", r"sec\s+86"],
            # Equality Act 2010 patterns
            "discrimination": [r"section\s+1[23]", r"s\s+1[23]", r"sec\s+1[23]"],
            "harassment": [r"section\s+26", r"s\s+26", r"sec\s+26"],
            "victimisation": [r"section\s+27", r"s\s+27", r"sec\s+27"],
            # Health and Safety at Work etc. Act 1974 patterns
            "general_duties": [r"section\s+2", r"s\s+2", r"sec\s+2"],
            "risk_assessment": [r"section\s+3", r"s\s+3", r"sec\s+3"],
            # Companies Act 2006 patterns
            "director_duties": [r"section\s+17[12345]", r"s\s+17[12345]", r"sec\s+17[12345]"],
            "accounts": [r"section\s+3[89]", r"s\s+3[89]", r"sec\s+3[89]"],
            "audit": [r"section\s+4[12]", r"s\s+4[12]", r"sec\s+4[12]"],
        }

        # Compile regex patterns
        self.compiled_patterns = {}
        for category, patterns in self.section_patterns.items():
            self.compiled_patterns[category] = [
                re.compile(pattern, re.IGNORECASE) for pattern in patterns
            ]

    def detect_section_number(self, text: str) -> str | None:
        """
        Detect section number from text using UK patterns.
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

        # UK sometimes uses just numbers in margins
        margin_matches = re.findall(r"^\s*(\d+[a-z]*)\s*[-–—]\s*[A-Z]", text_lower, re.MULTILINE)
        if margin_matches:
            return margin_matches[0]

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

        # Schedule patterns (level 1 alternative for schedules)
        if re.match(r"^(schedule\s+\d+[a-z]*)\.?\s*[A-Z]", heading_text, re.IGNORECASE):
            return 1

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


def create_gb_sample_manifest() -> dict:
    """Create a sample manifest for UK testing."""
    return {
        "jurisdiction": "gb",
        "version": "1.0",
        "last_updated": "2026-09-10",
        "sections": [
            {
                "id": "gb_section_94",
                "title": "Right not to be unfairly dismissed",
                "act": "Employment Rights Act 1996",
            },
            {
                "id": "gb_section_95",
                "title": "Remedy for unfair dismissal",
                "act": "Employment Rights Act 1996",
            },
            {"id": "gb_section_86", "title": "Notice period", "act": "Employment Rights Act 1996"},
            {
                "id": "gb_section_135",
                "title": "Redundancy payment calculation",
                "act": "Employment Rights Act 1996",
            },
            {
                "id": "gb_section_136",
                "title": "Redundancy payment upper limit",
                "act": "Employment Rights Act 1996",
            },
            {"id": "gb_section_13", "title": "Discrimination", "act": "Equality Act 2010"},
            {"id": "gb_section_14", "title": "Harassment", "act": "Equality Act 2010"},
            {
                "id": "gb_section_26",
                "title": "Harassment related to protected characteristics",
                "act": "Equality Act 2010",
            },
            {"id": "gb_section_27", "title": "Victimisation", "act": "Equality Act 2010"},
            {
                "id": "gb_section_2",
                "title": "General duties of employers to employees",
                "act": "Health and Safety at Work etc. Act 1974",
            },
            {
                "id": "gb_section_3",
                "title": "General duties of employers and self-employed to persons other than employees",
                "act": "Health and Safety at Work etc. Act 1974",
            },
            {
                "id": "gb_section_171",
                "title": "General duties of directors",
                "act": "Companies Act 2006",
            },
            {
                "id": "gb_section_172",
                "title": "Duty to promote the success of the company",
                "act": "Companies Act 2006",
            },
            {
                "id": "gb_section_173",
                "title": "Duty to exercise independent judgment",
                "act": "Companies Act 2006",
            },
            {
                "id": "gb_section_174",
                "title": "Duty to exercise reasonable care, skill and diligence",
                "act": "Companies Act 2006",
            },
            {
                "id": "gb_section_175",
                "title": "Duty to avoid conflicts of interest",
                "act": "Companies Act 2006",
            },
            {
                "id": "gb_section_176",
                "title": "Duty not to accept benefits from third parties",
                "act": "Companies Act 2006",
            },
            {
                "id": "gb_section_177",
                "title": "Duty to declare interest in proposed transaction or arrangement",
                "act": "Companies Act 2006",
            },
        ],
    }


def main():
    """Example usage and testing."""
    import json
    import sys

    # Create sample data directory for testing
    sample_data_dir = Path(
        "/home/machinemustlearn/WORKSPACE/NOMOS-LEGAL/nomos-backend/data/sample_gb"
    )
    sample_data_dir.mkdir(parents=True, exist_ok=True)

    # Create a sample legal text file
    sample_content = """
PART 1
INTRODUCTION

CHAPTER 1
EMPLOYMENT RIGHTS

SECTION 94
RIGHT NOT TO BE UNFAIRLY DISMISSED

An employee has the right not to be subjected to unfair dismissal by his employer.

SECTION 95
REMEDY FOR UNFAIR DISMISSAL

(1) Where a tribunal finds that a person has been unfairly dismissed, the tribunal shall make such order as it considers just and equitable having regard to the loss sustained by the complainant in consequence of the dismissal insofar as that loss is attributable to the action taken by the employer.

(2) An order under subsection (1) may require the employer to—
    (a) pay the complainant compensation of such amount as the tribunal determines; or
    (b) reinstate the complainant in his former employment; or
    (c) re-engage the complainant in employment which is, so far as is practicable, similar to the former employment of the complainant.

SECTION 86
NOTICE PERIOD

(1) The minimum period of notice which may be given by an employer to terminate an employee's contract of employment is—
    (a) one week, if the employee has been continuously employed for one month or more but less than two years;
    (b) two weeks, if the employee has been continuously employed for two years or more but less than five years;
    (c) one week for each year of continuous employment, if the employee has been continuously employed for five years or more but less than twelve years;
    (d) twelve weeks, if the employee has been continuously employed for twelve years or more.

CHAPTER 2
HEALTH AND SAFETY

SECTION 2
GENERAL DUTIES OF EMPLOYERS TO EMPLOYEES

It shall be the duty of every employer to ensure, so far as is reasonably practicable, the health, safety and welfare at work of all his employees.
"""

    sample_file = sample_data_dir / "employment_rights_act_sample.txt"
    with open(sample_file, "w") as f:
        f.write(sample_content)

    # Parse the sample file
    parser = GBParser()
    sections = parser.parse_file(sample_file)

    # Build heading tree
    tree = parser.build_heading_tree(sections)

    # Create sample manifest
    manifest = create_gb_sample_manifest()

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
    success = main()
    import sys

    sys.exit(0 if success else 1)
