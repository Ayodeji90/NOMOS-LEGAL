"""Retrieval building blocks owned by the search/retrieval workstream.

Modules:
- rrf:       Reciprocal Rank Fusion for hybrid (sparse + dense) retrieval.
- synonyms:  Synonym/alias dictionary loader interface + file loader.
- za_focus:  ZA act-focus detection (ported from juris-backend za-focus.js).
- service:   Main retrieval service interface (hybrid search pipeline).
"""

from app.services.retrieval.rrf import fuse_ranked_lists, rrf_score
from app.services.retrieval.service import (
    RetrievalService,
    retrieval_service,
    retrieve_excerpts,
)
from app.services.retrieval.synonyms import (
    JsonFileSynonymDictLoader,
    SynonymDict,
    SynonymDictLoader,
    load_za_synonym_dict,
)
from app.services.retrieval.za_focus import (
    ActAlias,
    build_retrieve_query,
    detect_act_focus,
    detect_all_act_focuses,
    is_za_exclusive_mismatch,
    za_act_label,
)

__all__ = [
    "fuse_ranked_lists",
    "rrf_score",
    "SynonymDict",
    "SynonymDictLoader",
    "JsonFileSynonymDictLoader",
    "load_za_synonym_dict",
    "ActAlias",
    "detect_act_focus",
    "detect_all_act_focuses",
    "is_za_exclusive_mismatch",
    "build_retrieve_query",
    "za_act_label",
    "RetrievalService",
    "retrieval_service",
    "retrieve_excerpts",
]
