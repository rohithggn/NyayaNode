"""Deterministic mock ONDC party data (no database)."""

import hashlib
from typing import Any

from core.mock_schemas import (
    BuyerProfileResponse,
    LogisticsTrackingResponse,
    ScanEvent,
    SellerOrderResponse,
)

ITEM_VALUE_INR = 499.00
ITEM_NAME = "Cotton Kurta - Blue XL"


def _stable_bucket(key: str, modulo: int) -> int:
    """Return a stable integer bucket in [0, modulo) using MD5."""
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return int(digest, 16) % modulo


def _scan(
    status: str,
    timestamp: str,
    location: str,
) -> ScanEvent:
    return ScanEvent(status=status, timestamp=timestamp, location=location)


def build_logistics_tracking(tracking_id: str) -> LogisticsTrackingResponse:
    """Build a deterministic logistics tracking response for the given ID."""
    preset = _stable_bucket(tracking_id, 4)

    presets: list[dict[str, Any]] = [
        {
            "current_status": "DELIVERED",
            "delivery_timestamp": "2025-01-14T14:30:00Z",
            "delivery_confirmed_by": "OTP",
            "last_scan_location": "Koramangala Hub, Bangalore",
            "package_condition_flag": "INTACT",
            "scan_history": [
                _scan("PICKED_UP", "2025-01-13T08:15:00Z", "Whitefield FC, Bangalore"),
                _scan("IN_TRANSIT", "2025-01-13T18:40:00Z", "Hosur Road Hub, Bangalore"),
                _scan(
                    "OUT_FOR_DELIVERY",
                    "2025-01-14T11:05:00Z",
                    "Koramangala Hub, Bangalore",
                ),
                _scan("DELIVERED", "2025-01-14T14:30:00Z", "Indiranagar, Bangalore"),
            ],
        },
        {
            "current_status": "IN_TRANSIT",
            "delivery_timestamp": None,
            "delivery_confirmed_by": None,
            "last_scan_location": "Andheri East Hub, Mumbai",
            "package_condition_flag": "INTACT",
            "scan_history": [
                _scan("PICKED_UP", "2025-01-13T07:30:00Z", "Bhiwandi FC, Mumbai"),
                _scan("IN_TRANSIT", "2025-01-14T06:20:00Z", "Andheri East Hub, Mumbai"),
                _scan(
                    "OUT_FOR_DELIVERY",
                    "2025-01-14T12:45:00Z",
                    "Bandra Sort Center, Mumbai",
                ),
            ],
        },
        {
            "current_status": "LOST",
            "delivery_timestamp": None,
            "delivery_confirmed_by": None,
            "last_scan_location": "Connaught Place Hub, Delhi",
            "package_condition_flag": "TAMPERED",
            "scan_history": [
                _scan("PICKED_UP", "2025-01-12T09:00:00Z", "Okhla FC, Delhi"),
                _scan("IN_TRANSIT", "2025-01-12T22:10:00Z", "Connaught Place Hub, Delhi"),
                _scan("LOST", "2025-01-13T16:00:00Z", "Karol Bagh, Delhi"),
            ],
        },
        {
            "current_status": "DAMAGED",
            "delivery_timestamp": "2025-01-14T16:45:00Z",
            "delivery_confirmed_by": "PHOTO",
            "last_scan_location": "Salt Lake Hub, Kolkata",
            "package_condition_flag": "DAMAGED",
            "scan_history": [
                _scan("PICKED_UP", "2025-01-13T06:45:00Z", "Howrah FC, Kolkata"),
                _scan("IN_TRANSIT", "2025-01-13T20:30:00Z", "Salt Lake Hub, Kolkata"),
                _scan(
                    "OUT_FOR_DELIVERY",
                    "2025-01-14T13:15:00Z",
                    "Park Street Hub, Kolkata",
                ),
                _scan("DAMAGED", "2025-01-14T16:45:00Z", "Ballygunge, Kolkata"),
            ],
        },
    ]

    data = presets[preset]
    return LogisticsTrackingResponse(
        tracking_id=tracking_id,
        order_id="order_xyz",
        lsp_id="ondc_lsp_007",
        current_status=data["current_status"],
        delivery_timestamp=data["delivery_timestamp"],
        delivery_confirmed_by=data["delivery_confirmed_by"],
        last_scan_location=data["last_scan_location"],
        scan_history=data["scan_history"],
        package_condition_flag=data["package_condition_flag"],
    )


def build_seller_order(seller_id: str, order_id: str) -> SellerOrderResponse:
    """Build a deterministic seller order response."""
    preset = _stable_bucket(f"{seller_id}:{order_id}", 4)

    stances: list[dict[str, Any]] = [
        {"seller_dispute_stance": "REJECT_REFUND", "seller_counter_offer_inr": None},
        {"seller_dispute_stance": "ACCEPT_REFUND", "seller_counter_offer_inr": None},
        {
            "seller_dispute_stance": "PARTIAL_REFUND",
            "seller_counter_offer_inr": round(ITEM_VALUE_INR * 0.5, 2),
        },
        {"seller_dispute_stance": "PENDING_REVIEW", "seller_counter_offer_inr": None},
    ]

    stance = stances[preset]
    return SellerOrderResponse(
        order_id=order_id,
        seller_id=seller_id,
        item_name=ITEM_NAME,
        item_value_inr=ITEM_VALUE_INR,
        packed_at="2025-01-13T09:00:00Z",
        packaging_type="STANDARD_POLY_BAG",
        fragile_flagged=False,
        seller_dispute_stance=stance["seller_dispute_stance"],
        seller_counter_offer_inr=stance["seller_counter_offer_inr"],
    )


def build_buyer_profile(buyer_id: str) -> BuyerProfileResponse:
    """Build a deterministic buyer profile response."""
    preset = _stable_bucket(buyer_id, 3)

    profiles = [
        {
            "name": "Priya Sharma",
            "dispute_history_count": 2,
            "account_age_days": 387,
            "verified_kyc": True,
        },
        {
            "name": "Arjun Mehta",
            "dispute_history_count": 0,
            "account_age_days": 45,
            "verified_kyc": True,
        },
        {
            "name": "Lakshmi Iyer",
            "dispute_history_count": 5,
            "account_age_days": 812,
            "verified_kyc": False,
        },
    ]

    profile = profiles[preset]
    return BuyerProfileResponse(buyer_id=buyer_id, **profile)
