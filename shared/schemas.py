"""
shared/schemas.py
=================
Central Pydantic schema definitions for the NyayaNode platform.

WHO USES THIS:
  - Member 1 (Lead AI Architect): imports DisputeRequest, DisputeResponse, AuditEntry
  - Member 3 (Backend / FastAPI): imports all models for API request/response validation
  - Member 5 (QA): imports all models to generate synthetic test cases via .model_json_schema()
  - Member 4 (Frontend): uses the JSON schema to type-check API calls (run `python -m shared.schemas` to print schema)

ONDC Dispute Flow:
  DisputeRequest → ArbitrationState → DisputeResponse

DO NOT modify field names without notifying all members — this is a shared contract.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class DisputeType(str, Enum):
    """ONDC-recognised dispute categories."""
    DAMAGED_ITEM = "DAMAGED_ITEM"
    WRONG_ITEM = "WRONG_ITEM"
    NOT_DELIVERED = "NOT_DELIVERED"
    REFUND_DENIED = "REFUND_DENIED"


class DisputeStatus(str, Enum):
    """Lifecycle status of an arbitration session."""
    PENDING = "PENDING"
    EVIDENCE_COLLECTION = "EVIDENCE_COLLECTION"
    NEGOTIATION = "NEGOTIATION"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    ROLLED_BACK = "ROLLED_BACK"


class DecisionType(str, Enum):
    """Final arbitration outcome."""
    FULL_REFUND = "FULL_REFUND"
    PARTIAL_REFUND = "PARTIAL_REFUND"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


class EvidenceType(str, Enum):
    """Types of evidence a buyer can submit."""
    IMAGE_URL = "image_url"
    TEXT = "text"
    ORDER_ID = "order_id"
    TRACKING_ID = "tracking_id"


class AuditEventType(str, Enum):
    """Discrete events logged in the arbitration audit trail."""
    DISPUTE_INITIATED = "DISPUTE_INITIATED"
    EVIDENCE_COLLECTED = "EVIDENCE_COLLECTED"
    LOGISTICS_QUERIED = "LOGISTICS_QUERIED"
    NEGOTIATION_SENT = "NEGOTIATION_SENT"
    NEGOTIATION_RECEIVED = "NEGOTIATION_RECEIVED"
    DECISION_DRAFTED = "DECISION_DRAFTED"
    DECISION_FINALISED = "DECISION_FINALISED"
    ESCALATED_TO_HUMAN = "ESCALATED_TO_HUMAN"
    ROLLBACK_TRIGGERED = "ROLLBACK_TRIGGERED"
    BUDGET_WARNING = "BUDGET_WARNING"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class EvidenceItem(BaseModel):
    """A single piece of evidence submitted by the buyer."""
    type: EvidenceType
    content: str = Field(..., min_length=1, max_length=8192)
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class LogisticsSnapshot(BaseModel):
    """Tracking data pulled from the logistics provider."""
    logistics_id: str
    carrier: Optional[str] = None
    current_status: Optional[str] = None
    last_location: Optional[str] = None
    estimated_delivery: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    delivery_attempts: int = 0
    raw_response: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}


class NegotiationProposal(BaseModel):
    """A settlement proposal exchanged between arbitrator and seller."""
    proposal_id: str = Field(default_factory=lambda: str(uuid4()))
    proposed_by: str  # "arbitrator" | "seller" | "buyer"
    refund_amount_inr: float = Field(..., ge=0.0)
    reasoning: str
    accepted: Optional[bool] = None
    counter_proposal_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}


class AuditEntry(BaseModel):
    """Immutable audit log entry for every action taken by the arbitrator."""
    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    dispute_id: str
    event_type: AuditEventType
    actor: str = "arbitrator"  # who triggered this event
    description: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    inference_cost_inr: float = Field(default=0.0, ge=0.0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}


class BudgetStatus(BaseModel):
    """Real-time budget consumption tracking (Cascadeflow integration)."""
    dispute_id: str
    budget_cap_inr: float = 5.0
    consumed_inr: float = 0.0
    remaining_inr: float = 5.0
    llm_calls: int = 0
    is_exhausted: bool = False
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}

    @field_validator("remaining_inr", mode="before")
    @classmethod
    def clamp_remaining(cls, v: float) -> float:
        return max(0.0, v)


# ---------------------------------------------------------------------------
# Primary API Contract Models
# ---------------------------------------------------------------------------


class DisputeRequest(BaseModel):
    """
    POST /agents/arbitrate — inbound payload from Member 3's FastAPI backend.
    Member 4 (frontend) constructs this and posts it via the backend proxy.
    """
    dispute_id: str = Field(default_factory=lambda: str(uuid4()))
    buyer_id: str = Field(..., min_length=1, max_length=128)
    seller_id: str = Field(..., min_length=1, max_length=128)
    logistics_id: str = Field(..., min_length=1, max_length=128)
    order_id: str = Field(..., min_length=1, max_length=128)
    dispute_type: DisputeType
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=20)
    dispute_amount_inr: float = Field(..., gt=0.0, le=500_000.0)
    buyer_preferred_language: str = Field(default="en", max_length=10)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}

    @field_validator("dispute_amount_inr")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        return round(v, 2)


class DisputeResponse(BaseModel):
    """
    Response from POST /agents/arbitrate.
    Also returned by GET /agents/dispute/{dispute_id}/status.
    Member 4 renders this in the dispute tracker UI.
    """
    dispute_id: str
    status: DisputeStatus
    decision: DecisionType = DecisionType.PENDING
    refund_amount_inr: float = Field(default=0.0, ge=0.0)
    reasoning: str = ""
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    total_inference_cost_inr: float = Field(default=0.0, ge=0.0)
    hindsight_session_id: Optional[str] = None
    audit_trail: list[AuditEntry] = Field(default_factory=list)
    logistics_snapshot: Optional[LogisticsSnapshot] = None
    negotiation_history: list[NegotiationProposal] = Field(default_factory=list)
    budget_status: Optional[BudgetStatus] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}


class ArbitrationState(BaseModel):
    """
    Internal LangGraph state object — passed between agent nodes.
    Member 1 only. Not exposed via HTTP directly.
    Serialised into Hindsight for multi-week memory persistence.
    """
    dispute_id: str
    request: DisputeRequest
    status: DisputeStatus = DisputeStatus.PENDING
    decision: DecisionType = DecisionType.PENDING
    refund_amount_inr: float = 0.0
    reasoning: str = ""
    confidence_score: float = 0.0

    # Tool outputs
    logistics_snapshot: Optional[LogisticsSnapshot] = None
    processed_evidence: list[dict[str, Any]] = Field(default_factory=list)
    negotiation_history: list[NegotiationProposal] = Field(default_factory=list)

    # Audit + cost tracking
    audit_trail: list[AuditEntry] = Field(default_factory=list)
    budget_status: BudgetStatus = Field(default_factory=lambda: BudgetStatus(dispute_id=""))
    hindsight_session_id: Optional[str] = None

    # Control flow flags
    evidence_sufficient: bool = False
    negotiation_attempted: bool = False
    should_escalate: bool = False
    error_message: Optional[str] = None
    iteration_count: int = 0
    max_iterations: int = 10

    model_config = {"from_attributes": True}

    def to_response(self) -> DisputeResponse:
        """Convert internal state to the public API response model."""
        return DisputeResponse(
            dispute_id=self.dispute_id,
            status=self.status,
            decision=self.decision,
            refund_amount_inr=round(self.refund_amount_inr, 2),
            reasoning=self.reasoning,
            confidence_score=round(self.confidence_score, 4),
            total_inference_cost_inr=round(self.budget_status.consumed_inr, 4),
            hindsight_session_id=self.hindsight_session_id,
            audit_trail=self.audit_trail,
            logistics_snapshot=self.logistics_snapshot,
            negotiation_history=self.negotiation_history,
            budget_status=self.budget_status,
            resolved_at=datetime.utcnow() if self.status in (
                DisputeStatus.RESOLVED, DisputeStatus.ESCALATED
            ) else None,
        )

    def add_audit(
        self,
        event_type: AuditEventType,
        description: str,
        metadata: dict[str, Any] | None = None,
        cost_inr: float = 0.0,
    ) -> None:
        """Convenience method to append an audit entry and update budget."""
        entry = AuditEntry(
            dispute_id=self.dispute_id,
            event_type=event_type,
            description=description,
            metadata=metadata or {},
            inference_cost_inr=cost_inr,
        )
        self.audit_trail.append(entry)
        self.budget_status.consumed_inr = round(
            self.budget_status.consumed_inr + cost_inr, 6
        )
        self.budget_status.remaining_inr = round(
            max(0.0, self.budget_status.budget_cap_inr - self.budget_status.consumed_inr), 6
        )
        if self.budget_status.consumed_inr >= self.budget_status.budget_cap_inr:
            self.budget_status.is_exhausted = True


# ---------------------------------------------------------------------------
# Status polling model (GET /agents/dispute/{id}/status)
# ---------------------------------------------------------------------------


class DisputeStatusResponse(BaseModel):
    """Lightweight status response for frontend polling."""
    dispute_id: str
    status: DisputeStatus
    decision: DecisionType
    refund_amount_inr: float
    confidence_score: float
    total_inference_cost_inr: float
    last_event: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# CLI: print JSON schema for frontend/QA use
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    schemas = {
        "DisputeRequest": DisputeRequest.model_json_schema(),
        "DisputeResponse": DisputeResponse.model_json_schema(),
        "AuditEntry": AuditEntry.model_json_schema(),
    }
    print(json.dumps(schemas, indent=2))
