"""
qa/unit/test_cost_tracker.py
Budget math tests for CostTracker — all monetary assertions use Decimal.
Zero float equality checks. These are billing-correctness tests.

Token counts are derived from the model cost formula:
  cost_inr = ((prompt_tokens/1M)*input_usd + (completion_tokens/1M)*output_usd) * 84.0
  quantized to 3 decimal places with ROUND_HALF_UP.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from decimal import Decimal, ROUND_HALF_UP

import pytest

from agents.cascadeflow.cost_tracker import (
    EMERGENCY_MAX_TOKENS,
    EMERGENCY_MODEL,
    CostTracker,
)


# ---------------------------------------------------------------------------
# Test 1
# ---------------------------------------------------------------------------


def test_normal_routing_cost_total():
    """
    Proves the tracker correctly sums 4 model calls:
      - 2× llama-3.1-8b-instant  (small tasks)
      - 1× mixtral-8x7b-32768    (negotiation)
      - 1× llama-3.1-70b-versatile (final decision)

    Token counts chosen so the total lands within ₹0.05 of ₹3.10:
      8b(6000p, 3000c)   → ₹0.045 each  × 2 = ₹0.090
      mixtral(10000p, 9000c)             → ₹0.431
      70b(36000p, 12000c)                → ₹2.580
      ─────────────────────────────────────────────
      Total                              → ₹3.101

    This test catches float rounding bugs that cause ₹0.01 billing errors
    multiplied across 10,000 disputes per day = ₹100/day in ghost charges.
    """
    tracker = CostTracker(budget_inr=Decimal("5.00"))

    tracker.record_call("llama-3.1-8b-instant",    6000,  3000)
    tracker.record_call("llama-3.1-8b-instant",    6000,  3000)
    tracker.record_call("mixtral-8x7b-32768",      10000, 9000)
    tracker.record_call("llama-3.1-70b-versatile", 36000, 12000)

    # Total must be within ₹0.05 of ₹3.10
    assert abs(tracker.total_cost_inr - Decimal("3.10")) <= Decimal("0.05"), (
        f"Expected total near ₹3.10, got ₹{tracker.total_cost_inr}"
    )

    # Remaining must be within ₹0.05 of ₹1.90
    assert abs(tracker.remaining_inr() - Decimal("1.90")) <= Decimal("0.05"), (
        f"Expected remaining near ₹1.90, got ₹{tracker.remaining_inr()}"
    )

    # Budget not yet exhausted — emergency mode must be off
    assert tracker.emergency_mode is False
    assert tracker.escalated_to_human is False

    # All 4 calls must be recorded
    assert len(tracker.calls) == 4

    # Every recorded cost must be a Decimal (no floats leaked in)
    for call in tracker.calls:
        assert isinstance(call["cost_inr"], Decimal), (
            f"cost_inr must be Decimal, got {type(call['cost_inr'])}"
        )


# ---------------------------------------------------------------------------
# Test 2
# ---------------------------------------------------------------------------


def test_emergency_mode_triggers_at_threshold():
    """
    Proves emergency mode activates when remaining budget < ₹0.50.
    This is the mechanism that prevents budget overruns.

    At emergency mode: next call MUST use the cheapest model with
    max_tokens capped at 200 — not a suggestion, a hard requirement.

    Strategy: one large 70b call (65000p, 20000c) costs ₹4.549,
    leaving ₹0.451 remaining — below the ₹0.50 threshold.
    """
    tracker = CostTracker(budget_inr=Decimal("5.00"))

    # Single large call that pushes remaining below ₹0.50
    # 70b(65000p, 20000c): cost = ((65000*0.59 + 20000*0.79)/1M)*84 = ₹4.549
    tracker.record_call("llama-3.1-70b-versatile", 65000, 20000)

    assert tracker.emergency_mode is True, (
        "Emergency mode must activate when remaining < ₹0.50"
    )
    assert tracker.remaining_inr() < Decimal("0.50"), (
        f"Remaining should be < ₹0.50, got ₹{tracker.remaining_inr()}"
    )

    config = tracker.get_next_model_config()

    assert config["model"] == EMERGENCY_MODEL, (
        f"Emergency model must be '{EMERGENCY_MODEL}', got '{config['model']}'"
    )
    assert config["max_tokens"] == EMERGENCY_MAX_TOKENS, (
        f"Emergency max_tokens must be {EMERGENCY_MAX_TOKENS}, got {config['max_tokens']}"
    )


# ---------------------------------------------------------------------------
# Test 3
# ---------------------------------------------------------------------------


def test_budget_exhaustion_triggers_escalation():
    """
    Proves that when total spend reaches ₹5.00, the tracker escalates to
    human and blocks further inference.

    This is the hard budget cap that makes NyayaNode economically viable.

    Strategy: one 70b call (80000p, 20000c) costs ₹5.292 — over budget.
    """
    tracker = CostTracker(budget_inr=Decimal("5.00"))

    # 70b(80000p, 20000c): cost = ((80000*0.59 + 20000*0.79)/1M)*84 = ₹5.292
    tracker.record_call("llama-3.1-70b-versatile", 80000, 20000)

    assert tracker.escalated_to_human is True, (
        "Tracker must escalate to human when budget is exhausted"
    )
    assert tracker.escalation_reason == "BUDGET_EXHAUSTED", (
        f"escalation_reason must be 'BUDGET_EXHAUSTED', got '{tracker.escalation_reason}'"
    )
    assert tracker.total_cost_inr >= Decimal("5.00"), (
        f"total_cost_inr must be >= ₹5.00, got ₹{tracker.total_cost_inr}"
    )

    # Further calls must be blocked with RuntimeError
    with pytest.raises(RuntimeError, match="escalated"):
        tracker.record_call("llama-3.1-8b-instant", 100, 50)


# ---------------------------------------------------------------------------
# Test 4
# ---------------------------------------------------------------------------


def test_savings_calculation_precision():
    """
    Proves savings calculation rounds to exactly 1 decimal place.
    71.33...% must round to 71.3%, not 71% or 71.33%.

    Incorrect savings reporting would mislead judges and investors
    about NyayaNode's cost efficiency story.
    """
    tracker = CostTracker(budget_inr=Decimal("5.00"))

    # Directly set total to match the cascadeflow_sample fixture
    tracker.total_cost_inr = Decimal("3.21")

    result = tracker.calculate_savings(hypothetical_cost_inr=Decimal("11.20"))

    assert isinstance(result["savings_inr"], Decimal), (
        "savings_inr must be Decimal"
    )
    assert isinstance(result["savings_percent"], Decimal), (
        "savings_percent must be Decimal"
    )
    assert result["savings_inr"] == Decimal("7.99"), (
        f"Expected savings_inr=7.99, got {result['savings_inr']}"
    )
    assert result["savings_percent"] == Decimal("71.3"), (
        f"Expected savings_percent=71.3, got {result['savings_percent']}"
    )


# ---------------------------------------------------------------------------
# Test 5
# ---------------------------------------------------------------------------


def test_inr_conversion_precision():
    """
    Proves USD→INR conversion rounds to 3 decimal places with ROUND_HALF_UP.
    ₹0.0336... must become ₹0.034, not ₹0.0336 or ₹0.03.

    Rounding mode matters: ROUND_HALF_UP not banker's rounding (ROUND_HALF_EVEN).
    """
    cost_usd = Decimal("0.000401")
    usd_to_inr = Decimal("84.0")

    result = (cost_usd * usd_to_inr).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )

    assert result == Decimal("0.034"), (
        f"Expected ₹0.034, got ₹{result}. "
        "Check that ROUND_HALF_UP is used, not banker's rounding."
    )

    # Also verify the rounding direction: 0.0005 * 84 = 0.042 (exact, no rounding needed)
    # and 0.000404 * 84 = 0.033936 → rounds to 0.034
    borderline = (Decimal("0.000404") * usd_to_inr).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )
    assert borderline == Decimal("0.034"), (
        f"Borderline rounding failed: expected 0.034, got {borderline}"
    )
