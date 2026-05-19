"""Agent orchestration bridge — trigger and monitor arbitration runs."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from services.agent_runner import run_and_persist
from services.dispute_service import require_dispute
from services.sse_manager import sse_manager
from services.supabase_client import get_client

logger = logging.getLogger(__name__)

router = APIRouter()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_seconds(started_at_str: str) -> int:
    """Return whole seconds elapsed since started_at (ISO string)."""
    started = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return max(0, int((now - started).total_seconds()))


def _derive_stage(elapsed: int) -> tuple[str, list[str]]:
    """
    Derive current_stage and stages_completed from elapsed seconds.
      0-3s  → EVIDENCE_COLLECTION, []
      3-7s  → NEGOTIATION,         [EVIDENCE_COLLECTION]
      7s+   → DECISION,            [EVIDENCE_COLLECTION, NEGOTIATION]
    """
    if elapsed < 3:
        return "EVIDENCE_COLLECTION", []
    if elapsed < 7:
        return "NEGOTIATION", ["EVIDENCE_COLLECTION"]
    return "DECISION", ["EVIDENCE_COLLECTION", "NEGOTIATION"]


@router.post(
    "/{dispute_id}/arbitrate",
    status_code=status.HTTP_200_OK,
    summary="Trigger agent arbitration for a dispute",
)
async def trigger_arbitration(
    dispute_id: str,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Create an agent_runs row, link it to the dispute, and fire the agent
    as a BackgroundTask. Returns immediately with the run ID.

    Returns 409 if an agent run is already RUNNING for this dispute.
    """
    # Verify dispute exists
    await require_dispute(dispute_id)

    client = await get_client()

    # Check for an existing RUNNING run
    existing = (
        await client.table("agent_runs")
        .select("id, status")
        .eq("dispute_id", dispute_id)
        .eq("status", "RUNNING")
        .limit(1)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail=f"Agent is already RUNNING for dispute {dispute_id}",
        )

    # Create agent_runs row
    now = _utc_now_iso()
    run_resp = (
        await client.table("agent_runs")
        .insert({
            "dispute_id": dispute_id,
            "status": "RUNNING",
            "started_at": now,
        })
        .execute()
    )
    rows = run_resp.data or []
    if not rows:
        raise HTTPException(status_code=500, detail="Failed to create agent run")

    run_id = str(rows[0]["id"])

    # Write agent_run_id back to the dispute
    await (
        client.table("disputes")
        .update({"agent_run_id": run_id, "updated_at": now})
        .eq("id", dispute_id)
        .execute()
    )

    # Fire agent as BackgroundTask
    background_tasks.add_task(run_and_persist, dispute_id, run_id)

    logger.info("Arbitration started: dispute=%s run=%s", dispute_id, run_id)

    return {"agent_run_id": run_id, "status": "STARTED"}


@router.get(
    "/{dispute_id}/agent-status",
    summary="Get latest agent run status for a dispute",
)
async def get_agent_status(dispute_id: str) -> dict[str, Any]:
    """
    Return the latest agent run for a dispute with stage derivation.
    Returns 404 if no run exists.
    """
    client = await get_client()

    run_resp = (
        await client.table("agent_runs")
        .select("id, status, started_at, completed_at")
        .eq("dispute_id", dispute_id)
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = run_resp.data or []
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No agent run found for dispute {dispute_id}",
        )

    run = rows[0]
    run_status: str = run["status"]

    # Elapsed is measured from started_at; for completed runs use completed_at as ceiling
    started_at: str = run["started_at"]
    completed_at: str | None = run.get("completed_at")

    if completed_at:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        ended = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
        elapsed = max(0, int((ended - started).total_seconds()))
    else:
        elapsed = _elapsed_seconds(started_at)

    current_stage, stages_completed = _derive_stage(elapsed)

    return {
        "run_id": str(run["id"]),
        "status": run_status,
        "current_stage": current_stage,
        "stages_completed": stages_completed,
        "elapsed_seconds": elapsed,
    }


async def _event_stream(dispute_id: str, request: Request) -> AsyncGenerator[str, None]:
    """
    Async generator that streams SSE events for a dispute.

    - Yields a 'connected' event immediately.
    - Waits on the queue with a 30s timeout; sends keepalive on timeout.
    - Exits cleanly on 'complete' event or client disconnect.
    """
    queue = await sse_manager.subscribe(dispute_id)
    try:
        # Yield connected event immediately
        yield sse_manager.format_event(
            "connected",
            {"dispute_id": dispute_id, "message": "Stream connected"},
        )

        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            try:
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # Keepalive comment — prevents proxy/browser from closing idle connection
                yield ":\n\n"
                continue
            except asyncio.CancelledError:
                break

            event_type: str = message["event"]
            data: dict = message["data"]
            yield sse_manager.format_event(event_type, data)

            # Close stream after the terminal event
            if event_type == "complete":
                break

    except asyncio.CancelledError:
        pass
    finally:
        await sse_manager.unsubscribe(dispute_id, queue)
        logger.debug("SSE stream closed for dispute=%s", dispute_id)


@router.get(
    "/{dispute_id}/stream",
    summary="Stream real-time dispute events (SSE)",
    # No API key — browser EventSource cannot set custom headers
    include_in_schema=True,
)
async def stream_dispute_events(dispute_id: str, request: Request) -> StreamingResponse:
    """
    Server-Sent Events stream for live dispute progress.

    No X-API-Key required — browser EventSource API cannot send custom headers.
    Connect before triggering /arbitrate to receive all events.
    """
    return StreamingResponse(
        _event_stream(dispute_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
