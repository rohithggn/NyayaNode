"""
agents/core/state_machine.py
============================
Dispute arbitration state machine for NyayaNode.

WHO USES THIS:
  - Member 1 (Lead AI Architect): imported by arbitrator.py — every LangGraph
    node calls transition() before mutating ArbitrationState.
  - Member 3 (Backend): calls get_allowed_transitions() in the status endpoint
    so the frontend can render valid next actions.
  - Member 5 (QA): imports DisputeStateMachine to write transition-coverage tests.

STATE LIFECYCLE:
  PENDING
    └─► EVIDENCE_COLLECTION   (dispute accepted, collecting buyer evidence)
          └─► NEGOTIATION     (evidence sufficient, attempting seller settlement)
                ├─► RESOLVED  (agreement reached OR unilateral decision issued)
                └─► ESCALATED (confidence too low, budget exhausted, or high-value)
          └─► ESCALATED       (evidence collection failed / insufficient)
    └─► ESCALATED             (immediate escalation: amount > threshold, fraud flag)
  ANY ─► ROLLED_BACK          (Hindsight rollback triggered by Member 1)

RULES:
  - Transitions are validated; illegal moves raise DisputeTransitionError.
  - Terminal states (RESOLVED, ESCALATED) accept no further transitions
    except ROLLED_BACK.
  - Every transition is logged to ArbitrationState.audit_trail automatically.
"""

from __future__ import annotations

import sys
import os
from datetime import datetime
from typing import Callable

# ---------------------------------------------------------------------------
# Path setup — works whether run from repo root or agents/ directory
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from shared.schemas import (
    ArbitrationState,
    AuditEventType,
    DecisionType,
    DisputeStatus,
    DisputeType,
)
from shared.constants import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    ESCALATION_THRESHOLD_INR,
    MIN_CONFIDENCE_TO_RESOLVE,
    REFUND_POLICY,
)


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------


class DisputeTransitionError(Exception):
    """Raised when an illegal state transition is attempted."""

    def __init__(self, from_state: DisputeStatus, to_state: DisputeStatus, reason: str = ""):
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        super().__init__(
            f"Illegal transition: {from_state.value} → {to_state.value}"
            + (f" — {reason}" if reason else "")
        )


class InsufficientEvidenceError(Exception):
    """Raised when evidence_sufficient guard fails."""
    pass


class BudgetExhaustedError(Exception):
    """Raised when the ₹5 per-dispute budget is exhausted mid-transition."""
    pass


class ConfidenceTooLowError(Exception):
    """Raised when confidence_score is below MIN_CONFIDENCE_TO_RESOLVE."""
    pass


# ---------------------------------------------------------------------------
# Transition Table
# ---------------------------------------------------------------------------

# Maps (from_state, to_state) → True if the transition is permitted.
# ROLLED_BACK is handled separately (allowed from any non-terminal state).
_ALLOWED_TRANSITIONS: dict[tuple[DisputeStatus, DisputeStatus], bool] = {
    # ── From PENDING ────────────────────────────────────────────────────────
    (DisputeStatus.PENDING, DisputeStatus.EVIDENCE_COLLECTION): True,
    (DisputeStatus.PENDING, DisputeStatus.ESCALATED): True,   # immediate escalation
    # ── From EVIDENCE_COLLECTION ─────────────────────────────────────────────
    (DisputeStatus.EVIDENCE_COLLECTION, DisputeStatus.NEGOTIATION): True,
    (DisputeStatus.EVIDENCE_COLLECTION, DisputeStatus.ESCALATED): True,
    (DisputeStatus.EVIDENCE_COLLECTION, DisputeStatus.RESOLVED): True,  # clear-cut case
    # ── From NEGOTIATION ────────────────────────────────────────────────────
    (DisputeStatus.NEGOTIATION, DisputeStatus.RESOLVED): True,
    (DisputeStatus.NEGOTIATION, DisputeStatus.ESCALATED): True,
    # ── Terminal states accept no further moves (except ROLLED_BACK) ────────
    (DisputeStatus.RESOLVED, DisputeStatus.ROLLED_BACK): True,
    (DisputeStatus.ESCALATED, DisputeStatus.ROLLED_BACK): True,
    # ── ROLLED_BACK can restart from PENDING ─────────────────────────────────
    (DisputeStatus.ROLLED_BACK, DisputeStatus.PENDING): True,
}

# States from which ROLLED_BACK is always permitted (Hindsight integration)
_ROLLBACKABLE_STATES: frozenset[DisputeStatus] = frozenset(
    {
        DisputeStatus.PENDING,
        DisputeStatus.EVIDENCE_COLLECTION,
        DisputeStatus.NEGOTIATION,
        DisputeStatus.RESOLVED,
        DisputeStatus.ESCALATED,
    }
)

# Terminal states — no agent action possible after these
_TERMINAL_STATES: frozenset[DisputeStatus] = frozenset(
    {DisputeStatus.RESOLVED, DisputeStatus.ESCALATED, DisputeStatus.ROLLED_BACK}
)


# ---------------------------------------------------------------------------
# Guard Functions
# ---------------------------------------------------------------------------
# Guards are callables: (ArbitrationState) → None
# They raise an exception if the guard condition fails.
# Multiple guards can be chained per transition.


def _guard_evidence_sufficient(state: ArbitrationState) -> None:
    """Ensure evidence collection has produced usable data before negotiation."""
    if not state.evidence_sufficient:
        raise InsufficientEvidenceError(
            f"Cannot proceed to NEGOTIATION: evidence_sufficient=False "
            f"for dispute {state.dispute_id}. "
            f"Collected {len(state.processed_evidence)} evidence item(s)."
        )


def _guard_budget_not_exhausted(state: ArbitrationState) -> None:
    """Prevent transitions when the ₹5 budget cap has been hit."""
    if state.budget_status.is_exhausted:
        raise BudgetExhaustedError(
            f"Budget exhausted for dispute {state.dispute_id}: "
            f"₹{state.budget_status.consumed_inr:.4f} / "
            f"₹{state.budget_status.budget_cap_inr:.2f} spent."
        )


def _guard_confidence_sufficient(state: ArbitrationState) -> None:
    """Require minimum confidence score before issuing a RESOLVED decision."""
    if state.confidence_score < MIN_CONFIDENCE_TO_RESOLVE:
        raise ConfidenceTooLowError(
            f"Confidence {state.confidence_score:.2f} below minimum "
            f"{MIN_CONFIDENCE_TO_RESOLVE:.2f} — must escalate to human arbitrator."
        )


def _guard_not_high_value_dispute(state: ArbitrationState) -> None:
    """High-value disputes (> ₹50,000) must always be escalated, never auto-resolved."""
    amount = state.request.dispute_amount_inr
    if amount > ESCALATION_THRESHOLD_INR:
        raise DisputeTransitionError(
            state.status,
            DisputeStatus.RESOLVED,
            f"Dispute amount ₹{amount:,.2f} exceeds auto-resolution threshold "
            f"₹{ESCALATION_THRESHOLD_INR:,.2f}. Must escalate.",
        )


def _guard_decision_set(state: ArbitrationState) -> None:
    """Ensure a concrete decision has been set before marking as RESOLVED."""
    if state.decision == DecisionType.PENDING:
        raise DisputeTransitionError(
            state.status,
            DisputeStatus.RESOLVED,
            "Cannot resolve dispute without a concrete decision (not PENDING).",
        )


# Map (from, to) → list of guard functions to run in order
_TRANSITION_GUARDS: dict[
    tuple[DisputeStatus, DisputeStatus], list[Callable[[ArbitrationState], None]]
] = {
    (DisputeStatus.EVIDENCE_COLLECTION, DisputeStatus.NEGOTIATION): [
        _guard_budget_not_exhausted,
        _guard_evidence_sufficient,
    ],
    (DisputeStatus.NEGOTIATION, DisputeStatus.RESOLVED): [
        _guard_budget_not_exhausted,
        _guard_confidence_sufficient,
        _guard_not_high_value_dispute,
        _guard_decision_set,
    ],
    (DisputeStatus.EVIDENCE_COLLECTION, DisputeStatus.RESOLVED): [
        _guard_budget_not_exhausted,
        _guard_confidence_sufficient,
        _guard_not_high_value_dispute,
        _guard_decision_set,
    ],
}


# ---------------------------------------------------------------------------
# Refund Calculator
# ---------------------------------------------------------------------------


def calculate_refund_amount(state: ArbitrationState) -> float:
    """
    Apply ONDC refund policy to derive the appropriate refund amount.

    Uses the dispute type, confidence score, and dispute amount to look up
    the correct refund percentage from shared/constants.py REFUND_POLICY.

    Returns the refund amount in INR (rounded to 2 decimal places).
    """
    dispute_type = state.request.dispute_type.value
    policy = REFUND_POLICY.get(dispute_type, {})

    if not policy:
        # Unknown type — conservative default: 50%
        multiplier = 0.50
    elif state.confidence_score >= CONFIDENCE_HIGH:
        multiplier = policy.get("high_confidence", 1.0)
    elif state.confidence_score >= CONFIDENCE_MEDIUM:
        multiplier = policy.get("medium_confidence", 0.75)
    else:
        multiplier = policy.get("low_confidence", 0.50)

    refund = round(state.request.dispute_amount_inr * multiplier, 2)
    return refund


# ---------------------------------------------------------------------------
# State Machine Class
# ---------------------------------------------------------------------------


class DisputeStateMachine:
    """
    Validates and executes state transitions for a single dispute arbitration.

    Usage (inside LangGraph nodes):
        sm = DisputeStateMachine(state)
        sm.transition(DisputeStatus.EVIDENCE_COLLECTION)

    The machine mutates `state` in-place and appends audit entries.
    It does NOT persist state — that is Hindsight's responsibility.
    """

    def __init__(self, state: ArbitrationState) -> None:
        self.state = state

    # ── Public API ──────────────────────────────────────────────────────────

    def transition(
        self,
        to_status: DisputeStatus,
        reason: str = "",
        skip_guards: bool = False,
    ) -> ArbitrationState:
        """
        Attempt a state transition. Runs all registered guards first.

        Args:
            to_status:    The target DisputeStatus.
            reason:       Human-readable reason, stored in audit trail.
            skip_guards:  True only for rollback operations (Hindsight).

        Returns:
            The mutated ArbitrationState (same object, mutated in-place).

        Raises:
            DisputeTransitionError:  If the transition is not in the table.
            InsufficientEvidenceError, BudgetExhaustedError,
            ConfidenceTooLowError:   If a guard condition fails.
        """
        from_status = self.state.status

        # ── 1. Validate the transition is in the table ────────────────────
        self._assert_transition_allowed(from_status, to_status)

        # ── 2. Run guard functions ────────────────────────────────────────
        if not skip_guards:
            self._run_guards(from_status, to_status)

        # ── 3. Compute refund amount when resolving ───────────────────────
        if to_status == DisputeStatus.RESOLVED and self.state.refund_amount_inr == 0.0:
            self.state.refund_amount_inr = calculate_refund_amount(self.state)

        # ── 4. Apply transition ───────────────────────────────────────────
        self.state.status = to_status

        # ── 5. Log audit entry ────────────────────────────────────────────
        audit_event = _STATUS_TO_AUDIT_EVENT.get(to_status, AuditEventType.DISPUTE_INITIATED)
        description = reason or f"Transitioned from {from_status.value} to {to_status.value}"
        self.state.add_audit(
            event_type=audit_event,
            description=description,
            metadata={
                "from_status": from_status.value,
                "to_status": to_status.value,
                "confidence_score": self.state.confidence_score,
                "budget_consumed_inr": self.state.budget_status.consumed_inr,
            },
        )

        return self.state

    def can_transition(self, to_status: DisputeStatus) -> bool:
        """Return True if the transition is allowed WITHOUT running guards."""
        from_status = self.state.status
        if to_status == DisputeStatus.ROLLED_BACK:
            return from_status in _ROLLBACKABLE_STATES
        return (from_status, to_status) in _ALLOWED_TRANSITIONS

    def get_allowed_transitions(self) -> list[DisputeStatus]:
        """
        Return all valid next states from the current status.
        Used by Member 3's backend to populate the frontend status panel.
        """
        current = self.state.status
        allowed: list[DisputeStatus] = []

        for (from_s, to_s) in _ALLOWED_TRANSITIONS:
            if from_s == current:
                allowed.append(to_s)

        # ROLLED_BACK is always appended if current is rollbackable
        if current in _ROLLBACKABLE_STATES and DisputeStatus.ROLLED_BACK not in allowed:
            allowed.append(DisputeStatus.ROLLED_BACK)

        return allowed

    def is_terminal(self) -> bool:
        """Return True if no further agent actions are possible."""
        return self.state.status in _TERMINAL_STATES

    def should_escalate(self) -> bool:
        """
        Heuristic: returns True if the dispute should be escalated rather than
        auto-resolved. Called by the arbitrator decision node.
        """
        state = self.state

        # Rule 1: High-value dispute
        if state.request.dispute_amount_inr > ESCALATION_THRESHOLD_INR:
            state.should_escalate = True
            return True

        # Rule 2: Budget exhausted
        if state.budget_status.is_exhausted:
            state.should_escalate = True
            return True

        # Rule 3: Low confidence after max negotiation rounds
        if state.confidence_score < MIN_CONFIDENCE_TO_RESOLVE and state.negotiation_attempted:
            state.should_escalate = True
            return True

        # Rule 4: Iteration limit hit
        if state.iteration_count >= state.max_iterations:
            state.should_escalate = True
            return True

        return False

    def force_escalate(self, reason: str) -> ArbitrationState:
        """
        Directly escalate a dispute, bypassing normal transition guards.
        Used when budget exhaustion or system errors force an early exit.
        """
        self.state.should_escalate = True
        self.state.error_message = reason

        # Allow escalation from any non-terminal state
        if not self.is_terminal():
            self.state.status = DisputeStatus.ESCALATED
            self.state.add_audit(
                event_type=AuditEventType.ESCALATED_TO_HUMAN,
                description=f"Force-escalated: {reason}",
                metadata={"reason": reason, "forced": True},
            )
        return self.state

    # ── Private Helpers ─────────────────────────────────────────────────────

    def _assert_transition_allowed(
        self, from_status: DisputeStatus, to_status: DisputeStatus
    ) -> None:
        """Raise DisputeTransitionError if the (from, to) pair is not in the table."""
        if to_status == DisputeStatus.ROLLED_BACK:
            if from_status not in _ROLLBACKABLE_STATES:
                raise DisputeTransitionError(
                    from_status,
                    to_status,
                    f"{from_status.value} is not rollbackable.",
                )
            return

        if (from_status, to_status) not in _ALLOWED_TRANSITIONS:
            raise DisputeTransitionError(
                from_status,
                to_status,
                f"No path from {from_status.value} to {to_status.value} "
                f"in the transition table.",
            )

    def _run_guards(
        self, from_status: DisputeStatus, to_status: DisputeStatus
    ) -> None:
        """Run all guard functions for this (from, to) pair in order."""
        guards = _TRANSITION_GUARDS.get((from_status, to_status), [])
        for guard_fn in guards:
            guard_fn(self.state)


# ---------------------------------------------------------------------------
# Audit Event Mapping
# ---------------------------------------------------------------------------

_STATUS_TO_AUDIT_EVENT: dict[DisputeStatus, AuditEventType] = {
    DisputeStatus.PENDING: AuditEventType.DISPUTE_INITIATED,
    DisputeStatus.EVIDENCE_COLLECTION: AuditEventType.EVIDENCE_COLLECTED,
    DisputeStatus.NEGOTIATION: AuditEventType.NEGOTIATION_SENT,
    DisputeStatus.RESOLVED: AuditEventType.DECISION_FINALISED,
    DisputeStatus.ESCALATED: AuditEventType.ESCALATED_TO_HUMAN,
    DisputeStatus.ROLLED_BACK: AuditEventType.ROLLBACK_TRIGGERED,
}


# ---------------------------------------------------------------------------
# Factory Function (used by arbitrator.py)
# ---------------------------------------------------------------------------


def create_state_machine(state: ArbitrationState) -> DisputeStateMachine:
    """
    Factory used by LangGraph nodes to get a state machine bound to current state.

    Example (in arbitrator.py):
        sm = create_state_machine(state)
        sm.transition(DisputeStatus.EVIDENCE_COLLECTION, reason="Dispute accepted")
    """
    return DisputeStateMachine(state)


# ---------------------------------------------------------------------------
# Self-test (run: python agents/core/state_machine.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    from datetime import datetime
    from shared.schemas import (
        ArbitrationState, BudgetStatus, DisputeRequest,
        DisputeType, EvidenceItem, EvidenceType,
    )

    print("=" * 60)
    print("NyayaNode — State Machine Self-Test")
    print("=" * 60)

    def _make_state(amount: float = 500.0) -> ArbitrationState:
        req = DisputeRequest(
            buyer_id="buyer_001",
            seller_id="seller_042",
            logistics_id="lsp_007",
            order_id="order_xyz",
            dispute_type=DisputeType.DAMAGED_ITEM,
            evidence=[EvidenceItem(type=EvidenceType.TEXT, content="Broken package")],
            dispute_amount_inr=amount,
        )
        budget = BudgetStatus(dispute_id=req.dispute_id)
        return ArbitrationState(
            dispute_id=req.dispute_id,
            request=req,
            budget_status=budget,
        )

    errors: list[str] = []

    # ── Test 1: Happy path ───────────────────────────────────────────────
    print("\n[1] Happy path: PENDING → EVIDENCE → NEGOTIATION → RESOLVED")
    state = _make_state()
    state.budget_status.dispute_id = state.dispute_id
    sm = create_state_machine(state)

    sm.transition(DisputeStatus.EVIDENCE_COLLECTION, "Dispute accepted")
    assert state.status == DisputeStatus.EVIDENCE_COLLECTION, "Failed EVIDENCE_COLLECTION"

    state.evidence_sufficient = True
    sm.transition(DisputeStatus.NEGOTIATION, "Evidence sufficient")
    assert state.status == DisputeStatus.NEGOTIATION, "Failed NEGOTIATION"

    state.confidence_score = 0.88
    state.decision = DecisionType.FULL_REFUND
    sm.transition(DisputeStatus.RESOLVED, "Settlement agreed")
    assert state.status == DisputeStatus.RESOLVED, "Failed RESOLVED"
    assert state.refund_amount_inr > 0, "Refund not calculated"
    print(f"   ✅ Passed — refund: ₹{state.refund_amount_inr}, audit entries: {len(state.audit_trail)}")

    # ── Test 2: Illegal transition ───────────────────────────────────────
    print("\n[2] Illegal transition: RESOLVED → NEGOTIATION (must raise)")
    state2 = _make_state()
    state2.budget_status.dispute_id = state2.dispute_id
    sm2 = create_state_machine(state2)
    sm2.transition(DisputeStatus.EVIDENCE_COLLECTION, "Accept")
    state2.evidence_sufficient = True
    sm2.transition(DisputeStatus.NEGOTIATION, "Evidence ok")
    state2.confidence_score = 0.90
    state2.decision = DecisionType.FULL_REFUND
    sm2.transition(DisputeStatus.RESOLVED, "Done")

    try:
        sm2.transition(DisputeStatus.NEGOTIATION, "Should fail")
        errors.append("Test 2 FAILED: should have raised DisputeTransitionError")
    except DisputeTransitionError as e:
        print(f"   ✅ Correctly blocked: {e}")

    # ── Test 3: Guard — insufficient evidence ────────────────────────────
    print("\n[3] Guard: evidence_sufficient=False blocks NEGOTIATION")
    state3 = _make_state()
    state3.budget_status.dispute_id = state3.dispute_id
    sm3 = create_state_machine(state3)
    sm3.transition(DisputeStatus.EVIDENCE_COLLECTION, "Accept")

    try:
        sm3.transition(DisputeStatus.NEGOTIATION, "Should fail")
        errors.append("Test 3 FAILED: should have raised InsufficientEvidenceError")
    except InsufficientEvidenceError as e:
        print(f"   ✅ Correctly blocked: {e}")

    # ── Test 4: Guard — low confidence blocks RESOLVED ───────────────────
    print("\n[4] Guard: confidence < 0.70 blocks RESOLVED")
    state4 = _make_state()
    state4.budget_status.dispute_id = state4.dispute_id
    sm4 = create_state_machine(state4)
    sm4.transition(DisputeStatus.EVIDENCE_COLLECTION, "Accept")
    state4.evidence_sufficient = True
    sm4.transition(DisputeStatus.NEGOTIATION, "Evidence ok")
    state4.confidence_score = 0.45   # too low
    state4.decision = DecisionType.PARTIAL_REFUND

    try:
        sm4.transition(DisputeStatus.RESOLVED, "Should fail")
        errors.append("Test 4 FAILED: should have raised ConfidenceTooLowError")
    except ConfidenceTooLowError as e:
        print(f"   ✅ Correctly blocked: {e}")

    # ── Test 5: High-value dispute blocks auto-resolution ────────────────
    print("\n[5] Guard: amount > ₹50,000 blocks RESOLVED")
    state5 = _make_state(amount=75_000.0)
    state5.budget_status.dispute_id = state5.dispute_id
    sm5 = create_state_machine(state5)
    sm5.transition(DisputeStatus.EVIDENCE_COLLECTION, "Accept")
    state5.evidence_sufficient = True
    sm5.transition(DisputeStatus.NEGOTIATION, "Evidence ok")
    state5.confidence_score = 0.95
    state5.decision = DecisionType.FULL_REFUND

    try:
        sm5.transition(DisputeStatus.RESOLVED, "Should fail")
        errors.append("Test 5 FAILED: should have raised DisputeTransitionError for high value")
    except DisputeTransitionError as e:
        print(f"   ✅ Correctly blocked: {e}")

    # ── Test 6: Rollback from any state ──────────────────────────────────
    print("\n[6] Rollback from NEGOTIATION")
    state6 = _make_state()
    state6.budget_status.dispute_id = state6.dispute_id
    sm6 = create_state_machine(state6)
    sm6.transition(DisputeStatus.EVIDENCE_COLLECTION, "Accept")
    state6.evidence_sufficient = True
    sm6.transition(DisputeStatus.NEGOTIATION, "Evidence ok")
    sm6.transition(DisputeStatus.ROLLED_BACK, "Hindsight rollback triggered", skip_guards=True)
    assert state6.status == DisputeStatus.ROLLED_BACK
    print(f"   ✅ Rolled back — audit entries: {len(state6.audit_trail)}")

    # ── Test 7: Force escalate ───────────────────────────────────────────
    print("\n[7] Force escalate from EVIDENCE_COLLECTION")
    state7 = _make_state()
    state7.budget_status.dispute_id = state7.dispute_id
    sm7 = create_state_machine(state7)
    sm7.transition(DisputeStatus.EVIDENCE_COLLECTION, "Accept")
    sm7.force_escalate("Budget exhausted mid-collection")
    assert state7.status == DisputeStatus.ESCALATED
    print(f"   ✅ Escalated — reason: {state7.error_message}")

    # ── Test 8: Refund calculation ───────────────────────────────────────
    print("\n[8] Refund calculation across confidence bands")
    for confidence, expected_pct, label in [
        (0.90, 1.00, "high"),
        (0.65, 0.75, "medium"),
        (0.30, 0.50, "low"),
    ]:
        s = _make_state(amount=1000.0)
        s.budget_status.dispute_id = s.dispute_id
        s.confidence_score = confidence
        refund = calculate_refund_amount(s)
        expected = round(1000.0 * expected_pct, 2)
        assert refund == expected, f"Expected ₹{expected}, got ₹{refund}"
        print(f"   ✅ {label} confidence ({confidence}) → ₹{refund} ({expected_pct*100:.0f}%)")

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if errors:
        print(f"❌ {len(errors)} TEST(S) FAILED:")
        for e in errors:
            print(f"   • {e}")
        sys.exit(1)
    else:
        print("🎉 ALL STATE MACHINE TESTS PASSED")
        print("=" * 60)
