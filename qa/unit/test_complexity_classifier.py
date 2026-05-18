"""
qa/unit/test_complexity_classifier.py
Tests for the Cascadeflow complexity classifier and model routing logic.
These tests enforce the cost-saving routing rules that keep NyayaNode
under ₹5.00 per dispute.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest

from agents.cascadeflow.complexity_classifier import (
    COMPLEXITY_TIERS,
    classify_complexity,
    get_model_for_task,
)

# Canonical model names — single source of truth for assertions
MODEL_8B   = "llama-3.1-8b-instant"
MODEL_MIX  = "mixtral-8x7b-32768"
MODEL_70B  = "llama-3.1-70b-versatile"


# ---------------------------------------------------------------------------
# Test 1
# ---------------------------------------------------------------------------


def test_low_value_single_evidence_is_simple():
    """
    ₹499 dispute with 1 evidence item → SIMPLE tier → cheapest model.

    SIMPLE disputes must never be routed to expensive models.
    Misrouting 100 SIMPLE disputes to 70b costs ~₹215 extra per day.
    """
    tier = classify_complexity(dispute_amount_inr=499.0, evidence_count=1)

    assert tier == "SIMPLE", (
        f"₹499 / 1 evidence should be SIMPLE, got '{tier}'"
    )
    assert COMPLEXITY_TIERS["SIMPLE"] == MODEL_8B, (
        "SIMPLE tier must map to the cheapest model"
    )

    # Confirm the model returned for a generic task matches the tier
    model = get_model_for_task("FINAL_DECISION", tier)
    assert model == MODEL_8B


# ---------------------------------------------------------------------------
# Test 2
# ---------------------------------------------------------------------------


def test_medium_value_is_medium_complexity():
    """
    ₹799 dispute with 2 evidence items → MEDIUM tier.

    Disputes between ₹500-₹2000 warrant a mid-tier model for better
    reasoning without the cost of the 70b model.
    """
    tier = classify_complexity(dispute_amount_inr=799.0, evidence_count=2)

    assert tier == "MEDIUM", (
        f"₹799 / 2 evidence should be MEDIUM, got '{tier}'"
    )
    assert COMPLEXITY_TIERS["MEDIUM"] == MODEL_MIX

    # Boundary: exactly ₹500 is still MEDIUM (> 500 condition)
    tier_boundary = classify_complexity(dispute_amount_inr=500.01, evidence_count=1)
    assert tier_boundary == "MEDIUM"

    # Boundary: exactly ₹500 with 1 evidence is SIMPLE
    tier_simple = classify_complexity(dispute_amount_inr=500.0, evidence_count=1)
    assert tier_simple == "SIMPLE"


# ---------------------------------------------------------------------------
# Test 3
# ---------------------------------------------------------------------------


def test_high_value_is_complex():
    """
    ₹8999 dispute → COMPLEX tier regardless of evidence count.

    High-value disputes always use the most capable model to minimise
    the risk of a wrong decision on a large refund.
    """
    for evidence_count in (0, 1, 2, 5, 10):
        tier = classify_complexity(
            dispute_amount_inr=8999.0, evidence_count=evidence_count
        )
        assert tier == "COMPLEX", (
            f"₹8999 with {evidence_count} evidence items should be COMPLEX, got '{tier}'"
        )

    # Boundary: exactly ₹2000 is NOT complex (> 2000 condition)
    tier_boundary = classify_complexity(dispute_amount_inr=2000.0, evidence_count=1)
    assert tier_boundary != "COMPLEX", (
        "₹2000 exactly should not be COMPLEX (boundary is > 2000)"
    )

    # Just above ₹2000 is COMPLEX
    tier_above = classify_complexity(dispute_amount_inr=2000.01, evidence_count=1)
    assert tier_above == "COMPLEX"


# ---------------------------------------------------------------------------
# Test 4
# ---------------------------------------------------------------------------


def test_multi_party_always_complex():
    """
    Multi-party disputes always route to COMPLEX tier for safety.

    Even a ₹50 multi-party dispute involves coordination risk that
    requires the most capable model.
    """
    for amount in (50.0, 499.0, 799.0, 1500.0, 8999.0):
        tier = classify_complexity(
            dispute_amount_inr=amount,
            evidence_count=1,
            is_multi_party=True,
        )
        assert tier == "COMPLEX", (
            f"Multi-party dispute at ₹{amount} should be COMPLEX, got '{tier}'"
        )


# ---------------------------------------------------------------------------
# Test 5
# ---------------------------------------------------------------------------


def test_evidence_parsing_always_uses_cheap_model():
    """
    EVIDENCE_PARSING task always uses the 8b model regardless of dispute
    complexity — this is the core cost-saving routing rule.

    Parsing evidence is a mechanical extraction task; it does not require
    the reasoning depth of the 70b model. Routing it to 8b saves ~₹0.40
    per dispute on average.
    """
    # Even a COMPLEX dispute must use 8b for evidence parsing
    complex_tier = classify_complexity(
        dispute_amount_inr=8999.0, evidence_count=5
    )
    assert complex_tier == "COMPLEX"

    model = get_model_for_task("EVIDENCE_PARSING", complex_tier)
    assert model == MODEL_8B, (
        f"EVIDENCE_PARSING must always use {MODEL_8B}, got '{model}'"
    )

    # Same rule applies for all tiers
    for tier in ("SIMPLE", "MEDIUM", "COMPLEX"):
        assert get_model_for_task("EVIDENCE_PARSING", tier) == MODEL_8B

    # STATUS_CHECK and FORMATTING also use cheap model
    for task in ("STATUS_CHECK", "FORMATTING"):
        assert get_model_for_task(task, "COMPLEX") == MODEL_8B, (
            f"Task '{task}' must always use {MODEL_8B}"
        )


# ---------------------------------------------------------------------------
# Test 6
# ---------------------------------------------------------------------------


def test_final_decision_uses_tier_model():
    """
    Final decisions use the tier-appropriate model.

    FINAL_DECISION is the most consequential task — it determines the
    refund outcome. It must use the model matched to the dispute's
    complexity, not the cheapest model.
    """
    # SIMPLE → 8b
    model_simple = get_model_for_task("FINAL_DECISION", "SIMPLE")
    assert model_simple == MODEL_8B, (
        f"FINAL_DECISION/SIMPLE should use {MODEL_8B}, got '{model_simple}'"
    )

    # MEDIUM → mixtral
    model_medium = get_model_for_task("FINAL_DECISION", "MEDIUM")
    assert model_medium == MODEL_MIX, (
        f"FINAL_DECISION/MEDIUM should use {MODEL_MIX}, got '{model_medium}'"
    )

    # COMPLEX → 70b
    model_complex = get_model_for_task("FINAL_DECISION", "COMPLEX")
    assert model_complex == MODEL_70B, (
        f"FINAL_DECISION/COMPLEX should use {MODEL_70B}, got '{model_complex}'"
    )

    # NEGOTIATION also follows tier routing
    assert get_model_for_task("NEGOTIATION", "COMPLEX") == MODEL_70B
    assert get_model_for_task("NEGOTIATION", "MEDIUM") == MODEL_MIX
