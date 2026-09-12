"""Per-jurisdiction v2 rollout flags (E1).

RETRIEVAL_V2_JURISDICTIONS is a comma-separated allowlist, e.g. "za".
Only listed ids use the hybrid retrieval path; unlisted jurisdictions
stay on the legacy lexical path. Rollback is removing an id — no code
deploy needed. Prototype scope is ZA-only (Nigeria next).
"""

from app.core.config import get_settings


def parse_v2_jurisdictions(raw: str) -> set:
    return {p.strip().lower() for p in str(raw or "").split(",") if p.strip()}


def uses_v2(jurisdiction_id: str, raw: str | None = None) -> bool:
    if raw is None:
        raw = get_settings().RETRIEVAL_V2_JURISDICTIONS
    return str(jurisdiction_id or "").strip().lower() in parse_v2_jurisdictions(raw)
