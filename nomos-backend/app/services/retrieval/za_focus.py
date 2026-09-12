"""ZA act-focus detection (dict v1) — Python port of juris-backend-src/za-focus.js.

South African Act aliases for ZA retrieval boosting. ``za_exclusive`` aliases
may short-circuit a non-ZA ask (BCEA on the UK picker). Shared names such as
"Companies Act" are not exclusive; every common-law country has one.

Port notes (semantics preserved 1:1 from the JS source):
- Single-word keys match on word boundaries; multi-word keys are substrings.
- Longest matching key wins within an alias.
- Multi-alias disambiguation order: "under the X" phrasing -> exactly one
  short (<= 5 chars, no space) key -> earliest position in the query.
- Foreign-year suppression (e.g. Ireland's Consumer Protection Act 2007).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ActAlias:
    """One act's alias entry in the ZA dict v1."""

    keys: tuple[str, ...]
    title_needles: tuple[str, ...]
    label: str
    za_exclusive: bool = False
    focus: str = ""
    # compare=False/hash=False keeps frozen instances hashable despite the dict field
    topic_focus: dict[str, str] = field(default_factory=dict, compare=False, hash=False)
    foreign_years: tuple[str, ...] = ()
    shared_pickers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActFocusHit:
    """A detected alias plus the key that triggered it."""

    alias: ActAlias
    key: str


# --- ZA dict v1: act aliases (ported verbatim from za-focus.js) -------------

BCEA = ActAlias(
    keys=("bcea", "basic conditions of employment"),
    title_needles=("basic conditions of employment",),
    label="the BCEA (Basic Conditions of Employment Act)",
    za_exclusive=True,
    focus="BCEA overtime working time section 10",
    topic_focus={
        "overtime": "BCEA overtime working time section 10",
        "working time": "BCEA Chapter Two regulation of working time",
        "hours of work": "BCEA ordinary hours of work section 9",
    },
)

COMPANIES_ACT = ActAlias(
    # Do not use bare "section 76" / "fiduciary dut"; those steal POPIA and Constitution.
    keys=("companies act", "director duties", "71 of 2008"),
    title_needles=("companies act",),
    label="the South African Companies Act",
    za_exclusive=False,
    focus="Companies Act 71 of 2008 directors duties section 76 good faith",
    topic_focus={
        "fiduciary": "Companies Act 71 of 2008 section 76 standards of directors conduct fiduciary",
        "personally liable": "Companies Act 71 of 2008 section 77 liability of directors section 218",
        "liability": "Companies Act 71 of 2008 section 77 liability of directors prescribed officers",
    },
)

POPIA = ActAlias(
    keys=("popia", "protection of personal information"),
    title_needles=("protection of personal information",),
    label="POPIA (Protection of Personal Information Act)",
    za_exclusive=True,
    focus="Protection of Personal Information Act POPIA obligations",
    topic_focus={
        "processing": (
            "POPIA conditions for lawful processing of personal information sections 8 to 25"
        ),
        "personal information": (
            "POPIA conditions for lawful processing sections 8 9 10 11 12 13 14 15 16 "
            "17 18 19 20 21 22 23 24 25"
        ),
    },
)

LRA = ActAlias(
    keys=("labour relations act", "lra"),
    title_needles=("labour relations act",),
    label="the Labour Relations Act",
    za_exclusive=True,
    focus="Labour Relations Act unfair dismissal section 188",
    topic_focus={
        "dismissal": (
            "Labour Relations Act unfair dismissal section 188 substantively fair procedurally fair"
        ),
        "unfair dismissal": "Labour Relations Act 66 of 1995 section 188 unfair dismissal",
    },
)

UNFAIR_DISMISSAL = ActAlias(
    keys=("unfair dismissal",),
    title_needles=("labour relations act",),
    label="the Labour Relations Act",
    za_exclusive=False,
    focus="Labour Relations Act unfair dismissal",
)

CPA = ActAlias(
    keys=("consumer protection act", "cpa"),
    title_needles=("consumer protection act",),
    label="the Consumer Protection Act",
    za_exclusive=True,
    # Ireland's Consumer Protection Act 2007 shares the name.
    foreign_years=("2007",),
    shared_pickers=("ie",),
    focus="Consumer Protection Act return of goods",
)

CONSTITUTION = ActAlias(
    # Not exclusive: Ireland/Germany/etc. have constitutions. Only used to rank ZA hits.
    keys=("constitution of the republic", "section 9 of the constitution", "the constitution"),
    title_needles=("constitution of the republic of south africa",),
    label="the Constitution of the Republic of South Africa, 1996",
    za_exclusive=False,
    focus="Constitution of the Republic of South Africa 1996 section 9 equality",
    topic_focus={
        "equality": (
            "Constitution of the Republic of South Africa 1996 section 9 equality "
            "unfair discrimination"
        ),
    },
)

#: Order matters: it is the fallback tiebreak order in detect_act_focus.
ACT_ALIASES: tuple[ActAlias, ...] = (
    BCEA,
    COMPANIES_ACT,
    POPIA,
    LRA,
    UNFAIR_DISMISSAL,
    CPA,
    CONSTITUTION,
)

_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_WORD_BOUNDARY_CACHE: dict[str, re.Pattern[str]] = {}


def query_years(query: str) -> list[str]:
    """Return all (19|20)xx years mentioned in the query, in order."""
    # findall with a single capture group returns the group strings directly.
    return _YEAR_RE.findall(query or "")


def has_foreign_year(query: str, alias: ActAlias | None) -> bool:
    """True if the query mentions a year that belongs to a foreign namesake."""
    if not alias or not alias.foreign_years:
        return False
    years = query_years(query)
    return any(y in alias.foreign_years for y in years)


def key_in_query(hay: str, key: str) -> bool:
    """Word-boundary match for single words; substring for multi-word keys.

    Mirrors keyInQuery() in za-focus.js: ``hay`` is expected lowercased.
    """
    needle = (key or "").lower()
    if not needle:
        return False
    if " " in needle:
        return needle in hay
    pattern = _WORD_BOUNDARY_CACHE.get(needle)
    if pattern is None:
        pattern = re.compile(rf"(?:^|[^a-z0-9]){re.escape(needle)}(?:$|[^a-z0-9])", re.IGNORECASE)
        _WORD_BOUNDARY_CACHE[needle] = pattern
    return pattern.search(hay) is not None


def detect_all_act_focuses(query: str) -> list[ActFocusHit]:
    """All act aliases whose keys appear in the query (longest key per alias)."""
    lower = (query or "").lower()
    hits: list[ActFocusHit] = []
    for alias in ACT_ALIASES:
        if has_foreign_year(query, alias):
            continue
        matched_key = ""
        for key in alias.keys:
            if key and key_in_query(lower, key) and len(key) > len(matched_key):
                matched_key = key
        if matched_key:
            hits.append(ActFocusHit(alias=alias, key=matched_key))
    return hits


def detect_act_focus(query: str) -> ActAlias | None:
    """Pick the single act focus for a query, or None."""
    hits = detect_all_act_focuses(query)
    if not hits:
        return None
    if len(hits) == 1:
        return hits[0].alias
    lower = (query or "").lower()
    under = next(
        (
            h
            for h in hits
            if (f"under the {h.key}" in lower or f"under {h.key}" in lower)
            or (h.alias.title_needles and f"under the {h.alias.title_needles[0]}" in lower)
        ),
        None,
    )
    if under:
        return under.alias
    shorts = [h for h in hits if len(h.key) <= 5 and " " not in h.key]
    if len(shorts) == 1:
        return shorts[0].alias
    first = hits[0]
    first_pos = lower.find(first.key)
    for h in hits[1:]:
        pos = lower.find(h.key)
        if pos >= 0 and (first_pos < 0 or pos < first_pos):
            first_pos = pos
            first = h
    return first.alias


def build_retrieve_query(
    query: str,
    history: Sequence[dict] | None = None,
    max_chars: int = 2500,
) -> str:
    """Carry the last act-focused user turn into the retrieve query.

    If the query itself has an act focus, it is used as-is (capped). Else the
    most recent prior user message with an act focus is appended so sparse +
    dense retrieval see the act name.
    """
    q = (query or "").strip()
    if not q:
        return q
    if detect_act_focus(q):
        return q[:max_chars]
    prior_users = [
        (str((m or {}).get("content") or "")).strip()
        for m in (history or [])
        if (m or {}).get("role") == "user"
    ]
    prior_users = [c for c in prior_users if c and c != q]
    for content in reversed(prior_users):
        if detect_act_focus(content):
            return f"{q}. {content}"[:max_chars]
    return q[:max_chars]


def za_act_label(focus: ActAlias | None) -> str | None:
    """Human label for a detected focus, e.g. 'the Labour Relations Act'."""
    if not focus:
        return None
    return focus.label or f"the {focus.title_needles[0]}"


def is_za_exclusive_mismatch(query: str, jurisdiction_id: str | None) -> bool:
    """True when a za-exclusive act is asked about on another jurisdiction."""
    if not jurisdiction_id or jurisdiction_id == "za":
        return False
    focus = detect_act_focus(query)
    if not focus or not focus.za_exclusive:
        return False
    if jurisdiction_id in focus.shared_pickers:
        return False
    if has_foreign_year(query, focus):
        return False
    return True
