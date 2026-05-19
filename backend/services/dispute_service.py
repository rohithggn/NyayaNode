"""Dispute persistence, audit logging, and status transition rules."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException

from core.dispute_schemas import CreateDisputeRequest, DisputeResponse, EvidenceInput
from services.supabase_client import get_client

LEGAL_TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("PENDING", "EVIDENCE_COLLECTION"),
        ("EVIDENCE_COLLECTION", "NEGOTIATION"),
        ("NEGOTIATION", "RESOLVED"),
        ("NEGOTIATION", "ESCALATED"),
    }
)


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO format for Postgres."""
    return datetime.now(timezone.utc).isoformat()


def can_transition(current: str, target: str) -> bool:
    """Return True if the status change is allowed."""
    if current == target:
        return False
    if target == "ESCALATED":
        return True
    return (current, target) in LEGAL_TRANSITIONS


def row_to_dispute(row: dict[str, Any]) -> DisputeResponse:
    """Map a Supabase/PostgREST row dict to a DisputeResponse."""
    return DisputeResponse.model_validate(row)


async def write_audit_event(
    dispute_id: str,
    event_type: str,
    actor: str,
    payload: Optional[dict[str, Any]] = None,
) -> None:
    """Insert an audit_events row for a dispute."""
    client = await get_client()
    await (
        client.table("audit_events")
        .insert(
            {
                "dispute_id": dispute_id,
                "event_type": event_type,
                "actor": actor,
                "payload": payload or {},
            }
        )
        .execute()
    )


async def get_dispute_row(dispute_id: str) -> Optional[dict[str, Any]]:
    """Fetch a single dispute by UUID or return None."""
    client = await get_client()
    response = (
        await client.table("disputes").select("*").eq("id", dispute_id).limit(1).execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


async def require_dispute(dispute_id: str) -> dict[str, Any]:
    """Fetch dispute or raise 404 RFC 7807 via HTTPException."""
    row = await get_dispute_row(dispute_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found")
    return row


async def create_dispute(body: CreateDisputeRequest) -> DisputeResponse:
    """Insert dispute and evidence rows; write DISPUTE_CREATED audit event."""
    client = await get_client()
    now = utc_now_iso()

    dispute_row = {
        "buyer_id": body.buyer_id,
        "seller_id": body.seller_id,
        "logistics_id": body.logistics_id,
        "order_id": body.order_id,
        "dispute_type": body.dispute_type,
        "status": "PENDING",
        "dispute_amount_inr": float(body.dispute_amount_inr),
        "updated_at": now,
    }

    insert_resp = await client.table("disputes").insert(dispute_row).execute()
    rows = insert_resp.data or []
    if not rows:
        raise HTTPException(status_code=500, detail="Failed to create dispute")

    dispute = rows[0]
    dispute_id = str(dispute["id"])

    if body.evidence:
        await _insert_evidence(dispute_id, body.evidence)

    await write_audit_event(
        dispute_id,
        event_type="DISPUTE_CREATED",
        actor="system",
        payload={
            "order_id": body.order_id,
            "dispute_type": body.dispute_type,
            "evidence_count": len(body.evidence),
        },
    )

    return row_to_dispute(dispute)


async def _insert_evidence(dispute_id: str, items: list[EvidenceInput]) -> None:
    """Bulk-insert evidence rows for a dispute."""
    client = await get_client()
    records = [
        {
            "dispute_id": dispute_id,
            "submitted_by": "buyer",
            "evidence_type": item.type,
            "content": item.content,
        }
        for item in items
    ]
    await client.table("evidence").insert(records).execute()


async def list_disputes(
    status: Optional[str],
    limit: int,
    offset: int,
) -> tuple[list[DisputeResponse], int]:
    """Return paginated disputes and total count."""
    client = await get_client()
    query = client.table("disputes").select("*", count="exact")
    if status:
        query = query.eq("status", status)
    response = await query.order("created_at", desc=True).range(
        offset, offset + limit - 1
    ).execute()

    rows = response.data or []
    total = response.count if response.count is not None else len(rows)
    return [row_to_dispute(row) for row in rows], total


async def patch_dispute_status(
    dispute_id: str,
    target_status: str,
    reason: Optional[str],
) -> DisputeResponse:
    """Validate transition, update dispute, and write audit event."""
    current = await require_dispute(dispute_id)
    current_status = current["status"]

    if not can_transition(current_status, target_status):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Illegal status transition from {current_status} to {target_status}"
            ),
        )

    now = utc_now_iso()
    client = await get_client()
    update_payload: dict[str, Any] = {
        "status": target_status,
        "updated_at": now,
    }
    if target_status == "ESCALATED":
        update_payload["escalated_to_human"] = True

    update_resp = (
        await client.table("disputes")
        .update(update_payload)
        .eq("id", dispute_id)
        .execute()
    )
    rows = update_resp.data or []
    if not rows:
        updated = await get_dispute_row(dispute_id)
        if updated is None:
            raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found")
        row = updated
    else:
        row = rows[0]

    await write_audit_event(
        dispute_id,
        event_type="STATUS_CHANGED",
        actor="system",
        payload={
            "from_status": current_status,
            "to_status": target_status,
            "reason": reason,
        },
    )

    return row_to_dispute(row)
