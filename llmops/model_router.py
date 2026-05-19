"""
NyayaNode - AI Dispute Arbitration System for ONDC
Model Router: classifies dispute tasks and selects the appropriate LLM
based on task complexity and remaining budget.
"""

from enum import Enum
from typing import Tuple

from llmops.cost_tracker import MODEL_REGISTRY, ModelCostConfig


# ---------------------------------------------------------------------------
# 1. Task type taxonomy
# ---------------------------------------------------------------------------

class TaskType(Enum):
    SIMPLE_READ     = "simple_read"       # reading tracking status, fetching order details
    FORMAT_EVIDENCE = "format_evidence"   # formatting buyer/seller data into structured form
    ANALYZE_CLAIM   = "analyze_claim"     # comparing buyer claim vs seller claim
    NEGOTIATE       = "negotiate"         # generating settlement proposals
    FINAL_VERDICT   = "final_verdict"     # issuing the legal arbitration decision


# ---------------------------------------------------------------------------
# 2. Task → capability tier mapping
# ---------------------------------------------------------------------------

TASK_TIER_MAP: dict[TaskType, str] = {
    TaskType.SIMPLE_READ:     "cheap",
    TaskType.FORMAT_EVIDENCE: "cheap",
    TaskType.ANALYZE_CLAIM:   "mid",
    TaskType.NEGOTIATE:       "mid",
    TaskType.FINAL_VERDICT:   "premium",
}

# Canonical model for each tier (sourced from MODEL_REGISTRY)
_TIER_MODEL: dict[str, str] = {
    "cheap":   "gemini-flash",
    "mid":     "gpt-3.5-turbo",
    "premium": "gpt-4o",
}

# Tier ordering for budget-cap comparisons
_TIER_RANK: dict[str, int] = {"cheap": 0, "mid": 1, "premium": 2}


# ---------------------------------------------------------------------------
# 3. Task classification
# ---------------------------------------------------------------------------

# Keyword lists are checked in priority order (most specific first).
_KEYWORD_MAP: list[tuple[TaskType, list[str]]] = [
    (TaskType.FINAL_VERDICT,   ["verdict", "decision", "ruling", "judgment", "final"]),
    (TaskType.NEGOTIATE,       ["settlement", "propose", "negotiate", "offer", "compromise"]),
    (TaskType.ANALYZE_CLAIM,   ["compare", "analyze", "claim", "buyer says", "seller says"]),
    (TaskType.FORMAT_EVIDENCE, ["format", "structure", "organize", "summarize evidence"]),
    (TaskType.SIMPLE_READ,     ["tracking", "status", "order details", "fetch", "get"]),
]


def classify_task(prompt: str) -> TaskType:
    """
    Classify a natural-language prompt into a TaskType by keyword matching.
    Checks in priority order (highest-stakes tasks first) so that a prompt
    containing both "fetch" and "verdict" is correctly classified as
    FINAL_VERDICT rather than SIMPLE_READ.

    Defaults to ANALYZE_CLAIM when no keywords match.
    """
    lower = prompt.lower()
    for task_type, keywords in _KEYWORD_MAP:
        if any(kw in lower for kw in keywords):
            return task_type
    return TaskType.ANALYZE_CLAIM


# ---------------------------------------------------------------------------
# 4. Model selection with budget guardrails
# ---------------------------------------------------------------------------

def select_model(task_type: TaskType, budget_remaining: float) -> Tuple[str, bool]:
    """
    Choose the best model for a task given the remaining budget.

    Budget guardrails:
      - budget_remaining < 1.0  → force "cheap" tier regardless of task
      - budget_remaining < 2.0  → cap at "mid"  tier (no premium)

    Returns:
        (model_name, downgraded)
        downgraded=True when the tier was forced lower than the task requires.
    """
    required_tier = TASK_TIER_MAP[task_type]

    # Determine the budget-imposed ceiling
    if budget_remaining < 1.0:
        allowed_tier = "cheap"
    elif budget_remaining < 2.0:
        allowed_tier = "mid"
    else:
        allowed_tier = "premium"  # no restriction

    # Apply the lower of required vs allowed
    if _TIER_RANK[required_tier] <= _TIER_RANK[allowed_tier]:
        effective_tier = required_tier
        downgraded = False
    else:
        effective_tier = allowed_tier
        downgraded = True

    return _TIER_MODEL[effective_tier], downgraded


# ---------------------------------------------------------------------------
# 5. Unified routing entry point
# ---------------------------------------------------------------------------

def route(prompt: str, budget_remaining: float) -> dict:
    """
    Classify a prompt and select the appropriate model in one call.

    Returns:
        {
            "task_type":        str   – TaskType enum value,
            "tier":             str   – effective capability tier,
            "model":            str   – model name from MODEL_REGISTRY,
            "budget_remaining": float – passed through for reference,
            "downgraded":       bool  – True if budget forced a lower tier,
        }
    """
    task_type = classify_task(prompt)
    model_name, downgraded = select_model(task_type, budget_remaining)

    # Derive the effective tier from the chosen model
    effective_tier = next(
        cfg.capability_tier
        for cfg in MODEL_REGISTRY.values()
        if cfg.model_name == model_name
    )

    return {
        "task_type":        task_type.value,
        "tier":             effective_tier,
        "model":            model_name,
        "budget_remaining": budget_remaining,
        "downgraded":       downgraded,
    }


# ---------------------------------------------------------------------------
# 6. Demo / smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    test_cases: list[tuple[str, float]] = [
        ("fetch the tracking status for order ORD-001",   5.0),
        ("get order details for this dispute",            5.0),
        ("format the evidence into a structured report",  5.0),
        ("analyze the claim: buyer says item was broken", 5.0),
        ("compare the buyer and seller statements",       5.0),
        ("propose a settlement of 50% refund",            5.0),
        ("negotiate a compromise with the seller",        5.0),
        ("issue the final verdict for this dispute",      5.0),
        ("what is the ruling on this case",               5.0),
        ("fetch tracking status for order ORD-002",       0.5),  # budget-constrained
    ]

    for prompt, budget in test_cases:
        result = route(prompt, budget)
        downgrade_note = " ⚠ DOWNGRADED" if result["downgraded"] else ""
        print(f"\nPrompt : {prompt!r}")
        print(f"Budget : ₹{budget:.1f}")
        print(f"Result : {json.dumps(result, indent=2)}{downgrade_note}")
