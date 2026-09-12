#!/usr/bin/env python3
"""
Parser for South African Acts distributed as typeset Government Gazette text
(pdftotext -layout output of the official gazette PDFs).

Both source texts (BCEA 75/1997, Companies Act 71/2008) share the gazette
layout:

- section headings are flush-left lines ("Definitions", "Purposes of Act")
- section bodies start with an indented "N." marker ("  7. The purposes...")
- gazette column line-numbers trail many lines ("...corporate governance  50")
- pages are separated by a form-feed line followed by a right-aligned page no.
- structural headers ("CHAPTER 2", "Part B", "SCHEDULE 1") sit between chapters

Section detection is a *sequential* state machine: a heading only opens a new
section when the next numbered marker continues the running sequence. This
kills false positives from the table of contents, amendment lists in the
Schedules, and cross-references inside body text, which all contain numbered
"provisions" that do not continue the sequence.

Everything produced is a ``Section`` dataclass compatible with the existing
``ZAChunker`` (id, title=heading, content, level, parent_id), with the
parent chain recorded in ``metadata`` for spot-checks.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.parsers.za_parser import Section

DEBUG = bool(os.environ.get("GAZETTE_PARSER_DEBUG"))


def _dbg(msg: str) -> None:
    if DEBUG:
        print(f"[gazette] {msg}")


# ---------------------------------------------------------------------------
# Line classification patterns
# ---------------------------------------------------------------------------

# Body start: indented "N." (e.g. "  7. The purposes of this Act are to—").
# Gazette justification varies the indent between 1 and 4 spaces (observed
# " 8.", "  7.", and "    31."), so accept 1-4 and require a space after the
# dot. Subsection continuations use "(N)" markers, not "N.", so this does
# not collide with nested content.
RE_BODY_START = re.compile(r"^\s{1,4}(\d{1,3})\.\s+(\S.*)$")

# Heading flush-left line (no leading whitespace, no trailing column number)
RE_HEADING = re.compile(r"^[A-Z(‘'\"](?!\f).*$", re.IGNORECASE)

# Structural headers. Gazette layout CENTERS these lines, so they must be
# matched with optional leading whitespace, and body schedule headers can
# carry a trailing gazette column/page number ("SCHEDULE 2    30"), so an
# optional trailing number is tolerated. A structural line otherwise carries
# nothing (the chapter/part title sits on the following line). SCHEDULE and
# PART stay case-SENSITIVE so mid-sentence references ("Schedule 1; and",
# "Part B of ...") never match; CHAPTER is uppercase in practice.
RE_CHAPTER = re.compile(r"^\s*CHAPTER\s+([A-Z0-9]+)(?:\s+\d{1,3})?\s*$", re.IGNORECASE)
RE_PART = re.compile(r"^\s*Part\s+([A-Z0-9]+)(?:\s+\d{1,3})?\s*$")
RE_SCHEDULE = re.compile(r"^\s*SCHEDULE\s+([A-Z0-9]+)(?:\s+\d{1,3})?\s*$")
RE_ANNEX = re.compile(r"^\s*ANNEXURE\s+([A-Z0-9]+)(?:\s+\d{1,3})?\s*$", re.IGNORECASE)

# Trailing gazette column line-number: 1-3 digit number at end of a line.
# Applied ONLY to body lines, never to structural headers — e.g. the ToC
# line "SCHEDULE 1 ... 50" is a structural header plus a page ref; stripping
# the number would leave "SCHEDULE" unmatched and leak schedule items into
# the numbered body stream.
RE_TRAILING_LINENO = re.compile(r"\s+\d{1,3}\s*$")

# Page-break artifact: form feed, optionally followed by right-aligned page no
RE_PAGEBREAK = re.compile(r"^\f\s*\d*\s*$")

# Lines that look like headings but never are
RE_NOT_HEADING = re.compile(r"^(CHAPTER|PART|SCHEDULE|ANNEXURE|CHAPTER\s|\f)", re.IGNORECASE)


@dataclass
class GazetteSection:
    """Intermediate parse unit before conversion to parser.Section."""

    kind: str  # "preamble" | "section" | "schedule"
    number: int | None = None
    label: str = ""  # e.g. "Schedule 1" for schedules
    heading: str = ""
    body_lines: list[str] = field(default_factory=list)
    chapter: str = ""
    part: str = ""


def _is_heading_line(line: str) -> bool:
    """Heuristic: flush-left line that is neither structural nor numbered.

    Applied to the cleaned line (trailing column number already stripped by
    the caller for heading candidates).
    """
    if not line or line != line.lstrip():
        return False
    if line.startswith("\f"):
        return False
    if RE_CHAPTER.match(line) or RE_PART.match(line):
        return False
    if RE_SCHEDULE.match(line) or RE_ANNEX.match(line):
        return False
    if RE_BODY_START.match(line):
        return False
    return True


def _clean_body_line(line: str) -> str:
    """Strip gazette column line-numbers and normalise internal whitespace."""
    line = line.rstrip()
    line = RE_TRAILING_LINENO.sub("", line)
    return line.rstrip()


_WORD_NUMS = {
    "ONE": 1,
    "TWO": 2,
    "THREE": 3,
    "FOUR": 4,
    "FIVE": 5,
    "SIX": 6,
    "SEVEN": 7,
    "EIGHT": 8,
    "NINE": 9,
    "TEN": 10,
    "ELEVEN": 11,
    "TWELVE": 12,
    "THIRTEEN": 13,
    "FOURTEEN": 14,
}


def _norm_struct_no(token: str) -> str:
    """Normalise a structural number token ('ONE', '2', 'B') to a label part."""
    tok = token.strip().upper().rstrip(".")
    if tok in _WORD_NUMS:
        return str(_WORD_NUMS[tok])
    return token.strip().rstrip(".")


def _consume_structural_title(lines: list[str], i: int, n: int) -> int:
    """Return the index after an optional centered structural-title line.

    Gazette chapters/parts carry their title on the following centered line
    ("CHAPTER TWO" / "Regulation of working time"). The title line is
    indented and never a numbered body start, which distinguishes it from a
    body continuation.
    """
    t = i
    while t < n and not lines[t].strip():
        t += 1
    if t < n:
        cand = lines[t].rstrip()
        if cand and cand != cand.lstrip() and not RE_BODY_START.match(cand):
            return t + 1
    return i


# Preamble handling: the citation/long-title block is small, but the table
# of contents that follows it is redundant for retrieval (every entry exists
# as a real section) and pollutes chunk text. Once the first numbered ToC
# entry appears, all further pre-section material is dropped until the first
# numbered section opens.
RE_TOC_ENTRY = re.compile(r"^\s*\d{1,3}\.\s+")


def parse_gazette_text(text: str) -> list[GazetteSection]:
    """Parse gazette text into an ordered list of GazetteSection units."""
    units: list[GazetteSection] = []
    current: GazetteSection | None = None
    chapter = ""
    part = ""
    seen_schedule = False
    seen_sections = False
    next_expected = 1

    lines = text.split("\n")
    i = 0
    n = len(lines)
    preamble_open = True  # still collecting citation/long-title lines
    while i < n:
        raw = lines[i]
        raw_line = raw.rstrip()

        # --- page-break artifacts ------------------------------------------
        if RE_PAGEBREAK.match(raw_line):
            i += 1
            continue

        # --- structural headers (matched on the RAW line: the ToC form
        #     "    CHAPTER SIX        25" and the body form "CHAPTER SIX"
        #     both carry trailing page/line numbers that must NOT be
        #     stripped before matching) ----------------------------------
        m = RE_CHAPTER.match(raw_line)
        if m:
            if seen_sections:
                chapter = f"Chapter {m.group(1)}".strip()
                part = ""
                if current is not None:
                    current.chapter = chapter
            i = _consume_structural_title(lines, i + 1, n)
            continue
        m = RE_PART.match(raw_line)
        if m:
            if seen_sections:
                part = f"Part {m.group(1)}"
                if current is not None:
                    current.part = part
            i = _consume_structural_title(lines, i + 1, n)
            continue
        m = RE_SCHEDULE.match(raw_line)
        if m:
            # Only trust a schedule header once the numbered body has started;
            # the table of contents also contains "SCHEDULE N" lines.
            if seen_sections:
                seen_schedule = True
                current = GazetteSection(
                    kind="schedule",
                    label=f"Schedule {_norm_struct_no(m.group(1))}",
                    chapter=chapter,
                    part=part,
                )
                units.append(current)
            i = _consume_structural_title(lines, i + 1, n)
            continue
        m = RE_ANNEX.match(raw_line)
        if m:
            if seen_sections:
                seen_schedule = True
                current = GazetteSection(
                    kind="schedule",
                    label=f"Annexure {_norm_struct_no(m.group(1))}",
                    chapter=chapter,
                    part=part,
                )
                units.append(current)
            i = _consume_structural_title(lines, i + 1, n)
            continue

        # --- cleaned line for content decisions -----------------------------
        line = RE_TRAILING_LINENO.sub("", raw_line).rstrip()
        if line.startswith("\f"):
            line = line.lstrip("\f").strip()
        if not line:
            if current is not None:
                current.body_lines.append("")
            i += 1
            continue

        # --- body continuation for an open section --------------------------
        if current is not None and not _is_heading_line(line):
            current.body_lines.append(_clean_body_line(raw_line))
            i += 1
            continue

        # --- preamble ToC cut-off -------------------------------------------
        # Numbered ToC entries (flush-left or indented) mark the start of the
        # table of contents; everything after them until section 1 opens is
        # ToC material and is dropped.
        if not seen_sections and RE_TOC_ENTRY.match(line):
            preamble_open = False
            i += 1
            continue

        # --- heading line? only opens a section if the NEXT body marker
        #     continues the running sequence -------------------------------
        if _is_heading_line(line):
            # peek past blank lines for the numbered body start
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if j < n:
                mb = RE_BODY_START.match(lines[j].rstrip())
                _dbg(
                    f"L{i + 1} HEAD {line[:48]!r} "
                    f"peek={mb.group(1) if mb else None} next={next_expected}"
                )
                if mb:
                    no = int(mb.group(1))
                    if not seen_schedule and (
                        no == next_expected or (no == 1 and not seen_sections)
                    ):
                        current = GazetteSection(
                            kind="section",
                            number=no,
                            heading=line.strip(),
                            chapter=chapter,
                            part=part,
                        )
                        units.append(current)
                        seen_sections = True
                        next_expected = no + 1
                        current.body_lines.append(_clean_body_line(lines[j]))
                        i = j + 1
                        continue
            # heading not followed by an in-sequence marker:
            # it is either preamble/title-page text or noise.
            if current is not None:
                # swallow orphan headings into the open unit as body text
                current.body_lines.append(_clean_body_line(raw_line))
                i += 1
                continue
            # before any section: preamble material (skipped once the ToC
            # has started)
            if not preamble_open:
                i += 1
                continue
            if not units or units[-1].kind != "preamble":
                current = GazetteSection(kind="preamble", heading="")
                units.append(current)
            current.body_lines.append(_clean_body_line(raw_line))
            i += 1
            continue

        i += 1

    return units


def _mk_section_id(act_slug: str, unit: GazetteSection) -> str:
    if unit.kind == "section":
        return f"{act_slug}_section_{unit.number}"
    if unit.kind == "schedule":
        return f"{act_slug}_{unit.label.lower().replace(' ', '_')}"
    return f"{act_slug}_preamble"


def _mk_title(unit: GazetteSection) -> str:
    if unit.kind == "section":
        return unit.heading or f"Section {unit.number}"
    if unit.kind == "schedule":
        return unit.label
    return "Preamble"


def sections_from_units(
    act_slug: str,
    units: list[GazetteSection],
) -> list["Section"]:
    """Convert GazetteSection units into za_parser.Section objects."""
    # Imported here so this module mirrors za_parser's dataclass contract
    # without creating an import cycle at module load time.
    from app.parsers.za_parser import Section

    out: list[Section] = []
    for idx, unit in enumerate(units):
        content = "\n".join(line for line in unit.body_lines if line.strip()).strip()
        if not content and unit.kind == "preamble":
            continue
        parent_id = None
        parent_chain: list[str] = []
        if unit.chapter:
            parent_chain.append(unit.chapter)
        if unit.part:
            parent_chain.append(unit.part)
        if parent_chain:
            parent_id = f"{act_slug}_{parent_chain[0].lower().replace(' ', '_')}"
        meta = {
            "act_slug": act_slug,
            "kind": unit.kind,
            "section_number": unit.number,
            "label": unit.label,
            "chapter": unit.chapter,
            "part": unit.part,
            "parent_chain": parent_chain,
            "unit_index": idx,
        }
        out.append(
            Section(
                id=_mk_section_id(act_slug, unit),
                title=_mk_title(unit),
                content=content,
                level=1 if unit.kind == "preamble" else 2,
                parent_id=parent_id,
            )
        )
        # stash metadata (za_parser.Section is a plain dataclass; append attr)
        out[-1].gazette_meta = meta
    return out


def parse_file(act_slug: str, path: Path) -> list["Section"]:
    """Parse one gazette text file into Sections."""
    text = path.read_text(encoding="utf-8", errors="replace")
    units = parse_gazette_text(text)
    return sections_from_units(act_slug, units)


if __name__ == "__main__":
    import sys

    for p in sys.argv[1:]:
        secs = parse_file(Path(p).stem.replace("_full", ""), Path(p))
        numbered = [s for s in secs if s.id.endswith(tuple("0123456789"))]
        print(f"{p}: {len(secs)} units, {len(numbered)} numbered sections")
        for s in secs[:5]:
            print("  ", s.id, "|", s.title[:60])
