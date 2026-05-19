"""Dispute audit trail and cascadeflow audit endpoints."""

from typing import Any

from fastapi import APIRouter

from services.dispute_service import require_dispute
from services.supabase_client import get_client

router = APIRouter()


@router.get(
    "/{dispute_id}/audit-trail",
    summary="Get chronological audit trail for a dispute",
)
async def get_audit_trail(dispute_id: str) -> dict[str, Any]:
    """
    Return all audit events for a dispute ordered oldest-first.
    Returns 404 if the dispute does not exist.
    """
    await require_dispute(dispute_id)

    client = await get_client()
    resp = (
        await client.table("audit_events")
        .select("id, event_type, actor, payload, timestamp")
        .eq("dispute_id", dispute_id)
        .order("timestamp", desc=False)
        .execute()
    )
    events = resp.data or []

    return {
        "dispute_id": dispute_id,
        "events": events,
        "total": len(events),
    }


@router.get(
    "/{dispute_id}/cascadeflow-audit",
    summary="Get cascadeflow cost/audit JSON from the latest agent run",
)
async def get_cascadeflow_audit(dispute_id: str) -> dict[str, Any]:
    """
    Return the cascadeflow_audit JSONB from the most recent agent run.
    Returns a graceful NO_RUN response if no agent run exists yet.
    """
    await require_dispute(dispute_id)

    client = await get_client()
    resp = (
        await client.table("agent_runs")
        .select("id, status, started_at, completed_at, cascadeflow_audit")
        .eq("dispute_id", dispute_id)
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = resp.data or []

    if not rows or rows[0].get("cascadeflow_audit") is None:
        return {"status": "NO_RUN", "message": "Agent has not run yet"}

    return rows[0]["cascadeflow_audit"]
