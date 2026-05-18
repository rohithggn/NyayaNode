"""
shared/schemas.py
Pydantic v2 schema contracts for NyayaNode.
STUB — Member 1 will replace this with the production version.
All tests in qa/unit/test_schemas.py are written against this contract.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

import uuid

from pydantic import BaseModel, field_validator


class DisputeType(str, Enum):
    DAMAGED_ITEM = "DAMAGED_ITEM"
    WRONG_ITEM = "WRONG_ITEM"
    NOT_DELIVERED = "NOT_DELIVERED"
    REFUND_DENIED = "REFUND_DENIED"


class DisputeDecision(str, Enum):
    FULL_REFUND = "FULL_REFUND"
    PARTIAL_REFUND = "PARTIAL_REFUND"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


class DisputeStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


class EvidenceItem(BaseModel):
    type: str
    content: str

    @field_validator("type")
    @classmethod
    def type_must_be_valid(cls, v: str) -> str:
        valid_types = {"text", "image_url", "tracking_data", "document_url"}
        if v not in valid_types:
            raise ValueError(
                f"Evidence type '{v}' is not valid. Must be one of {valid_types}"
            )
        return v


class DisputeRequest(BaseModel):
    buyer_id: str
    seller_id: str
    logistics_id: str
    order_id: str
    dispute_type: DisputeType
    dispute_amount_inr: float
    evidence: list[EvidenceItem]
    description: Optional[str] = None

    @field_validator("dispute_amount_inr")
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("dispute_amount_inr must be greater than 0")
        return v


class DisputeResponse(BaseModel):
    dispute_id: str
    status: DisputeStatus
    decision: Optional[DisputeDecision] = None
    refund_amount_inr: Optional[float] = None
    reasoning: Optional[str] = None
    confidence_score: Optional[float] = None
    total_inference_cost_inr: Optional[float] = None
    hindsight_session_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ModelCall(BaseModel):
    call_id: str
    model: str
    task_type: str
    prompt_tokens: int
    completion_tokens: int
    cost_inr: float
    latency_ms: int


class CascadeflowAudit(BaseModel):
    session_id: str
    dispute_id: str
    budget_inr: float
    total_cost_inr: float
    budget_exhausted: bool
    emergency_mode_triggered: bool
    escalated_to_human: bool
    escalation_reason: Optional[str]
    model_calls: list[ModelCall]
    savings_vs_gpt4o_inr: float
    savings_percent: float
    created_at: datetime
    completed_at: datetime
