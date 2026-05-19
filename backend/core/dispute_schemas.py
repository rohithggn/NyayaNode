"""Pydantic models for dispute API requests and responses."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

DisputeType = Literal["DAMAGED_ITEM", "WRONG_ITEM", "NOT_DELIVERED", "REFUND_DENIED"]
DisputeStatus = Literal[
    "PENDING",
    "EVIDENCE_COLLECTION",
    "NEGOTIATION",
    "RESOLVED",
    "ESCALATED",
]
EvidenceType = Literal["text", "image_url", "tracking_data"]


class EvidenceInput(BaseModel):
    """Evidence submitted when opening a dispute."""

    type: EvidenceType = Field(description="Evidence type: text, image_url, or tracking_data")
    content: str = Field(min_length=1)


class CreateDisputeRequest(BaseModel):
    """Request body for POST /api/v1/disputes."""

    buyer_id: str = Field(min_length=1)
    seller_id: str = Field(min_length=1)
    logistics_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    dispute_type: DisputeType
    evidence: list[EvidenceInput] = Field(default_factory=list)
    dispute_amount_inr: Decimal = Field(gt=0, decimal_places=2)

    @field_validator("dispute_amount_inr", mode="before")
    @classmethod
    def coerce_amount(cls, value: Any) -> Any:
        return Decimal(str(value))


class StatusPatchRequest(BaseModel):
    """Request body for PATCH /api/v1/disputes/{id}/status."""

    status: DisputeStatus
    reason: Optional[str] = None


class DisputeResponse(BaseModel):
    """Full dispute row returned by the API."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    buyer_id: str
    seller_id: str
    logistics_id: str
    order_id: str
    dispute_type: str
    status: str
    decision: Optional[str] = None
    dispute_amount_inr: Decimal
    refund_amount_inr: Optional[Decimal] = None
    reasoning: Optional[str] = None
    confidence_score: Optional[Decimal] = None
    hindsight_session_id: Optional[str] = None
    total_cost_inr: Optional[Decimal] = None
    budget_inr: Optional[Decimal] = None
    escalated_to_human: bool = False
    agent_run_id: Optional[UUID] = None


class DisputeListResponse(BaseModel):
    """Paginated list of disputes."""

    data: list[DisputeResponse]
    total: int
    limit: int
    offset: int
