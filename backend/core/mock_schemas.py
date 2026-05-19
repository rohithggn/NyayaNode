"""Pydantic models for mock ONDC party API responses."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

LogisticsStatus = Literal["DELIVERED", "IN_TRANSIT", "LOST", "DAMAGED"]
PackageCondition = Literal["INTACT", "TAMPERED", "DAMAGED"]
DeliveryConfirmation = Literal["OTP", "PHOTO", "SIGNATURE"]
ScanStatus = Literal[
    "PICKED_UP",
    "IN_TRANSIT",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "LOST",
    "DAMAGED",
]
SellerStance = Literal[
    "REJECT_REFUND",
    "ACCEPT_REFUND",
    "PARTIAL_REFUND",
    "PENDING_REVIEW",
]


class ScanEvent(BaseModel):
    """Single logistics scan event."""

    status: str
    timestamp: str
    location: str


class LogisticsTrackingResponse(BaseModel):
    """Mock LSP tracking payload for an ONDC shipment."""

    tracking_id: str
    order_id: str = "order_xyz"
    lsp_id: str = "ondc_lsp_007"
    current_status: LogisticsStatus
    delivery_timestamp: Optional[str] = None
    delivery_confirmed_by: Optional[DeliveryConfirmation] = None
    last_scan_location: str
    scan_history: list[ScanEvent]
    package_condition_flag: PackageCondition


class SellerOrderResponse(BaseModel):
    """Mock seller order details for dispute context."""

    order_id: str
    seller_id: str
    item_name: str
    item_value_inr: float
    packed_at: str
    packaging_type: str = "STANDARD_POLY_BAG"
    fragile_flagged: bool = False
    seller_dispute_stance: SellerStance
    seller_counter_offer_inr: Optional[float] = None


class BuyerProfileResponse(BaseModel):
    """Mock buyer profile for dispute context."""

    buyer_id: str
    name: str
    dispute_history_count: int
    account_age_days: int
    verified_kyc: bool
