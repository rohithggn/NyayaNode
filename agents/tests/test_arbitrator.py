"""
agents/tests/test_arbitrator.py
────────────────────────────────
NyayaNode — Full Async Test Suite
Covers all 4 dispute types + edge cases:
  - Budget exhaustion
  - Rollback
  - Escalation (amount > ₹50k)
  - Evidence insufficient
  - Negotiation counter-offer paths
  - State machine illegal transitions

Run:
    cd nyayanode/
    source agents/.venv/bin/activate
    pip install pytest pytest-asyncio httpx --quiet
    PYTHONPATH=. pytest agents/tests/test_arbitrator.py -v
"""

from __future__ import annotations

import asyncio
import uuid
import pytest
import pytest_asyncio

# ── Tool imports (Tasks 6) ────────────────────────────────────────────────────
from agents.tools.evidence_tool    import collect_and_analyse_evidence
from agents.tools.logistics_tool   import correlate_logistics
from agents.tools.negotiation_tool import run_negotiation

# ── State machine (Task 2) ────────────────────────────────────────────────────
from agents.core.state_machine import (
    DisputeStateMachine,
    DisputeStatus,
    DisputeTransitionError,
)

# ── Shared schemas (Task 1) ───────────────────────────────────────────────────
from shared.schemas import (
    DisputeRequest,
    DisputeType,
    ArbitrationState,
    DecisionType,
    AuditEventType,
)

# ── Memory / rollback (Task 4) ────────────────────────────────────────────────
from agents.hindsight.memory_bank import MemoryBank
from agents.hindsight.rollback    import RollbackEngine

# ── Budget harness (Task 5) ───────────────────────────────────────────────────
from agents.cascadeflow.budget_harness import BudgetHarness, BudgetExhaustedError

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_request(
    dispute_type: str = "DAMAGED_ITEM",
    amount: float = 500.0,
    evidence: list | None = None,
) -> DisputeRequest:
    return DisputeRequest(
        buyer_id="buyer_test_001",
        seller_id="seller_test_042",
        logistics_id="lsp_test_007",
        order_id=f"order_{uuid.uuid4().hex[:8]}",
        dispute_type=DisputeType(dispute_type),
        evidence=evidence or [{"type": "image_url", "content": "damaged_box.jpg"}],
        dispute_amount_inr=amount,
    )


def make_state(request: DisputeRequest) -> ArbitrationState:
    state = ArbitrationState(dispute_id=request.dispute_id, request=request)
    state.hindsight_session_id = str(uuid.uuid4())
    return state


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: Evidence Tool Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEvidenceTool:

    @pytest.mark.asyncio
    async def test_damaged_item_returns_strong_evidence(self):
        result = await collect_and_analyse_evidence(
            "sess_01", "DAMAGED_ITEM",
            [{"type": "image_url", "content": "crushed_box.jpg"}], 500.0
        )
        assert result["strength"] == "STRONG"
        assert result["evidence_sufficient"] is True
        assert result["confidence"] >= 0.80

    @pytest.mark.asyncio
    async def test_wrong_item_high_confidence(self):
        result = await collect_and_analyse_evidence(
            "sess_02", "WRONG_ITEM",
            [{"type": "image_url", "content": "wrong_sku.jpg"},
             {"type": "text", "content": "inv_001.pdf"}], 800.0
        )
        assert result["confidence"] >= 0.85
        assert result["evidence_sufficient"] is True

    @pytest.mark.asyncio
    async def test_empty_evidence_insufficient(self):
        result = await collect_and_analyse_evidence(
            "sess_03", "DAMAGED_ITEM", [], 200.0
        )
        assert result["evidence_sufficient"] is False
        assert result["strength"] in ("WEAK", "NONE")

    @pytest.mark.asyncio
    async def test_large_amount_reduces_confidence(self):
        low  = await collect_and_analyse_evidence("s_lo", "DAMAGED_ITEM", [{"type":"image_url","content":"x"}], 500.0)
        high = await collect_and_analyse_evidence("s_hi", "DAMAGED_ITEM", [{"type":"image_url","content":"x"}], 20_000.0)
        assert high["confidence"] < low["confidence"], "Large amount must lower confidence"

    @pytest.mark.asyncio
    async def test_unknown_dispute_type_fallback(self):
        result = await collect_and_analyse_evidence(
            "sess_04", "MYSTERY_DISPUTE",
            [{"type": "text", "content": "something went wrong"}], 100.0
        )
        # Must not crash; returns weak fallback
        assert "strength" in result
        assert result["strength"] == "WEAK"

    @pytest.mark.asyncio
    async def test_not_delivered_escalation_recommendation(self):
        result = await collect_and_analyse_evidence(
            "sess_05", "NOT_DELIVERED",
            [{"type": "text", "content": "never received package"}], 300.0
        )
        assert "ESCALATE" in result["recommended_action"] or result["evidence_sufficient"] is True


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: Logistics Tool Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLogisticsTool:

    @pytest.mark.asyncio
    async def test_damaged_item_lsp_at_fault(self):
        result = await correlate_logistics("s1", "order_001", "lsp_007", "DAMAGED_ITEM")
        assert result["verdict"] == "LSP_AT_FAULT"
        assert result["lsp_liability_score"] >= 0.70

    @pytest.mark.asyncio
    async def test_wrong_item_seller_at_fault(self):
        result = await correlate_logistics("s2", "order_002", "lsp_007", "WRONG_ITEM")
        assert result["verdict"] == "SELLER_AT_FAULT"
        assert result["lsp_liability_score"] < 0.30

    @pytest.mark.asyncio
    async def test_not_delivered_has_anomalies(self):
        result = await correlate_logistics("s3", "order_003", "lsp_007", "NOT_DELIVERED")
        assert len(result["anomalies"]) > 0

    @pytest.mark.asyncio
    async def test_quality_issue_low_lsp_score(self):
        result = await correlate_logistics("s4", "order_004", "lsp_007", "REFUND_DENIED")
        assert result["lsp_liability_score"] < 0.30

    @pytest.mark.asyncio
    async def test_result_has_all_required_keys(self):
        result = await correlate_logistics("s5", "order_005", "lsp_007", "DAMAGED_ITEM")
        for key in ["report", "verdict", "lsp_liability_score", "confidence", "anomalies"]:
            assert key in result, f"Missing key: {key}"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: Negotiation Tool Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestNegotiationTool:

    @pytest.mark.asyncio
    async def test_final_refund_never_exceeds_proposal(self):
        import random; random.seed(99)
        for dispute_type in ["DAMAGED_ITEM", "WRONG_ITEM", "NOT_DELIVERED", "REFUND_DENIED"]:
            result = await run_negotiation(
                f"s_{dispute_type}", dispute_type, 700.0, "FULL_REFUND", 0.85
            )
            assert result["final_refund_inr"] <= 700.0, \
                f"{dispute_type}: refund {result['final_refund_inr']} > proposal 700"

    @pytest.mark.asyncio
    async def test_final_refund_always_positive(self):
        import random; random.seed(7)
        result = await run_negotiation("s_pos", "DAMAGED_ITEM", 500.0, "FULL_REFUND", 0.88)
        assert result["final_refund_inr"] > 0

    @pytest.mark.asyncio
    async def test_outcome_is_valid_enum(self):
        valid = {"SELLER_ACCEPTED", "COUNTER_OFFER_ACCEPTED", "SELLER_REJECTED", "TIMED_OUT", "ESCALATED"}
        result = await run_negotiation("s_enum", "REFUND_DENIED", 400.0, "PARTIAL_REFUND", 0.62)
        assert result["outcome"] in valid, f"Invalid outcome: {result['outcome']}"

    @pytest.mark.asyncio
    async def test_rounds_at_least_one(self):
        result = await run_negotiation("s_rounds", "DAMAGED_ITEM", 600.0, "FULL_REFUND", 0.88)
        assert result["rounds"] >= 1

    @pytest.mark.asyncio
    async def test_resolution_notes_non_empty(self):
        result = await run_negotiation("s_notes", "WRONG_ITEM", 300.0, "FULL_REFUND", 0.91)
        assert result["resolution_notes"] and len(result["resolution_notes"]) > 5


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: State Machine Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStateMachine:

    def _fresh_state(self, amount: float = 500.0) -> ArbitrationState:
        req = make_request(amount=amount)
        return make_state(req)

    def test_happy_path_pending_to_resolved(self):
        state = self._fresh_state()
        sm = DisputeStateMachine(state)
        sm.transition(DisputeStatus.EVIDENCE_COLLECTION)
        state.evidence_sufficient = True
        sm.transition(DisputeStatus.NEGOTIATION)
        state.confidence_score = 0.85
        sm.transition(DisputeStatus.RESOLVED)
        assert state.status == DisputeStatus.RESOLVED

    def test_illegal_transition_raises(self):
        state = self._fresh_state()
        sm = DisputeStateMachine(state)
        sm.transition(DisputeStatus.EVIDENCE_COLLECTION)
        sm.transition(DisputeStatus.NEGOTIATION, skip_guards=True)
        sm.transition(DisputeStatus.RESOLVED, skip_guards=True)
        with pytest.raises(DisputeTransitionError):
            sm.transition(DisputeStatus.NEGOTIATION)

    def test_evidence_guard_blocks_negotiation(self):
        state = self._fresh_state()
        sm = DisputeStateMachine(state)
        sm.transition(DisputeStatus.EVIDENCE_COLLECTION)
        state.evidence_sufficient = False
        with pytest.raises(Exception):
            sm.transition(DisputeStatus.NEGOTIATION)

    def test_confidence_guard_blocks_resolved(self):
        state = self._fresh_state()
        sm = DisputeStateMachine(state)
        sm.transition(DisputeStatus.EVIDENCE_COLLECTION)
        sm.transition(DisputeStatus.NEGOTIATION, skip_guards=True)
        state.confidence_score = 0.45  # Below 0.70 minimum
        with pytest.raises(Exception):
            sm.transition(DisputeStatus.RESOLVED)

    def test_amount_guard_blocks_resolved_above_50k(self):
        state = self._fresh_state(amount=75_000.0)
        sm = DisputeStateMachine(state)
        sm.transition(DisputeStatus.EVIDENCE_COLLECTION)
        sm.transition(DisputeStatus.NEGOTIATION, skip_guards=True)
        state.confidence_score = 0.90
        with pytest.raises(Exception):
            sm.transition(DisputeStatus.RESOLVED)

    def test_force_escalate_from_any_state(self):
        for status in [DisputeStatus.EVIDENCE_COLLECTION, DisputeStatus.NEGOTIATION]:
            state = self._fresh_state()
            sm = DisputeStateMachine(state)
            sm.transition(DisputeStatus.EVIDENCE_COLLECTION)
            if status == DisputeStatus.NEGOTIATION:
                sm.transition(DisputeStatus.NEGOTIATION, skip_guards=True)
            sm.force_escalate("Test escalation")
            assert state.status == DisputeStatus.ESCALATED

    def test_rollback_rewinds_state(self):
        state = self._fresh_state()
        sm = DisputeStateMachine(state)
        sm.transition(DisputeStatus.EVIDENCE_COLLECTION)
        sm.transition(DisputeStatus.NEGOTIATION, skip_guards=True)
        sm.rollback()
        assert state.status == DisputeStatus.EVIDENCE_COLLECTION


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: Memory + Rollback Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryAndRollback:

    @pytest.mark.asyncio
    async def test_checkpoint_and_retrieve(self):
        bank = MemoryBank()
        state = make_state(make_request())
        session_id = state.hindsight_session_id

        await bank.open_session(session_id, state)
        state.confidence_score = 0.82
        await bank.checkpoint(session_id, state, "evidence")

        retrieved = await bank.get_latest(session_id)
        assert retrieved is not None
        assert retrieved.confidence_score == 0.82

    @pytest.mark.asyncio
    async def test_rollback_engine_rewinds(self):
        bank = MemoryBank()
        engine = RollbackEngine(bank)
        state = make_state(make_request())
        sid = state.hindsight_session_id

        await bank.open_session(sid, state)
        state.confidence_score = 0.75
        await bank.checkpoint(sid, state, "evidence")
        state.confidence_score = 0.30   # Something went wrong
        await bank.checkpoint(sid, state, "negotiation")

        result = await engine.auto_rollback(sid, state)
        assert result.reentry_node == "evidence"
        assert result.rolled_back_state.confidence_score == 0.75

    @pytest.mark.asyncio
    async def test_max_rollback_limit_enforced(self):
        bank = MemoryBank()
        engine = RollbackEngine(bank, max_rollbacks=2)
        state = make_state(make_request())
        sid = state.hindsight_session_id
        await bank.open_session(sid, state)
        await bank.checkpoint(sid, state, "evidence")

        await engine.auto_rollback(sid, state)
        await engine.auto_rollback(sid, state)
        result = await engine.auto_rollback(sid, state)
        assert result.status == "LIMIT_EXCEEDED"

    @pytest.mark.asyncio
    async def test_session_not_found_handled(self):
        bank = MemoryBank()
        engine = RollbackEngine(bank)
        state = make_state(make_request())
        # Never opened session
        result = await engine.auto_rollback("nonexistent_session", state)
        assert result.status == "SESSION_NOT_FOUND"


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: Budget Harness Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBudgetHarness:

    @pytest.mark.asyncio
    async def test_fresh_dispute_approves_heavy_model(self):
        harness = BudgetHarness()
        state = make_state(make_request())
        result = await harness.gate(state, model="llama-3.3-70b-versatile", estimated_cost=0.06)
        assert result.approved is True
        assert result.model == "llama-3.3-70b-versatile"

    @pytest.mark.asyncio
    async def test_charge_tracks_correctly(self):
        harness = BudgetHarness()
        state = make_state(make_request())
        await harness.charge(state, actual_cost=0.12, node="evidence_node")
        assert abs(state.budget_status.consumed_inr - 0.12) < 0.001

    @pytest.mark.asyncio
    async def test_downgrade_at_70_percent(self):
        harness = BudgetHarness()
        state = make_state(make_request())
        # Consume 72% of budget
        await harness.charge(state, actual_cost=3.60, node="evidence_node")
        result = await harness.gate(state, model="llama-3.3-70b-versatile", estimated_cost=0.10)
        assert result.model == "llama-3.1-8b-instant", f"Expected downgrade, got {result.model}"

    @pytest.mark.asyncio
    async def test_hard_block_when_exhausted(self):
        harness = BudgetHarness()
        state = make_state(make_request())
        await harness.charge(state, actual_cost=5.0, node="evidence_node")
        with pytest.raises(BudgetExhaustedError):
            harness.gate(state, model="llama-3.1-8b-instant", estimated_cost=0.01)

    @pytest.mark.asyncio
    async def test_warning_emitted_at_80_percent(self):
        harness = BudgetHarness()
        state = make_state(make_request())
        await harness.charge(state, actual_cost=4.10, node="evidence_node")  # 82%
        harness.gate(state, model="llama-3.1-8b-instant", estimated_cost=0.01)
        warning_events = [e for e in state.audit_trail if "BUDGET_WARNING" in str(e)]
        assert len(warning_events) >= 1

    @pytest.mark.asyncio
    async def test_consumed_never_exceeds_cap(self):
        harness = BudgetHarness()
        state = make_state(make_request())
        await harness.charge(state, actual_cost=4.99, node="n1")
        await harness.charge(state, actual_cost=0.50, node="n2")   # Would overspend
        assert state.budget_status.consumed_inr <= 5.0 + 0.001  # Allow float tolerance


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7: End-to-End Integration Tests (no live LLM)
# ─────────────────────────────────────────────────────────────────────────────

class TestEndToEnd:
    """
    Full pipeline tests using mock backends.
    No GROQ_API_KEY required — these run entirely on mock data.
    """

    @pytest.mark.asyncio
    async def test_damaged_item_full_pipeline(self):
        req = make_request("DAMAGED_ITEM", 500.0)
        state = make_state(req)

        ev = await collect_and_analyse_evidence(
            state.hindsight_session_id, "DAMAGED_ITEM",
            req.evidence, req.dispute_amount_inr
        )
        assert ev["evidence_sufficient"] is True

        lg = await correlate_logistics(
            state.hindsight_session_id, req.order_id, req.logistics_id, "DAMAGED_ITEM"
        )
        assert lg["lsp_liability_score"] >= 0.70

        ng = await run_negotiation(
            state.hindsight_session_id, "DAMAGED_ITEM",
            req.dispute_amount_inr * ev["confidence"],
            "FULL_REFUND", ev["confidence"]
        )
        assert ng["final_refund_inr"] > 0
        assert ng["outcome"] in {"SELLER_ACCEPTED", "COUNTER_OFFER_ACCEPTED", "SELLER_REJECTED"}

    @pytest.mark.asyncio
    async def test_not_delivered_pipeline(self):
        req = make_request("NOT_DELIVERED", 650.0)
        state = make_state(req)

        ev = await collect_and_analyse_evidence(
            state.hindsight_session_id, "NOT_DELIVERED", req.evidence, req.dispute_amount_inr
        )
        lg = await correlate_logistics(
            state.hindsight_session_id, req.order_id, req.logistics_id, "NOT_DELIVERED"
        )
        assert len(lg["anomalies"]) > 0   # GPS mismatch must be flagged

    @pytest.mark.asyncio
    async def test_escalation_above_50k(self):
        """Disputes above ₹50,000 must be blocked at state machine level."""
        req = make_request("DAMAGED_ITEM", 75_000.0)
        state = make_state(req)
        sm = DisputeStateMachine(state)
        sm.transition(DisputeStatus.EVIDENCE_COLLECTION)
        sm.transition(DisputeStatus.NEGOTIATION, skip_guards=True)
        state.confidence_score = 0.90
        with pytest.raises(Exception):
            sm.transition(DisputeStatus.RESOLVED)
        # Force escalate path
        sm.force_escalate("Amount exceeds ₹50,000 arbitration threshold")
        assert state.status == DisputeStatus.ESCALATED

    @pytest.mark.asyncio
    async def test_budget_exhaustion_mid_pipeline(self):
        """If budget is exhausted before negotiation, pipeline must escalate gracefully."""
        harness = BudgetHarness()
        state = make_state(make_request("DAMAGED_ITEM", 500.0))

        # Exhaust budget during evidence phase
        await harness.charge(state, actual_cost=5.0, node="evidence_node")
        assert state.budget_status.is_exhausted is True

        # Downstream negotiation should not be called — state machine escalates
        sm = DisputeStateMachine(state)
        sm.force_escalate("Budget exhausted mid-pipeline")
        assert state.status == DisputeStatus.ESCALATED

    @pytest.mark.asyncio
    async def test_rollback_then_resume(self):
        """After rollback, pipeline can resume from safe checkpoint."""
        bank = MemoryBank()
        engine = RollbackEngine(bank)
        state = make_state(make_request("REFUND_DENIED", 300.0))
        sid = state.hindsight_session_id

        await bank.open_session(sid, state)
        state.confidence_score = 0.70
        await bank.checkpoint(sid, state, "evidence")

        # Simulate a bad state
        state.confidence_score = 0.10
        result = await engine.auto_rollback(sid, state)
        assert result.reentry_node == "evidence"
        assert result.rolled_back_state.confidence_score == 0.70


# ─────────────────────────────────────────────────────────────────────────────
# Run directly (without pytest)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import subprocess, sys
    sys.exit(subprocess.call([
        "python", "-m", "pytest",
        "agents/tests/test_arbitrator.py", "-v", "--tb=short"
    ]))
