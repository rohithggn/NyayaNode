"""
agents/hindsight/rollback.py
=============================
Agent rollback logic for NyayaNode — rewinds ArbitrationState to any
prior Hindsight checkpoint and re-enters the LangGraph from that point.

WHO USES THIS:
  - Member 1 (Lead AI Architect): calls perform_rollback() from
    arbitrator.py when a node detects a corrupt or invalid state.
  - Member 3 (Backend): exposes POST /agents/dispute/{id}/rollback
    so a human supervisor can rewind a dispute to a safe checkpoint.
  - Member 5 (QA): imports RollbackEngine for rollback scenario tests.

ROLLBACK SCENARIOS:
  1. AUTOMATIC — triggered internally when:
       - State corruption is detected mid-graph
       - Budget exhausted but dispute can be restarted cheaply
       - LLM returns a structurally invalid decision
  2. MANUAL — triggered by human supervisor via API when:
       - An arbitration decision is disputed by a party
       - A system error corrupted the negotiation state
       - A new piece of evidence arrives post-decision

ROLLBACK SAFETY CONTRACT:
  - Original checkpoints are NEVER deleted (immutable audit trail).
  - Rollback creates a new checkpoint of type "ROLLBACK" before restoring.
  - The rolled-back state is re-entered at the node AFTER the target
    checkpoint (not the checkpoint's node itself) to avoid re-running
    the same node with the same inputs.
  - Maximum 3 rollbacks per dispute to prevent infinite loops.

INTEGRATION WITH STATE MACHINE:
  After restoring state, rollback calls:
    sm.transition(ROLLED_BACK, skip_guards=True)   ← records in audit trail
    sm.transition(PENDING, skip_guards=True)        ← resets for re-entry
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

import structlog
from dotenv import load_dotenv

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

load_dotenv(os.path.join(_REPO_ROOT, ".env"))

from agents.hindsight.memory_bank import (
    HindsightCheckpoint,
    HindsightSession,
    MemoryBank,
    get_hindsight_client,
)
from agents.core.state_machine import create_state_machine
from shared.schemas import (
    ArbitrationState,
    AuditEventType,
    BudgetStatus,
    DisputeStatus,
)

log = structlog.get_logger("nyayanode.rollback")

MAX_ROLLBACKS_PER_DISPUTE = 3


# ---------------------------------------------------------------------------
# Rollback Result
# ---------------------------------------------------------------------------


class RollbackStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    CHECKPOINT_NOT_FOUND = "CHECKPOINT_NOT_FOUND"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"


class RollbackResult:
    """
    Result returned by perform_rollback().
    Consumed by arbitrator.py to decide whether to re-run the graph.
    """

    def __init__(
        self,
        status: RollbackStatus,
        restored_state: ArbitrationState | None = None,
        rolled_back_to_checkpoint: HindsightCheckpoint | None = None,
        reentry_node: str | None = None,
        reason: str = "",
        rollback_id: str | None = None,
    ) -> None:
        self.status = status
        self.restored_state = restored_state
        self.rolled_back_to_checkpoint = rolled_back_to_checkpoint
        self.reentry_node = reentry_node
        self.reason = reason
        self.rollback_id = rollback_id or str(uuid.uuid4())
        self.timestamp = datetime.utcnow()

    @property
    def succeeded(self) -> bool:
        return self.status == RollbackStatus.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        return {
            "rollback_id": self.rollback_id,
            "status": self.status.value,
            "reentry_node": self.reentry_node,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
            "rolled_back_to": (
                self.rolled_back_to_checkpoint.checkpoint_id
                if self.rolled_back_to_checkpoint
                else None
            ),
            "rolled_back_to_node": (
                self.rolled_back_to_checkpoint.node_name
                if self.rolled_back_to_checkpoint
                else None
            ),
        }


# ---------------------------------------------------------------------------
# Node Re-entry Map
# ---------------------------------------------------------------------------

# When rolling back to a checkpoint taken AFTER a node, we re-enter at
# the NEXT node in the pipeline (not the same node — that would repeat work).
# "rollback_to_node" → "reenter_at_node"
_REENTRY_MAP: dict[str, str] = {
    "intake":       "evidence",       # rolled back to post-intake → re-run from evidence
    "evidence":     "logistics",      # rolled back to post-evidence → re-run from logistics
    "logistics":    "decision",       # rolled back to post-logistics → re-run from decision
    "decision":     "negotiation",    # rolled back to post-decision → re-run from negotiation
    "negotiation":  "resolve",        # rolled back to post-negotiation → re-run from resolve
    "resolve":      "intake",         # rolled back all the way → full restart
    "escalate":     "intake",         # de-escalation → full restart
}

# Node names in execution order — used to find the latest safe checkpoint
_NODE_ORDER = ["intake", "evidence", "logistics", "decision", "negotiation", "resolve"]


# ---------------------------------------------------------------------------
# Rollback Engine
# ---------------------------------------------------------------------------


class RollbackEngine:
    """
    Manages rollback operations for NyayaNode arbitration agents.

    Usage in arbitrator.py:
        engine = RollbackEngine()
        result = await engine.perform_rollback(
            session_id=state.hindsight_session_id,
            target_checkpoint_id=checkpoint_id,  # None = latest safe
            reason="LLM returned invalid decision structure",
        )
        if result.succeeded:
            # Re-enter graph at result.reentry_node with result.restored_state
    """

    def __init__(self, bank: MemoryBank | None = None) -> None:
        self._bank = bank or MemoryBank(client=get_hindsight_client())
        # Track rollback count per dispute to enforce MAX_ROLLBACKS
        self._rollback_counts: dict[str, int] = {}

    async def perform_rollback(
        self,
        session_id: str,
        target_checkpoint_id: str | None = None,
        reason: str = "",
    ) -> RollbackResult:
        """
        Restore ArbitrationState to a prior checkpoint.

        Args:
            session_id:            Hindsight session ID (stored in state.hindsight_session_id).
            target_checkpoint_id:  Specific checkpoint to restore. If None, uses the
                                   latest safe checkpoint (one node before current).
            reason:                Human-readable reason for the rollback (audit trail).

        Returns:
            RollbackResult with restored_state ready to feed back into the graph.
        """
        rollback_id = str(uuid.uuid4())
        log.info(
            "rollback_initiated",
            session_id=session_id,
            target_checkpoint_id=target_checkpoint_id,
            reason=reason,
            rollback_id=rollback_id,
        )

        # ── 1. Load session ─────────────────────────────────────────────────
        session = await self._bank.recall(session_id)
        if not session:
            log.error("rollback_session_not_found", session_id=session_id)
            return RollbackResult(
                status=RollbackStatus.SESSION_NOT_FOUND,
                reason=f"Session {session_id} not found in Hindsight store",
                rollback_id=rollback_id,
            )

        # ── 2. Check rollback limit ─────────────────────────────────────────
        dispute_id = session.dispute_id
        rollback_count = self._rollback_counts.get(dispute_id, 0)
        if rollback_count >= MAX_ROLLBACKS_PER_DISPUTE:
            log.warning(
                "rollback_limit_exceeded",
                dispute_id=dispute_id,
                count=rollback_count,
            )
            return RollbackResult(
                status=RollbackStatus.LIMIT_EXCEEDED,
                reason=f"Rollback limit ({MAX_ROLLBACKS_PER_DISPUTE}) exceeded for dispute {dispute_id}",
                rollback_id=rollback_id,
            )

        # ── 3. Resolve target checkpoint ────────────────────────────────────
        checkpoints = await self._bank.checkpoints(session_id)
        if not checkpoints:
            return RollbackResult(
                status=RollbackStatus.CHECKPOINT_NOT_FOUND,
                reason="No checkpoints available for rollback",
                rollback_id=rollback_id,
            )

        if target_checkpoint_id:
            target_cp = next(
                (cp for cp in checkpoints if cp.checkpoint_id == target_checkpoint_id),
                None,
            )
            if not target_cp:
                return RollbackResult(
                    status=RollbackStatus.CHECKPOINT_NOT_FOUND,
                    reason=f"Checkpoint {target_checkpoint_id} not found in session",
                    rollback_id=rollback_id,
                )
        else:
            # Default: roll back one step (to second-to-last checkpoint)
            target_cp = self._find_safe_checkpoint(checkpoints)

        # ── 4. Restore state from checkpoint snapshot ────────────────────────
        try:
            restored_state = ArbitrationState(**target_cp.state_snapshot)
        except Exception as e:
            log.error("rollback_deserialisation_failed", error=str(e))
            return RollbackResult(
                status=RollbackStatus.FAILED,
                reason=f"Failed to deserialise checkpoint state: {str(e)[:100]}",
                rollback_id=rollback_id,
            )

        # ── 5. Apply state machine transitions ──────────────────────────────
        sm = create_state_machine(restored_state)

        # If not already in a rollbackable state, force it
        if restored_state.status not in (
            DisputeStatus.RESOLVED, DisputeStatus.ESCALATED,
            DisputeStatus.PENDING, DisputeStatus.EVIDENCE_COLLECTION,
            DisputeStatus.NEGOTIATION,
        ):
            restored_state.status = DisputeStatus.PENDING

        sm.transition(
            DisputeStatus.ROLLED_BACK,
            reason=f"Rollback triggered: {reason}",
            skip_guards=True,
        )
        sm.transition(
            DisputeStatus.PENDING,
            reason="Reset to PENDING for graph re-entry",
            skip_guards=True,
        )

        # ── 6. Reset budget for fresh run ────────────────────────────────────
        remaining = restored_state.budget_status.remaining_inr
        if remaining < 0.5:  # Less than ₹0.50 remaining → reset partially
            restored_state.budget_status.remaining_inr = (
                restored_state.budget_status.budget_cap_inr * 0.5
            )
            restored_state.budget_status.is_exhausted = False
            log.info(
                "rollback_budget_reset",
                dispute_id=dispute_id,
                new_remaining=restored_state.budget_status.remaining_inr,
            )

        # ── 7. Add rollback audit entry ──────────────────────────────────────
        restored_state.add_audit(
            event_type=AuditEventType.ROLLBACK_TRIGGERED,
            description=(
                f"State rolled back to checkpoint '{target_cp.node_name}' "
                f"(seq={target_cp.sequence}). Reason: {reason}"
            ),
            metadata={
                "rollback_id": rollback_id,
                "target_checkpoint_id": target_cp.checkpoint_id,
                "target_node": target_cp.node_name,
                "target_sequence": target_cp.sequence,
                "total_checkpoints": len(checkpoints),
                "rollback_number": rollback_count + 1,
            },
        )

        # ── 8. Save rollback as a new checkpoint ─────────────────────────────
        await self._bank.checkpoint(
            session=session,
            state=restored_state,
            node_name=f"rollback_{rollback_id[:8]}",
            metadata={
                "rollback_id": rollback_id,
                "rolled_back_to": target_cp.checkpoint_id,
                "reason": reason,
            },
        )

        # ── 9. Update rollback counter ───────────────────────────────────────
        self._rollback_counts[dispute_id] = rollback_count + 1

        # ── 10. Determine graph re-entry point ───────────────────────────────
        reentry_node = _REENTRY_MAP.get(target_cp.node_name, "intake")

        log.info(
            "rollback_complete",
            rollback_id=rollback_id,
            dispute_id=dispute_id,
            rolled_back_to=target_cp.node_name,
            reentry_node=reentry_node,
            rollback_number=rollback_count + 1,
        )

        return RollbackResult(
            status=RollbackStatus.SUCCESS,
            restored_state=restored_state,
            rolled_back_to_checkpoint=target_cp,
            reentry_node=reentry_node,
            reason=reason,
            rollback_id=rollback_id,
        )

    async def get_rollback_history(self, session_id: str) -> list[dict[str, Any]]:
        """
        Return all rollback events from a session's audit trail.
        Used by Member 3's backend for the dispute history endpoint.
        """
        checkpoints = await self._bank.checkpoints(session_id)
        rollbacks = [
            cp.to_dict()
            for cp in checkpoints
            if cp.node_name.startswith("rollback_")
        ]
        return rollbacks

    async def can_rollback(self, session_id: str) -> dict[str, Any]:
        """
        Check whether a dispute can be rolled back and list available
        target checkpoints. Used by Member 3's backend.
        """
        session = await self._bank.recall(session_id)
        if not session:
            return {"can_rollback": False, "reason": "Session not found"}

        dispute_id = session.dispute_id
        rollback_count = self._rollback_counts.get(dispute_id, 0)

        if rollback_count >= MAX_ROLLBACKS_PER_DISPUTE:
            return {
                "can_rollback": False,
                "reason": f"Rollback limit ({MAX_ROLLBACKS_PER_DISPUTE}) reached",
                "rollbacks_used": rollback_count,
            }

        checkpoints = await self._bank.checkpoints(session_id)
        safe_targets = [
            {
                "checkpoint_id": cp.checkpoint_id,
                "node_name": cp.node_name,
                "sequence": cp.sequence,
                "created_at": cp.created_at.isoformat(),
                "state_hash": cp.state_hash,
                "reentry_node": _REENTRY_MAP.get(cp.node_name, "intake"),
            }
            for cp in checkpoints
            if not cp.node_name.startswith("rollback_")
        ]

        return {
            "can_rollback": True,
            "rollbacks_remaining": MAX_ROLLBACKS_PER_DISPUTE - rollback_count,
            "rollbacks_used": rollback_count,
            "available_targets": safe_targets,
        }

    @staticmethod
    def _find_safe_checkpoint(
        checkpoints: list[HindsightCheckpoint],
    ) -> HindsightCheckpoint:
        """
        Find the best automatic rollback target:
        - Exclude rollback checkpoints themselves
        - Return second-to-last non-rollback checkpoint
          (last = current state, second-to-last = previous safe state)
        """
        non_rollback = [
            cp for cp in checkpoints
            if not cp.node_name.startswith("rollback_")
        ]
        if len(non_rollback) >= 2:
            return non_rollback[-2]   # one step back
        return non_rollback[0]        # only one — return it (fresh start)


# ---------------------------------------------------------------------------
# Convenience Functions (for arbitrator.py)
# ---------------------------------------------------------------------------


async def auto_rollback(
    state: ArbitrationState,
    bank: MemoryBank,
    reason: str,
) -> RollbackResult:
    """
    Convenience function for automatic rollback triggered inside a LangGraph node.

    Usage in arbitrator.py:
        result = await auto_rollback(state, bank, "LLM parse failure")
        if result.succeeded:
            state = result.restored_state
    """
    if not state.hindsight_session_id:
        log.warning("auto_rollback_no_session", dispute_id=state.dispute_id)
        return RollbackResult(
            status=RollbackStatus.SESSION_NOT_FOUND,
            reason="No Hindsight session ID on state — rollback not possible",
        )

    engine = RollbackEngine(bank=bank)
    return await engine.perform_rollback(
        session_id=state.hindsight_session_id,
        target_checkpoint_id=None,   # auto-select latest safe
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    async def _self_test():
        print("=" * 60)
        print("NyayaNode — Rollback Engine Self-Test")
        print("=" * 60)

        from agents.hindsight.memory_bank import LocalHindsightClient, MemoryBank
        from shared.schemas import (
            ArbitrationState, BudgetStatus, DecisionType,
            DisputeRequest, DisputeType, EvidenceItem, EvidenceType,
        )

        def _make_state() -> ArbitrationState:
            req = DisputeRequest(
                buyer_id="buyer_001",
                seller_id="seller_042",
                logistics_id="lsp_007",
                order_id="order_xyz",
                dispute_type=DisputeType.DAMAGED_ITEM,
                evidence=[EvidenceItem(type=EvidenceType.TEXT, content="Broken box")],
                dispute_amount_inr=500.0,
            )
            budget = BudgetStatus(dispute_id=req.dispute_id, budget_cap_inr=5.0)
            return ArbitrationState(
                dispute_id=req.dispute_id, request=req, budget_status=budget
            )

        client = LocalHindsightClient()
        bank = MemoryBank(client=client)
        engine = RollbackEngine(bank=bank)

        # ── Setup: create session and checkpoints ─────────────────────────
        state = _make_state()
        session = await bank.open(state.dispute_id)
        state.hindsight_session_id = session.session_id

        # Simulate graph execution through 3 nodes
        state.status = DisputeStatus.EVIDENCE_COLLECTION
        cp_intake = await bank.checkpoint(session, state, "intake")

        state.status = DisputeStatus.EVIDENCE_COLLECTION
        state.confidence_score = 0.75
        cp_evidence = await bank.checkpoint(session, state, "evidence")

        state.status = DisputeStatus.NEGOTIATION
        state.decision = DecisionType.FULL_REFUND
        cp_logistics = await bank.checkpoint(session, state, "logistics")

        print(f"\n[Setup] {len(session.checkpoints)} checkpoints created")

        # ── Test 1: Auto-rollback (no target specified) ───────────────────
        print("\n[1] Auto-rollback to latest safe checkpoint...")
        result = await engine.perform_rollback(
            session_id=session.session_id,
            reason="Test auto-rollback",
        )
        assert result.succeeded, f"Failed: {result.reason}"
        assert result.restored_state is not None
        assert result.restored_state.status == DisputeStatus.PENDING
        assert result.reentry_node == "logistics"  # rolled back to evidence([-2]) → re-enter at logistics
        print(f"   ✅ Rolled back to: {result.rolled_back_to_checkpoint.node_name}")
        print(f"   ✅ Re-entry node: {result.reentry_node}")
        print(f"   ✅ Restored status: {result.restored_state.status.value}")

        # ── Test 2: Targeted rollback to specific checkpoint ──────────────
        print("\n[2] Targeted rollback to intake checkpoint...")
        result2 = await engine.perform_rollback(
            session_id=session.session_id,
            target_checkpoint_id=cp_intake.checkpoint_id,
            reason="Supervisor requested restart",
        )
        assert result2.succeeded
        assert result2.rolled_back_to_checkpoint.node_name == "intake"
        assert result2.reentry_node == "evidence"
        print(f"   ✅ Targeted rollback successful → reentry: {result2.reentry_node}")

        # -- Test 3: Rollback limit enforcement
        print("\n[3] Rollback limit enforcement (max=3)...")
        # 2 rollbacks done - third succeeds, fourth hits limit
        result3a = await engine.perform_rollback(
            session_id=session.session_id,
            reason="Third rollback within limit",
        )
        assert result3a.succeeded, f"Third should succeed: {result3a.reason}"
        result3b = await engine.perform_rollback(
            session_id=session.session_id,
            reason="Fourth rollback should be blocked",
        )
        assert result3b.status == RollbackStatus.LIMIT_EXCEEDED
        print(f"   OK Limit enforced after {MAX_ROLLBACKS_PER_DISPUTE} rollbacks")

        # ── Test 4: Session not found ─────────────────────────────────────
        print("\n[4] Session not found returns graceful error...")
        result4 = await engine.perform_rollback(
            session_id="nonexistent-session-id",
            reason="Test",
        )
        assert result4.status == RollbackStatus.SESSION_NOT_FOUND
        print(f"   ✅ Graceful error: {result4.status.value}")

        # ── Test 5: can_rollback() status check ───────────────────────────
        print("\n[5] can_rollback() check...")
        state5 = _make_state()
        session5 = await bank.open(state5.dispute_id)
        await bank.checkpoint(session5, state5, "intake")
        status5 = await engine.can_rollback(session5.session_id)
        assert status5["can_rollback"] is True
        assert status5["rollbacks_remaining"] == MAX_ROLLBACKS_PER_DISPUTE
        assert len(status5["available_targets"]) > 0
        print(f"   ✅ can_rollback=True, targets: {len(status5['available_targets'])}")

        # ── Test 6: auto_rollback convenience function ────────────────────
        print("\n[6] auto_rollback() convenience function...")
        state6 = _make_state()
        state6.hindsight_session_id = None   # No session — should fail gracefully
        result6 = await auto_rollback(state6, bank, "No session test")
        assert result6.status == RollbackStatus.SESSION_NOT_FOUND
        print(f"   ✅ Graceful no-session handling: {result6.status.value}")

        print("\n" + "=" * 60)
        print("🎉 ALL ROLLBACK TESTS PASSED")
        print("=" * 60)

    asyncio.run(_self_test())
