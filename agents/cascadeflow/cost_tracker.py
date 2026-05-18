"""
agents/cascadeflow/cost_tracker.py
Cost tracker for Cascadeflow. Tracks INR spend per dispute session.
Member 2 will replace the internals — the interface is the contract.
"""

from decimal import Decimal, ROUND_HALF_UP

USD_TO_INR = Decimal("84.0")

# Model costs in USD per 1M tokens
MODEL_COSTS_USD_PER_1M = {
    "llama-3.1-8b-instant":    {"input": Decimal("0.05"),  "output": Decimal("0.08")},
    "mixtral-8x7b-32768":      {"input": Decimal("0.27"),  "output": Decimal("0.27")},
    "llama-3.1-70b-versatile": {"input": Decimal("0.59"),  "output": Decimal("0.79")},
}

EMERGENCY_MODE_THRESHOLD_INR = Decimal("0.50")
EMERGENCY_MODEL = "llama-3.1-8b-instant"
EMERGENCY_MAX_TOKENS = 200


class CostTracker:
    def __init__(self, budget_inr: Decimal = Decimal("5.00")):
        self.budget_inr = budget_inr
        self.total_cost_inr = Decimal("0.000")
        self.calls: list[dict] = []
        self.emergency_mode = False
        self.escalated_to_human = False
        self.escalation_reason: str | None = None

    def record_call(
        self, model: str, prompt_tokens: int, completion_tokens: int
    ) -> Decimal:
        """
        Records a model call, updates running total. Returns cost in INR.
        Raises RuntimeError if the session has already been escalated to human
        (budget exhausted) — further inference is blocked.
        """
        if self.escalated_to_human:
            raise RuntimeError(
                "Session escalated to human review. "
                "No further model calls are permitted for this dispute."
            )

        costs = MODEL_COSTS_USD_PER_1M[model]
        cost_usd = (
            (Decimal(prompt_tokens) / Decimal("1000000")) * costs["input"]
            + (Decimal(completion_tokens) / Decimal("1000000")) * costs["output"]
        )
        cost_inr = (cost_usd * USD_TO_INR).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )
        self.total_cost_inr += cost_inr
        self.calls.append(
            {
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost_inr": cost_inr,
            }
        )
        self._check_budget()
        return cost_inr

    def remaining_inr(self) -> Decimal:
        return (self.budget_inr - self.total_cost_inr).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )

    def _check_budget(self) -> None:
        remaining = self.remaining_inr()
        if remaining < EMERGENCY_MODE_THRESHOLD_INR and not self.emergency_mode:
            self.emergency_mode = True
        if self.total_cost_inr >= self.budget_inr:
            self.escalated_to_human = True
            self.escalation_reason = "BUDGET_EXHAUSTED"

    def get_next_model_config(self) -> dict:
        """Returns model config for next call, respecting emergency mode."""
        if self.emergency_mode:
            return {"model": EMERGENCY_MODEL, "max_tokens": EMERGENCY_MAX_TOKENS}
        return {"model": "llama-3.1-70b-versatile", "max_tokens": 2048}

    def calculate_savings(self, hypothetical_cost_inr: Decimal) -> dict:
        """Calculate savings vs a hypothetical expensive baseline."""
        savings_inr = (hypothetical_cost_inr - self.total_cost_inr).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        savings_percent = (
            (savings_inr / hypothetical_cost_inr) * Decimal("100")
        ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return {"savings_inr": savings_inr, "savings_percent": savings_percent}
