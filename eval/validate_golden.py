"""Validate golden QA files against golden_schema.json rules (stdlib only).

Usage: python -m eval.validate_golden eval/golden/za.json
Exit 0 when valid, 1 with errors listed otherwise.
"""

import json
import sys

REQUIRED = [
    "id",
    "jurisdiction",
    "corpus_id",
    "question",
    "must_refuse",
    "expected_acts",
    "expected_sections",
    "tags",
]
REFUSAL_REASONS = {
    "wrong-jurisdiction",
    "act-not-held",
    "case-law-gap",
    "no-on-point-statute",
}


def validate(items):
    errors = []
    if not isinstance(items, list) or not items:
        return ["golden file must be a non-empty JSON array"]
    seen = set()
    for i, it in enumerate(items):
        where = it.get("id", f"index {i}") if isinstance(it, dict) else f"index {i}"
        if not isinstance(it, dict):
            errors.append(f"{where}: item must be an object")
            continue
        for key in REQUIRED:
            if key not in it:
                errors.append(f"{where}: missing required key '{key}'")
        if it.get("id") in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(it.get("id"))
        if not isinstance(it.get("question", ""), str) or len(it["question"]) < 10:
            errors.append(f"{where}: question must be a string of >= 10 chars")
        if not isinstance(it.get("must_refuse"), bool):
            errors.append(f"{where}: must_refuse must be boolean")
        for key in ("expected_acts", "expected_sections", "tags"):
            if key in it and not isinstance(it[key], list):
                errors.append(f"{where}: '{key}' must be an array")
        if it.get("must_refuse"):
            reason = it.get("refusal_reason", "")
            if reason not in REFUSAL_REASONS:
                errors.append(
                    f"{where}: refusal_reason must be one of {sorted(REFUSAL_REASONS)}"
                )
            if it.get("expected_sections"):
                errors.append(
                    f"{where}: must-refuse items must have empty expected_sections"
                )
        else:
            if not it.get("expected_sections"):
                errors.append(f"{where}: answerable items need >= 1 expected section")
            if not it.get("expected_acts"):
                errors.append(f"{where}: answerable items need >= 1 expected act")
    return errors


def main(paths):
    failed = False
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            items = json.load(fh)
        errors = validate(items)
        if errors:
            failed = True
            print(f"{path}: {len(errors)} error(s)")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"{path}: OK ({len(items)} items)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
