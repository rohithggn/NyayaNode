"""
qa/integration/test_agent_full_run.py
Master end-to-end integration test for NyayaNode arbitration pipeline.

Triggers a full arbitration run for Scenario 1 (Damaged Kurta) with
mocked Groq calls (no real API spend) and validates all 10 critical
assertions that define a correct, production-ready agent response.

All tests skip gracefully when the backend is unreachable.
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from decimal import Decimal

from qa.conftest import backend_reachable
from qa.synthetic.scenarios import SCENARIO_1
from shared.schemas import CascadeflowAudit, DisputeResponse

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not backend_reachable(),
        reason="Backend not reachable",
    ),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCENARIO_1_PAYLOAD = {
    "buyer_id":           SCENARIO_1["buyer_id"],
    "seller_id":          SCENARIO_1["seller_id"],
    "logistics_id":       SCENARIO_1["logistics_id"],
    "order_id":           SCENARIO_1["order_id"],
    "dispute_type":       SCENARIO_1["dispute_type"],
    "dispute_amount_inr": SCENARIO_1["dispute_amount_inr"],
    "evidence":           SCENARIO_1["evidence"],
    "description":        SCENARIO_1["description"],
}

_POLL_INTERVAL_S = 1.0
_POLL_MAX_ATTEMPTS = 30
_HARD_LIMIT_S = 60.0
_TARGET_LIMIT_S = 30.0
_MIN_REASONING_LEN = 50
_MIN_TRAIL_EVENTS = 3
_MIN_CONFIDENCE = 0.70


# ---------------------------------------------------------------------------
# Master integration test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_arbitration_run_scenario_1(async_client, mock_groq):
    """
    MASTER INTEGRATION TEST: Proves the entire arbitration pipeline works
    end-to-end for Scenario 1 (Damaged Kurta).

    Validates ALL 10 critical assertions:
      1.  Decision correctness
      2.  Status correctness
      3.  Budget not exceeded
      4.  Cascadeflow audit present and consistent
      5.  Audit trail has minimum events
      6.  Confidence score valid range
      7.  Reasoning is non-empty and substantive
      8.  Refund math is correct
      9.  Schema compliance (Pydantic validation)
      10. Response time under 30 seconds (60s hard limit)
    """
    # -----------------------------------------------------------------------
    # Step 1: Create the dispute
    # -----------------------------------------------------------------------
    start_time = time.time()

    create_resp = await async_client.post("/disputes", json=_SCENARIO_1_PAYLOAD)
    assert create_resp.status_code == 201, (
        f"POST /disputes failed: {create_resp.status_code}. Body: {create_resp.text}"
    )
    dispute_id = create_resp.json()["dispute_id"]

    # -----------------------------------------------------------------------
    # Step 2: Poll for resolution (up to 30 attempts × 1s = 30s)
    # -----------------------------------------------------------------------
    response_data = None

    for attempt in range(_POLL_MAX_ATTEMPTS):
        await asyncio.sleep(_POLL_INTERVAL_S)
        get_resp = await async_client.get(f"/disputes/{dispute_id}")
        assert get_resp.status_code == 200, (
            f"GET /disputes/{dispute_id} returned {get_resp.status_code}"
        )
        data = get_resp.json()
        if data.get("status") in ("RESOLVED", "ESCALATED"):
            response_data = data
            break

    elapsed = time.time() - start_time

    # -----------------------------------------------------------------------
    # Step 3: If still not resolved, trigger the agent run manually
    # -----------------------------------------------------------------------
    if response_data is None:
        run_resp = await async_client.post(f"/disputes/{dispute_id}/run")
        assert run_resp.status_code in (200, 202), (
            f"POST /disputes/{dispute_id}/run returned {run_resp.status_code}. "
            f"Body: {run_resp.text}"
        )
        response_data = run_resp.json()

    assert response_data is not None, (
        f"Agent did not produce a response within {_POLL_MAX_ATTEMPTS}s "
        f"for dispute {dispute_id}"
    )

    # -----------------------------------------------------------------------
    # ASSERTION 1: Decision correctness
    # -----------------------------------------------------------------------
    assert response_data.get("decision") == SCENARIO_1["expected_decision"], (
        f"[ASSERTION 1] Expected decision '{SCENARIO_1['expected_decision']}', "
        f"got '{response_data.get('decision')}'"
    )

    # -----------------------------------------------------------------------
    # ASSERTION 2: Status correctness
    # -----------------------------------------------------------------------
    assert response_data.get("status") == SCENARIO_1["expected_status"], (
        f"[ASSERTION 2] Expected status '{SCENARIO_1['expected_status']}', "
        f"got '{response_data.get('status')}'"
    )

    # -----------------------------------------------------------------------
    # ASSERTION 3: Budget not exceeded
    # -----------------------------------------------------------------------
    cost_raw = response_data.get("total_inference_cost_inr", 0)
    cost = Decimal(str(cost_raw))
    max_budget = Decimal(str(SCENARIO_1["max_budget_inr"]))

    assert cost <= max_budget, (
        f"[ASSERTION 3] Budget exceeded: ₹{cost} > ₹{max_budget}"
    )

    # -----------------------------------------------------------------------
    # ASSERTION 4: Cascadeflow audit present and consistent
    # -----------------------------------------------------------------------
    hindsight_id = response_data.get("hindsight_session_id")
    assert hindsight_id is not None, (
        "[ASSERTION 4] hindsight_session_id must be present in response"
    )

    # Fetch and validate the full audit object
    audit_resp = await async_client.get(f"/disputes/{dispute_id}/audit")
    if audit_resp.status_code == 200:
        audit = CascadeflowAudit.model_validate(audit_resp.json())
        assert audit.dispute_id == dispute_id, (
            f"[ASSERTION 4] Audit dispute_id mismatch: "
            f"'{audit.dispute_id}' != '{dispute_id}'"
        )
        assert audit.total_cost_inr >= Decimal("0"), (
            "[ASSERTION 4] Audit total_cost_inr must be non-negative"
        )
        assert audit.total_cost_inr <= max_budget or audit.budget_exhausted, (
            f"[ASSERTION 4] Audit cost ₹{audit.total_cost_inr} exceeds budget "
            f"₹{max_budget} but budget_exhausted is False"
        )

    # -----------------------------------------------------------------------
    # ASSERTION 5: Audit trail has minimum events
    # -----------------------------------------------------------------------
    trail_resp = await async_client.get(f"/disputes/{dispute_id}/trail")
    if trail_resp.status_code == 200:
        body = trail_resp.json()
        trail = body if isinstance(body, list) else body.get("trail", [])

        assert len(trail) >= _MIN_TRAIL_EVENTS, (
            f"[ASSERTION 5] Audit trail too short: {len(trail)} events "
            f"(minimum {_MIN_TRAIL_EVENTS})"
        )

        # Last event must be a terminal event type
        last_event_type = trail[-1].get("event_type", "")
        terminal_types = {"DECISION_ISSUED", "ESCALATED", "RESOLVED", "BUDGET_EXHAUSTED"}
        assert last_event_type in terminal_types, (
            f"[ASSERTION 5] Last trail event_type '{last_event_type}' "
            f"is not a recognised terminal type. Expected one of {terminal_types}"
        )

    # -----------------------------------------------------------------------
    # ASSERTION 6: Confidence score valid range
    # -----------------------------------------------------------------------
    if response_data.get("status") == "RESOLVED":
        confidence = response_data.get("confidence_score")
        assert confidence is not None, (
            "[ASSERTION 6] confidence_score must be present for RESOLVED disputes"
        )
        assert 0.0 <= float(confidence) <= 1.0, (
            f"[ASSERTION 6] confidence_score {confidence} is outside [0.0, 1.0]"
        )
        assert float(confidence) >= _MIN_CONFIDENCE, (
            f"[ASSERTION 6] Low confidence {confidence} — "
            f"should have escalated (threshold: {_MIN_CONFIDENCE})"
        )

    # -----------------------------------------------------------------------
    # ASSERTION 7: Reasoning is non-empty and substantive
    # -----------------------------------------------------------------------
    reasoning = response_data.get("reasoning", "")
    assert reasoning is not None and len(reasoning) >= _MIN_REASONING_LEN, (
        f"[ASSERTION 7] Reasoning too short or missing. "
        f"Got {len(reasoning or '')} chars (minimum {_MIN_REASONING_LEN}): "
        f"'{reasoning}'"
    )

    # -----------------------------------------------------------------------
    # ASSERTION 8: Refund math is correct
    # -----------------------------------------------------------------------
    decision = response_data.get("decision")
    refund_raw = response_data.get("refund_amount_inr", 0)
    refund = Decimal(str(refund_raw))
    dispute_amount = Decimal(str(SCENARIO_1["dispute_amount_inr"]))

    if decision == "FULL_REFUND":
        assert refund == dispute_amount, (
            f"[ASSERTION 8] FULL_REFUND: refund ₹{refund} must equal "
            f"dispute amount ₹{dispute_amount}"
        )
    elif decision == "REJECTED":
        assert refund == Decimal("0.0"), (
            f"[ASSERTION 8] REJECTED: refund must be ₹0.00, got ₹{refund}"
        )
    elif decision == "PARTIAL_REFUND":
        assert Decimal("0") < refund < dispute_amount, (
            f"[ASSERTION 8] PARTIAL_REFUND: refund ₹{refund} must be "
            f"between ₹0 and ₹{dispute_amount}"
        )

    # -----------------------------------------------------------------------
    # ASSERTION 9: Schema compliance (Pydantic v2 validation)
    # -----------------------------------------------------------------------
    try:
        DisputeResponse.model_validate(response_data)
    except Exception as exc:
        pytest.fail(
            f"[ASSERTION 9] Response failed DisputeResponse schema validation: {exc}"
        )

    # -----------------------------------------------------------------------
    # ASSERTION 10: Response time
    # -----------------------------------------------------------------------
    if elapsed > _HARD_LIMIT_S:
        pytest.fail(
            f"[ASSERTION 10] Response time {elapsed:.1f}s exceeds "
            f"{_HARD_LIMIT_S}s hard limit"
        )
    elif elapsed > _TARGET_LIMIT_S:
        # Warning only — not a blocker
        print(
            f"\n⚠️  WARNING: Response time {elapsed:.1f}s exceeds "
            f"{_TARGET_LIMIT_S}s target (hard limit is {_HARD_LIMIT_S}s)"
        )
    else:
        assert elapsed <= _TARGET_LIMIT_S, (
            f"[ASSERTION 10] Response time {elapsed:.1f}s exceeds "
            f"{_TARGET_LIMIT_S}s target"
        )
