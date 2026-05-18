"""
qa/unit/test_schemas.py
Schema contract tests for NyayaNode — DEPLOYMENT BLOCKERS.
These tests define the interface contract between all members.
If any test here fails, the build must not proceed to staging.
"""

import json
import os
import sys

# Ensure the monorepo root is on sys.path so both `shared` and `qa` are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from shared.schemas import (
    CascadeflowAudit,
    DisputeDecision,
    DisputeRequest,
    DisputeResponse,
    DisputeStatus,
    DisputeType,
    EvidenceItem,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")

_NOW = datetime.now(timezone.utc)

_VALID_EVIDENCE = [
    {"type": "text", "content": "Package arrived damaged."},
]

_VALID_REQUEST_PAYLOAD = {
    "buyer_id": "ondc_buyer_001",
    "seller_id": "ondc_seller_042",
    "logistics_id": "ondc_lsp_007",
    "order_id": "order_demo_001",
    "dispute_type": "DAMAGED_ITEM",
    "dispute_amount_inr": 499.0,
    "evidence": _VALID_EVIDENCE,
    "description": "Kurta arrived with a large stain.",
}

_VALID_RESPONSE_PAYLOAD = {
    "dispute_id": "fixture-dispute-0001-0000-0000-000000000001",
    "status": "RESOLVED",
    "decision": "FULL_REFUND",
    "refund_amount_inr": 499.0,
    "reasoning": "Logistics confirms damage.",
    "confidence_score": 0.92,
    "total_inference_cost_inr": 3.21,
    "hindsight_session_id": "cf_session_demo_001",
    "created_at": _NOW,
    "updated_at": _NOW,
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_dispute_request_all_fields_present():
    """
    Proves DisputeRequest can be instantiated with all required fields and raises
    no ValidationError. This is the deployment contract between Member 3 (backend)
    and Member 1 (agent).
    """
    req = DisputeRequest.model_validate(_VALID_REQUEST_PAYLOAD)

    assert req.buyer_id == "ondc_buyer_001"
    assert req.seller_id == "ondc_seller_042"
    assert req.logistics_id == "ondc_lsp_007"
    assert req.order_id == "order_demo_001"
    assert req.dispute_type == DisputeType.DAMAGED_ITEM
    assert req.dispute_amount_inr == 499.0
    assert len(req.evidence) == 1
    assert req.evidence[0].type == "text"
    assert req.description == "Kurta arrived with a large stain."


def test_dispute_response_all_fields_present():
    """
    Proves DisputeResponse can be instantiated and that the status field accepts
    a valid DisputeStatus enum value. If this fails, the frontend (Member 4) will
    receive malformed responses.
    """
    resp = DisputeResponse.model_validate(_VALID_RESPONSE_PAYLOAD)

    assert resp.dispute_id == "fixture-dispute-0001-0000-0000-000000000001"
    assert resp.status == DisputeStatus.RESOLVED
    assert resp.decision == DisputeDecision.FULL_REFUND
    assert resp.refund_amount_inr == 499.0
    assert resp.confidence_score == 0.92
    assert resp.total_inference_cost_inr == 3.21
    assert resp.hindsight_session_id == "cf_session_demo_001"
    assert isinstance(resp.created_at, datetime)
    assert isinstance(resp.updated_at, datetime)


def test_dispute_type_enum_values():
    """
    Proves DisputeType has EXACTLY 4 values and no others.
    Adding a 5th type without updating all handlers is a bug.
    """
    actual_values = {member.value for member in DisputeType}
    expected_values = {"DAMAGED_ITEM", "WRONG_ITEM", "NOT_DELIVERED", "REFUND_DENIED"}

    assert actual_values == expected_values, (
        f"DisputeType enum mismatch.\n"
        f"  Expected: {sorted(expected_values)}\n"
        f"  Got:      {sorted(actual_values)}"
    )


def test_dispute_decision_enum_values():
    """
    Proves DisputeDecision has EXACTLY 4 values and no others.
    The frontend renders different UI for each — unknown values would cause a
    render crash.
    """
    actual_values = {member.value for member in DisputeDecision}
    expected_values = {"FULL_REFUND", "PARTIAL_REFUND", "REJECTED", "PENDING"}

    assert actual_values == expected_values, (
        f"DisputeDecision enum mismatch.\n"
        f"  Expected: {sorted(expected_values)}\n"
        f"  Got:      {sorted(actual_values)}"
    )


def test_evidence_item_type_validation():
    """
    Proves EvidenceItem rejects invalid types and accepts valid ones.
    Malformed evidence would corrupt the agent's context window.
    """
    # Invalid type must raise
    with pytest.raises(ValidationError) as exc_info:
        EvidenceItem(type="random_garbage", content="some content")
    assert "random_garbage" in str(exc_info.value)

    # All valid types must be accepted without error
    for valid_type in ("text", "image_url", "tracking_data", "document_url"):
        item = EvidenceItem(type=valid_type, content="some content")
        assert item.type == valid_type


def test_dispute_request_negative_amount_rejected():
    """
    Proves the schema rejects economically nonsensical disputes.
    A negative dispute amount would corrupt the refund math.
    """
    base = {**_VALID_REQUEST_PAYLOAD}

    # Negative amount must raise
    with pytest.raises(ValidationError) as exc_info:
        DisputeRequest.model_validate({**base, "dispute_amount_inr": -100.0})
    assert "dispute_amount_inr" in str(exc_info.value)

    # Zero amount must also raise
    with pytest.raises(ValidationError) as exc_info:
        DisputeRequest.model_validate({**base, "dispute_amount_inr": 0.0})
    assert "dispute_amount_inr" in str(exc_info.value)


def test_cascadeflow_audit_schema():
    """
    Proves the CascadeflowAudit schema parses the fixture file without error.
    This is the integration contract between Member 2 (Cascadeflow) and
    Member 4 (frontend dashboard).
    """
    fixture_path = os.path.join(_FIXTURES_DIR, "cascadeflow_sample.json")
    assert os.path.exists(fixture_path), (
        f"Fixture file not found: {fixture_path}. "
        "Run Prompt 1 setup to generate qa/fixtures/."
    )

    with open(fixture_path, encoding="utf-8") as fh:
        data = json.load(fh)

    audit = CascadeflowAudit.model_validate(data)

    assert len(audit.model_calls) == 3, (
        f"Expected 3 model_calls, got {len(audit.model_calls)}"
    )
    assert audit.budget_exhausted is False
    assert audit.total_cost_inr == pytest.approx(3.21, rel=1e-6)
    assert audit.session_id == "cf_session_demo_001"
    assert audit.dispute_id == "fixture-dispute-0001-0000-0000-000000000001"
    assert audit.escalated_to_human is False
    assert audit.escalation_reason is None
