"""
qa/unit/test_budget_harness.py
Budget harness integration tests — emergency mode, escalation, and isolation.
These tests verify the end-to-end budget enforcement behaviour of CostTracker.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from decimal import Decimal

import pytest

from agents.cascadeflow.cost_tracker import (
    EMERGENCY_MAX_TOKENS,
    EMERGENCY_MODEL,
    CostTracker,
)


# ---------------------------------------------------------------------------
# Test 1
# ---------------------------------------------------------------------------


def test_full_scenario_under_budget():
    """
    Run a simulated 4-call arbitration and prove total < ₹5.00.

    Simulates a realistic MEDIUM-complexity dispute:
      call 1 — EVIDENCE_PARSING  : 8b  (6000p,  3000c) → ₹0.045
      call 2 — NEGOTIATION       : mix (10000p, 9000c) → ₹0.431
      call 3 — COUNTER_OFFER     : mix (8000p,  6000c) → ₹0.295
      call 4 — FINAL_DECISION    : 70b (20000p, 8000c) → ₹1.487
      ─────────────────────────────────────────────────────────
      Total                                            → ₹2.258

    All assertions use Decimal — no float comparisons.
    """
    tracker = CostTracker(budget_inr=Decimal("5.00"))

    tracker.record_call("llama-3.1-8b-instant",    6000,  3000)
    tracker.record_call("mixtral-8x7b-32768",      10000, 9000)
    tracker.record_call("mixtral-8x7b-32768",      8000,  6000)
    tracker.record_call("llama-3.1-70b-versatile", 20000, 8000)

    assert tracker.total_cost_inr < Decimal("5.00"), (
        f"Total ₹{tracker.total_cost_inr} must be under the ₹5.00 budget"
    )
    assert tracker.remaining_inr() > Decimal("0.00"), (
        "Remaining budget must be positive after a normal arbitration"
    )
    assert tracker.escalated_to_human is False, (
        "A normal under-budget run must not escalate to human"
    )
    assert len(tracker.calls) == 4


# ---------------------------------------------------------------------------
# Test 2
# ---------------------------------------------------------------------------


def test_emergency_mode_produces_shorter_response():
    """
    When emergency_mode=True, max_tokens must be 200, not 2048.

    Emergency mode is the last line of defence before human escalation.
    A 200-token cap forces the model to produce a concise decision rather
    than an expensive chain-of-thought response.
    """
    tracker = CostTracker(budget_inr=Decimal("5.00"))

    # Normal mode: max_tokens should be 2048
    normal_config = tracker.get_next_model_config()
    assert normal_config["max_tokens"] == 2048, (
        f"Normal mode max_tokens should be 2048, got {normal_config['max_tokens']}"
    )

    # Trigger emergency mode by spending > ₹4.50
    # 70b(65000p, 20000c) → ₹4.549, leaving ₹0.451 < ₹0.50 threshold
    tracker.record_call("llama-3.1-70b-versatile", 65000, 20000)

    assert tracker.emergency_mode is True

    emergency_config = tracker.get_next_model_config()

    assert emergency_config["max_tokens"] == EMERGENCY_MAX_TOKENS, (
        f"Emergency max_tokens must be {EMERGENCY_MAX_TOKENS}, "
        f"got {emergency_config['max_tokens']}"
    )
    assert emergency_config["max_tokens"] == 200  # explicit value check
    assert emergency_config["model"] == EMERGENCY_MODEL


# ---------------------------------------------------------------------------
# Test 3
# ---------------------------------------------------------------------------


def test_escalation_halts_all_further_calls():
    """
    After escalation (budget exhausted), record_call must raise RuntimeError.
    This is the hard stop that prevents infinite spend on a single dispute.

    The stub implements this guard in record_call — Member 2 must preserve it.
    """
    tracker = CostTracker(budget_inr=Decimal("5.00"))

    # Exhaust the budget: 70b(80000p, 20000c) → ₹5.292
    tracker.record_call("llama-3.1-70b-versatile", 80000, 20000)

    assert tracker.escalated_to_human is True
    assert tracker.escalation_reason == "BUDGET_EXHAUSTED"

    # Any further call — regardless of model or token count — must be blocked
    with pytest.raises(RuntimeError, match="escalated"):
        tracker.record_call("llama-3.1-8b-instant", 10, 10)

    with pytest.raises(RuntimeError, match="escalated"):
        tracker.record_call("mixtral-8x7b-32768", 100, 50)

    with pytest.raises(RuntimeError, match="escalated"):
        tracker.record_call("llama-3.1-70b-versatile", 1, 1)

    # Call count must not have increased after escalation
    assert len(tracker.calls) == 1, (
        "No calls should be recorded after escalation"
    )


# ---------------------------------------------------------------------------
# Test 4
# ---------------------------------------------------------------------------


def test_budget_resets_per_dispute():
    """
    Each new CostTracker instance starts at ₹0.000 spend.
    Proves disputes don't share budget state (isolation guarantee).

    A shared-state bug would cause dispute N's spend to bleed into
    dispute N+1, triggering false emergency mode or wrong savings figures.
    """
    tracker1 = CostTracker(budget_inr=Decimal("5.00"))
    tracker2 = CostTracker(budget_inr=Decimal("5.00"))

    # Record several calls on tracker1
    tracker1.record_call("llama-3.1-8b-instant",    6000,  3000)
    tracker1.record_call("mixtral-8x7b-32768",      10000, 9000)
    tracker1.record_call("llama-3.1-70b-versatile", 20000, 8000)

    # tracker2 must be completely unaffected
    assert tracker2.total_cost_inr == Decimal("0.000"), (
        f"tracker2 must start at ₹0.000, got ₹{tracker2.total_cost_inr}"
    )
    assert tracker2.remaining_inr() == Decimal("5.000"), (
        f"tracker2 remaining must be ₹5.000, got ₹{tracker2.remaining_inr()}"
    )
    assert tracker2.emergency_mode is False
    assert tracker2.escalated_to_human is False
    assert len(tracker2.calls) == 0

    # tracker1 must have its own state
    assert tracker1.total_cost_inr > Decimal("0.000")
    assert len(tracker1.calls) == 3

    # A third fresh tracker also starts clean
    tracker3 = CostTracker()
    assert tracker3.total_cost_inr == Decimal("0.000")
    assert tracker3.budget_inr == Decimal("5.00")  # default budget
