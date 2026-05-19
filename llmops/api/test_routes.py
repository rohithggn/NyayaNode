"""
NyayaNode - AI Dispute Arbitration System for ONDC
Integration tests for /api/dispute/* routes.

Run from the project root:
    python3 -m llmops.api.test_routes
"""

import json
import sys

from flask import Flask

from llmops.api.routes import create_api_routes


# ---------------------------------------------------------------------------
# Test harness setup
# ---------------------------------------------------------------------------

def build_test_app():
    """Create a minimal Flask app with the API routes mounted."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    active_disputes: dict = {}
    create_api_routes(app, active_disputes)
    return app


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------

_PASS = "\033[32mPASS\033[0m"
_FAIL = "\033[31mFAIL\033[0m"
_results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    tag = _PASS if condition else _FAIL
    msg = f"  [{tag}] {name}"
    if detail:
        msg += f"\n         {detail}"
    print(msg)
    _results.append((name, condition, detail))
    return condition


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def run_tests():
    app    = build_test_app()
    client = app.test_client()

    print("\n" + "=" * 60)
    print("NyayaNode — API Route Tests")
    print("=" * 60)

    # ------------------------------------------------------------------ #
    # Test 1: Start a dispute                                              #
    # ------------------------------------------------------------------ #
    print("\nTest 1: POST /api/dispute/start")
    r    = client.post(
        "/api/dispute/start",
        data=json.dumps({"dispute_id": "ONDC-TEST-001", "max_budget": 5.0}),
        content_type="application/json",
    )
    body = r.get_json()
    check("Status code is 201",          r.status_code == 201,          f"got {r.status_code}")
    check("status == 'started'",         body.get("status") == "started")
    check("dispute_id echoed correctly", body.get("dispute_id") == "ONDC-TEST-001")
    check("max_budget echoed correctly", body.get("max_budget") == 5.0,  f"got {body.get('max_budget')}")

    # ------------------------------------------------------------------ #
    # Test 2: Run a cheap step                                             #
    # ------------------------------------------------------------------ #
    print("\nTest 2: POST /api/dispute/step — fetch tracking status")
    r    = client.post(
        "/api/dispute/step",
        data=json.dumps({"dispute_id": "ONDC-TEST-001",
                         "prompt": "fetch tracking status for ORD-001"}),
        content_type="application/json",
    )
    body = r.get_json()
    check("Status code is 200",          r.status_code == 200,          f"got {r.status_code}")
    check("step == 1",                   body.get("step") == 1,         f"got {body.get('step')}")
    check("task_type == 'simple_read'",  body.get("task_type") == "simple_read",
          f"got {body.get('task_type')}")
    check("model == 'gemini-flash'",     body.get("model") == "gemini-flash",
          f"got {body.get('model')}")
    check("tier == 'cheap'",             body.get("tier") == "cheap",   f"got {body.get('tier')}")
    check("downgraded == False",         body.get("downgraded") is False)
    check("cost > 0",                    (body.get("cost") or 0) > 0,   f"got {body.get('cost')}")
    check("response is mock string",
          body.get("response") == "[SIMULATED LLM RESPONSE]")

    # ------------------------------------------------------------------ #
    # Test 3: Run a premium step                                           #
    # ------------------------------------------------------------------ #
    print("\nTest 3: POST /api/dispute/step — issue final verdict")
    r    = client.post(
        "/api/dispute/step",
        data=json.dumps({"dispute_id": "ONDC-TEST-001",
                         "prompt": "issue the final verdict"}),
        content_type="application/json",
    )
    body = r.get_json()
    check("Status code is 200",           r.status_code == 200,          f"got {r.status_code}")
    check("step == 2",                    body.get("step") == 2,         f"got {body.get('step')}")
    check("task_type == 'final_verdict'", body.get("task_type") == "final_verdict",
          f"got {body.get('task_type')}")
    check("model == 'gpt-4o'",            body.get("model") == "gpt-4o", f"got {body.get('model')}")
    check("tier == 'premium'",            body.get("tier") == "premium", f"got {body.get('tier')}")

    # ------------------------------------------------------------------ #
    # Test 4: Get cost report                                              #
    # ------------------------------------------------------------------ #
    print("\nTest 4: GET /api/dispute/cost/ONDC-TEST-001")
    r    = client.get("/api/dispute/cost/ONDC-TEST-001")
    body = r.get_json()
    check("Status code is 200",           r.status_code == 200,          f"got {r.status_code}")
    check("dispute_id correct",           body.get("dispute_id") == "ONDC-TEST-001")
    check("total_steps == 2",             body.get("total_steps") == 2,  f"got {body.get('total_steps')}")
    check("total_cost > 0",              (body.get("total_cost") or 0) > 0)
    check("budget_remaining < 5.0",      (body.get("budget_remaining") or 5.0) < 5.0)
    check("call_log has 2 entries",       len(body.get("call_log", [])) == 2,
          f"got {len(body.get('call_log', []))}")
    check("models_used is a list",        isinstance(body.get("models_used"), list))

    # ------------------------------------------------------------------ #
    # Test 5: List all disputes                                            #
    # ------------------------------------------------------------------ #
    print("\nTest 5: GET /api/dispute/all")
    r    = client.get("/api/dispute/all")
    body = r.get_json()
    check("Status code is 200",           r.status_code == 200,          f"got {r.status_code}")
    disputes = body.get("disputes", [])
    check("disputes list has 1 entry",    len(disputes) == 1,            f"got {len(disputes)}")
    if disputes:
        d = disputes[0]
        check("dispute_id present",       d.get("dispute_id") == "ONDC-TEST-001")
        check("total_spent present",      "total_spent"      in d)
        check("budget_remaining present", "budget_remaining" in d)
        check("total_steps present",      "total_steps"      in d)
        check("budget_exhausted present", "budget_exhausted" in d)

    # ------------------------------------------------------------------ #
    # Test 6: Delete dispute                                               #
    # ------------------------------------------------------------------ #
    print("\nTest 6: DELETE /api/dispute/ONDC-TEST-001")
    r    = client.delete("/api/dispute/ONDC-TEST-001")
    body = r.get_json()
    check("Status code is 200",           r.status_code == 200,          f"got {r.status_code}")
    check("status == 'deleted'",          body.get("status") == "deleted")
    check("dispute_id echoed",            body.get("dispute_id") == "ONDC-TEST-001")

    # ------------------------------------------------------------------ #
    # Test 7: Cost after deletion → 404                                   #
    # ------------------------------------------------------------------ #
    print("\nTest 7: GET /api/dispute/cost/ONDC-TEST-001 (expect 404)")
    r    = client.get("/api/dispute/cost/ONDC-TEST-001")
    body = r.get_json()
    check("Status code is 404",           r.status_code == 404,          f"got {r.status_code}")
    check("error field present",          "error" in body,               f"got {body}")

    # ------------------------------------------------------------------ #
    # Summary                                                              #
    # ------------------------------------------------------------------ #
    total  = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = total - passed

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} passed", end="")
    if failed:
        print(f"  |  {failed} FAILED", end="")
    print("\n" + "=" * 60)

    return failed == 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
