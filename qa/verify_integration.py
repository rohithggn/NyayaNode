#!/usr/bin/env python3
"""
NyayaNode QA Integration Verifier
Run this to confirm Member 5's QA layer is correctly set up.
Usage: python qa/verify_integration.py
"""

import ast
import json
import os
import sys

# Ensure monorepo root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Check harness
# ---------------------------------------------------------------------------

def check(label: str, fn) -> bool:
    try:
        fn()
        print(f"  \u2705 {label}")
        return True
    except Exception as e:
        print(f"  \u274c {label}")
        print(f"     Error: {e}")
        return False


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_scenarios_import():
    from qa.synthetic.scenarios import ALL_SCENARIOS  # noqa: F401


def check_scenarios_fields():
    from qa.synthetic.scenarios import ALL_SCENARIOS
    assert len(ALL_SCENARIOS) == 5, (
        f"Expected 5 scenarios, got {len(ALL_SCENARIOS)}"
    )
    required = [
        "name",
        "dispute_type",
        "expected_decision",
        "expected_status",
        "max_budget_inr",
        "mock_logistics_status",
        "mock_seller_stance",
    ]
    for s in ALL_SCENARIOS:
        for field in required:
            assert field in s, (
                f"Missing field '{field}' in scenario '{s['name']}'"
            )


def check_schemas():
    from shared.schemas import (  # noqa: F401
        CascadeflowAudit,
        DisputeDecision,
        DisputeRequest,
        DisputeResponse,
        DisputeStatus,
        DisputeType,
        EvidenceItem,
        ModelCall,
    )
    assert len(DisputeType) == 4, (
        f"DisputeType must have 4 values, got {len(DisputeType)}"
    )
    assert len(DisputeDecision) == 4, (
        f"DisputeDecision must have 4 values, got {len(DisputeDecision)}"
    )


def check_factory():
    from qa.synthetic.dispute_generator import DisputeFactory
    factory = DisputeFactory(seed=42)
    disputes = factory.generate(2)
    assert len(disputes) == 2, f"Expected 2 disputes, got {len(disputes)}"
    assert disputes[0].dispute_id != disputes[1].dispute_id, (
        "Generated disputes must have unique IDs"
    )


def check_fixtures():
    # Resolve paths relative to the monorepo root
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    disputes_path = os.path.join(root, "qa", "fixtures", "disputes.json")
    with open(disputes_path, encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 3, f"Expected 3 fixture disputes, got {len(data)}"

    cascade_path = os.path.join(root, "qa", "fixtures", "cascadeflow_sample.json")
    with open(cascade_path, encoding="utf-8") as f:
        audit = json.load(f)
    assert "session_id" in audit, "cascadeflow_sample.json missing 'session_id'"
    assert "model_calls" in audit, "cascadeflow_sample.json missing 'model_calls'"
    assert len(audit["model_calls"]) == 3, (
        f"Expected 3 model_calls, got {len(audit['model_calls'])}"
    )


def check_cost_tracker():
    from decimal import Decimal
    from agents.cascadeflow.cost_tracker import CostTracker
    tracker = CostTracker(budget_inr=Decimal("5.00"))
    assert tracker.total_cost_inr == Decimal("0.000"), (
        f"Initial total_cost_inr must be 0.000, got {tracker.total_cost_inr}"
    )
    assert tracker.emergency_mode is False, "Initial emergency_mode must be False"
    assert tracker.escalated_to_human is False, (
        "Initial escalated_to_human must be False"
    )


def check_conftest():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    conftest_path = os.path.join(root, "qa", "conftest.py")
    with open(conftest_path, encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    fixture_names = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    required = ["async_client", "dispute_factory", "mock_groq", "all_scenarios"]
    for name in required:
        assert name in fixture_names, (
            f"Missing fixture '{name}' in qa/conftest.py"
        )


def check_cicd():
    import yaml  # pyyaml — installed in venv

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    qa_yml = os.path.join(root, ".github", "workflows", "qa.yml")
    with open(qa_yml, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert "schema-contract-check" in config["jobs"], (
        "Missing 'schema-contract-check' job in qa.yml"
    )
    assert "unit-tests" in config["jobs"], (
        "Missing 'unit-tests' job in qa.yml"
    )
    assert config["jobs"]["unit-tests"]["needs"] == "schema-contract-check", (
        "unit-tests job must depend on schema-contract-check"
    )

    assert os.path.exists(os.path.join(root, "setup_hooks.sh")), (
        "setup_hooks.sh not found at repo root"
    )
    assert os.path.exists(os.path.join(root, "qa", "run_all.sh")), (
        "qa/run_all.sh not found"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("\n\U0001f3db\ufe0f  NyayaNode QA Layer Verification")
    print("=" * 45)

    results = []

    print("\n[1] Scenarios")
    results.append(check("ALL_SCENARIOS imports correctly",       check_scenarios_import))
    results.append(check("All 5 scenarios have required fields",  check_scenarios_fields))

    print("\n[2] Schemas")
    results.append(check("shared/schemas.py imports with correct enums", check_schemas))

    print("\n[3] DisputeFactory")
    results.append(check("DisputeFactory generates unique disputes", check_factory))

    print("\n[4] Fixtures")
    results.append(check("Fixture JSON files are valid", check_fixtures))

    print("\n[5] CostTracker")
    results.append(check("CostTracker initializes correctly", check_cost_tracker))

    print("\n[6] conftest.py")
    results.append(check("conftest.py has all required fixtures", check_conftest))

    print("\n[7] CI/CD Files")
    results.append(check("GitHub Actions + hook scripts exist", check_cicd))

    # Summary
    passed = sum(1 for r in results if r)
    total  = len(results)

    print(f"\n{'=' * 45}")
    if passed == total:
        print(f"\u2705 All {total}/{total} checks passed.")
        print("   Member 5's QA layer is ready.")
        print("   Share this output with the team lead.\n")
        return 0
    else:
        print(f"\u274c {total - passed}/{total} checks FAILED.")
        print("   Fix the errors above before the demo.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
