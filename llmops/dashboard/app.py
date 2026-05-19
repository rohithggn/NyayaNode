"""
NyayaNode - AI Dispute Arbitration System for ONDC
Dashboard API: Flask server exposing dispute lifecycle endpoints.
"""

import dataclasses
from flask import Flask, request, jsonify, render_template

from llmops.agent_harness import AgentHarness

app = Flask(__name__)

# In-memory store: dispute_id -> AgentHarness instance
ACTIVE_DISPUTES: dict[str, AgentHarness] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _harness_to_dict(call_result) -> dict:
    """Convert an AgentCall dataclass to a plain dict for JSON serialisation."""
    return dataclasses.asdict(call_result)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    """Serve the live cost dashboard."""
    return render_template("index.html")


@app.post("/dispute/start")
def dispute_start():
    """
    Start a new dispute session.

    Request JSON:
        { "dispute_id": str, "max_budget": float }

    Response JSON:
        { "status": "started", "dispute_id": str }
    """
    body = request.get_json(force=True)
    dispute_id = body.get("dispute_id", "").strip()
    max_budget = float(body.get("max_budget", 5.0))

    if not dispute_id:
        return jsonify({"error": "dispute_id is required"}), 400

    if dispute_id in ACTIVE_DISPUTES:
        return jsonify({"error": f"Dispute '{dispute_id}' already exists"}), 409

    ACTIVE_DISPUTES[dispute_id] = AgentHarness(dispute_id, max_budget_inr=max_budget)
    return jsonify({"status": "started", "dispute_id": dispute_id}), 201


@app.post("/dispute/step")
def dispute_step():
    """
    Execute one pipeline step for an existing dispute.

    Request JSON:
        { "dispute_id": str, "prompt": str }

    Response JSON:
        AgentCall as dict
    """
    body = request.get_json(force=True)
    dispute_id = body.get("dispute_id", "").strip()
    prompt     = body.get("prompt", "").strip()

    if not dispute_id or not prompt:
        return jsonify({"error": "dispute_id and prompt are required"}), 400

    harness = ACTIVE_DISPUTES.get(dispute_id)
    if harness is None:
        return jsonify({"error": f"Dispute '{dispute_id}' not found. Start it first."}), 404

    agent_call = harness.call(prompt, mock_response="[SIMULATED LLM RESPONSE]")
    return jsonify(_harness_to_dict(agent_call)), 200


@app.get("/dispute/cost/<dispute_id>")
def dispute_cost(dispute_id: str):
    """
    Return the full budget report for a dispute.

    Response JSON:
        get_report() dict
    """
    harness = ACTIVE_DISPUTES.get(dispute_id)
    if harness is None:
        return jsonify({"error": f"Dispute '{dispute_id}' not found"}), 404

    return jsonify(harness.get_report()), 200


@app.get("/dispute/all")
def dispute_all():
    """
    Return a lightweight summary of every active dispute.

    Response JSON:
        { "disputes": [ { dispute_id, total_steps, total_cost,
                          budget_remaining, budget_exhausted } ] }
    """
    summaries = []
    for dispute_id, harness in ACTIVE_DISPUTES.items():
        report = harness.get_report()
        summaries.append({
            "dispute_id":       dispute_id,
            "total_steps":      report["total_steps"],
            "total_cost":       report["total_cost"],
            "budget_remaining": report["budget_remaining"],
            "budget_exhausted": report["budget_exhausted"],
        })
    return jsonify({"disputes": summaries}), 200


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(port=5001, debug=True)
