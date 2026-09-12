#!/usr/bin/env python3
"""
Nigerian legal corpus parser.
Handles section extraction and heading tree construction for Nigerian legislation.
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


class NGParser:
    """Parser for Nigerian legislation."""

    def __init__(self):
        # Nigerian section patterns based on common acts
        self.section_patterns = {
            "labour_act": [
                r"section\s+1", r"s\s+1", r"sec\s+1",  # General provisions
                r"section\s+2", r"s\s+2", r"sec\s+2",  # Application
                r"section\s+3", r"s\s+3", r"sec\s+3",  # Administration
                r"section\s+4", r"s\s+4", r"sec\s+4",  # Protection of wages
                r"section\s+5", r"s\s+5", r"sec\s+5",  # Contracts
                r"section\s+6", r"s\s+6", r"sec\s+6",  # Working hours
                r"section\s+7", r"s\s+7", r"sec\s+7",  # Leave
                r"section\s+8", r"s\s+8", r"sec\s+8",  # Maternity protection
                r"section\s+9", r"s\s+9", r"sec\s+9",  # Termination
                r"section\s+10", r"s\s+10", r"sec\s+10",  # Notice
                r"section\s+11", r"s\s+11", r"sec\s+11",  # Severance
                r"section\s+12", r"s\s+12", r"sec\s+12",  # Redundancy
                r"section\s+13", r"s\s+13", r"sec\s+13",  # Insolvency
                r"section\s+14", r"s\s+14", r"sec\s+14",  # Records
                r"section\s+15", r"s\s+15", r"sec\s+15",  # Inspection
                r"section\s+16", r"s\s+16", r"sec\s+16",  # Offences
                r"section\s+17", r"s\s+17", r"sec\s+17",  # Regulations
                r"section\s+18", r"s\s+18", r"sec\s+18",  # Miscellaneous
            ],
            "camaa": [  # Companies and Allied Matters Act
                r"section\s+1", r"s\s+1", r"sec\s+1",  # General
                r"section\s+2", r"s\s+2", r"sec\s+2",  # Application
                r"section\s+3", r"s\s+3", r"sec\s+3",  # Formation
                r"section\s+4", r"s\s+4", r"sec\s+4",  # Share capital
                r"section\s+5", r"s\s+5", r"sec\s+5",  # Membership
                r"section\s+6", r"s\s+6", r"sec\s+6",  # Management
                r"section\s+7", r"s\s+7", r"sec\s+7",  # Meetings
                r"section\s+8", r"s\s+8", r"sec\s+8",  # Accounts
                r"section\s+9", r"s\s+9", r"sec\s+9",  # Audit
                r"section\s+10", r"s\s+10", r"sec\s+10",  # Dividends
                r"section\s+11", r"s\s+11", r"sec\s+11",  # Winding up
                r"section\s+12", r"s\s+12", r"sec\s+12",  # Insolvency
                r"section\s+13", r"s\s+13", r"sec\s+13",  # Receivership
                r"section\s+14", r"s\s+14", r"sec\s+14",  # Schemes
                r"section\s+15", r"s\s+15", r"sec\s+15",  # Takeovers
                r"section\s+16", r"s\s+16", r"sec\s+16",  # Regulations
                r"section\s+17", r"s\s+17", r"sec\s+17",  # Miscellaneous
            ],
            "employee_compensation": [
                r"section\s+1", r"s\s+1", r"sec\s+1",  # General
                r"section\s+2", r"s\s+2", r"sec\s+2",  # Application
                r"section\s+3", r"s\s+3", r"sec\s+3",  # Compensation
                r"section\s+4", r"s\s+4", r"sec\s+4",  # Benefits
                r"section\s+5", r"s\s+5", r"sec\s+5",  # Medical
                r"section\s+6", r"s\s+6", r"sec\s+6",  # Rehabilitation
                r"section\s+7", r"s\s+7", r"sec\s+7",  # Death benefits
                r"section\s+8", r"s\s+8", r"sec\s+8",  # Appeals
                r"section\s+9", r"s\s+9", r"sec\s+9",  # Offences
                r"section\s+10", r"s\s+10", r"sec\s+10",  # Regulations
            ]
        }

        # Compile regex patterns
        self.compiled_patterns = {}
        for category, patterns in self.section_patterns.items():
            self.compiled_patterns[category] = [
                re.compile(pattern, re.IGNORECASE) for pattern in patterns
            ]

    def detect_section_number(self, text: str) -> str | None:
        """
        Detect section number from text using Nigerian patterns.
        Returns section identifier like '1', '2', etc.
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