"""
qa/unit/test_state_machine.py
State machine transition tests for NyayaNode dispute lifecycle.

These tests validate LEGAL STATE TRANSITIONS, not AI decisions.
They are written against a local transition table and will be updated
to import from agents/ once Member 1 ships the state machine module.
"""

import os
import sys
from dataclasses import dataclass

import pytest

# Ensure the monorepo root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from shared.schemas import DisputeStatus

# ---------------------------------------------------------------------------
# Local transition table (mirrors what agents/ will implement)
# Update the import below once Member 1 ships agents/state_machine.py:
#   from agents.state_machine import VALID_TRANSITIONS, apply_transition
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[tuple[str, str], str] = {
    ("OPEN", "AGENT_STARTED"): "IN_PROGRESS",
    ("IN_PROGRESS", "DECISION_ISSUED"): "RESOLVED",
    ("IN_PROGRESS", "BUDGET_EXHAUSTED"): "ESCALATED",
    ("IN_PROGRESS", "LOW_CONFIDENCE"): "ESCALATED",
}


def apply_transition(
    from_state: str,
    event: str,
    table: dict[tuple[str, str], str] = VALID_TRANSITIONS,
) -> str | None:
    """
    Return the target state for (from_state, event), or None if the
    transition is not defined (i.e. it is illegal).
    """
    return table.get((from_state, event))


# ---------------------------------------------------------------------------
# Helper dataclass for documenting transition scenarios
# ---------------------------------------------------------------------------


@dataclass
class StateTransition:
    from_state: str
    event: str
    to_state: str


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_valid_transitions_from_open():
    """
    Proves OPEN can transition to IN_PROGRESS when the agent starts.
    Any other event from OPEN must not produce a valid target state.
    """
    t = StateTransition(from_state="OPEN", event="AGENT_STARTED", to_state="IN_PROGRESS")

    result = apply_transition(t.from_state, t.event)

    assert result == t.to_state, (
        f"Expected OPEN --[AGENT_STARTED]--> IN_PROGRESS, got '{result}'"
    )

    # Sanity: an undefined event from OPEN must return None
    assert apply_transition("OPEN", "DECISION_ISSUED") is None
    assert apply_transition("OPEN", "BUDGET_EXHAUSTED") is None


def test_valid_transitions_from_in_progress():
    """
    Proves IN_PROGRESS can only go to RESOLVED or ESCALATED.
    No other target state is legal from IN_PROGRESS.
    """
    valid_cases = [
        StateTransition("IN_PROGRESS", "DECISION_ISSUED", "RESOLVED"),
        StateTransition("IN_PROGRESS", "BUDGET_EXHAUSTED", "ESCALATED"),
        StateTransition("IN_PROGRESS", "LOW_CONFIDENCE", "ESCALATED"),
    ]

    for t in valid_cases:
        result = apply_transition(t.from_state, t.event)
        assert result == t.to_state, (
            f"Expected IN_PROGRESS --[{t.event}]--> {t.to_state}, got '{result}'"
        )

    # No transition from IN_PROGRESS should lead back to OPEN
    assert apply_transition("IN_PROGRESS", "AGENT_STARTED") is None

    # Collect all reachable states from IN_PROGRESS
    reachable = {
        v
        for (from_s, _), v in VALID_TRANSITIONS.items()
        if from_s == "IN_PROGRESS"
    }
    assert reachable == {"RESOLVED", "ESCALATED"}, (
        f"IN_PROGRESS must only reach RESOLVED or ESCALATED, got {reachable}"
    )


def test_invalid_transition_resolved_to_open():
    """
    Proves a RESOLVED dispute cannot be re-opened without explicit appeal logic.
    This prevents double-refund attacks.
    """
    # Attempting to restart an already-resolved dispute must not yield a state
    result = apply_transition("RESOLVED", "AGENT_STARTED")
    assert result is None, (
        f"RESOLVED --[AGENT_STARTED]--> should be illegal, but got '{result}'"
    )

    # No event whatsoever should move RESOLVED to any other state
    all_events = {event for (_, event) in VALID_TRANSITIONS}
    for event in all_events:
        assert apply_transition("RESOLVED", event) is None, (
            f"RESOLVED must be terminal; unexpected transition on event '{event}'"
        )


def test_escalated_is_terminal():
    """
    Proves ESCALATED is a terminal state — no further automated transitions.
    Prevents infinite escalation loops.
    """
    all_events = {event for (_, event) in VALID_TRANSITIONS}

    for event in all_events:
        result = apply_transition("ESCALATED", event)
        assert result is None, (
            f"ESCALATED must be terminal; unexpected transition on event '{event}'"
        )

    # Explicitly verify the most tempting illegal transition
    assert apply_transition("ESCALATED", "AGENT_STARTED") is None
    assert apply_transition("ESCALATED", "DECISION_ISSUED") is None


def test_all_dispute_statuses_have_transitions_defined():
    """
    Proves every DisputeStatus enum value has at least one transition defined
    OR is explicitly a terminal state. Missing transitions are silent bugs.

    Terminal states (RESOLVED, ESCALATED) are intentionally absent as sources
    in VALID_TRANSITIONS — that is correct and expected.
    """
    all_statuses = {member.value for member in DisputeStatus}

    # States that appear as a source in the transition table
    source_states = {from_s for (from_s, _) in VALID_TRANSITIONS}

    # States that appear as a target (reachable states)
    target_states = set(VALID_TRANSITIONS.values())

    # Every status must be either a source (has outgoing transitions)
    # or a target (is reachable), or both.
    for status in all_statuses:
        is_source = status in source_states
        is_target = status in target_states
        assert is_source or is_target, (
            f"DisputeStatus.{status} is neither a source nor a target in "
            f"VALID_TRANSITIONS. It is unreachable and has no defined behaviour."
        )

    # Specifically: OPEN and IN_PROGRESS must have outgoing transitions
    assert "OPEN" in source_states, "OPEN must have at least one outgoing transition"
    assert "IN_PROGRESS" in source_states, (
        "IN_PROGRESS must have at least one outgoing transition"
    )

    # RESOLVED and ESCALATED must be reachable
    assert "RESOLVED" in target_states, "RESOLVED must be reachable"
    assert "ESCALATED" in target_states, "ESCALATED must be reachable"
