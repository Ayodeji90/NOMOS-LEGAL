"""Synonym / alias dictionary loader interface and the ZA JSON v1 loader.

The dict powers query expansion and act-alias resolution for retrieval:

- ``synonyms``:        domain -> term -> alias list (colloquial -> statutory
                       language, e.g. "sacking" -> dismissal language).
- ``act_aliases``:     short key -> full act title (BCEA/LRA/POPIA/...).
- ``section_patterns``: topic -> statutory section citation variants.

Loaders implement :class:`SynonymDictLoader`; the concrete v1 implementation
reads the JSON dict at ``settings.ZA_SYNONYM_DICT_PATH`` (default
``app/data/za_synonyms.json``).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import settings


class SynonymDictError(ValueError):
    """Raised when a synonym dictionary is missing or malformed."""


@dataclass(frozen=True)
class SynonymDict:
    """Immutable view over a loaded synonym dictionary."""

    version: str
    jurisdiction: str
    description: str = ""
    #: domain -> term -> aliases (order preserved)
    synonyms: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    #: short alias -> full act title, e.g. "bcea" -> "Basic Conditions of ..."
    act_aliases: dict[str, str] = field(default_factory=dict)
    #: topic -> citation variants, e.g. "overtime" -> ["section 10", "s 10"]
    section_patterns: dict[str, list[str]] = field(default_factory=dict)
    source_path: str = ""

    # -- lookups ----------------------------------------------------------

    def aliases_for(self, domain: str, term: str) -> list[str]:
        """Aliases of ``term`` within one domain (empty if absent)."""
        return list(self.synonyms.get(domain, {}).get(_norm(term), []))

    def expand_term(self, term: str, domain: str | None = None) -> list[str]:
        """Union of aliases for ``term`` across domains (deduped, stable order).

        Case-insensitive on term keys. ``term`` itself is never included in
        the result; callers prepend the original term when expanding queries.
        """
        domains = [domain] if domain else list(self.synonyms)
        out: list[str] = []
        seen: set[str] = set()
        for d in domains:
            for alias in self.synonyms.get(d, {}).get(_norm(term), []):
                key = alias.lower()
                if key not in seen:
                    seen.add(key)
                    out.append(alias)
        return out

    def lookup_act(self, alias: str) -> str | None:
        """Full act title for a short alias key (case-insensitive)."""
        return self.act_aliases.get(_norm(alias))

    def sections_for(self, topic: str) -> list[str]:
        """Citation variants for a topic, e.g. sections_for("overtime")."""
        return list(self.section_patterns.get(_norm(topic), []))

    @property
    def term_count(self) -> int:
        return sum(len(terms) for terms in self.synonyms.values())


def _norm(s: str) -> str:
    return (s or "").strip().lower()


class SynonymDictLoader(ABC):
    """Interface for synonym dictionary loaders.

    Implementations must be pure loaders (no query-time behaviour) and
    idempotent: calling :meth:`load` twice yields equivalent dicts.
    """

    @abstractmethod
    def load(self) -> SynonymDict:
        """Load and return the dictionary. Raises SynonymDictError on failure."""


class JsonFileSynonymDictLoader(SynonymDictLoader):
    """Loads a synonym dict from a JSON file (dict format v1).

    Path resolution: absolute paths are used as-is; relative paths are
    resolved against the process CWD first, then against the app root
    (``nomos-backend/``) so the service works regardless of launch dir.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def resolve_path(self) -> Path:
        if self._path.is_absolute():
            return self._path
        if self._path.exists():
            return self._path
        app_root = Path(__file__).resolve().parents[2]  # app/services/retrieval -> backend root
        candidate = app_root / self._path
        return candidate if candidate.exists() else self._path

    def load(self) -> SynonymDict:
        path = self.resolve_path()
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SynonymDictError(f"synonym dict not readable: {path} ({exc})") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SynonymDictError(f"synonym dict is not valid JSON: {path} ({exc})") from exc
        return _dict_from_mapping(data, source_path=str(path))


def _require_mapping(obj: Any, where: str) -> dict:
    if not isinstance(obj, dict):
        raise SynonymDictError(f"synonym dict '{where}' must be an object")
    return obj


def _require_str_list(obj: Any, where: str) -> list[str]:
    if not isinstance(obj, list) or not all(isinstance(x, str) for x in obj):
        raise SynonymDictError(f"synonym dict '{where}' must be a list of strings")
    return list(obj)


def _dict_from_mapping(data: Any, source_path: str = "") -> SynonymDict:
    root = _require_mapping(data, "root")
    version = root.get("version")
    if not isinstance(version, str) or not version:
        raise SynonymDictError("synonym dict 'version' must be a non-empty string")
    jurisdiction = root.get("jurisdiction")
    if not isinstance(jurisdiction, str) or not jurisdiction:
        raise SynonymDictError("synonym dict 'jurisdiction' must be a non-empty string")

    synonyms_raw = _require_mapping(root.get("synonyms", {}), "synonyms")
    synonyms: dict[str, dict[str, list[str]]] = {}
    for domain, terms in synonyms_raw.items():
        terms_map = _require_mapping(terms, f"synonyms.{domain}")
        synonyms[_norm(domain)] = {
            _norm(term): _require_str_list(aliases, f"synonyms.{domain}.{term}")
            for term, aliases in terms_map.items()
        }

    act_raw = _require_mapping(root.get("act_aliases", {}), "act_aliases")
    act_aliases = {(_norm(k)): v for k, v in act_raw.items() if isinstance(v, str)}

    patterns_raw = _require_mapping(root.get("section_patterns", {}), "section_patterns")
    section_patterns = {
        _norm(topic): _require_str_list(patterns, f"section_patterns.{topic}")
        for topic, patterns in patterns_raw.items()
    }

    return SynonymDict(
        version=version,
        jurisdiction=jurisdiction,
        description=str(root.get("description", "")),
        synonyms=synonyms,
        act_aliases=act_aliases,
        section_patterns=section_patterns,
        source_path=source_path,
    )


@lru_cache(maxsize=8)
def _load_cached(resolved_path: str) -> SynonymDict:
    return JsonFileSynonymDictLoader(resolved_path).load()


# Week 5 E2: per-jurisdiction dict registry. NG joins ZA; new jurisdictions
# register their settings path here and load_synonym_dict() handles the rest.
_JURISDICTION_DICT_PATHS: dict[str, str] = {
    "za": settings.ZA_SYNONYM_DICT_PATH,
    "ng": settings.NG_SYNONYM_DICT_PATH,
}


def load_synonym_dict(jurisdiction: str, path: str | None = None) -> SynonymDict:
    """Load (and cache) the synonym dict for a jurisdiction id.

    Falls back to the ZA dict for unknown ids only when the caller explicitly
    passes ``path``; otherwise unknown ids raise SynonymDictError so a typo'd
    jurisdiction never silently expands with the wrong country's vocabulary.
    """
    p = path if path is not None else _JURISDICTION_DICT_PATHS.get(
        (jurisdiction or "").lower()
    )
    if p is None:
        raise SynonymDictError(
            f"no synonym dict registered for jurisdiction {jurisdiction!r}"
        )
    resolved = str(JsonFileSynonymDictLoader(p).resolve_path())
    return _load_cached(resolved)


def load_za_synonym_dict(path: str | None = None) -> SynonymDict:
    """Load (and cache) the ZA synonym dict v1 from settings or an explicit path."""
    return load_synonym_dict("za", path=path)


def clear_synonym_cache() -> None:
    """Reset the cached dict (useful in tests and after dict updates)."""
    _load_cached.cache_clear()
