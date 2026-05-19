"""Agent stub and persistence layer for dispute arbitration runs."""

import asyncio
import logging
from datetime import datetime, timezone

from services.supabase_client import get_client
from services.dispute_service import write_audit_event
from services.sse_manager import sse_manager

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_agent_stub(dispute_id: str) -> dict:
    """Simulate a 5-second agent run and return a fixed arbitration outcome."""
    await asyncio.sleep(5)
    return {
        "status": "RESOLVED",
        "decision": "FULL_REFUND",
        "refund_amount_inr": 499.0,
        "reasoning": "STUB: logistics confirmed damage",
        "confidence_score": 0.95,
        "total_inference_cost_inr": 2.84,
    }


async def run_and_persist(dispute_id: str, run_id: str) -> None:
    """
    Execute the agent stub and persist all results to the DB.

    Steps:
      1. Mark agent_runs row as RUNNING
      2. Write AGENT_STARTED audit event
      3. Run the stub
      4. Update disputes row with arbitration outcome
      5. Mark agent_runs as COMPLETE
      6. Write AGENT_COMPLETED audit event
      7. Escalate if confidence_score < 0.6
    On any exception: mark agent_runs as FAILED and write AGENT_FAILED audit event.
    """
    client = await get_client()

    # 1. Mark run as RUNNING
    await client.table("agent_runs").update({"status": "RUNNING"}).eq("id", run_id).execute()

    # 2. Audit: AGENT_STARTED
    await write_audit_event(
        dispute_id,
        event_type="AGENT_STARTED",
        actor="agent",
        payload={"run_id": run_id},
    )

    try:
        # SSE: evidence collection starting
        await sse_manager.publish(
            dispute_id,
            "status_update",
            {"status": "EVIDENCE_COLLECTION", "message": "Agent gathering evidence..."},
        )

        # 3. Run the stub
        result = await run_agent_stub(dispute_id)

        # SSE: mid-run cost update (simulated mid-point cost)
        await sse_manager.publish(
            dispute_id,
            "cost_update",
            {"total_cost_inr": 0.84, "budget_remaining_inr": 4.16},
        )

        # SSE: negotiation stage
        await sse_manager.publish(
            dispute_id,
            "status_update",
            {"status": "NEGOTIATION", "message": "Agent contacting seller..."},
        )

        confidence: float = float(result.get("confidence_score", 1.0))

        # 4. Update dispute row
        dispute_update: dict = {
            "status": result["status"],
            "decision": result["decision"],
            "refund_amount_inr": result["refund_amount_inr"],
            "reasoning": result["reasoning"],
            "confidence_score": confidence,
            "total_cost_inr": result["total_inference_cost_inr"],
            "updated_at": _utc_now_iso(),
        }
        if confidence < 0.6:
            dispute_update["escalated_to_human"] = True

        await client.table("disputes").update(dispute_update).eq("id", dispute_id).execute()

        # SSE: decision made
        await sse_manager.publish(
            dispute_id,
            "decision",
            {"decision": result["decision"], "refund_amount_inr": result["refund_amount_inr"]},
        )

        # 5. Mark run as COMPLETE
        cascadeflow_audit = {
            "run_id": run_id,
            "dispute_id": dispute_id,
            "result": result,
            "completed_at": _utc_now_iso(),
        }
        await (
            client.table("agent_runs")
            .update({
                "status": "COMPLETE",
                "completed_at": _utc_now_iso(),
                "cascadeflow_audit": cascadeflow_audit,
            })
            .eq("id", run_id)
            .execute()
        )

        # 6. Audit: AGENT_COMPLETED
        await write_audit_event(
            dispute_id,
            event_type="AGENT_COMPLETED",
            actor="agent",
            payload={"run_id": run_id, **result},
        )

        # SSE: complete — this closes all subscriber streams
        await sse_manager.publish(
            dispute_id,
            "complete",
            {"dispute_id": dispute_id, "final_status": result["status"]},
        )

        # 7. Escalate if low confidence
        if confidence < 0.6:
            await write_audit_event(
                dispute_id,
                event_type="ESCALATION_TRIGGERED",
                actor="agent",
                payload={"run_id": run_id, "confidence_score": confidence, "reason": "low_confidence"},
            )
            logger.warning(
                "Dispute %s escalated to human: confidence_score=%.2f", dispute_id, confidence
            )

        logger.info("Agent run %s completed for dispute %s: %s", run_id, dispute_id, result)

    except Exception:
        logger.exception("Agent run %s failed for dispute %s", run_id, dispute_id)

        # On failure: mark run as FAILED
        await client.table("agent_runs").update({"status": "FAILED"}).eq("id", run_id).execute()

        await write_audit_event(
            dispute_id,
            event_type="AGENT_FAILED",
            actor="agent",
            payload={"run_id": run_id},
        )


# When Member 1 pushes their code, replace run_agent_stub with:
# from agents.core.arbitrator import ArbitratorAgent
