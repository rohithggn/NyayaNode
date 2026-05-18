"""
qa/integration/test_frontend_api.py
Integration tests for the API routes consumed by the Next.js frontend.

These endpoints power the dashboard: audit trails, cost breakdowns,
and aggregate statistics. All tests skip when the backend is unreachable.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest

from qa.conftest import backend_reachable
from qa.synthetic.scenarios import SCENARIO_1
from shared.schemas import CascadeflowAudit

pytestmark = pytest.mark.skipif(
    not backend_reachable(),
    reason="FastAPI backend not reachable — skipping integration tests",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_DISPUTE_PAYLOAD = {
    "buyer_id":           SCENARIO_1["buyer_id"],
    "seller_id":          SCENARIO_1["seller_id"],
    "logistics_id":       SCENARIO_1["logistics_id"],
    "order_id":           SCENARIO_1["order_id"],
    "dispute_type":       SCENARIO_1["dispute_type"],
    "dispute_amount_inr": SCENARIO_1["dispute_amount_inr"],
    "evidence":           SCENARIO_1["evidence"],
    "description":        SCENARIO_1["description"],
}


async def _create_dispute(async_client) -> str:
    """Helper: create a dispute and return its dispute_id."""
    resp = await async_client.post("/disputes", json=_VALID_DISPUTE_PAYLOAD)
    assert resp.status_code == 201, (
        f"Setup failed: POST /disputes returned {resp.status_code}. "
        f"Body: {resp.text}"
    )
    return resp.json()["dispute_id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cascadeflow_audit_endpoint(async_client):
    """
    Proves the audit endpoint returns a valid CascadeflowAudit.
    The frontend dashboard reads this to render the cost breakdown panel.

    Creates a dispute first, then fetches its audit record.
    The response must parse cleanly into the CascadeflowAudit schema.
    """
    dispute_id = await _create_dispute(async_client)

    response = await async_client.get(f"/disputes/{dispute_id}/audit")

    assert response.status_code == 200, (
        f"Expected 200 from GET /disputes/{dispute_id}/audit, "
        f"got {response.status_code}. Body: {response.text}"
    )

    body = response.json()

    # Must parse into CascadeflowAudit without ValidationError
    audit = CascadeflowAudit.model_validate(body)

    assert audit.dispute_id == dispute_id, (
        f"Audit dispute_id '{audit.dispute_id}' does not match '{dispute_id}'"
    )
    assert isinstance(audit.model_calls, list), (
        "model_calls must be a list"
    )
    assert audit.budget_inr > 0, "budget_inr must be positive"
    assert audit.total_cost_inr >= 0, "total_cost_inr must be non-negative"
    assert audit.total_cost_inr <= audit.budget_inr or audit.budget_exhausted, (
        "total_cost_inr must not exceed budget unless budget_exhausted is True"
    )


@pytest.mark.asyncio
async def test_audit_trail_endpoint(async_client):
    """
    Proves the audit trail has minimum required events.
    The frontend renders a timeline from this data.

    Each event must carry: event_type, timestamp, dispute_id.
    """
    dispute_id = await _create_dispute(async_client)

    response = await async_client.get(f"/disputes/{dispute_id}/trail")

    assert response.status_code == 200, (
        f"Expected 200 from GET /disputes/{dispute_id}/trail, "
        f"got {response.status_code}. Body: {response.text}"
    )

    body = response.json()

    # Accept bare list or envelope {"trail": [...]}
    if isinstance(body, list):
        trail = body
    elif isinstance(body, dict) and "trail" in body:
        trail = body["trail"]
    else:
        pytest.fail(
            f"Trail endpoint must return a list or an object with 'trail' key. "
            f"Got: {type(body).__name__}"
        )

    assert len(trail) >= 1, (
        f"Audit trail must have at least 1 event, got {len(trail)}"
    )

    # Validate required fields on every event
    required_fields = {"event_type", "timestamp", "dispute_id"}
    for i, event in enumerate(trail):
        missing = required_fields - set(event.keys())
        assert not missing, (
            f"Trail event {i} is missing required fields: {missing}. "
            f"Event: {event}"
        )
        assert event["dispute_id"] == dispute_id, (
            f"Trail event {i} has wrong dispute_id: '{event['dispute_id']}'"
        )
        assert isinstance(event["event_type"], str) and event["event_type"], (
            f"Trail event {i} event_type must be a non-empty string"
        )
        assert isinstance(event["timestamp"], str) and event["timestamp"], (
            f"Trail event {i} timestamp must be a non-empty ISO8601 string"
        )


@pytest.mark.asyncio
async def test_stats_endpoint(async_client):
    """
    Proves the dashboard stats endpoint exists and returns aggregate metrics.
    The frontend header bar reads this to show live KPIs.

    Accepts either /stats or /disputes/stats — both are valid routes.
    Required fields: total_disputes, resolved_count, avg_cost_inr.
    """
    # Try /disputes/stats first, fall back to /stats
    response = await async_client.get("/disputes/stats")
    if response.status_code == 404:
        response = await async_client.get("/stats")

    assert response.status_code == 200, (
        f"Expected 200 from stats endpoint, got {response.status_code}. "
        f"Body: {response.text}"
    )

    body = response.json()

    required_fields = {"total_disputes", "resolved_count", "avg_cost_inr"}
    missing = required_fields - set(body.keys())
    assert not missing, (
        f"Stats response is missing required fields: {missing}. "
        f"Got keys: {set(body.keys())}"
    )

    # Type checks
    assert isinstance(body["total_disputes"], int), (
        f"total_disputes must be an int, got {type(body['total_disputes']).__name__}"
    )
    assert isinstance(body["resolved_count"], int), (
        f"resolved_count must be an int, got {type(body['resolved_count']).__name__}"
    )
    assert isinstance(body["avg_cost_inr"], (int, float)), (
        f"avg_cost_inr must be numeric, got {type(body['avg_cost_inr']).__name__}"
    )

    # Sanity bounds
    assert body["total_disputes"] >= 0
    assert body["resolved_count"] >= 0
    assert body["resolved_count"] <= body["total_disputes"], (
        "resolved_count cannot exceed total_disputes"
    )
    assert body["avg_cost_inr"] >= 0
