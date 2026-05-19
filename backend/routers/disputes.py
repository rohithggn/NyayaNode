"""Dispute CRUD and lifecycle routes."""

import logging

from fastapi import APIRouter, BackgroundTasks, Query, status

from core.dispute_schemas import (
    CreateDisputeRequest,
    DisputeListResponse,
    DisputeResponse,
    DisputeStatus,
    StatusPatchRequest,
)
from services.agent_runner import run_and_persist
from services.dispute_service import (
    create_dispute,
    list_disputes,
    patch_dispute_status,
    require_dispute,
    row_to_dispute,
)
from services.supabase_client import get_client

logger = logging.getLogger(__name__)

router = APIRouter()


async def _run_agent_background(dispute_id: str) -> None:
    """Create an agent_runs row and execute run_and_persist as a background task."""
    from datetime import datetime, timezone
    try:
        client = await get_client()
        now = datetime.now(timezone.utc).isoformat()
        run_resp = (
            await client.table("agent_runs")
            .insert({"dispute_id": dispute_id, "status": "RUNNING", "started_at": now})
            .execute()
        )
        rows = run_resp.data or []
        if not rows:
            logger.error("Failed to create agent_runs row for dispute %s", dispute_id)
            return
        run_id = str(rows[0]["id"])
        await client.table("disputes").update({"agent_run_id": run_id, "updated_at": now}).eq("id", dispute_id).execute()
        await run_and_persist(dispute_id, run_id)
    except Exception:
        logger.exception("Background agent setup failed for dispute %s", dispute_id)


@router.post(
    "",
    response_model=DisputeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create dispute",
)
async def create_dispute_endpoint(
    body: CreateDisputeRequest,
    background_tasks: BackgroundTasks,
) -> DisputeResponse:
    """
    Open a new dispute, store evidence, log an audit event, and queue the agent stub.

    Returns immediately with status PENDING while the agent runs in the background.
    """
    dispute = await create_dispute(body)
    background_tasks.add_task(_run_agent_background, str(dispute.id))
    return dispute


@router.get(
    "/{dispute_id}",
    response_model=DisputeResponse,
    summary="Get dispute by ID",
)
async def get_dispute_endpoint(dispute_id: str) -> DisputeResponse:
    """Return a single dispute by UUID."""
    row = await require_dispute(dispute_id)
    return row_to_dispute(row)


@router.get(
    "",
    response_model=DisputeListResponse,
    summary="List disputes",
)
async def list_disputes_endpoint(
    status: DisputeStatus | None = Query(default=None, description="Filter by status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DisputeListResponse:
    """Return a paginated list of disputes, optionally filtered by status."""
    data, total = await list_disputes(status=status, limit=limit, offset=offset)
    return DisputeListResponse(data=data, total=total, limit=limit, offset=offset)


@router.patch(
    "/{dispute_id}/status",
    response_model=DisputeResponse,
    summary="Update dispute status",
)
async def patch_dispute_status_endpoint(
    dispute_id: str,
    body: StatusPatchRequest,
) -> DisputeResponse:
    """
    Apply a legal status transition and record an audit event.

    ESCALATED is allowed from any current status. Other transitions follow the
    dispute lifecycle rules.
    """
    return await patch_dispute_status(
        dispute_id,
        target_status=body.status,
        reason=body.reason,
    )
