"""
NyayaNode - AI Dispute Arbitration System for ONDC
API Routes: registers all /api/dispute/* endpoints on a Flask app instance.
Designed to be mounted by any Flask app via create_api_routes().
"""

import dataclasses

from flask import request, jsonify

from llmops.agent_harness import AgentHarness
from llmops.cost_tracker import BudgetExhaustedError


def create_api_routes(app, active_disputes: dict) -> None:
    """
    Register all dispute API routes on `app`.

    Parameters
    ----------
    app              : Flask application instance
    active_disputes  : shared dict { dispute_id -> AgentHarness }
                       managed by the caller (allows multiple mounts to
                       share the same in-memory store if needed)
    """

    # ------------------------------------------------------------------ #
    # POST /api/dispute/start                                              #
    # ------------------------------------------------------------------ #
    @app.post("/api/dispute/start")
    def api_dispute_start():
        """
        Create a new dispute session.

        Request JSON:
            { "dispute_id": str, "max_budget": float }   (max_budget defaults to 5.0)

        Response JSON (201):
            { "status": "started", "dispute_id": str, "max_budget": float }
        """
        body       = request.get_json(force=True) or {}
        dispute_id = str(body.get("dispute_id", "")).strip()
        max_budget = float(body.get("max_budget", 5.0))

        if not dispute_id:
            return jsonify({"error": "dispute_id is required"}), 400

        if dispute_id in active_disputes:
            return jsonify({"error": f"Dispute '{dispute_id}' already exists"}), 409

        active_disputes[dispute_id] = AgentHarness(dispute_id, max_budget_inr=max_budget)

        return jsonify({
            "status":     "started",
            "dispute_id": dispute_id,
            "max_budget": max_budget,
        }), 201

    # ------------------------------------------------------------------ #
    # POST /api/dispute/step                                               #
    # ------------------------------------------------------------------ #
    @app.post("/api/dispute/step")
    def api_dispute_step():
        """
        Execute one pipeline step for an existing dispute.

        Request JSON:
            { "dispute_id": str, "prompt": str }

        Response JSON (200):
            AgentCall as dict

        Error responses:
            404  dispute not found
            402  budget exhausted
        """
        body       = request.get_json(force=True) or {}
        dispute_id = str(body.get("dispute_id", "")).strip()
        prompt     = str(body.get("prompt", "")).strip()

        if not dispute_id or not prompt:
            return jsonify({"error": "dispute_id and prompt are required"}), 400

        harness = active_disputes.get(dispute_id)
        if harness is None:
            return jsonify({"error": "dispute not found"}), 404

        try:
            agent_call = harness.call(prompt, mock_response="[SIMULATED LLM RESPONSE]")
        except BudgetExhaustedError:
            return jsonify({"error": "budget exhausted", "dispute_id": dispute_id}), 402

        return jsonify(dataclasses.asdict(agent_call)), 200

    # ------------------------------------------------------------------ #
    # GET /api/dispute/cost/<dispute_id>                                   #
    # ------------------------------------------------------------------ #
    @app.get("/api/dispute/cost/<dispute_id>")
    def api_dispute_cost(dispute_id: str):
        """
        Return the full budget report for a dispute.

        Response JSON (200):
            get_report() dict

        Error responses:
            404  dispute not found
        """
        harness = active_disputes.get(dispute_id)
        if harness is None:
            return jsonify({"error": "dispute not found"}), 404

        return jsonify(harness.get_report()), 200

    # ------------------------------------------------------------------ #
    # GET /api/dispute/all                                                 #
    # ------------------------------------------------------------------ #
    @app.get("/api/dispute/all")
    def api_dispute_all():
        """
        Return a lightweight summary of every active dispute.

        Response JSON (200):
            { "disputes": [ { dispute_id, total_spent, budget_remaining,
                               total_steps, budget_exhausted } ] }
        """
        summaries = []
        for dispute_id, harness in active_disputes.items():
            report = harness.get_report()
            summaries.append({
                "dispute_id":       dispute_id,
                "total_spent":      report["total_cost"],
                "budget_remaining": report["budget_remaining"],
                "total_steps":      report["total_steps"],
                "budget_exhausted": report["budget_exhausted"],
            })

        return jsonify({"disputes": summaries}), 200

    # ------------------------------------------------------------------ #
    # DELETE /api/dispute/<dispute_id>                                     #
    # ------------------------------------------------------------------ #
    @app.delete("/api/dispute/<dispute_id>")
    def api_dispute_delete(dispute_id: str):
        """
        Remove a dispute from the active store.

        Response JSON (200):
            { "status": "deleted", "dispute_id": str }

        Error responses:
            404  dispute not found
        """
        if dispute_id not in active_disputes:
            return jsonify({"error": "dispute not found"}), 404

        del active_disputes[dispute_id]
        return jsonify({"status": "deleted", "dispute_id": dispute_id}), 200
