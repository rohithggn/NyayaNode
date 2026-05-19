"""
NyayaNode - AI Dispute Arbitration System for ONDC
Demo: simulates 3 pre-loaded dispute scenarios end-to-end.
"""

from llmops.agent_harness import AgentHarness
from llmops.cost_tracker import BudgetExhaustedError

MOCK = "[SIMULATED LLM RESPONSE]"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def banner(title: str) -> None:
    line = "=" * 60
    print(f"\n{line}")
    print(f"  {title}")
    print(line)


def print_step(call) -> None:
    downgrade_flag = "  ⚠  DOWNGRADED" if call.downgraded else ""
    print(
        f"  Step {call.step:>2} | {call.task_type:<18} | "
        f"{call.model:<15} | {call.tier:<8} | "
        f"₹{call.cost:.6f}{downgrade_flag}"
    )


def print_summary(report: dict) -> None:
    print(f"\n  {'─'*54}")
    print(f"  dispute_id      : {report['dispute_id']}")
    print(f"  total_steps     : {report['total_steps']}")
    print(f"  total_cost      : ₹{report['total_cost']:.6f}")
    print(f"  budget_remaining: ₹{report['budget_remaining']:.6f}")
    print(f"  budget_exhausted: {report['budget_exhausted']}")
    print(f"  models_used     : {', '.join(report['models_used'])}")
    print(f"  downgrades      : {report['downgrades']}")
    print(f"  {'─'*54}")
    print(
        f"  Cost: ₹{report['total_cost']:.4f} | "
        f"Steps: {report['total_steps']} | "
        f"Downgrades: {report['downgrades']}"
    )


def run_scenario(dispute_id: str, max_budget: float, steps: list[str]) -> dict:
    """Run all steps for one scenario; returns the final report."""
    harness = AgentHarness(dispute_id, max_budget_inr=max_budget)

    print(f"\n  {'Step':>6} | {'Task Type':<18} | {'Model':<15} | {'Tier':<8} | Cost")
    print(f"  {'─'*54}")

    for prompt in steps:
        try:
            call = harness.call(prompt, mock_response=MOCK)
            print_step(call)
        except BudgetExhaustedError as exc:
            print(f"\n  [BudgetExhaustedError] {exc}")
            break

    return harness.get_report()


# ---------------------------------------------------------------------------
# Scenario 1 — Simple tracking dispute (cheap tier throughout)
# ---------------------------------------------------------------------------

banner("SCENARIO 1: Cheap Dispute — Simple Tracking Issue")

report1 = run_scenario(
    dispute_id="ONDC-DEMO-001",
    max_budget=5.0,
    steps=[
        "fetch tracking status for order ORD-2025-BLR-441",
        "get order details for dispute ONDC-DEMO-001",
        "format the evidence into structured report",
        "issue the final verdict: item delivered, dispute rejected",
    ],
)
print_summary(report1)


# ---------------------------------------------------------------------------
# Scenario 2 — Damaged item with drop sensor (full pipeline)
# ---------------------------------------------------------------------------

banner("SCENARIO 2: Edge Case — Damaged Item with Drop Sensor")

report2 = run_scenario(
    dispute_id="ONDC-DEMO-002",
    max_budget=5.0,
    steps=[
        "fetch tracking status for order ORD-2025-MUM-887",
        "analyze the claim: buyer says phone arrived with cracked screen",
        "compare buyer photo evidence vs logistics drop sensor telemetry",
        "propose a settlement: 90% refund due to confirmed drop event in transit",
        "issue the final verdict for ONDC-DEMO-002",
    ],
)
print_summary(report2)


# ---------------------------------------------------------------------------
# Scenario 3 — Budget exhausted (hard cap demo)
# ---------------------------------------------------------------------------

banner("SCENARIO 3: Budget Exhausted — Hard Cap Demo (max ₹0.50)")

report3 = run_scenario(
    dispute_id="ONDC-DEMO-003",
    max_budget=0.5,
    steps=[
        "fetch tracking status for order ORD-2025-DEL-332",
        "analyze the claim: buyer says wrong item delivered",
        "compare buyer and seller statements",
        "propose a settlement of full refund",
        "issue the final verdict for ONDC-DEMO-003",
    ],
)
print_summary(report3)


# ---------------------------------------------------------------------------
# Cross-scenario comparison
# ---------------------------------------------------------------------------

banner("CROSS-SCENARIO COMPARISON")

scenarios = [
    ("ONDC-DEMO-001", "Cheap Dispute",          report1),
    ("ONDC-DEMO-002", "Damaged Item",           report2),
    ("ONDC-DEMO-003", "Budget Exhausted (₹0.5)", report3),
]

print(f"\n  {'ID':<16} {'Label':<28} {'Cost':>10}  {'Steps':>6}  {'Downgrades':>10}")
print(f"  {'─'*72}")
for dispute_id, label, report in scenarios:
    print(
        f"  {dispute_id:<16} {label:<28} "
        f"₹{report['total_cost']:>8.4f}  "
        f"{report['total_steps']:>6}  "
        f"{report['downgrades']:>10}"
    )
print()
