"""
qa/e2e/test_demo_scenarios.py
Canonical demo scenario tests for NyayaNode.

Runs all 5 canonical scenarios and proves the system works exactly as
judges will see it. This is the master demo test suite — if all 5 pass,
NyayaNode ships.

All tests skip gracefully when the backend is unreachable.
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from decimal import Decimal

import httpx
import pytest

from qa.conftest import backend_reachable
from qa.synthetic.scenarios import ALL_SCENARIOS, SCENARIO_5
from shared.schemas import DisputeDecision, DisputeResponse, DisputeStatus

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(
        not backend_reachable(),
        reason="Backend not reachable",
    ),
]


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def run_scenario_and_wait(
    client: httpx.AsyncClient,
    scenario: dict,
    timeout_seconds: int = 45,
) -> tuple[dict, float]:
    """
    Creates a dispute from scenario data, triggers agent, polls until
    resolved or timeout.
    Returns (response_data, elapsed_seconds).
    """
    start = time.time()

    # Create dispute
    payload = {
        "buyer_id":           scenario["buyer_id"],
        "seller_id":          scenario["seller_id"],
        "logistics_id":       scenario["logistics_id"],
        "order_id":           scenario["order_id"],
        "dispute_type":       scenario["dispute_type"],
        "dispute_amount_inr": scenario["dispute_amount_inr"],
        "evidence":           scenario["evidence"],
        "description":        scenario.get("description", ""),
    }

    create_resp = await client.post("/disputes", json=payload)
    assert create_resp.status_code == 201, (
        f"Failed to create dispute for '{scenario['name']}': {create_resp.text}"
    )
    dispute_id = create_resp.json()["dispute_id"]

    # Trigger agent run
    await client.post(f"/disputes/{dispute_id}/run")

    # Poll for completion
    final_data = None
    while time.time() - start < timeout_seconds:
        await asyncio.sleep(2.0)
        resp = await client.get(f"/disputes/{dispute_id}")
        data = resp.json()
        if data.get("status") in ("RESOLVED", "ESCALATED"):
            final_data = data
            break

    elapsed = time.time() - start

    assert final_data is not None, (
        f"Scenario '{scenario['name']}' did not complete in {timeout_seconds}s"
    )
    return final_data, elapsed


# ---------------------------------------------------------------------------
# Parametrized: all 5 canonical scenarios
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "scenario",
    ALL_SCENARIOS,
    ids=[s["name"] for s in ALL_SCENARIOS],
)
@pytest.mark.asyncio
async def test_scenario_decision_correct(
    scenario: dict,
    async_client: httpx.AsyncClient,
    mock_groq,
):
    """
    PARAMETRIZED: Runs each of the 5 canonical scenarios and asserts:
      1. Decision matches expected_decision
      2. Status matches expected_status
      3. Total cost <= max_budget_inr (₹5.00)
      4. Refund math is internally consistent
      5. Response arrived within 45 seconds

    This is the master demo test. If all 5 pass, NyayaNode ships.
    """
    response_data, elapsed = await run_scenario_and_wait(async_client, scenario)

    # 1. Decision
    assert response_data["decision"] == scenario["expected_decision"], (
        f"[{scenario['name']}] Decision mismatch: "
        f"expected={scenario['expected_decision']}, "
        f"got={response_data['decision']}"
    )

    # 2. Status
    assert response_data["status"] == scenario["expected_status"], (
        f"[{scenario['name']}] Status mismatch: "
        f"expected={scenario['expected_status']}, "
        f"got={response_data['status']}"
    )

    # 3. Budget
    cost = Decimal(str(response_data.get("total_inference_cost_inr", 0)))
    max_budget = Decimal(str(scenario["max_budget_inr"]))
    assert cost <= max_budget, (
        f"[{scenario['name']}] Budget exceeded: ₹{cost} > ₹{max_budget}"
    )

    # 4. Refund math
    decision = response_data["decision"]
    refund = Decimal(str(response_data.get("refund_amount_inr", 0)))
    amount = Decimal(str(scenario["dispute_amount_inr"]))

    if decision == "FULL_REFUND":
        assert refund == amount, (
            f"[{scenario['name']}] Full refund should be ₹{amount}, got ₹{refund}"
        )
    elif decision == "REJECTED":
        assert refund == Decimal("0"), (
            f"[{scenario['name']}] Rejected should refund ₹0, got ₹{refund}"
        )
    elif decision == "PARTIAL_REFUND":
        assert Decimal("0") < refund < amount, (
            f"[{scenario['name']}] Partial refund ₹{refund} not in (0, {amount})"
        )
    # PENDING / ESCALATED: no refund math assertion required

    # 5. Timing
    if elapsed > 30:
        print(f"\n⚠️  [{scenario['name']}] Slow: {elapsed:.1f}s")


# ---------------------------------------------------------------------------
# Scenario 5 escalation guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scenario_5_escalates_not_resolves(
    async_client: httpx.AsyncClient,
    mock_groq,
):
    """
    CRITICAL: Scenario 5 (Expensive Watch) must ESCALATE, not RESOLVE.

    High-value ambiguous disputes must always go to human review.
    If this test fails, NyayaNode could auto-resolve ₹8999 disputes with
    insufficient confidence — legal liability.

    Note: mock_groq returns FULL_REFUND by default. The backend's own
    escalation logic (high value + ambiguous evidence + no logistics
    confirmation) must override the LLM suggestion and force ESCALATED.
    """
    response_data, _ = await run_scenario_and_wait(async_client, SCENARIO_5)

    assert response_data["status"] == "ESCALATED", (
        "Scenario 5 (₹8999 ambiguous watch) must escalate to human review, "
        f"but got status={response_data['status']}"
    )
    assert response_data.get("decision") in ("PENDING", None), (
        f"Escalated dispute should have PENDING or null decision, "
        f"got {response_data.get('decision')}"
    )
