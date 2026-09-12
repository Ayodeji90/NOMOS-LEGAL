"""AI services for NOMOS v2.

Modules:
- embedding_service: Text embedding generation (Vertex AI text-embedding-005)
- query_understanding: Query analysis and expansion (Gemini Flash)
- writer_service: Grounded answer generation (Gemini Pro)
- verifier_service: Grounding verification (citation realism, section realism, NLI)
- repair_service: Bounded repair loop on verification failure
- gates: Jurisdiction and named-Act gates for honest jurisdiction enforcement
- thresholds: Jurisdiction-specific thresholds for verification and coverage
- nli_service: Natural Language Inference for claim verification (Week 10)
- structural_rules: Structural override rules for controlling provision (Week 10)
"""

from app.services.ai.embedding_service import (
    EmbeddingService,
    embedding_service,
    get_embedding_provider,
)
from app.services.ai.gates import (
    GateResult,
    GateService,
    JurisdictionGate,
    NamedActGate,
    gate_service,
)
from app.services.ai.nli_service import (
    NLIResult,
    NLIService,
    nli_service,
)
from app.services.ai.query_understanding import (
    query_understanding_service,
    understand_query,
    understand_query_log_only,
)
from app.services.ai.repair_service import (
    RepairService,
    repair_service,
)
from app.services.ai.structural_rules import (
    StructuralOverrideRules,
    structural_rules,
)
from app.services.ai.thresholds import (
    JurisdictionThresholds,
    thresholds,
)
from app.services.ai.verifier_service import (
    VerifierService,
    verifier_service,
)
from app.services.ai.writer_service import (
    WriterService,
    writer_service,
)

__all__ = [
    "EmbeddingService",
    "embedding_service",
    "get_embedding_provider",
    "understand_query",
    "understand_query_log_only",
    "query_understanding_service",
    "WriterService",
    "writer_service",
    "VerifierService",
    "verifier_service",
    "RepairService",
    "repair_service",
    "GateService",
    "gate_service",
    "JurisdictionGate",
    "NamedActGate",
    "GateResult",
    "JurisdictionThresholds",
    "thresholds",
    "NLIService",
    "nli_service",
    "NLIResult",
    "StructuralOverrideRules",
    "structural_rules",
]
