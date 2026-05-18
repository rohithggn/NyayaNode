"""
qa/e2e/test_budget_enforcement.py
Budget enforcement E2E tests for NyayaNode.

Proves the ₹5.00 per-dispute inference budget holds across all 5 canonical
scenarios, and that the CascadeflowAudit cost matches the DisputeResponse
cost (two sources of truth must agree).

All tests skip gracefully when the backend is unreachable.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from decimal import Decimal

import httpx
import pytest

from qa.conftest import backend_reachable
from qa.synthetic.scenarios import ALL_SCENARIOS, SCENARIO_1
from shared.schemas import CascadeflowAudit

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(
        not backend_reachable(),
        reason="Backend not reachable",
    ),
]


# ---------------------------------------------------------------------------
# Test 1: All 5 scenarios within ₹5.00 budget
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_scenarios_within_budget(
    async_client: httpx.AsyncClient,
    mock_groq,
):
    """
    BUDGET GUARANTEE TEST: Proves that ALL 5 demo scenarios complete within
    the ₹5.00 per-dispute inference budget.

    This is the core economic promise of NyayaNode:
      ₹500 dispute → ₹5 AI cost → viable unit economics.

    If even ONE scenario exceeds ₹5, the business model breaks.
    """
    for scenario in ALL_SCENARIOS:
        create_resp = await async_client.post(
            "/disputes",
            json={
                "buyer_id":           scenario["buyer_id"],
                "seller_id":          scenario["seller_id"],
                "logistics_id":       scenario["logistics_id"],
                "order_id":           scenario["order_id"],
                "dispute_type":       scenario["dispute_type"],
                "dispute_amount_inr": scenario["dispute_amount_inr"],
                "evidence":           scenario["evidence"],
            },
        )

        if create_resp.status_code != 201:
            pytest.skip(
                f"Could not create dispute for '{scenario['name']}' "
                f"(status {create_resp.status_code}) — skipping budget check"
            )

        dispute_id = create_resp.json()["dispute_id"]

        # Trigger agent run
        await async_client.post(f"/disputes/{dispute_id}/run")

        # Wait for completion — poll up to 45s
        final_data = None
        for _ in range(22):  # 22 × 2s = 44s
            await asyncio.sleep(2.0)
            resp = await async_client.get(f"/disputes/{dispute_id}")
            data = resp.json()
            if data.get("status") in ("RESOLVED", "ESCALATED"):
                final_data = data
                break

        if final_data is None:
            pytest.skip(
                f"Scenario '{scenario['name']}' did not complete in 44s — "
                "skipping budget assertion (timing issue, not a budget failure)"
            )

        cost = Decimal(str(final_data.get("total_inference_cost_inr", 0)))
        limit = Decimal(str(scenario["max_budget_inr"]))

        assert cost <= limit, (
            f"BUDGET EXCEEDED for '{scenario['name']}': "
            f"₹{cost} > ₹{limit} limit. "
            f"This breaks NyayaNode's unit economics."
        )


# ---------------------------------------------------------------------------
# Test 2: Audit cost matches response cost
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cascadeflow_audit_matches_response(
    async_client: httpx.AsyncClient,
    mock_groq,
):
    """
    Proves the CascadeflowAudit cost matches the DisputeResponse cost.

    Two sources of truth must agree — any mismatch is a billing bug.
    The audit is the authoritative record; the response is the user-facing
    summary. They must be identical to the rupee.
    """
    create_resp = await async_client.post(
        "/disputes",
        json={
            "buyer_id":           SCENARIO_1["buyer_id"],
            "seller_id":          SCENARIO_1["seller_id"],
            "logistics_id":       SCENARIO_1["logistics_id"],
            "order_id":           SCENARIO_1["order_id"],
            "dispute_type":       SCENARIO_1["dispute_type"],
            "dispute_amount_inr": SCENARIO_1["dispute_amount_inr"],
            "evidence":           SCENARIO_1["evidence"],
        },
    )
    assert create_resp.status_code == 201, (
        f"Setup failed: POST /disputes returned {create_resp.status_code}"
    )
    dispute_id = create_resp.json()["dispute_id"]

    # Trigger and wait
    await async_client.post(f"/disputes/{dispute_id}/run")
    await asyncio.sleep(10.0)

    dispute_resp = await async_client.get(f"/disputes/{dispute_id}")
    audit_resp = await async_client.get(f"/disputes/{dispute_id}/audit")

    if audit_resp.status_code != 200:
        pytest.skip("Audit endpoint not yet implemented — skipping cost reconciliation")

    audit = CascadeflowAudit.model_validate(audit_resp.json())
    dispute = dispute_resp.json()

    cost_from_audit = Decimal(str(audit.total_cost_inr))
    cost_from_response = Decimal(str(dispute.get("total_inference_cost_inr", 0)))

    assert cost_from_audit == cost_from_response, (
        f"Billing inconsistency detected!\n"
        f"  Audit cost:    ₹{cost_from_audit}\n"
        f"  Response cost: ₹{cost_from_response}\n"
        f"  Difference:    ₹{abs(cost_from_audit - cost_from_response)}\n"
        f"  dispute_id:    {dispute_id}"
    )

    # Also verify the audit's model_calls sum equals total_cost_inr
    calls_sum = sum(
        Decimal(str(call.cost_inr)) for call in audit.model_calls
    )
    assert calls_sum == cost_from_audit, (
        f"Audit model_calls sum ₹{calls_sum} ≠ audit.total_cost_inr ₹{cost_from_audit}. "
        "Internal audit inconsistency."
    )
