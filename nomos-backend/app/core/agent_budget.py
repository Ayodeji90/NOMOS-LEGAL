"""
Agent loop budget enforcement.

Week 12 E1: Timeout and budget enforcement for agent loop.
- Max 3 rounds
- Max 12 excerpts to writer
- Max 2 writer calls (including repair)
- Max tokens per role

This system enforces budgets to prevent runaway agent loops and excessive resource usage.
"""
import logging

import structlog
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings

logger = structlog.get_logger(__name__)


@dataclass
class AgentBudget:
    """Budget limits for agent loop execution."""
    max_rounds: int = 3
    max_excerpts_to_writer: int = 12
    max_writer_calls: int = 2
    max_tokens_understanding: int = 1000
    max_tokens_writer: int = 4000
    max_tokens_verifier: int = 2000
    max_total_round_time_ms: float = 30000  # 30s total per agent loop


@dataclass
class AgentBudgetState:
    """Current state of budget consumption."""
    rounds_completed: int = 0
    excerpts_sent_to_writer: int = 0
    writer_calls_made: int = 0
    tokens_understanding: int = 0
    tokens_writer: int = 0
    tokens_verifier: int = 0
    round_time_ms: float = 0.0
    total_time_ms: float = 0.0


class AgentBudgetEnforcer:
    """Enforces budget limits during agent loop execution."""

    def __init__(self, budget: AgentBudget | None = None):
        self.budget = budget or AgentBudget()
        self.state = AgentBudgetState()
        self.logger = logger.bind(service="AgentBudgetEnforcer")

    def can_start_round(self) -> tuple[bool, str | None]:
        """Check if another round can be started."""
        if self.state.rounds_completed >= self.budget.max_rounds:
            return False, f"Max rounds ({self.budget.max_rounds}) exceeded"
        return True, None

    def can_send_excerpts(self, count: int) -> tuple[bool, str | None]:
        """Check if excerpts can be sent to writer."""
        total = self.state.excerpts_sent_to_writer + count
        if total > self.budget.max_excerpts_to_writer:
            return False, f"Max excerpts ({self.budget.max_excerpts_to_writer}) would be exceeded"
        return True, None

    def can_call_writer(self) -> tuple[bool, str | None]:
        """Check if writer can be called."""
        if self.state.writer_calls_made >= self.budget.max_writer_calls:
            return False, f"Max writer calls ({self.budget.max_writer_calls}) exceeded"
        return True, None

    def can_use_tokens_understanding(self, tokens: int) -> tuple[bool, str | None]:
        """Check if understanding tokens can be used."""
        total = self.state.tokens_understanding + tokens
        if total > self.budget.max_tokens_understanding:
            return False, f"Max understanding tokens ({self.budget.max_tokens_understanding}) would be exceeded"
        return True, None

    def can_use_tokens_writer(self, tokens: int) -> tuple[bool, str | None]:
        """Check if writer tokens can be used."""
        total = self.state.tokens_writer + tokens
        if total > self.budget.max_tokens_writer:
            return False, f"Max writer tokens ({self.budget.max_tokens_writer}) would be exceeded"
        return True, None

    def can_use_tokens_verifier(self, tokens: int) -> tuple[bool, str | None]:
        """Check if verifier tokens can be used."""
        total = self.state.tokens_verifier + tokens
        if total > self.budget.max_tokens_verifier:
            return False, f"Max verifier tokens ({self.budget.max_tokens_verifier}) would be exceeded"
        return True, None

    def record_round_start(self):
        """Record start of a new round."""
        self.state.rounds_completed += 1
        self.logger.info(
            "Agent round started",
            round=self.state.rounds_completed,
            max_rounds=self.budget.max_rounds,
        )

    def record_excerpts_sent(self, count: int):
        """Record excerpts sent to writer."""
        self.state.excerpts_sent_to_writer += count
        self.logger.debug(
            "Excerpts sent to writer",
            count=count,
            total=self.state.excerpts_sent_to_writer,
            max=self.budget.max_excerpts_to_writer,
        )

    def record_writer_call(self):
        """Record a writer call."""
        self.state.writer_calls_made += 1
        self.logger.info(
            "Writer call recorded",
            call=self.state.writer_calls_made,
            max=self.budget.max_writer_calls,
        )

    def record_tokens_understanding(self, tokens: int):
        """Record understanding tokens used."""
        self.state.tokens_understanding += tokens
        self.logger.debug(
            "Understanding tokens used",
            tokens=tokens,
            total=self.state.tokens_understanding,
            max=self.budget.max_tokens_understanding,
        )

    def record_tokens_writer(self, tokens: int):
        """Record writer tokens used."""
        self.state.tokens_writer += tokens
        self.logger.debug(
            "Writer tokens used",
            tokens=tokens,
            total=self.state.tokens_writer,
            max=self.budget.max_tokens_writer,
        )

    def record_tokens_verifier(self, tokens: int):
        """Record verifier tokens used."""
        self.state.tokens_verifier += tokens
        self.logger.debug(
            "Verifier tokens used",
            tokens=tokens,
            total=self.state.tokens_verifier,
            max=self.budget.max_tokens_verifier,
        )

    def record_round_time(self, time_ms: float):
        """Record time taken for a round."""
        self.state.round_time_ms = time_ms
        self.state.total_time_ms += time_ms
        self.logger.info(
            "Agent round completed",
            round=self.state.rounds_completed,
            time_ms=round(time_ms, 2),
            total_time_ms=round(self.state.total_time_ms, 2),
        )

    def get_budget_status(self) -> dict[str, Any]:
        """Get current budget consumption status."""
        return {
            "rounds": {
                "completed": self.state.rounds_completed,
                "max": self.budget.max_rounds,
                "remaining": self.budget.max_rounds - self.state.rounds_completed,
            },
            "excerpts": {
                "sent": self.state.excerpts_sent_to_writer,
                "max": self.budget.max_excerpts_to_writer,
                "remaining": self.budget.max_excerpts_to_writer - self.state.excerpts_sent_to_writer,
            },
            "writer_calls": {
                "made": self.state.writer_calls_made,
                "max": self.budget.max_writer_calls,
                "remaining": self.budget.max_writer_calls - self.state.writer_calls_made,
            },
            "tokens": {
                "understanding": {
                    "used": self.state.tokens_understanding,
                    "max": self.budget.max_tokens_understanding,
                },
                "writer": {
                    "used": self.state.tokens_writer,
                    "max": self.budget.max_tokens_writer,
                },
                "verifier": {
                    "used": self.state.tokens_verifier,
                    "max": self.budget.max_tokens_verifier,
                },
            },
            "timing": {
                "round_time_ms": round(self.state.round_time_ms, 2),
                "total_time_ms": round(self.state.total_time_ms, 2),
                "max_total_time_ms": self.budget.max_total_round_time_ms,
            },
        }

    def reset(self):
        """Reset budget state for new agent loop."""
        old_state = self.state
        self.state = AgentBudgetState()
        self.logger.info(
            "Agent budget reset",
            previous_rounds=old_state.rounds_completed,
            previous_time_ms=round(old_state.total_time_ms, 2),
        )


# Global instance
agent_budget_enforcer = AgentBudgetEnforcer()


def get_agent_budget_enforcer() -> AgentBudgetEnforcer:
    """Get the global agent budget enforcer instance."""
    return agent_budget_enforcer
