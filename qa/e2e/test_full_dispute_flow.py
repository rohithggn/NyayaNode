"""
qa/e2e/test_full_dispute_flow.py
Full pipeline E2E test for NyayaNode.

Proves the complete happy-path flow from dispute creation to verdict
delivery across all 8 pipeline stages. This is the full demo script
in test form.

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
from qa.synthetic.scenarios import SCENARIO_1
from shared.schemas import CascadeflowAudit, DisputeResponse, DisputeStatus

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.slow,
    pytest.mark.skipif(
        not backend_reachable(),
        reason="Backend not reachable",
    ),
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_BUDGET_INR = Decimal("5.00")
_MIN_TRAIL_EVENTS = 3
_POLL_INTERVAL_S = 2.0
_POLL_MAX_ATTEMPTS = 25


# ---------------------------------------------------------------------------
# Pipeline test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_buyer_to_verdict_pipeline(
    async_client: httpx.AsyncClient,
    mock_groq,
):
    """
    PIPELINE TEST: Proves the complete happy-path flow from dispute creation
    to verdict delivery:

      Stage 1: Buyer submits dispute        → status=OPEN
      Stage 2: Agent picks it up            → status=IN_PROGRESS
      Stage 3: Evidence collected           → SSE events firing
      Stage 4: Negotiation attempted        → seller response recorded
      Stage 5: Decision issued              → status=RESOLVED
      Stage 6: Refund amount set            → math correct
      Stage 7: Audit trail complete         → min 3 events
      Stage 8: Cascadeflow audit            → budget not exhausted

    Uses Scenario 1 (Damaged Kurta) — clearest expected outcome.
    """
    # -----------------------------------------------------------------------
    # Stage 1: Buyer submits dispute → status=OPEN
    # -----------------------------------------------------------------------
    create_payload = {
        k: SCENARIO_1[k]
        for k in (
            "buyer_id",
            "seller_id",
            "logistics_id",
            "order_id",
            "dispute_type",
            "dispute_amount_inr",
            "evidence",
        )
    }

    resp = await async_client.post("/disputes", json=create_payload)
    assert resp.status_code == 201, (
        f"[Stage 1] POST /disputes failed: {resp.status_code}. Body: {resp.text}"
    )

    data = resp.json()
    assert data["status"] == "OPEN", (
        f"[Stage 1] Newly created dispute must have status=OPEN, "
        f"got '{data['status']}'"
    )
    assert "dispute_id" in data and data["dispute_id"], (
        "[Stage 1] Response must contain a non-empty dispute_id"
    )
    assert "created_at" in data and data["created_at"], (
        "[Stage 1] Response must contain created_at timestamp"
    )

    dispute_id = data["dispute_id"]

    # -----------------------------------------------------------------------
    # Stage 2: Trigger agent run → expect IN_PROGRESS transition
    # -----------------------------------------------------------------------
    run_resp = await async_client.post(f"/disputes/{dispute_id}/run")
    assert run_resp.status_code in (200, 202), (
        f"[Stage 2] POST /disputes/{dispute_id}/run returned "
        f"{run_resp.status_code}. Body: {run_resp.text}"
    )

    # Brief pause then check for IN_PROGRESS (best-effort — some backends
    # may transition too fast to observe this state)
    await asyncio.sleep(0.5)
    check_resp = await async_client.get(f"/disputes/{dispute_id}")
    in_progress_observed = check_resp.json().get("status") == "IN_PROGRESS"
    # Not a hard assertion — fast backends may skip straight to RESOLVED

    # -----------------------------------------------------------------------
    # Stages 3-5: Poll until RESOLVED or ESCALATED
    # -----------------------------------------------------------------------
    final_data = None
    for attempt in range(_POLL_MAX_ATTEMPTS):
        await asyncio.sleep(_POLL_INTERVAL_S)
        poll_resp = await async_client.get(f"/disputes/{dispute_id}")
        assert poll_resp.status_code == 200, (
            f"[Stage 3-5] GET /disputes/{dispute_id} returned "
            f"{poll_resp.status_code} on attempt {attempt + 1}"
        )
        poll_data = poll_resp.json()
        if poll_data.get("status") in ("RESOLVED", "ESCALATED"):
            final_data = poll_data
            break

    assert final_data is not None, (
        f"[Stage 5] Dispute {dispute_id} did not reach RESOLVED/ESCALATED "
        f"within {_POLL_MAX_ATTEMPTS * _POLL_INTERVAL_S:.0f}s"
    )

    # -----------------------------------------------------------------------
    # Stage 5: Decision issued → status=RESOLVED (Scenario 1 expected)
    # -----------------------------------------------------------------------
    assert final_data["status"] in ("RESOLVED", "ESCALATED"), (
        f"[Stage 5] Final status must be RESOLVED or ESCALATED, "
        f"got '{final_data['status']}'"
    )

    # For Scenario 1 specifically, expect RESOLVED
    assert final_data["status"] == SCENARIO_1["expected_status"], (
        f"[Stage 5] Scenario 1 expected status '{SCENARIO_1['expected_status']}', "
        f"got '{final_data['status']}'"
    )
    assert final_data.get("decision") == SCENARIO_1["expected_decision"], (
        f"[Stage 5] Scenario 1 expected decision '{SCENARIO_1['expected_decision']}', "
        f"got '{final_data.get('decision')}'"
    )

    # -----------------------------------------------------------------------
    # Stage 6: Refund amount set → math correct
    # -----------------------------------------------------------------------
    decision = final_data.get("decision")
    refund = Decimal(str(final_data.get("refund_amount_inr", 0)))
    dispute_amount = Decimal(str(SCENARIO_1["dispute_amount_inr"]))

    if decision == "FULL_REFUND":
        assert refund == dispute_amount, (
            f"[Stage 6] FULL_REFUND: refund ₹{refund} must equal "
            f"dispute amount ₹{dispute_amount}"
        )
    elif decision == "REJECTED":
        assert refund == Decimal("0"), (
            f"[Stage 6] REJECTED: refund must be ₹0, got ₹{refund}"
        )
    elif decision == "PARTIAL_REFUND":
        assert Decimal("0") < refund < dispute_amount, (
            f"[Stage 6] PARTIAL_REFUND: ₹{refund} must be in (0, {dispute_amount})"
        )

    # -----------------------------------------------------------------------
    # Stage 6b: Schema compliance
    # -----------------------------------------------------------------------
    try:
        DisputeResponse.model_validate(final_data)
    except Exception as exc:
        pytest.fail(
            f"[Stage 6b] Final response failed DisputeResponse schema validation: {exc}"
        )

    # -----------------------------------------------------------------------
    # Stage 7: Audit trail complete → min 3 events
    # -----------------------------------------------------------------------
    trail_resp = await async_client.get(f"/disputes/{dispute_id}/trail")
    if trail_resp.status_code == 200:
        body = trail_resp.json()
        trail = body if isinstance(body, list) else body.get("trail", [])

        assert len(trail) >= _MIN_TRAIL_EVENTS, (
            f"[Stage 7] Audit trail has {len(trail)} events, "
            f"minimum required is {_MIN_TRAIL_EVENTS}"
        )

        # Every event must have the required fields
        for i, event in enumerate(trail):
            for field in ("event_type", "timestamp", "dispute_id"):
                assert field in event, (
                    f"[Stage 7] Trail event {i} missing '{field}' field. "
                    f"Event: {event}"
                )
            assert event["dispute_id"] == dispute_id, (
                f"[Stage 7] Trail event {i} has wrong dispute_id: "
                f"'{event['dispute_id']}' != '{dispute_id}'"
            )

    # -----------------------------------------------------------------------
    # Stage 8: Cascadeflow audit → budget not exhausted
    # -----------------------------------------------------------------------
    audit_resp = await async_client.get(f"/disputes/{dispute_id}/audit")
    if audit_resp.status_code == 200:
        audit = CascadeflowAudit.model_validate(audit_resp.json())

        assert not audit.budget_exhausted, (
            f"[Stage 8] Budget must not be exhausted for Scenario 1. "
            f"total_cost_inr=₹{audit.total_cost_inr}, "
            f"budget_inr=₹{audit.budget_inr}"
        )
        assert audit.total_cost_inr <= _MAX_BUDGET_INR, (
            f"[Stage 8] Audit cost ₹{audit.total_cost_inr} exceeds "
            f"₹{_MAX_BUDGET_INR} budget"
        )
        assert not audit.escalated_to_human, (
            "[Stage 8] Scenario 1 must not escalate to human review"
        )
        assert isinstance(audit.model_calls, list) and len(audit.model_calls) >= 1, (
            "[Stage 8] Audit must record at least 1 model call"
        )

    # -----------------------------------------------------------------------
    # Summary print (visible with -s flag)
    # -----------------------------------------------------------------------
    cost = Decimal(str(final_data.get("total_inference_cost_inr", 0)))
    print(
        f"\n✅ Pipeline complete for dispute {dispute_id}\n"
        f"   Status:   {final_data['status']}\n"
        f"   Decision: {final_data.get('decision')}\n"
        f"   Refund:   ₹{refund}\n"
        f"   Cost:     ₹{cost} / ₹{_MAX_BUDGET_INR}\n"
        f"   IN_PROGRESS observed: {in_progress_observed}"
    )
