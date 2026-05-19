"""
Seed script — inserts 5 realistic disputes into the NyayaNode database.

Run from the backend/ directory:
    python seed_data.py

Idempotent: checks order_id before inserting to avoid duplicates.
"""

import asyncio
import sys
from datetime import datetime, timezone

import env_loader  # noqa: F401 — loads backend/.env

from services.supabase_client import get_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Seed data definitions
# ---------------------------------------------------------------------------

DISPUTES = [
    {
        "order_id": "order_dmg_001",
        "buyer_id": "ondc_buyer_001",
        "seller_id": "ondc_seller_042",
        "logistics_id": "ondc_lsp_007",
        "dispute_type": "DAMAGED_ITEM",
        "dispute_amount_inr": 499.00,
        "status": "RESOLVED",
        "decision": "FULL_REFUND",
        "refund_amount_inr": 499.00,
        "confidence_score": 0.95,
        "reasoning": "Logistics confirmed damage during transit; full refund mandated",
        "escalated_to_human": False,
        "evidence": [
            {"type": "text", "content": "Box arrived completely crushed on delivery"},
            {"type": "tracking_data", "content": "TRK001234"},
        ],
        "audit_events": [
            ("DISPUTE_CREATED", "system", {"order_id": "order_dmg_001", "dispute_type": "DAMAGED_ITEM"}),
            ("AGENT_STARTED", "agent", {"stage": "EVIDENCE_COLLECTION"}),
            ("AGENT_COMPLETED", "agent", {"decision": "FULL_REFUND", "confidence_score": 0.95}),
        ],
    },
    {
        "order_id": "order_ndl_002",
        "buyer_id": "ondc_buyer_002",
        "seller_id": "ondc_seller_015",
        "logistics_id": "ondc_lsp_003",
        "dispute_type": "NOT_DELIVERED",
        "dispute_amount_inr": 1299.00,
        "status": "RESOLVED",
        "decision": "REJECTED",
        "refund_amount_inr": 0.00,
        "confidence_score": 0.88,
        "reasoning": "Logistics confirmed OTP-verified delivery at buyer address",
        "escalated_to_human": False,
        "evidence": [
            {"type": "text", "content": "I never received my package"},
            {"type": "tracking_data", "content": "TRK002345"},
        ],
        "audit_events": [
            ("DISPUTE_CREATED", "system", {"order_id": "order_ndl_002", "dispute_type": "NOT_DELIVERED"}),
            ("AGENT_STARTED", "agent", {"stage": "EVIDENCE_COLLECTION"}),
            ("AGENT_COMPLETED", "agent", {"decision": "REJECTED", "confidence_score": 0.88}),
        ],
    },
    {
        "order_id": "order_wrng_003",
        "buyer_id": "ondc_buyer_003",
        "seller_id": "ondc_seller_028",
        "logistics_id": "ondc_lsp_011",
        "dispute_type": "WRONG_ITEM",
        "dispute_amount_inr": 799.00,
        "status": "RESOLVED",
        "decision": "PARTIAL_REFUND",
        "refund_amount_inr": 400.00,
        "confidence_score": 0.78,
        "reasoning": "Seller offered partial refund; accepted by arbitrator",
        "escalated_to_human": False,
        "evidence": [
            {"type": "text", "content": "Received blue kurta, ordered red kurta"},
            {"type": "image_url", "content": "https://example.com/wrong-item.jpg"},
        ],
        "audit_events": [
            ("DISPUTE_CREATED", "system", {"order_id": "order_wrng_003", "dispute_type": "WRONG_ITEM"}),
            ("AGENT_STARTED", "agent", {"stage": "NEGOTIATION"}),
            ("AGENT_COMPLETED", "agent", {"decision": "PARTIAL_REFUND", "confidence_score": 0.78}),
        ],
    },
    {
        "order_id": "order_rfd_004",
        "buyer_id": "ondc_buyer_004",
        "seller_id": "ondc_seller_033",
        "logistics_id": "ondc_lsp_005",
        "dispute_type": "REFUND_DENIED",
        "dispute_amount_inr": 249.00,
        "status": "RESOLVED",
        "decision": "FULL_REFUND",
        "refund_amount_inr": 249.00,
        "confidence_score": 0.91,
        "reasoning": "Seller confirmed receipt of return; refund mandated",
        "escalated_to_human": False,
        "evidence": [
            {"type": "text", "content": "Item returned 5 days ago, no refund processed"},
        ],
        "audit_events": [
            ("DISPUTE_CREATED", "system", {"order_id": "order_rfd_004", "dispute_type": "REFUND_DENIED"}),
            ("AGENT_STARTED", "agent", {"stage": "EVIDENCE_COLLECTION"}),
            ("AGENT_COMPLETED", "agent", {"decision": "FULL_REFUND", "confidence_score": 0.91}),
        ],
    },
    {
        "order_id": "order_esc_005",
        "buyer_id": "ondc_buyer_005",
        "seller_id": "ondc_seller_099",
        "logistics_id": "ondc_lsp_020",
        "dispute_type": "DAMAGED_ITEM",
        "dispute_amount_inr": 8999.00,
        "status": "ESCALATED",
        "decision": "PENDING",
        "refund_amount_inr": None,
        "confidence_score": 0.41,
        "reasoning": "High-value dispute with ambiguous evidence; escalated to human arbitrator",
        "escalated_to_human": True,
        "evidence": [
            {"type": "text", "content": "Expensive laptop arrived with cracked screen"},
            {"type": "image_url", "content": "https://example.com/cracked-screen.jpg"},
        ],
        "audit_events": [
            ("DISPUTE_CREATED", "system", {"order_id": "order_esc_005", "dispute_type": "DAMAGED_ITEM"}),
            ("AGENT_STARTED", "agent", {"stage": "EVIDENCE_COLLECTION"}),
            ("ESCALATION_TRIGGERED", "agent", {"confidence_score": 0.41, "reason": "low_confidence"}),
        ],
    },
]


async def seed() -> None:
    client = await get_client()
    seeded = 0

    for spec in DISPUTES:
        order_id = spec["order_id"]

        # Idempotency check — skip if order_id already exists
        existing = (
            await client.table("disputes")
            .select("id")
            .eq("order_id", order_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            print(f"  skip (exists): {order_id}")
            continue

        now = _now()

        # Insert dispute row
        dispute_row = {
            "buyer_id": spec["buyer_id"],
            "seller_id": spec["seller_id"],
            "logistics_id": spec["logistics_id"],
            "order_id": order_id,
            "dispute_type": spec["dispute_type"],
            "dispute_amount_inr": spec["dispute_amount_inr"],
            "status": spec["status"],
            "decision": spec["decision"],
            "refund_amount_inr": spec["refund_amount_inr"],
            "confidence_score": spec["confidence_score"],
            "reasoning": spec["reasoning"],
            "escalated_to_human": spec["escalated_to_human"],
            "updated_at": now,
        }

        insert_resp = await client.table("disputes").insert(dispute_row).execute()
        rows = insert_resp.data or []
        if not rows:
            print(f"  ERROR: failed to insert dispute {order_id}", file=sys.stderr)
            continue

        dispute_id = str(rows[0]["id"])

        # Insert evidence rows
        evidence_records = [
            {
                "dispute_id": dispute_id,
                "submitted_by": "buyer",
                "evidence_type": ev["type"],
                "content": ev["content"],
            }
            for ev in spec["evidence"]
        ]
        await client.table("evidence").insert(evidence_records).execute()

        # Insert audit events
        audit_records = [
            {
                "dispute_id": dispute_id,
                "event_type": event_type,
                "actor": actor,
                "payload": payload,
            }
            for event_type, actor, payload in spec["audit_events"]
        ]
        await client.table("audit_events").insert(audit_records).execute()

        print(f"  seeded: {order_id} → {dispute_id}")
        seeded += 1

    print(f"Seeded {seeded} disputes successfully")


if __name__ == "__main__":
    asyncio.run(seed())
