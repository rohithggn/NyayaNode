"""
qa/integration/test_api_mock_ondc.py
Integration tests for the ONDC mock party APIs.

These stubs let the agent work without needing real ONDC network access.
All tests skip gracefully when the FastAPI backend is unreachable.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest

from qa.conftest import backend_reachable
from qa.synthetic.scenarios import SCENARIO_1

pytestmark = pytest.mark.skipif(
    not backend_reachable(),
    reason="FastAPI backend not reachable — skipping integration tests",
)

# ---------------------------------------------------------------------------
# Scenario 1 party IDs — used across all mock tests
# ---------------------------------------------------------------------------
_LOGISTICS_ID = SCENARIO_1["logistics_id"]   # "ondc_lsp_007"
_SELLER_ID    = SCENARIO_1["seller_id"]       # "ondc_seller_042"
_BUYER_ID     = SCENARIO_1["buyer_id"]        # "ondc_buyer_001"
_ORDER_ID     = SCENARIO_1["order_id"]        # "order_demo_001"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mock_logistics_status_endpoint(async_client):
    """
    Proves logistics mock returns expected delivery status.
    The agent reads this endpoint to determine if a package was delivered
    and whether it arrived damaged.
    """
    response = await async_client.get(
        f"/mock/logistics/{_LOGISTICS_ID}/status"
    )

    assert response.status_code == 200, (
        f"Expected 200 from /mock/logistics/{_LOGISTICS_ID}/status, "
        f"got {response.status_code}. Body: {response.text}"
    )

    body = response.json()

    assert "status" in body, (
        "Logistics response must contain 'status' field"
    )
    assert "package_condition" in body, (
        "Logistics response must contain 'package_condition' field"
    )
    assert "timestamp" in body, (
        "Logistics response must contain 'timestamp' field"
    )

    # Values must be non-empty strings
    assert isinstance(body["status"], str) and body["status"]
    assert isinstance(body["package_condition"], str) and body["package_condition"]
    assert isinstance(body["timestamp"], str) and body["timestamp"]


@pytest.mark.asyncio
async def test_mock_seller_stance_endpoint(async_client):
    """
    Proves seller mock returns the configured negotiation stance.
    The agent reads this to understand whether the seller is willing
    to refund, partially refund, or reject the claim.
    """
    response = await async_client.get(
        f"/mock/seller/{_SELLER_ID}/stance"
    )

    assert response.status_code == 200, (
        f"Expected 200 from /mock/seller/{_SELLER_ID}/stance, "
        f"got {response.status_code}. Body: {response.text}"
    )

    body = response.json()

    assert "stance" in body, (
        "Seller response must contain 'stance' field"
    )
    # counter_offer_inr is nullable — must be present but can be None/null
    assert "counter_offer_inr" in body, (
        "Seller response must contain 'counter_offer_inr' field (nullable)"
    )

    assert isinstance(body["stance"], str) and body["stance"]

    # counter_offer_inr must be a number or null
    coi = body["counter_offer_inr"]
    assert coi is None or isinstance(coi, (int, float)), (
        f"counter_offer_inr must be a number or null, got {type(coi).__name__}"
    )


@pytest.mark.asyncio
async def test_mock_buyer_evidence_endpoint(async_client):
    """
    Proves buyer mock returns the evidence list for a dispute.
    The agent uses this to build the context window for the LLM.
    """
    response = await async_client.get(
        f"/mock/buyer/{_BUYER_ID}/evidence/{_ORDER_ID}"
    )

    assert response.status_code == 200, (
        f"Expected 200 from /mock/buyer/{_BUYER_ID}/evidence/{_ORDER_ID}, "
        f"got {response.status_code}. Body: {response.text}"
    )

    body = response.json()

    assert "evidence" in body, (
        "Buyer evidence response must contain 'evidence' field"
    )
    assert isinstance(body["evidence"], list), (
        f"'evidence' must be a list, got {type(body['evidence']).__name__}"
    )

    # Each evidence item must have type and content fields
    for i, item in enumerate(body["evidence"]):
        assert "type" in item, f"Evidence item {i} missing 'type' field"
        assert "content" in item, f"Evidence item {i} missing 'content' field"


@pytest.mark.asyncio
@pytest.mark.slow
async def test_ondc_mock_scenario_1_full_chain(async_client):
    """
    Proves all 3 mock parties return consistent Scenario 1 data.
    This is the pre-flight check before running the full agent.

    Scenario 1 (Damaged Kurta):
      - logistics_status    == "DELIVERED"
      - package_condition   == "DAMAGED"
      - seller_stance       == "REJECT_REFUND"
    """
    # --- Logistics ---
    logistics_resp = await async_client.get(
        f"/mock/logistics/{_LOGISTICS_ID}/status"
    )
    assert logistics_resp.status_code == 200, (
        f"Logistics mock failed: {logistics_resp.status_code}"
    )
    logistics_body = logistics_resp.json()

    assert logistics_body["status"] == SCENARIO_1["mock_logistics_status"], (
        f"Expected logistics status '{SCENARIO_1['mock_logistics_status']}', "
        f"got '{logistics_body['status']}'"
    )
    assert logistics_body["package_condition"] == SCENARIO_1["mock_package_condition"], (
        f"Expected package_condition '{SCENARIO_1['mock_package_condition']}', "
        f"got '{logistics_body['package_condition']}'"
    )

    # --- Seller ---
    seller_resp = await async_client.get(
        f"/mock/seller/{_SELLER_ID}/stance"
    )
    assert seller_resp.status_code == 200, (
        f"Seller mock failed: {seller_resp.status_code}"
    )
    seller_body = seller_resp.json()

    assert seller_body["stance"] == SCENARIO_1["mock_seller_stance"], (
        f"Expected seller stance '{SCENARIO_1['mock_seller_stance']}', "
        f"got '{seller_body['stance']}'"
    )

    # --- Buyer evidence ---
    buyer_resp = await async_client.get(
        f"/mock/buyer/{_BUYER_ID}/evidence/{_ORDER_ID}"
    )
    assert buyer_resp.status_code == 200, (
        f"Buyer mock failed: {buyer_resp.status_code}"
    )
    buyer_body = buyer_resp.json()

    assert isinstance(buyer_body["evidence"], list)
    assert len(buyer_body["evidence"]) >= 1, (
        "Scenario 1 buyer must have at least 1 evidence item"
    )

    # Cross-check: evidence count must match the canonical scenario
    assert len(buyer_body["evidence"]) == len(SCENARIO_1["evidence"]), (
        f"Expected {len(SCENARIO_1['evidence'])} evidence items, "
        f"got {len(buyer_body['evidence'])}"
    )
