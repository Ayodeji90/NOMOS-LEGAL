#!/usr/bin/env python3
"""
South African legal corpus chunker.
Creates embedding-ready chunks from parsed legislation with parent context prepended.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.parsers.za_parser import Section


@dataclass
class LegalChunk:
    """Represents a chunk ready for embedding."""

    id: str
    content: str  # Text to be embedded (with parent context prepended)
    section_id: str
    act_name: str
    section_number: str
    heading: str
    chunk_index: int  # Index within the section if split
    total_chunks: int  # Total chunks for this section
    metadata: dict


class ZAChunker:
    """Chunker for South African legislation that creates embedding-ready chunks."""

    def __init__(self, max_chunk_size: int = 500):
        """
        Initialize the ZA chunker.

        Args:
            max_chunk_size: Maximum size of each chunk in characters
        """
        self.max_chunk_size = max_chunk_size

        # Import the parser (avoiding circular imports)
        from app.parsers.za_parser import ZAParser

        self.parser = ZAParser()

    def extract_act_info(self, text: str) -> tuple[str, str]:
        """
        Extract Act name and year from text.
        Returns (act_name, act_year) or defaults.
        """
        # Common patterns for South African acts
        act_patterns = [
            r"(basic conditions of employment act)\s*[\(]?\s*(\d{4})[\)]?",
            r"(companies act)\s*[\(]?\s*(\d{4})[\)]?",
            r"(labour relations act)\s*[\(]?\s*(\d{4})[\)]?",
            r"(protection of personal information act)\s*[\(]?\s*(\d{4})[\)]?",
            r"(constitution of the republic of south africa)\s*[\(]?\s*(\d{4})[\)]?",
        ]

        text_lower = text.lower()
        for pattern in act_patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                act_name = match.group(1).title()
                act_year = match.group(2)
                # Format act name properly
                if "basic conditions" in act_name.lower():
                    act_name = "Basic Conditions of Employment Act"
                elif "companies act" in act_name.lower():
                    act_name = "Companies Act"
                elif "labour relations" in act_name.lower():
                    act_name = "Labour Relations Act"
                elif "protection of personal information" in act_name.lower():
                    act_name = "Protection of Personal Information Act"
                elif "constitution" in act_name.lower():
                    act_name = "Constitution of the Republic of South Africa"
                return f"{act_name} {act_year}", act_year

        # Default fallback
        return "Unknown Act", "Unknown"

    def extract_section_number(self, section_title: str) -> str | None:
        """
        Extract section number from section title.
        Returns section number like '10', '37', etc. or None.
        """
        if not section_title:
            return None

        # Look for common section patterns
        section_matches = re.findall(r"section\s+(\d+[a-z]*)", section_title.lower())
        if section_matches:
            return section_matches[0]

        # Look for abbreviated forms
        sec_matches = re.findall(r"(?:s|sec)\.?\s*(\d+[a-z]*)", section_title.lower())
        if sec_matches:
            return sec_matches[0]

        return None

    def create_chunk_content(
        self,
        section: "Section",
        chunk_text: str,
        act_name: str,
        chunk_index: int = 0,
        total_chunks: int = 1,
        section_number: str | None = None,
    ) -> str:
        """
        Create chunk content with parent context prepended.

        Format: "[Act Name] [Section N ]Heading: [Chunk Text]"
        """
        context_parts = []
        if act_name:
            context_parts.append(act_name)

        # Prefer an explicitly provided number (gazette-derived); fall back
        # to extracting it from the title for legacy parsers.
        number = section_number or self.extract_section_number(section.title)
        if number:
            context_parts.append(f"Section {number}")

        # Append the heading exactly once: strip any section-number prefix
        # from the title first. (Previously the raw title was appended when
        # no number was found AND again via clean_title, producing
        # "Preamble Preamble:" double prefixes.)
        clean_title = ""
        if section.title:
            clean_title = re.sub(
                r"^(section\s+\d+[a-z]*\.?\s*)", "", section.title, flags=re.IGNORECASE
            )
            clean_title = re.sub(r"^(s\.?\s*\d+[a-z]*\.?\s*)", "", clean_title, flags=re.IGNORECASE)
            clean_title = clean_title.strip()
            if clean_title and len(clean_title) > 3:
                context_parts.append(clean_title)

        context = " ".join(context_parts)
        if context:
            return f"{context}: {chunk_text}"
        else:
            return chunk_text

    def chunk_section_text(self, text: str, max_size: int) -> list[str]:
        """
        Split section text into chunks of appropriate size.
        Tries to split on sentence boundaries when possible.
        """
        if len(text) <= max_size:
            return [text]

        chunks = []
        # Try to split on sentence boundaries first
        sentences = re.split(r"(?<=[.!?])\s+", text)

        current_chunk = ""
        for sentence in sentences:
            # If adding this sentence would exceed max size, save current chunk and start new one
            if len(current_chunk) + len(sentence) + 1 > max_size and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                if current_chunk:
                    current_chunk += " " + sentence
                else:
                    current_chunk = sentence

        # Don't forget the last chunk
        if current_chunk:
            chunks.append(current_chunk.strip())

        # If we still have chunks that are too large, force split them
        final_chunks = []
        for chunk in chunks:
            if len(chunk) <= max_size:
                final_chunks.append(chunk)
            else:
                # Force split on whitespace
                words = chunk.split()
                current_chunk = ""
                for word in words:
                    if len(current_chunk) + len(word) + 1 > max_size and current_chunk:
                        final_chunks.append(current_chunk.strip())
                        current_chunk = word
                    else:
                        if current_chunk:
                            current_chunk += " " + word
                        else:
                            current_chunk = word
                if current_chunk:
                    final_chunks.append(current_chunk.strip())

        return final_chunks if final_chunks else [text[:max_size]]

    def chunk_section(self, section: "Section", act_name: str) -> list[LegalChunk]:
        """
        Chunk a single section into embedding-ready pieces.

        Each chunk gets the parent context prepended: Act + Section + Heading
        """
        if not section.content or not section.content.strip():
            return []

        # Resolve the authoritative section number / schedule label from
        # gazette metadata when present (gazette headings are bare, so the
        # title carries no number).
        gaz_meta = getattr(section, "gazette_meta", None)
        is_schedule = bool(gaz_meta and gaz_meta.get("kind") == "schedule")
        if gaz_meta and gaz_meta.get("section_number") is not None and not is_schedule:
            resolved_number: str | None = str(gaz_meta["section_number"])
        elif is_schedule:
            resolved_number = None  # schedules use their label as the heading
        else:
            resolved_number = self.extract_section_number(section.title)

        # Split the section content into chunks
        text_chunks = self.chunk_section_text(section.content, self.max_chunk_size)

        # Create LegalChunk objects for each text chunk
        legal_chunks = []
        for i, chunk_text in enumerate(text_chunks):
            chunk_content = self.create_chunk_content(
                section,
                chunk_text,
                act_name,
                chunk_index=i,
                total_chunks=len(text_chunks),
                section_number=resolved_number,
            )

            chunk_id = f"{section.id}_chunk_{i}" if len(text_chunks) > 1 else section.id

            legal_chunk = LegalChunk(
                id=chunk_id,
                content=chunk_content,
                section_id=section.id,
                act_name=act_name,
                section_number=self.extract_section_number(section.title) or "unknown",
                heading=section.title or "",
                chunk_index=i,
                total_chunks=len(text_chunks),
                metadata={
                    "original_section_id": section.id,
                    "section_level": section.level,
                    "parent_id": section.parent_id,
                    "chunk_size": len(chunk_content),
                    "original_text_size": len(section.content),
                },
            )
            # Gazette-derived sections carry their true number in metadata;
            # use it so section_no is never a bare "unknown" in the DB.
            if gaz_meta:
                gn = gaz_meta.get("section_number")
                if gn is not None and not is_schedule:
                    legal_chunk.section_number = str(gn)
                if is_schedule:
                    legal_chunk.section_number = gaz_meta.get("label", "")
                    legal_chunk.heading = gaz_meta.get("label", legal_chunk.heading)
                    legal_chunk.metadata["is_schedule"] = True
            legal_chunks.append(legal_chunk)

        return legal_chunks

    def chunk_sections(
        self,
        sections: list["Section"],
        act_name: str | None = None,
    ) -> list[LegalChunk]:
        """
        Chunk a list of sections into embedding-ready pieces.

        Args:
            sections: Parsed sections to chunk.
            act_name: Optional canonical act name with year (e.g. "Basic
                Conditions of Employment Act 75 of 1997") used verbatim as the
                parent-context prefix. When omitted, it is derived from the
                section titles -- which only works for parsers whose titles
                carry the act name (not the gazette parser, whose headings are
                bare like "Definitions").
        """
        all_chunks = []

        if act_name is None:
            act_text = " ".join([s.title for s in sections if s.title])
            act_name, _ = self.extract_act_info(act_text)

        for section in sections:
            # Skip sections with no content
            if not section.content or not section.content.strip():
                continue

            section_chunks = self.chunk_section(section, act_name)
            all_chunks.extend(section_chunks)

        return all_chunks

    def chunk_file(self, file_path: Path) -> list[LegalChunk]:
        """
        Parse a file and chunk its contents.
        """
        sections = self.parser.parse_file(file_path)
        # Extract act info from the file content or path
        act_text = " ".join([s.title for s in sections if s.title]) or str(file_path)
        act_name, _ = self.extract_act_info(act_text)
        return self.chunk_sections(sections)

    def chunk_directory(self, directory_path: Path) -> list[LegalChunk]:
        """
        Parse all files in a directory and chunk their contents.
        """
        all_chunks = []

        if not directory_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory_path}")

        # Look for common legal text file extensions
        extensions = [".txt", ".xml", ".html", ".htm"]

        for ext in extensions:
            for file_path in directory_path.glob(f"*{ext}"):
                try:
                    chunks = self.chunk_file(file_path)
                    all_chunks.extend(chunks)
                except Exception as e:
                    print(f"Warning: Failed to chunk {file_path}: {e}")

        return all_chunks


def create_sample_chunks_for_testing():
    """Create sample chunks for testing the chunker."""
    import json
    import tempfile
    from pathlib import Path

    # Create temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create sample BCEA content (more complete than the earlier sample)
        bcea_content = """
BASIC CONDITIONS OF EMPLOYMENT ACT 75 OF 1997
[ASSENTED TO 2 DECEMBER 1997]
[DATE OF COMMENCEMENT: 1 DECEMBER 1998]

(English text signed by the President)
[ASSENTED TO 2 DECEMBER 1997]

CHAPTER 1
DEFINITIONS AND INTERPRETATION

SECTION 1
DEFINITIONS

In this Act, unless the context otherwise indicates-

"commission" means the Commission for Conciliation, Mediation and Arbitration established by section 112 of the Labour Relations Act, 1995 (Act 66 of 1995);

"employee" means, subject to the provisions of subsection (2), any person employed by an employer to work for remuneration;

"employer" means, subject to the provisions of subsection (2), any person who employs or provides work for any person and remunerates that person;

"employment" means a period during which an employee works for an employer;

"guarantee" in relation to severance pay, means a guarantee to pay an amount of money on a specified date to a specified person or body;

"industrial corporation" means a corporation or company, whether or not having a share capital, the activities of which are wholly or mainly of an industrial nature;

"leave" means any absence from work other than an absence for which provision is made elsewhere in this Act;

"minister" means the Minister of Labour;

"month" means a period calculated in terms of section 32;

"national economic, development and labour council" means the National Economic, Development and Labour Council, established by section 5 of the National Economic, Development and Labour Council Act, 1994 (Act 13 of 1994);

"night work" means work performed after 18h00 and before 06h00 the following day;

"ordinary hours of work", in relation to an employee, means the hours worked by an employee during the ordinary working hours;

"remuneration" means any payment in money or in kind, or both in money and in kind, made or owing to any person in return for work done by that person;

"sector" means any specific area of economic activity;

"sectoral determination" means a sectoral determination made by the Minister in terms of section 51;

"specified date" means the date on which an amount of money is guaranteed to be paid in terms of section 35(3);

"specified person" means the person to whom an amount of money is guaranteed to be paid in terms of section 35(3);

"week" means a period of seven days;

"year" means a period of twelve months;

SECTION 2
APPLICATION OF ACT

(1) This Act applies to all employers and workers but
SECTION 3
VARIATION OF SECTORS

The Minister may, by notice in the Gazette-
(a) establish a sector;
(b) vary or withdraw a sectoral determination;
(c) amend a sectoral determination.

SECTION 4
MINISTER MAY MAKE REGULATIONS

The Minister may make regulations-

SECTION 5
ACT BINDING ON ALL

This Act is binding on the state.

CHAPTER 2
REGULATION OF WORKING TIME

SECTION 6
ORDINARY HOURS OF WORK

(1) An employer may not require or permit an employee to work more than-
    (a) forty-five hours in any week; and
    (b) nine hours in any day if an employee works for five days or less in a week; or
    (c) eight hours in any day if an employee works for more than five days in a week.

(2) An employer may not require or permit an employee to work more than-
    (a) ten hours in any week; or
    (b) twelve hours in any day;
    unless the employee is paid overtime for those hours.

SECTION 7
OVERTIME

(1) An employer may not require or permit an employee to work overtime except-
    (a) in accordance with an agreement; and
    (b) within the limits prescribed in subsection (2).

(2) An employer may not require or permit an employee to work overtime exceeding-
    (a) ten hours in any week; or
    (b) twelve hours in any day.

(3) An agreement referred to in subsection (1) may-
    (a) be in writing or orally;
    (b) be for a specified period or indefinitely;
    (c) be for a specified amount of work or for work to be performed until a specified event occurs;
    (d) be reviewed periodically as agreed upon by the parties;
    (e) be terminated by giving notice in writing by either party to the other;
    (f) not be for work to be performed on a public holiday;
    (g) not be for more than the maximum limits prescribed in subsection (2).

SECTION 8
OVERTIME RATES

An employer shall pay an employee-
    (a) at least one and one-half times the employee's ordinary wage for work done on overtime; and
    (b) at least double the employee's ordinary wage for work done on a Sunday, unless such employee ordinarily works on a Sunday.

SECTION 9
MEAL INTERVALS

(1) An employer may not require or permit an employee to work for more than five hours continuously without an interval for a meal of at least one hour duration.
(2) An employer may not require or permit an employee to work for more than six hours continuously without an interval for a meal of at least one hour duration if such employee is employed in a workshop where work is carried on by means of furnaces, ovens or similar apparatus or if such employee is engaged in a foundry or blast furnace or similar work that requires the maintenance of a certain temperature in the metal being worked.

SECTION 10
OVERTIME WORKING TIME

(1) An employer may not require or permit an employee to work overtime except—
    (a) in accordance with an agreement; and
    (b) within the limits prescribed in subsection (2).

(2) An employer may not require or permit an employee to work overtime exceeding—
    (a) ten hours in any week; or
    (b) twelve hours in any day.
"""

        # Create sample Companies Act content
        companies_act_content = """
COMPANIES ACT 71 OF 2008
[ASSENTED TO 8 APRIL 2009]
[DATE OF COMMENCEMENT: 1 MAY 2011]

(English text signed by the President)

CHAPTER 1
INTERPRETATION, PURPOSE AND APPLICATION OF ACT

SECTION 1
DEFINITIONS

In this Act, unless the context otherwise indicates-

"affiliated", in relation to a person, means a person that is a subsidiary or holding company of, or a j oint venture with, that person;

"amendment", in relation to a profit company, a non-profit company or an external company, means-
(a) an alteration, or an addition to, any provision of the memorandum of incorporation of the company; or
(b) a restatement of the memorandum of incorporation of the company;

"ammunition" means any projectile or charged weapon, whether or not complete, designed to be discharged from a gun;

"annual return" means-
(a) in relation to a private company and a public company, a return in the prescribed form and containing the prescribed particulars, which a company is required to lodge with the Commission and the Tribunal within
SECTION 2
PURPOSE OF ACT

The purpose of this Act is to-
(a) promote compliance with the Bill of Rights as provided for in the Constitution in the administration of company law;
(b) promote and maintain high standards of ethical behaviour by directors, officers and other persons involved with a company;
(c) promote active supervision of the management of a company by its directors and officers;
(d) balance the rights and obligations of shareholders and directors within a company;
(e) encourage investment and facilitate the establishment, maintenance and existence of companies;
(f) provide for an efficient rescue and liquidation mechanism for financially distressed companies;
(g) promote the development of the economy through the promotion of trade, industry and other economic endeavours;
(h) provide for simple, affordable and accessible company formation and maintenance;
(i) provide an effective means of corporate governance;
(j) strengthen the responsibility and accountability of directors towards a company;
(k) reduce the costs associated with resolving disputes between shareholders and directors, or between shareholders or directors and other parties that are associated with a company;
(l) promote development of the business sector compatible therewith to facilitate investment and economic activity;
(m) ensure accountability and transparency in the affairs of companies;
(n) provide for the enforcement of judgments by, or against, a company;
(o) promote investment and facilitate the establishment, maintenance and existence of companies;
(p) provide for the protection of minority shareholders and other stakeholders;
(q) ensure compliance with international trends in company law;

SECTION 3
APPLICATION OF ACT

(1) This Act applies to-
    (a) every profit company that is incorporated in terms of this Act, whether or not it has share capital;
    (b) every profit company that is an external company in terms of this Act;
    (c) every non-profit company that is incorporated in terms of this Act;
    (d) every external company in terms of this Act that is a non-profit company;
    (e) every close corporation that is incorporated in terms of the Close Corporations Act, 1984 (Act 69 of 1984);
    (f) every company incorporated in terms of the previous Companies Act, 1973 (Act 61 of 1973) that has been converted to a company in terms of this Act;
    (g) every company that is a governmental enterprise as defined in the Public Finance Management Act, 1999 (Act 1 of 1999);
    (h) every company that is incorporated in terms of the Companies Act, 2006 (Act 13 of 2006) of the United Kingdom, as long as such company does not do business in the Republic of South Africa;
    (i) any other person, association or institution that in terms of any other Act is deemed to be a company;

SECTION 4
INTERPRETATION OF ACT

For the purposes of this Act, unless the context otherwise indicates-
    (a) words importing the masculine gender include the feminine gender;
    (b) words importing the feminine gender include the masculine gender;
    (c) words importing the singular number include the plural number;
    (d) words importing the plural number include the singular number;
    (e) words importing the present tense include the past tense and the future tense;
    (g) words importing the future tense include the present tense and the past tense;
    (h) the word "or" is used in the disjunctive sense;
    (i) the word "and" is used in the conjunctive sense;

SECTION 5
ACT BINDING ON STATE

This Act is binding on the state.

CHAPTER 2
INCORPORATION AND FINANCIAL LIABILITY

SECTION 6
INCORPORATION OF COMPANIES

(1) A person may incorporate a private company and a public company by delivering to the Commission-
    (a) a notice of incorporation in the prescribed form and containing the particulars as set forth in section 8(2);
    (b) the memorandum of incorporation of the company in the prepared form and containing the particulars as set forth in section 9(2);
    (c) the articles of the company in the prepared form and containing the particulars as set forth in section 10(2);
    (d) the prescribed fees as set forth in section 20(2);
    (e) a share certificate in the prepared form and containing the particulars as set forth in section 24(2);
    (f) a share transfer in the prepared form and containing the particulars as set forth in section 25(2);
    (g) a loan agreement in the prepared form and containing the particulars as set forth in section 26(2);
    (h) a lease agreement in the prepared form and containing the particulars as set forth in section 27(2);
    (i) a license agreement in the prepared form and containing the particulars as set forth in section 28(2);
    (j) a mortgage agreement in the prepared form and containing the particulars as set forth in section 29(2);
    (k) a security agreement in the prepared form and containing the particulars as set forth in section 30(2);
    (l) a floor space agreement in the prepared form and containing the particulars as set forth in section 31(2);
    (m) a reserved space agreement in the prepared form and containing the particulars as set forth in section 32(2);
    (n) a vacant space agreement in the prepared form and containing the particulars as set forth in section 33(2);
    (o) an occupancy agreement in the prepared form and containing the particulars as set forth in section 34(2);
    (p) an occupancy agreement in the prepared form and containing the particulars as set forth in section 35(2);
    (q) an occupancy agreement in the prepared form and containing the particulars as set forth in section 36(2);
    (r) an occupancy agreement in the prepared form and containing the particulars as set forth in section 37(2);
    (s) a shareholdings agreement in the prepared form and containing the particulars as set forth in section 38(2);
    (t) an allotment agreement in the prepared form and containing the particulars as set forth in section 39(2);
    (u) a consent agreement in the prepared form and containing the particulars as set forth in section 40(2);
    (v) an undertaking agreement in the prepared form and containing the particulars as set forth in section 41(2);
    (w) an indemnity agreement in the prepared form and containing the particulars as set forth in section 41(2);
    (x) a indemnity agreement in the prepared form and containing the particulars as set forth in section 42(2);
    (y) a restricted space agreement in the prepared form and containing the particulars as set forth in section 43(2);
    (z) a voting trust agreement in the prepared form and containing the particulars as set forth in section 44(2);

SECTION 7
ALTERNATIVE METHODS OF INCORPORATION

(1) A person may incorporate a private company and a public company by delivering to the Commission-
    (a) a notice of incorporation in the prepared form and containing the particulars as set forth in section 8(2);
    (b) the memorandum of incorporation of the company in the prepared form and containing the particulars as set forth in section 9(2);
    (c) the articles of the company in the prepared form and containing the particulars as set forth in section 10(2);
    (d) the prescribed fees as set forth in section 20(2);
    (e) a share certificate in the prepared form and containing the particulars as set forth in section 24(2);
    (f) a share transfer in the prepared form and containing the particulars as set forth in section 25(2);
    (g) a loan agreement in the prepared form and containing the particulars as set forth in section 26(2);
    (h) a lease agreement in the prepared form and containing the particulars as set forth in section 27(2);
    (i) a license agreement in the prepared form and containing the particulars as set forth in section 28(2);
    (j) a mortgage agreement in the prepared form and containing the particulars as set forth in section 29(2);
    (k) a security agreement in the prepared form and containing the particulars as set forth in section 30(2);
    (l) a floor space agreement in the prepared form and containing the particulars as set forth in section 31(2);
    (m) a reserved space agreement in the prepared form and containing the particulars as set forth in section 32(2);
    (n) a vacant space agreement in the prepared form and containing the particulars as set forth in section 33(2);
    (o) an occupancy agreement in the prepared form and containing the particulars as set forth in section 34(2);
    (p) an occupancy agreement in the prepared form and containing the particulars as set forth in section 35(2);
    (q) an occupancy agreement in the prepared form and containing the particulars as set forth in section 36(2);
    (r) an occupancy agreement in the prepared form and containing the particulars as set forth in section 37(2);
    (s) a shareholdings agreement in the prepared form and containing the particulars as set forth in section 38(2);
    (t) an allotment agreement in the prepared form and containing the particulars as set forth in section 39(2);
    (u) a consent agreement in the prepared form and containing the particulars as set forth in section 40(2);
    (v) an undertaking agreement in the prepared form and containing the particulars as set forth in section 41(2);
    (w) an indemnity agreement in the prepared form and containing the particulars as set forth in section 41(2);
    (x) a indemnity agreement in the prepared form and containing the particulars as set forth in section 42(2);
    (y) a restricted space agreement in the prepared form and containing the particulars as set forth in section 43(2);
    (z) a voting trust agreement in the prepared form and containing the particulars as set forth in section 44(2);

SECTION 7
ALTERNATIVE METHODS OF INCORPORATION

(1) A person may incorporate a private company and a public company by delivering to the Commission-
    (a) a notice of incorporation in the prepared form and containing the particulars as set forth in section 8(2);
    (b) the memorandum of incorporation of the company in the prepared form and containing the particulars as set forth in section 9(2);
    (c) the articles of the company in the prepared form and containing the particulars as set forth in section 10(2);
    (d) the prescribed fees as set forth in section 20(2);
    (e) a share certificate in the prepared form and containing the particulars as set forth in section 24(2);
    (f) a share transfer in the prepared form and containing the particulars as set forth in section 25(2);
    (g) a loan agreement in the prepared form and containing the particulars as set forth in section 26(2);
    (h) a lease agreement in the prepared form and containing the particulars as set forth in section 27(2);
    (i) a license agreement in the prepared form and containing the particulars as set forth in section 28(2);
    (j) a mortgage agreement in the prepared form and containing the particulars as set forth in section 29(2);
    (k) a security agreement in the prepared form and containing the particulars as set forth in section 30(2);
    (l) a floor space agreement in the prepared form and containing the particulars as set forth in section 31(2);
    (m) a reserved space agreement in the prepared form and containing the particulars as set forth in section 32(2);
    (n) a vacant space agreement in the prepared form and containing the particulars as set forth in section 33(2);
    (o) an occupancy agreement in the prepared form and containing the particulars as set forth in section 34(2);
    (p) an occupancy agreement in the prepared form and containing the particulars as set forth in section 35(2);
    (q) an occupancy agreement in the prepared form and containing the particulars as set forth in section 36(2);
    (r) an occupancy agreement in the prepared form and containing the particulars as set forth in section 37(2);
    (s) a shareholdings agreement in the prepared form and containing the particulars as set forth in section 38(2);
    (t) an allotment agreement in the prepared form and containing the particulars as set forth in section 39(2);
    (u) a consent agreement in the prepared form and containing the particulars as set forth in section 40(2);
    (v) an undertaking agreement in the prepared form and containing the particulars as set forth in section 41(2);
    (w) an indemnity agreement in the prepared form and containing the particulars as set forth in section 41(2);
    (x) a indemnity agreement in the prepared form and containing the particulars as set forth in section 42(2);
    (y) a restricted space agreement in the prepared form and containing the particulars as set forth in section 43(2);
    (z) a voting trust agreement in the prepared form and containing the particulars as set forth in section 44(2);

SECTION 75
DIRECTORS TO ACT IN GOOD FAITH

(1) Subject to subsection (2), a director of a company must-
    (a) act in good faith and in the best interests of the company;
    (b) act with the degree of care, skill and diligence that may reasonably be expected of a person carrying out the same activities or occupation in the community;
    (c) act honestly and in the proper use of his or her position; and
    (d) disclose to the other directors, the shareholders, the auditor and any committee of the board, whether standing or otherwise, all material information, whether financial or otherwise, that he or she has or obtains in relation to the company.

(2) A director of a company need not comply with subsection (1) if the director-
    (a) is exempted in terms of section 140(9);
    (b) is exempted in terms of section 142(8);
    (c) is exempted in terms of section 144(7);
    (d) is exempted in terms of section 146(6);
    (e) is exempted in terms of section 150(4);
    (g) is exempted in terms of section 152(3;
    (h) is exempted in terms of section 154(2);
    (i) is exempted in terms of section 156(1);

SECTION 76
STANDARDS OF DIRECTORS CONDUCT

(1) Subject to subsection (2), a director of a company must-
    (a) act honestly and in the proper use of his or her position;
    (b) avoid conflicts of interest;
    (c) not misuse company information;
    (d) not abuse his or her position;
    (e) maintain confidentiality of company information;
    (f) not engage in improper financial or sexual conduct;
    (g) exercise the degree of care, skill and diligence that may reasonably be expected of a person carrying out the same activities or occupation in the community;
    (h) comply with all applicable laws and regulations of the Republic of South Africa;
    (i) avoid any and all fronts, covers, shell companies and nominee arrangements;
    (j) attend board meetings and committee meetings of the board, whether standing or otherwise, as determined by the board;
    (j) not act as a nominee for, or nor to act in, or nor benefit from, any transaction where the other party does not have the necessary security clearance;
    (k) act honestly and in the proper use of his or her position;
    (l) exercise the degree of care, skill and diligence that may reasonably be expected of a person carrying out the same activities or occupation in the community;
    (m) avoid conflicts of interest;
    (n) not misuse company information;
    (o) not abuse his or her position;
    (p) maintain confidentiality of company information;
    (q) not engage in improper financial or sexual conduct;
    (r) exercise the degree of care, skill and diligence that may reasonably be expected of a person carrying out the same activities or occupation in the community;
    (s) comply with all applicable laws and regulations of the Republic of South Africa;
    (t) avoid any and all fronts, covers, shell companies and nominee arrangements;
    (u) attend board meetings and committee meetings of the board, whether standing or otherwise, as determined by the board;
    (v) not act as a nominee for, or nor to act in, or nor benefit from, any transaction where the other party does not have the necessary security clearance;

SECTION 77
LIABILITY OF DIRECTORS

(1) Subject to subsection (2), a director of a company is liable to the company for any loss, damager or expenses resulting from-
    (a) a breach of trust;
    (b) mismanagement;
    (c) negligence;
    (d) fraud;
    (e) dishonest or criminal conduct;
    (f) dishonist or dishonest conduct;
    (g) dishonist or criminal conduct;
    (h) abuse of power;
    (i) negligence;
    (j) misconduct;
    (k) abuse of power;
    (l) fraud;
    (m) abuse of power;
    (n) dishonist or criminal conduct;
    (o) negligence;
    (p) misconduct;
    (q) abuse of power;
    (r) fraud;
    (s) abuse of power;
    (t) negligence;
    (u) misconduct;

SECTION 188
UNFAIR DISMISSAL

(1) A dismissal is unfair if the employer fails to prove-
    (a) that the reason for the discharge is a fair reason; and
    (b) that the discharge was effected in accordance with a fair procedure.

(2) A dismissal is unfair if the reason for the discharge is-
    (a) incapacity of the employee;
    (b) the operational requirements of the employer;
    (c) the operational requirements of the employer;
    (d) a contravention of a statutory provision restating a general protection;
    (e) the operational requirements of the employer;
    (f) a contravention of a statutory provision restating a general protection;
    (g) a contravention of a statutory provision restating a general protection;
    (h) a contravention of a statutory provision restating a general protection;
    (i) a contravention of a statutory provision restating a general protection;
    (j) a contravention of a statutory provision restating a general protection;
    (k) a contravention of a statutory provision restating a general protection;
    (l) a contravention of a statutory provision restating a general protection;
"""

        # Save sample files
        bcea_file = temp_path / "bcea_full.txt"
        companies_act_file = temp_path / "companies_act_full.txt"

        with open(bcea_file, "w") as f:
            f.write(bcea_content)

        with open(companies_act_file, "w") as f:
            f.write(companies_act_content)

        # Create chunks
        chunker = ZAChunker(max_chunk_size=300)  # Smaller chunks for testing

        bcea_chunks = chunker.chunk_file(bcea_file)
        companies_act_chunks = chunker.chunk_file(companies_act_file)

        all_chunks = bcea_chunks + companies_act_chunks

        print(f"Created {len(bcea_chunks)} chunks from BCEA")
        print(f"Created {len(companies_act_chunks)} chunks from Companies Act")
        print(f"Total chunks: {len(all_chunks)}")

        # Save chunks for inspection
        chunks_data = []
        for chunk in all_chunks[:10]:  # Show first 10 chunks
            chunks_data.append(
                {
                    "id": chunk.id,
                    "act_name": chunk.act_name,
                    "section_number": chunk.section_number,
                    "heading": chunk.heading,
                    "chunk_index": chunk.chunk_index,
                    "total_chunks": chunk.total_chunks,
                    "content_preview": chunk.content[:200] + "..."
                    if len(chunk.content) > 200
                    else chunk.content,
                    "content_size": len(chunk.content),
                    "metadata": chunk.metadata,
                }
            )

        # Save to file for review
        output_file = temp_path / "sample_chunks.json"
        with open(output_file, "w") as f:
            json.dump(chunks_data, f, indent=2)

        print(f"Sample chunks saved to: {output_file}")

        # Show a few examples
        print("\n=== SAMPLE CHUNKS ===")
        for i, chunk_data in enumerate(chunks_data[:3]):
            print(f"\nChunk {i + 1}:")
            print(f"  ID: {chunk_data['id']}")
            print(f"  Act: {chunk_data['act_name']}")
            print(f"  Section: {chunk_data['section_number']}")
            print(f"  Heading: {chunk_data['heading']}")
            print(f"  Content Preview: {chunk_data['content_preview']}")
            print(f"  Size: {chunk_data['content_size']} characters")


if __name__ == "__main__":
    create_sample_chunks_for_testing()
