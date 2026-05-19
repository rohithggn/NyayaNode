"""
agents/tools/logistics_tool.py
───────────────────────────────
NyayaNode — Logistics Correlation Tool
Fetches shipment tracking data from the logistics service partner (LSP)
and correlates it against the buyer's dispute claim.

Integration points
──────────────────
• Called by  agents/core/arbitrator.py :: _logistics_node()
• Input  : order_id, logistics_id, dispute_type  (from ArbitrationState)
• Output : dict  merged into ArbitrationState.logistics_report
• LLM    : 8b model (cheap classification) via budget_harness.gate_llm_call()

Mock mode (default):
  LOGISTICS_BACKEND=mock   ← default
Real ONDC LSP API:
  LOGISTICS_BACKEND=real   ← Member 6 fills _RealLogisticsClient
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ── Enums ─────────────────────────────────────────────────────────────────────

class ShipmentStatus(str, Enum):
    PICKUP_PENDING    = "PICKUP_PENDING"
    IN_TRANSIT        = "IN_TRANSIT"
    OUT_FOR_DELIVERY  = "OUT_FOR_DELIVERY"
    DELIVERED         = "DELIVERED"
    DELIVERY_FAILED   = "DELIVERY_FAILED"
    RETURNED          = "RETURNED"
    LOST              = "LOST"

class LogisticsVerdict(str, Enum):
    LSP_AT_FAULT      = "LSP_AT_FAULT"       # Damage / non-delivery by LSP
    SELLER_AT_FAULT   = "SELLER_AT_FAULT"    # Wrong item packed at source
    BUYER_AT_FAULT    = "BUYER_AT_FAULT"     # False claim, already delivered
    INCONCLUSIVE      = "INCONCLUSIVE"       # Not enough data

# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class TrackingEvent:
    timestamp: str
    location: str
    status: str
    description: str
    verified: bool = True

@dataclass
class LogisticsReport:
    session_id: str
    order_id: str
    logistics_id: str
    shipment_status: ShipmentStatus
    verdict: LogisticsVerdict
    confidence: float
    delivery_attempts: int
    last_location: str
    estimated_delivery: str
    actual_delivery: str | None
    tracking_events: list[TrackingEvent]
    anomalies: list[str]            # anything unusual in the chain
    lsp_liability_score: float      # 0.0 = no fault, 1.0 = full fault
    notes: str
    analyzed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "order_id": self.order_id,
            "logistics_id": self.logistics_id,
            "shipment_status": self.shipment_status.value,
            "verdict": self.verdict.value,
            "confidence": self.confidence,
            "delivery_attempts": self.delivery_attempts,
            "last_location": self.last_location,
            "estimated_delivery": self.estimated_delivery,
            "actual_delivery": self.actual_delivery,
            "anomalies": self.anomalies,
            "lsp_liability_score": self.lsp_liability_score,
            "notes": self.notes,
            "analyzed_at": self.analyzed_at,
        }

# ── Mock Scenarios ─────────────────────────────────────────────────────────────

def _make_events(scenario: str) -> list[TrackingEvent]:
    base = datetime.now(timezone.utc) - timedelta(days=3)
    fmt = lambda d: d.isoformat()

    if scenario == "damaged":
        return [
            TrackingEvent(fmt(base),              "Mumbai Hub",         "PICKUP",          "Package picked up from seller"),
            TrackingEvent(fmt(base + timedelta(hours=6)),  "Mumbai Sorting",    "IN_TRANSIT",      "Sorted at hub"),
            TrackingEvent(fmt(base + timedelta(hours=18)), "Pune Transit Hub",  "IN_TRANSIT",      "Transferred to inter-city transport"),
            TrackingEvent(fmt(base + timedelta(days=1)),   "Bengaluru Hub",     "IN_TRANSIT",      "⚠️ Package flagged — weight discrepancy detected"),
            TrackingEvent(fmt(base + timedelta(days=2)),   "Mysuru Delivery",   "OUT_FOR_DELIVERY","Out for final delivery"),
            TrackingEvent(fmt(base + timedelta(days=2, hours=4)), "Buyer Address", "DELIVERED",    "Delivered — signature obtained"),
        ]
    if scenario == "not_delivered":
        return [
            TrackingEvent(fmt(base),              "Delhi Hub",          "PICKUP",          "Package picked up"),
            TrackingEvent(fmt(base + timedelta(hours=8)),  "Delhi Sorting",     "IN_TRANSIT",      "Sorted"),
            TrackingEvent(fmt(base + timedelta(days=1)),   "Noida Delivery",    "OUT_FOR_DELIVERY","Out for delivery"),
            TrackingEvent(fmt(base + timedelta(days=1, hours=5)), "Sector 62, Noida", "DELIVERED", "⚠️ Marked delivered — no GPS proof"),
        ]
    if scenario == "wrong_item":
        return [
            TrackingEvent(fmt(base),              "Chennai Hub",        "PICKUP",          "Package picked up — weight: 0.3 kg (ordered: 1.2 kg)"),
            TrackingEvent(fmt(base + timedelta(hours=10)), "Chennai Sorting",   "IN_TRANSIT",      "Sorted"),
            TrackingEvent(fmt(base + timedelta(days=1)),   "Hyderabad Hub",     "IN_TRANSIT",      "In transit"),
            TrackingEvent(fmt(base + timedelta(days=2)),   "Buyer Address",     "DELIVERED",       "Delivered"),
        ]
    # Generic
    return [
        TrackingEvent(fmt(base),              "Origin Hub",         "PICKUP",    "Package picked up"),
        TrackingEvent(fmt(base + timedelta(days=1)), "Transit Hub", "IN_TRANSIT","In transit"),
        TrackingEvent(fmt(base + timedelta(days=2)), "Destination", "DELIVERED", "Delivered"),
    ]

_MOCK_SCENARIOS: dict[str, dict] = {
    "DAMAGED_ITEM": {
        "shipment_status": ShipmentStatus.DELIVERED,
        "verdict": LogisticsVerdict.LSP_AT_FAULT,
        "confidence": 0.82,
        "delivery_attempts": 1,
        "anomalies": ["Weight discrepancy at Bengaluru hub — possible drop/crush event"],
        "lsp_liability_score": 0.85,
        "notes": "Tracking shows weight anomaly consistent with physical mishandling en route.",
        "scenario": "damaged",
    },
    "NOT_DELIVERED": {
        "shipment_status": ShipmentStatus.DELIVERED,   # LSP claims delivered
        "verdict": LogisticsVerdict.LSP_AT_FAULT,
        "confidence": 0.74,
        "delivery_attempts": 1,
        "anomalies": [
            "Delivery marked complete without GPS photo proof",
            "Delivery GPS coordinates 2.3 km from buyer's registered address",
        ],
        "lsp_liability_score": 0.78,
        "notes": "GPS mismatch strongly suggests misdelivery or false delivery scan.",
        "scenario": "not_delivered",
    },
    "WRONG_ITEM": {
        "shipment_status": ShipmentStatus.DELIVERED,
        "verdict": LogisticsVerdict.SELLER_AT_FAULT,
        "confidence": 0.89,
        "delivery_attempts": 1,
        "anomalies": ["Pickup weight (0.3 kg) does not match seller's declared weight (1.2 kg)"],
        "lsp_liability_score": 0.10,
        "notes": "Weight mismatch at pickup — wrong item packed by seller, not a logistics error.",
        "scenario": "wrong_item",
    },
    "QUALITY_ISSUE": {
        "shipment_status": ShipmentStatus.DELIVERED,
        "verdict": LogisticsVerdict.INCONCLUSIVE,
        "confidence": 0.55,
        "delivery_attempts": 1,
        "anomalies": [],
        "lsp_liability_score": 0.15,
        "notes": "No logistics anomaly detected. Quality issue likely a seller/manufacturing fault.",
        "scenario": "generic",
    },
}


class _MockLogisticsClient:
    async def correlate(
        self,
        session_id: str,
        order_id: str,
        logistics_id: str,
        dispute_type: str,
    ) -> LogisticsReport:
        await asyncio.sleep(random.uniform(0.05, 0.12))

        template = _MOCK_SCENARIOS.get(dispute_type, {
            "shipment_status": ShipmentStatus.DELIVERED,
            "verdict": LogisticsVerdict.INCONCLUSIVE,
            "confidence": 0.50,
            "delivery_attempts": 1,
            "anomalies": [],
            "lsp_liability_score": 0.20,
            "notes": "No anomalies found.",
            "scenario": "generic",
        })

        now = datetime.now(timezone.utc)
        return LogisticsReport(
            session_id=session_id,
            order_id=order_id,
            logistics_id=logistics_id,
            shipment_status=template["shipment_status"],
            verdict=template["verdict"],
            confidence=template["confidence"],
            delivery_attempts=template["delivery_attempts"],
            last_location="Buyer Address",
            estimated_delivery=(now - timedelta(days=2)).strftime("%Y-%m-%d"),
            actual_delivery=(now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            tracking_events=_make_events(template["scenario"]),
            anomalies=list(template["anomalies"]),
            lsp_liability_score=template["lsp_liability_score"],
            notes=template["notes"],
        )


# ── Real Client Stub (TODO: Member 6) ─────────────────────────────────────────

class _RealLogisticsClient:
    """
    TODO (Member 6): Connect to live ONDC LSP tracking API.

    Steps:
    1. Set LOGISTICS_BACKEND=real and ONDC_LSP_API_KEY in .env
    2. Implement correlate() calling the real tracking endpoint
    3. Map response fields to LogisticsReport
    4. Run: PYTHONPATH=. python agents/tools/logistics_tool.py  — all tests must pass
    """

    async def correlate(self, session_id, order_id, logistics_id, dispute_type) -> LogisticsReport:
        raise NotImplementedError("Real logistics client not yet implemented.")


# ── Singleton Factory ──────────────────────────────────────────────────────────

_client_instance = None

def _get_client():
    global _client_instance
    if _client_instance is None:
        backend = os.getenv("LOGISTICS_BACKEND", "mock").lower()
        _client_instance = _RealLogisticsClient() if backend == "real" else _MockLogisticsClient()
        logger.info("LogisticsTool initialised with backend=%s", backend)
    return _client_instance


# ── Public Interface ───────────────────────────────────────────────────────────

async def correlate_logistics(
    session_id: str,
    order_id: str,
    logistics_id: str,
    dispute_type: str,
) -> dict[str, Any]:
    """
    Main entry point for logistics_node in arbitrator.py.

    Returns dict for merging into ArbitrationState:
        state.logistics_report    = result["report"]
        state.lsp_liability_score = result["lsp_liability_score"]
    """
    client = _get_client()
    report = await client.correlate(
        session_id=session_id,
        order_id=order_id,
        logistics_id=logistics_id,
        dispute_type=dispute_type,
    )
    return {
        "report": report.to_dict(),
        "verdict": report.verdict.value,
        "lsp_liability_score": report.lsp_liability_score,
        "confidence": report.confidence,
        "anomalies": report.anomalies,
    }


# ── Self-Test ──────────────────────────────────────────────────────────────────

async def _run_tests():
    print("=" * 60)
    print("NyayaNode — Logistics Tool Self-Test")
    print("=" * 60)
    passed = 0

    def ok(label: str, condition: bool, detail: str = ""):
        nonlocal passed
        if condition:
            print(f"✅ [{passed+1}] {label}")
            passed += 1
        else:
            print(f"❌ [{passed+1}] {label} — {detail}")

    r1 = await correlate_logistics("s1", "order_001", "lsp_007", "DAMAGED_ITEM")
    ok("DAMAGED_ITEM → LSP_AT_FAULT", r1["verdict"] == "LSP_AT_FAULT", r1["verdict"])

    r2 = await correlate_logistics("s2", "order_002", "lsp_007", "WRONG_ITEM")
    ok("WRONG_ITEM → SELLER_AT_FAULT", r2["verdict"] == "SELLER_AT_FAULT", r2["verdict"])

    r3 = await correlate_logistics("s3", "order_003", "lsp_007", "NOT_DELIVERED")
    ok("NOT_DELIVERED → anomalies detected", len(r3["anomalies"]) > 0, str(r3["anomalies"]))

    r4 = await correlate_logistics("s4", "order_004", "lsp_007", "QUALITY_ISSUE")
    ok("QUALITY_ISSUE → low LSP liability", r4["lsp_liability_score"] < 0.3, str(r4["lsp_liability_score"]))

    r5 = await correlate_logistics("s5", "order_005", "lsp_007", "UNKNOWN_TYPE")
    ok("Unknown type → graceful fallback (no crash)", "verdict" in r5)

    r6 = await correlate_logistics("s6", "order_006", "lsp_007", "DAMAGED_ITEM")
    ok("Report dict has all required keys", all(
        k in r6 for k in ["report", "verdict", "lsp_liability_score", "confidence", "anomalies"]
    ))

    print("-" * 60)
    print(f"{'🎉 ALL LOGISTICS TOOL TESTS PASSED' if passed == 6 else f'⚠️  {passed}/6 passed'}")
    return passed == 6


if __name__ == "__main__":
    asyncio.run(_run_tests())
