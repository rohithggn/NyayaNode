# NyayaNode QA Layer — Member 5

## Quick Start (other members)

### Run unit tests before every push
```bash
.venv/Scripts/pytest qa/unit/ -v
# Must pass — these are deployment blockers
```

### Check if QA layer is set up correctly
```bash
.venv/Scripts/python qa/verify_integration.py
```

### Run full test suite (needs backend running)
```bash
bash qa/run_all.sh all
```

### Install the git pre-push hook
```bash
bash setup_hooks.sh
```

> **Windows note:** Always use `.venv/Scripts/pytest` (or activate the venv first with
> `source .venv/Scripts/activate`). Bare `pytest` resolves to the system Python which
> does not have the QA packages installed.

---

## Test Architecture

| Layer       | Command                              | When to run                          |
|-------------|--------------------------------------|--------------------------------------|
| Unit        | `pytest qa/unit/`                    | Every commit                         |
| Integration | `pytest qa/integration/`             | After Member 3's backend is up       |
| E2E         | `pytest qa/e2e/`                     | Before final deployment              |
| Full        | `bash qa/run_all.sh all`             | Before demo                          |

---

## The 5 Demo Scenarios (single source of truth)

All 5 scenarios live in **`qa/synthetic/scenarios.py`**.  
Every member imports from this file. **Never hardcode dispute data.**

| # | Name                        | Expected Decision    |
|---|-----------------------------|----------------------|
| 1 | Damaged Kurta               | FULL_REFUND          |
| 2 | Claimed Not Delivered       | REJECTED             |
| 3 | Wrong Size Sent             | PARTIAL_REFUND       |
| 4 | Refund Being Ignored        | FULL_REFUND          |
| 5 | Expensive Watch (Ambiguous) | PENDING → ESCALATED  |

```python
# Correct way to use scenarios in any test
from qa.synthetic.scenarios import SCENARIO_1, ALL_SCENARIOS
```

---

## Budget Contract

Every scenario must resolve within **₹5.00 inference budget**.  
Tests will fail if any scenario exceeds this limit.

```
₹500 dispute → ₹5 AI cost → viable unit economics
```

---

## Mocking Groq API (no real API calls during tests)

Use the `mock_groq` fixture from `conftest.py`:

```python
async def test_something(mock_groq, async_client):
    # All calls to api.groq.com are intercepted
    # Returns deterministic FULL_REFUND response
    ...
```

**Never** call the real Groq API in unit or integration tests.  
Only e2e tests may call real APIs (marked `@pytest.mark.slow`).

---

## File Map

```
qa/
├── conftest.py                  # Master pytest config + all fixtures
├── pytest.ini                   # asyncio_mode=auto, markers
├── requirements.txt             # Pinned QA dependencies
├── run_all.sh                   # Full suite runner (unit|integration|e2e|all)
├── verify_integration.py        # Standalone health check (no pytest needed)
├── README.md                    # This file
│
├── synthetic/
│   ├── scenarios.py             # 5 canonical scenarios (single source of truth)
│   └── dispute_generator.py     # Faker-based DisputeFactory
│
├── fixtures/
│   ├── disputes.json            # 3 static dispute fixtures (deterministic UUIDs)
│   └── cascadeflow_sample.json  # Realistic CascadeflowAudit fixture
│
├── unit/                        # Fast tests — no external services
│   ├── test_schemas.py          # 7 schema contract tests (DEPLOYMENT BLOCKERS)
│   ├── test_state_machine.py    # 5 state transition tests
│   ├── test_cost_tracker.py     # 5 budget math tests (Decimal only)
│   ├── test_complexity_classifier.py  # 6 routing logic tests
│   └── test_budget_harness.py   # 4 emergency mode + isolation tests
│
├── integration/                 # Skip gracefully if backend unreachable
│   ├── test_api_disputes.py     # 8 REST endpoint tests
│   ├── test_api_mock_ondc.py    # 4 ONDC mock party tests
│   ├── test_frontend_api.py     # 3 frontend API tests
│   ├── test_sse_stream.py       # 5 SSE streaming tests
│   └── test_agent_full_run.py   # 1 master integration test (10 assertions)
│
└── e2e/                         # Full pipeline — needs live backend
    ├── test_demo_scenarios.py   # 7 tests (5 parametrized scenarios + 2 guards)
    ├── test_budget_enforcement.py  # 2 budget guarantee tests
    └── test_full_dispute_flow.py   # 1 complete 8-stage pipeline test

setup_hooks.sh                   # One-time git pre-push hook installer
.github/workflows/qa.yml         # 4-job CI pipeline
```

---

## CI Pipeline (GitHub Actions)

```
schema-contract-check  →  unit-tests  →  integration-tests
                                       synthetic-data-check (parallel)
```

- **`schema-contract-check`** — BLOCKER: must pass before any merge
- **`unit-tests`** — runs all 27 unit tests + uploads coverage XML
- **`integration-tests`** — runs with `BACKEND_URL=localhost:9999` (all skip = OK in CI)
- **`synthetic-data-check`** — validates all 5 scenarios + dispute generator smoke test

---

## Coverage

Unit tests achieve **100% coverage** on stub modules:

| Module                                    | Coverage |
|-------------------------------------------|----------|
| `agents/cascadeflow/cost_tracker.py`      | 100%     |
| `agents/cascadeflow/complexity_classifier.py` | 100% |
| `shared/schemas.py`                       | 100%     |

Coverage report generated at: `qa/coverage_report/index.html`
