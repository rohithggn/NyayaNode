"""
NyayaNode - AI Dispute Arbitration System for ONDC
LLM Cost Tracker: tracks per-call and cumulative token costs per dispute.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any


# ---------------------------------------------------------------------------
# 1. Model cost configuration
# ---------------------------------------------------------------------------

@dataclass
class ModelCostConfig:
    model_name: str
    cost_per_1k_input_tokens: float   # in INR
    cost_per_1k_output_tokens: float  # in INR
    capability_tier: str              # "cheap", "mid", or "premium"


# ---------------------------------------------------------------------------
# 2. Model registry
# ---------------------------------------------------------------------------

MODEL_REGISTRY: Dict[str, ModelCostConfig] = {
    "gemini-flash": ModelCostConfig(
        model_name="gemini-flash",
        cost_per_1k_input_tokens=0.01,
        cost_per_1k_output_tokens=0.03,
        capability_tier="cheap",
    ),
    "gpt-3.5-turbo": ModelCostConfig(
        model_name="gpt-3.5-turbo",
        cost_per_1k_input_tokens=0.08,
        cost_per_1k_output_tokens=0.10,
        capability_tier="mid",
    ),
    "gpt-4o": ModelCostConfig(
        model_name="gpt-4o",
        cost_per_1k_input_tokens=0.83,
        cost_per_1k_output_tokens=2.50,
        capability_tier="premium",
    ),
}


# ---------------------------------------------------------------------------
# 3. Custom exception
# ---------------------------------------------------------------------------

class BudgetExhaustedError(Exception):
    """Raised when a dispute's LLM budget has been fully consumed."""


# ---------------------------------------------------------------------------
# 4. DisputeBudget
# ---------------------------------------------------------------------------

class DisputeBudget:
    """Tracks cumulative LLM spend for a single ONDC dispute."""

    def __init__(self, dispute_id: str, max_budget_inr: float = 5.0) -> None:
        self.dispute_id = dispute_id
        self.max_budget_inr = max_budget_inr
        self._total_spent: float = 0.0
        self._call_log: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def budget_remaining(self) -> float:
        return max(0.0, self.max_budget_inr - self._total_spent)

    @property
    def budget_exhausted(self) -> bool:
        return self._total_spent >= self.max_budget_inr

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_call(
        self,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
    ) -> Dict[str, Any]:
        """
        Record one LLM call and update the running cost.

        Raises:
            KeyError: if model_name is not in MODEL_REGISTRY.
            BudgetExhaustedError: if the budget was already exhausted
                                  before this call.
        Returns:
            dict with keys: model, cost_this_call, total_spent,
                            budget_remaining, budget_exhausted
        """
        if self.budget_exhausted:
            raise BudgetExhaustedError(
                f"Budget exhausted for dispute '{self.dispute_id}'. "
                f"Spent ₹{self._total_spent:.4f} of ₹{self.max_budget_inr:.2f}."
            )

        config = MODEL_REGISTRY[model_name]

        input_cost  = (input_tokens  / 1000) * config.cost_per_1k_input_tokens
        output_cost = (output_tokens / 1000) * config.cost_per_1k_output_tokens
        cost_this_call = input_cost + output_cost

        self._total_spent += cost_this_call

        entry = {
            "model": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_this_call": round(cost_this_call, 6),
            "total_spent": round(self._total_spent, 6),
            "budget_remaining": round(self.budget_remaining, 6),
            "budget_exhausted": self.budget_exhausted,
        }
        self._call_log.append(entry)

        return {
            "model": entry["model"],
            "cost_this_call": entry["cost_this_call"],
            "total_spent": entry["total_spent"],
            "budget_remaining": entry["budget_remaining"],
            "budget_exhausted": entry["budget_exhausted"],
        }

    def get_summary(self) -> Dict[str, Any]:
        """Return a full summary of budget usage for this dispute."""
        return {
            "dispute_id": self.dispute_id,
            "max_budget": self.max_budget_inr,
            "total_spent": round(self._total_spent, 6),
            "budget_remaining": round(self.budget_remaining, 6),
            "budget_exhausted": self.budget_exhausted,
            "total_calls": len(self._call_log),
            "call_log": self._call_log,
        }


# ---------------------------------------------------------------------------
# 5. Demo / smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    budget = DisputeBudget("ONDC-2025-TEST-001", max_budget_inr=5.0)

    calls = [
        ("gemini-flash",  500, 200),
        ("gemini-flash",  500, 200),
        ("gpt-3.5-turbo", 500, 200),
        ("gpt-4o",        500, 200),
    ]

    for i, (model, inp, out) in enumerate(calls, start=1):
        print(f"\n--- Call {i}: {model} ({inp} input / {out} output tokens) ---")
        try:
            result = budget.add_call(model, inp, out)
            print(json.dumps(result, indent=2))
        except BudgetExhaustedError as exc:
            print(f"[BudgetExhaustedError] {exc}")

    print("\n========== Full Budget Summary ==========")
    print(json.dumps(budget.get_summary(), indent=2))
