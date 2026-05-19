"""ONDC network webhook ingress — dispute-raised event receiver."""

import json
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, Request, status
from fastapi.responses import JSONResponse

from core.dispute_schemas import CreateDisputeRequest, EvidenceInput
from core.problem_details import problem_response
from services.agent_runner import run_and_persist
from services.dispute_service import create_dispute
from services.supabase_client import get_client

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# ONDC issue_sub_category → NyayaNode dispute_type mapping
# ---------------------------------------------------------------------------
_SUB_CATEGORY_MAP: dict[str, str] = {
    "ITM01": "WRONG_ITEM",
    "ITM02": "WRONG_ITEM",   # MISSING_ITEM treated as WRONG_ITEM
    "ITM03": "DAMAGED_ITEM",
    "ITM04": "WRONG_ITEM",
    "FLM01": "NOT_DELIVERED",
    "PMT01": "REFUND_DENIED",
}
_DEFAULT_DISPUTE_TYPE = "DAMAGED_ITEM"


def verify_ondc_signature(body: bytes, sig: str) -> bool:
    """
    MOCK: accept any non-empty signature.
    PRODUCTION: verify ED25519 against ONDC registry key.
    """
    logger.warning("ONDC_MOCK_VERIFY: using mock signature verification")
    return sig is not None and len(sig) > 0


def _map_dispute_type(sub_category: str) -> str:
    """Map ONDC issue_sub_category to NyayaNode dispute_type."""
    return _SUB_CATEGORY_MAP.get(sub_category, _DEFAULT_DISPUTE_TYPE)


def _require_context_fields(context: dict[str, Any]) -> list[str]:
    """Return list of missing required ONDC context fields."""
    required = ["domain", "action", "bap_id", "bpp_id", "transaction_id", "message_id", "timestamp"]
    return [f for f in required if not context.get(f)]


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
            logger.error("Failed to create agent_runs row for ONDC dispute %s", dispute_id)
            return
        run_id = str(rows[0]["id"])
        await client.table("disputes").update({"agent_run_id": run_id, "updated_at": now}).eq("id", dispute_id).execute()
        await run_and_persist(dispute_id, run_id)
    except Exception:
        logger.exception("Background agent setup failed for ONDC dispute %s", dispute_id)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get(
    "/health",
    summary="ONDC integration health",
    tags=["ONDC Webhook"],
)
async def ondc_health() -> dict[str, Any]:
    """Return ONDC mock-mode status."""
    return {"ondc_mock_mode": True, "signature_verification": "MOCK"}


@router.post(
    "/webhook/dispute-raised",
    summary="Receive ONDC dispute-raised event",
    status_code=status.HTTP_200_OK,
    tags=["ONDC Webhook"],
)
async def ondc_dispute_raised(
    request: Request,
    background_tasks: BackgroundTasks,
    x_ondc_signature: str | None = Header(default=None, alias="X-ONDC-Signature"),
) -> JSONResponse:
    """
    Ingest an ONDC grievance protocol `on_issue` event.

    - Verifies X-ONDC-Signature (mock for hackathon).
    - Maps ONDC fields to NyayaNode dispute schema.
    - Creates dispute in DB and triggers agent as BackgroundTask.
    - Returns ONDC ACK format with HTTP 200 (ONDC protocol requirement).
    """
    # Read body once — stream can only be consumed once in Starlette
    body_bytes = await request.body()

    # 1. Signature check
    if not x_ondc_signature:
        return problem_response(
            status=401,
            title="Missing ONDC Signature",
            detail="X-ONDC-Signature header is required",
            type_suffix="ondc-signature-missing",
        )

    if not verify_ondc_signature(body_bytes, x_ondc_signature):
        return problem_response(
            status=401,
            title="Invalid ONDC Signature",
            detail="X-ONDC-Signature verification failed",
            type_suffix="ondc-signature-invalid",
        )

    # 2. Parse JSON from already-read bytes (avoids double-read of stream)
    try:
        payload: dict[str, Any] = json.loads(body_bytes)
    except Exception:
        return problem_response(
            status=400,
            title="Invalid JSON",
            detail="Request body must be valid JSON",
            type_suffix="invalid-json",
        )

    context: dict[str, Any] = payload.get("context") or {}
    message: dict[str, Any] = payload.get("message") or {}

    # 3. Validate required context fields
    missing = _require_context_fields(context)
    if missing:
        return problem_response(
            status=400,
            title="Missing ONDC Context Fields",
            detail=f"Required context fields missing: {', '.join(missing)}",
            type_suffix="ondc-context-invalid",
        )

    # 4. Extract issue
    issue: dict[str, Any] = message.get("issue") or {}
    if not issue:
        return problem_response(
            status=400,
            title="Missing Issue Payload",
            detail="message.issue is required",
            type_suffix="ondc-issue-missing",
        )

    # 5. Map ONDC fields → NyayaNode dispute fields
    sub_category: str = issue.get("issue_sub_category", "")
    dispute_type = _map_dispute_type(sub_category)

    order_details: dict[str, Any] = issue.get("order_details") or {}
    source: dict[str, Any] = issue.get("source") or {}
    description: dict[str, Any] = issue.get("description") or {}

    buyer_id = source.get("id") or context.get("bap_id") or "ondc_buyer_unknown"
    seller_id = order_details.get("provider_id") or context.get("bpp_id") or "ondc_seller_unknown"
    order_id = issue.get("order_id") or order_details.get("id") or context.get("transaction_id", "unknown")

    # Build evidence from description fields
    evidence: list[EvidenceInput] = []
    short_desc = description.get("short_desc", "")
    long_desc = description.get("long_desc", "")
    if short_desc or long_desc:
        combined = f"{short_desc}. {long_desc}".strip(". ")
        evidence.append(EvidenceInput(type="text", content=combined or "ONDC dispute"))

    create_req = CreateDisputeRequest(
        buyer_id=buyer_id,
        seller_id=seller_id,
        logistics_id="ondc_logistics",
        order_id=order_id,
        dispute_type=dispute_type,  # type: ignore[arg-type]
        evidence=evidence,
        dispute_amount_inr="500.00",  # ONDC payload doesn't carry amount; use default
    )

    # 6. Create dispute in DB
    dispute = await create_dispute(create_req)

    # 7. Trigger agent as BackgroundTask
    background_tasks.add_task(_run_agent_background, str(dispute.id))

    logger.info(
        "ONDC dispute ingested: ondc_issue=%s → dispute_id=%s type=%s",
        issue.get("id"),
        dispute.id,
        dispute_type,
    )

    # 8. Return ONDC ACK (HTTP 200 per ONDC protocol)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"ack": {"status": "ACK"}},
    )
