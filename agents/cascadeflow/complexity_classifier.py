"""
agents/cascadeflow/complexity_classifier.py
Classifies dispute complexity to route to the appropriate model tier.
Member 2 will replace the internals — the interface is the contract.
"""

from decimal import Decimal

COMPLEXITY_TIERS = {
    "SIMPLE":  "llama-3.1-8b-instant",       # <₹500, single party, clear evidence
    "MEDIUM":  "mixtral-8x7b-32768",          # ₹500-₹2000, multi-party
    "COMPLEX": "llama-3.1-70b-versatile",     # >₹2000, ambiguous, high-value
}


def classify_complexity(
    dispute_amount_inr: float,
    evidence_count: int,
    is_multi_party: bool = False,
) -> str:
    """Returns complexity tier: SIMPLE, MEDIUM, or COMPLEX."""
    if dispute_amount_inr > 2000 or is_multi_party:
        return "COMPLEX"
    if dispute_amount_inr > 500 or evidence_count > 3:
        return "MEDIUM"
    return "SIMPLE"


def get_model_for_task(task_type: str, complexity: str) -> str:
    """Returns the appropriate model given task type and complexity."""
    simple_tasks = {"EVIDENCE_PARSING", "STATUS_CHECK", "FORMATTING"}
    if task_type in simple_tasks:
        return "llama-3.1-8b-instant"
    return COMPLEXITY_TIERS.get(complexity, "llama-3.1-70b-versatile")
