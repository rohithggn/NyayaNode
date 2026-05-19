# NyayaNode — LLMOps & Cost Engine

## What This Does

NyayaNode uses a **Cascadeflow** cost routing system to resolve ONDC disputes at a fraction of the cost of calling a single premium model for every step. Each dispute prompt is classified by task complexity, then routed to the cheapest model capable of handling it — with a hard per-dispute budget cap that automatically downgrades to a cheaper model if funds run low.

## Architecture

| File | Role |
|------|------|
| `cost_tracker.py` | Tracks INR cost per dispute; raises `BudgetExhaustedError` when the cap is hit |
| `model_router.py` | Routes tasks to cheap / mid / premium models based on keyword classification and remaining budget |
| `agent_harness.py` | Wraps every LLM call with routing, token estimation, budget enforcement, and a full call log |
| `dashboard/` | Live Flask cost dashboard with auto-refreshing budget gauge and model switch log |
| `api/routes.py` | REST API endpoints (`/api/dispute/*`) mountable on any Flask app |
| `demo/` | Pre-loaded demo scenarios showing cheap, full-pipeline, and budget-exhausted cases |

## How to Run

### Install

```bash
pip3 install flask
```

### Run demo

```bash
PYTHONPATH=. python3 llmops/demo/demo_disputes.py
```

### Run dashboard

```bash
PYTHONPATH=. python3 llmops/dashboard/app.py
```

Then open http://localhost:5001

### Run API tests

```bash
PYTHONPATH=. python3 llmops/api/test_routes.py
```

## Cost Comparison

| Approach | Cost per dispute |
|----------|-----------------|
| Without Cascadeflow (GPT-4o only) | ₹12–47 |
| With Cascadeflow routing | ₹0.45–3.80 |
| Savings | 85–95% |

## Demo Scenarios

- **ONDC-DEMO-001** — Simple tracking dispute (cheap tier, gemini-flash throughout)
- **ONDC-DEMO-002** — Damaged item with drop sensor (full pipeline: cheap → mid → premium)
- **ONDC-DEMO-003** — Budget exhausted scenario (hard cap at ₹0.50, shows forced downgrade)
