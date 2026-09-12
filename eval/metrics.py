"""NOMOS eval metrics — pure functions, stdlib only.

CI gates (blocking): jurisdiction leakage rate must be 0, refusal
correctness must be 100% (a should-refuse question that gets answered
is a hard fail). Recall/MRR/entailment are reported and tracked; bars
are set per jurisdiction from measured data, not vibes.
"""

import re

CITATION_RE = re.compile(r"\[(\d+)\]")

# Matches "s 145", "s. 145", "section 145", "sections 8 to 25",
# "section 76(2)(b)", "s 159(2)". Case-insensitive.
SECTION_REF_RE = re.compile(
    r"\b(?:ss?\.?|sections?)\s+(\d+[A-Za-z]?(?:\s*(?:\(\w+\)|to\s+\d+))?)",
    re.IGNORECASE,
)


def extract_citations(text):
    """Return sorted unique [n] citation numbers found in answer prose."""
    return sorted({int(n) for n in CITATION_RE.findall(str(text or ""))})


def citation_validity(answer_text, num_excerpts):
    """Every [n] must resolve to a retrieved excerpt (1-indexed).

    Returns {"valid": bool, "dangling": [n, ...]}.
    """
    cited = extract_citations(answer_text)
    dangling = [n for n in cited if n < 1 or n > num_excerpts]
    return {"valid": not dangling, "dangling": dangling}


def extract_section_refs(text):
    """Return section-number strings referenced in prose, e.g. ['76', '145(2)']."""
    return [m.group(1).strip() for m in SECTION_REF_RE.finditer(str(text or ""))]


def section_realism(answer_text, excerpts):
    """Every statutory ref in prose must exist in a cited excerpt's
    sectionNo/subsection metadata or text. Invented sections fail even
    when the Act name is real.

    excerpts: [{"sectionNo": "76", "subsection": "(2)", "text": "..."}]
    Returns {"ok": bool, "unverified": [ref, ...]}.
    """
    refs = extract_section_refs(answer_text)
    blobs = [
        " ".join(
            str(e.get(k) or "") for k in ("sectionNo", "subsection", "text")
        ).lower()
        for e in (excerpts or [])
    ]
    unverified = []
    for ref in refs:
        base = re.split(r"[\s(]", ref, 1)[0].lower().lstrip("0") or "0"
        hit = any(
            base
            and (
                f"s. {base}" in b
                or f"s {base}" in b
                or f"section {base}" in b
                or f" {base}(" in b
                or f" {base}." in b
                or f" {base} " in b
            )
            for b in blobs
        )
        if not hit:
            unverified.append(ref)
    return {"ok": not unverified, "unverified": unverified}


def recall_at_k(retrieved_ids, expected_ids, k=10):
    """Fraction of expected section ids present in top-k retrieved ids."""
    expected = list(dict.fromkeys(expected_ids or []))
    if not expected:
        return 1.0
    topk = set((retrieved_ids or [])[:k])
    return sum(1 for e in expected if e in topk) / len(expected)


def mrr(retrieved_ids, expected_ids):
    """Mean reciprocal rank of the first expected hit (single query)."""
    expected = set(expected_ids or [])
    for rank, rid in enumerate(retrieved_ids or [], start=1):
        if rid in expected:
            return 1.0 / rank
    return 0.0


def jurisdiction_leakage(results, expected_jurisdiction):
    """Wrong-jurisdiction excerpts must never enter an answer.

    results: [{"jurisdiction": "za", ...}]
    Returns {"rate": float, "leaked": [...]}. Any rate > 0 is a hard fail.
    """
    items = results or []
    leaked = [
        r
        for r in items
        if str(r.get("jurisdiction") or "").lower()
        != str(expected_jurisdiction).lower()
    ]
    rate = len(leaked) / len(items) if items else 0.0
    return {"rate": rate, "leaked": leaked}


def refusal_report(cases):
    """cases: [{"id": str, "must_refuse": bool, "refused": bool}]

    false_answers (should-refuse but answered) = hard fail.
    false_refusals (should-answer but refused) = tracked quality loss.
    """
    false_answers = [
        c["id"] for c in cases if c.get("must_refuse") and not c.get("refused")
    ]
    false_refusals = [
        c["id"] for c in cases if not c.get("must_refuse") and c.get("refused")
    ]
    total = len(cases)
    correct = total - len(false_answers) - len(false_refusals)
    return {
        "accuracy": correct / total if total else 1.0,
        "false_answers": false_answers,
        "false_refusals": false_refusals,
    }
