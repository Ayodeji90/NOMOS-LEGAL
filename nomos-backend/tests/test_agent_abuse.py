"""
Agent abuse caps tests.

Week 12 E6: Agent abuse caps (max expansions per request, max tokens per role).
These tests verify that the agent loop cannot be abused to consume excessive resources.
"""
import pytest
from app.core.agent_budget import AgentBudget, AgentBudgetEnforcer, AgentBudgetState


@pytest.mark.asyncio
async def test_max_rounds_enforcement():
    """Test that agent loop cannot exceed max rounds."""
    enforcer = AgentBudgetEnforcer()

    # Try to start more rounds than allowed
    for i in range(5):  # Max is 3
        can_start, reason = enforcer.can_start_round()
        if i < 3:
            assert can_start, f"Round {i+1} should be allowed"
        else:
            assert not can_start, f"Round {i+1} should be blocked"
            assert "Max rounds" in reason


@pytest.mark.asyncio
async def test_max_excerpts_enforcement():
    """Test that agent cannot send more excerpts than allowed."""
    enforcer = AgentBudgetEnforcer()

    # Try to send more excerpts than allowed
    max_excerpts = 12

    can_send, _ = enforcer.can_send_excerpts(max_excerpts)
    assert can_send, "Should be able to send max excerpts"

    can_send, reason = enforcer.can_send_excerpts(max_excerpts + 1)
    assert not can_send, "Should not be able to exceed max excerpts"
    assert "Max excerpts" in reason


@pytest.mark.asyncio
async def test_max_writer_calls_enforcement():
    """Test that agent cannot call writer more than allowed."""
    enforcer = AgentBudgetEnforcer()

    # Try to call writer more times than allowed
    max_calls = 2

    for i in range(max_calls):
        can_call, _ = enforcer.can_call_writer()
        assert can_call, f"Writer call {i+1} should be allowed"

    can_call, reason = enforcer.can_call_writer()
    assert not can_call, "Should not be able to exceed max writer calls"
    assert "Max writer calls" in reason


@pytest.mark.asyncio
async def test_max_tokens_understanding_enforcement():
    """Test that understanding tokens are capped."""
    enforcer = AgentBudgetEnforcer()

    max_tokens = 1000

    # Should be allowed within limit
    can_use, _ = enforcer.can_use_tokens_understanding(max_tokens)
    assert can_use

    # Should be blocked over limit
    can_use, reason = enforcer.can_use_tokens_understanding(max_tokens + 1)
    assert not can_use
    assert "Max understanding tokens" in reason


@pytest.mark.asyncio
async def test_max_tokens_writer_enforcement():
    """Test that writer tokens are capped."""
    enforcer = AgentBudgetEnforcer()

    max_tokens = 4000

    # Should be allowed within limit
    can_use, _ = enforcer.can_use_tokens_writer(max_tokens)
    assert can_use

    # Should be blocked over limit
    can_use, reason = enforcer.can_use_tokens_writer(max_tokens + 1)
    assert not can_use
    assert "Max writer tokens" in reason


@pytest.mark.asyncio
async def test_max_tokens_verifier_enforcement():
    """Test that verifier tokens are capped."""
    enforcer = AgentBudgetEnforcer()

    max_tokens = 2000

    # Should be allowed within limit
    can_use, _ = enforcer.can_use_tokens_verifier(max_tokens)
    assert can_use

    # Should be blocked over limit
    can_use, reason = enforcer.can_use_tokens_verifier(max_tokens + 1)
    assert not can_use
    assert "Max verifier tokens" in reason


@pytest.mark.asyncio
async def test_agent_budget_state_tracking():
    """Test that budget state is tracked correctly."""
    enforcer = AgentBudgetEnforcer()

    # Record some activity
    enforcer.record_round_start()
    enforcer.record_excerpts_sent(5)
    enforcer.record_writer_call()
    enforcer.record_tokens_understanding(500)
    enforcer.record_tokens_writer(2000)
    enforcer.record_tokens_verifier(1000)
    enforcer.record_round_time(1000)

    # Check state
    status = enforcer.get_budget_status()

    assert status["rounds"]["completed"] == 1
    assert status["rounds"]["remaining"] == 2
    assert status["excerpts"]["sent"] == 5
    assert status["excerpts"]["remaining"] == 7
    assert status["writer_calls"]["made"] == 1
    assert status["writer_calls"]["remaining"] == 1
    assert status["tokens"]["understanding"]["used"] == 500
    assert status["tokens"]["writer"]["used"] == 2000
    assert status["tokens"]["verifier"]["used"] == 1000


@pytest.mark.asyncio
async def test_agent_budget_reset():
    """Test that budget state can be reset."""
    enforcer = AgentBudgetEnforcer()

    # Record some activity
    enforcer.record_round_start()
    enforcer.record_excerpts_sent(10)
    enforcer.record_writer_call()

    # Reset
    enforcer.reset()

    # Check state is cleared
    status = enforcer.get_budget_status()

    assert status["rounds"]["completed"] == 0
    assert status["excerpts"]["sent"] == 0
    assert status["writer_calls"]["made"] == 0


@pytest.mark.asyncio
async def test_total_time_budget_enforcement():
    """Test that total time budget is enforced."""
    enforcer = AgentBudgetEnforcer()

    # Record a round that exceeds time budget
    enforcer.record_round_time(35000)  # 35 seconds, max is 30

    status = enforcer.get_budget_status()

    assert status["timing"]["round_time_ms"] == 35000
    assert status["timing"]["total_time_ms"] == 35000
    assert status["timing"]["max_total_time_ms"] == 30000


@pytest.mark.asyncio
async def test_concurrent_agent_loops_isolation():
    """Test that budget state is isolated between concurrent agent loops."""
    import asyncio

    enforcer1 = AgentBudgetEnforcer()
    enforcer2 = AgentBudgetEnforcer()

    async def run_agent_loop(enforcer, loop_id):
        enforcer.record_round_start()
        enforcer.record_excerpts_sent(5)
        enforcer.record_tokens_writer(1000)
        return enforcer.get_budget_status()

    # Run two agent loops concurrently
    status1, status2 = await asyncio.gather(
        run_agent_loop(enforcer1, 1),
        run_agent_loop(enforcer2, 2),
    )

    # Each should have its own state
    assert status1["rounds"]["completed"] == 1
    assert status2["rounds"]["completed"] == 1
    assert status1["excerpts"]["sent"] == 5
    assert status2["excerpts"]["sent"] == 5


@pytest.mark.asyncio
async def test_agent_budget_custom_limits():
    """Test that custom budget limits can be set."""
    custom_budget = AgentBudget(
        max_rounds=5,
        max_excerpts_to_writer=20,
        max_writer_calls=3,
        max_tokens_understanding=2000,
        max_tokens_writer=5000,
        max_tokens_verifier=3000,
    )

    enforcer = AgentBudgetEnforcer(budget=custom_budget)

    # Verify custom limits are enforced
    can_start, _ = enforcer.can_start_round()
    assert can_start

    # Should allow more than default
    can_send, _ = enforcer.can_send_excerpts(15)
    assert can_send

    # Should still enforce custom limit
    can_send, _ = enforcer.can_send_excerpts(21)
    assert not can_send


@pytest.mark.asyncio
async def test_agent_budget_exhaustion_recovery():
    """Test that system handles budget exhaustion gracefully."""
    enforcer = AgentBudgetEnforcer()

    # Exhaust all rounds
    for i in range(3):
        enforcer.record_round_start()

    # Should not be able to start another round
    can_start, _ = enforcer.can_start_round()
    assert not can_start

    # Reset and verify recovery
    enforcer.reset()

    can_start, _ = enforcer.can_start_round()
    assert can_start
