"""
NyayaNode - AI Dispute Arbitration System for ONDC
Agent Harness: orchestrates multi-step LLM calls for a single dispute,
wiring together routing, budget tracking, and call logging.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from llmops.cost_tracker import DisputeBudget, BudgetExhaustedError
from llmops.model_router import route, classify_task


# ---------------------------------------------------------------------------
# 1. Per-call record
# ---------------------------------------------------------------------------

@dataclass
class AgentCall:
    step: int
    prompt: str
    model: str
    task_type: str
    tier: str
    downgraded: bool
    input_tokens: int
    output_tokens: int
    cost: float
    response: str


# ---------------------------------------------------------------------------
# 2. Harness
# ---------------------------------------------------------------------------

class AgentHarness:
    """
    Orchestrates a sequence of LLM calls for one ONDC dispute.
    Handles routing, token estimation, budget tracking, and graceful
    fallback to the cheapest model when the budget is nearly exhausted.
    """

    # Cheapest fallback model used when budget is exhausted mid-call
    _FALLBACK_MODEL = "gemini-flash"
    _FALLBACK_TIER  = "cheap"

    def __init__(self, dispute_id: str, max_budget_inr: float = 5.0) -> None:
        self.dispute_id = dispute_id
        self.budget = DisputeBudget(dispute_id, max_budget_inr)
        self._calls: List[AgentCall] = []
        self._step = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_tokens(prompt: str) -> tuple[int, int]:
        """Rough token estimate: input = word_count × 2, output = 150."""
        input_tokens  = len(prompt.split()) * 2
        output_tokens = 150
        return input_tokens, output_tokens

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def call(
        self,
        prompt: str,
        mock_response: Optional[str] = None,
    ) -> AgentCall:
        """
        Execute one step of the dispute pipeline.

        Steps:
          a. Route the prompt to the best model given remaining budget.
          b. Estimate input/output tokens.
          c. Attempt to record the cost via DisputeBudget.add_call().
          d. On BudgetExhaustedError, fall back to gemini-flash and retry.
          e. Build and store an AgentCall record.
          f. Return the AgentCall.
        """
        self._step += 1

        # a. Routing decision
        routing = route(prompt, self.budget.budget_remaining)
        model      = routing["model"]
        task_type  = routing["task_type"]
        tier       = routing["tier"]
        downgraded = routing["downgraded"]

        # b. Token estimation
        input_tokens, output_tokens = self._estimate_tokens(prompt)

        # c. Attempt budget recording; d. fallback on exhaustion
        try:
            cost_entry = self.budget.add_call(model, input_tokens, output_tokens)
        except BudgetExhaustedError:
            # Force cheapest model and try once more
            model      = self._FALLBACK_MODEL
            tier       = self._FALLBACK_TIER
            downgraded = True
            cost_entry = self.budget.add_call(model, input_tokens, output_tokens)

        # e. Build record
        agent_call = AgentCall(
            step          = self._step,
            prompt        = prompt,
            model         = model,
            task_type     = task_type,
            tier          = tier,
            downgraded    = downgraded,
            input_tokens  = input_tokens,
            output_tokens = output_tokens,
            cost          = cost_entry["cost_this_call"],
            response      = mock_response or "[NO RESPONSE]",
        )
        self._calls.append(agent_call)
        return agent_call

    def get_report(self) -> dict:
        """Return a full summary of all calls made for this dispute."""
        models_used = list(dict.fromkeys(c.model for c in self._calls))  # ordered, unique
        downgrades  = sum(1 for c in self._calls if c.downgraded)

        call_log = [
            {
                "step":          c.step,
                "task_type":     c.task_type,
                "model":         c.model,
                "tier":          c.tier,
                "downgraded":    c.downgraded,
                "input_tokens":  c.input_tokens,
                "output_tokens": c.output_tokens,
                "cost":          c.cost,
                "prompt":        c.prompt,
                "response":      c.response,
            }
            for c in self._calls
        ]

        summary = self.budget.get_summary()

        return {
            "dispute_id":       self.dispute_id,
            "total_steps":      self._step,
            "total_cost":       summary["total_spent"],
            "budget_remaining": summary["budget_remaining"],
            "budget_exhausted": summary["budget_exhausted"],
            "models_used":      models_used,
            "downgrades":       downgrades,
            "call_log":         call_log,
        }


# ---------------------------------------------------------------------------
# 3. Demo / smoke-test — full 6-step dispute resolution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    MOCK = "[SIMULATED LLM RESPONSE]"

    steps = [
        "fetch the tracking status for order ORD-2025-BLR-441",
        "format the evidence: buyer photo shows cracked screen, delivery scan shows drop event",
        "analyze the claim: buyer says phone arrived broken, seller says item was perfect",
        "compare buyer and seller statements and identify discrepancy",
        "propose a settlement: 80% refund given logistics drop event confirmed",
        "issue the final verdict for dispute ONDC-2025-TEST-001",
    ]

    harness = AgentHarness("ONDC-2025-TEST-001", max_budget_inr=5.0)

    for prompt in steps:
        result = harness.call(prompt, mock_response=MOCK)

        print(f"\n{'='*60}")
        print(f"Step {result.step}: {result.task_type.upper()}")
        print(f"{'='*60}")
        print(f"  Prompt    : {result.prompt}")
        print(f"  Model     : {result.model}  [{result.tier}]")
        print(f"  Tokens    : {result.input_tokens} in / {result.output_tokens} out")
        print(f"  Cost      : ₹{result.cost:.6f}")
        print(f"  Response  : {result.response}")

        if result.downgraded:
            print(f"  ⚠  WARNING: Model was downgraded due to budget constraints.")

    print(f"\n{'='*60}")
    print("FULL DISPUTE REPORT")
    print(f"{'='*60}")

    report = harness.get_report()

    # Print report without the verbose call_log first
    summary = {k: v for k, v in report.items() if k != "call_log"}
    print(json.dumps(summary, indent=2))

    print("\n--- Call Log ---")
    for entry in report["call_log"]:
        log_line = {k: v for k, v in entry.items() if k != "prompt"}  # keep it readable
        print(json.dumps(log_line, indent=2))
