"""
agents/core/arbitrator.py
=========================
Core LangGraph arbitration agent loop for NyayaNode.

WHO USES THIS:
  - Member 1 (Lead AI Architect): owns this file entirely.
  - Member 3 (Backend / FastAPI): calls POST /agents/arbitrate and
    GET /agents/dispute/{id}/status — do NOT import this module directly,
    call it over HTTP.
  - Member 2 (Cascadeflow): plugs real SDK into _route_llm_call() and
    budget_harness.py — the hook is clearly marked.
  - Member 4 (Frontend): polls GET /agents/dispute/{id}/status and
    GET /agents/dispute/{id}/audit_trail.

LANGGRAPH NODE FLOW:
  [START]
     │
     ▼
  intake_node          ← validates request, initialises state
     │
     ▼
  evidence_node        ← processes buyer evidence via evidence_tool
     │
     ├─► [escalate_node] ← if evidence insufficient / budget gone
     │
     ▼
  logistics_node       ← pulls tracking data via logistics_tool
     │
     ▼
  decision_node        ← LLM drafts arbitration decision (70b model)
     │
     ├─► [escalate_node] ← if confidence < 0.70 or high-value
     │
     ▼
  negotiation_node     ← sends proposal to seller via negotiation_tool
     │
     ├─► [escalate_node] ← if seller rejects and confidence still low
     │
     ▼
  resolve_node         ← finalises decision, transitions to RESOLVED
     │
     ▼
  [END]

GROQ MODEL ROUTING:
  Heavy (llama-3.3-70b-versatile) → evidence analysis, final decision
  Light (llama-3.1-8b-instant)    → classification, simple yes/no calls

All LLM calls go through _route_llm_call() which Cascadeflow will gate.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Any, Literal

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from tenacity import retry, stop_after_attempt, wait_exponential

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

load_dotenv(os.path.join(_REPO_ROOT, ".env"))

from agents.core.state_machine import (
    BudgetExhaustedError,
    ConfidenceTooLowError,
    DisputeTransitionError,
    InsufficientEvidenceError,
    create_state_machine,
)
from shared.constants import (
    BUDGET_CAP_INR,
    GROQ_INR_PER_1K_70B,
    GROQ_INR_PER_1K_8B,
    LLM_HEAVY_MODEL,
    LLM_LIGHT_MODEL,
    MAX_AGENT_ITERATIONS,
    MAX_NEGOTIATION_ROUNDS,
    MAX_TOKENS_DECISION,
    MAX_TOKENS_EVIDENCE_ANALYSIS,
    MAX_TOKENS_NEGOTIATION,
    MIN_CONFIDENCE_TO_RESOLVE,
)
from shared.schemas import (
    ArbitrationState,
    AuditEventType,
    BudgetStatus,
    DecisionType,
    DisputeRequest,
    DisputeResponse,
    DisputeStatus,
    DisputeStatusResponse,
    EvidenceItem,
    NegotiationProposal,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger("nyayanode.arbitrator")

# ---------------------------------------------------------------------------
# LLM Client Factory
# ---------------------------------------------------------------------------

def _get_llm(model: str, max_tokens: int = 1024) -> ChatGroq:
    """
    Return a ChatGroq client for the given model.
    Raises RuntimeError if GROQ_API_KEY is not set.
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY not set. Copy .env.example → .env and add your key."
        )
    return ChatGroq(
        model=model,
        api_key=api_key,
        max_tokens=max_tokens,
        temperature=0.1,   # Low temp for consistent legal decisions
    )


# ---------------------------------------------------------------------------
# Cost Estimator
# ---------------------------------------------------------------------------

def _estimate_cost_inr(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    """
    Estimate inference cost in INR based on token counts.
    CASCADEFLOW HOOK: Member 2 replaces this with the real SDK call.
    """
    rate = GROQ_INR_PER_1K_70B if "70b" in model else GROQ_INR_PER_1K_8B
    total_tokens = prompt_tokens + completion_tokens
    return round((total_tokens / 1000) * rate, 6)


# ---------------------------------------------------------------------------
# Core LLM Routing Function
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _route_llm_call(
    state: ArbitrationState,
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_tokens: int,
    task_label: str,
) -> tuple[str, float]:
    """
    Route a single LLM call through budget check → Groq → cost tracking.

    CASCADEFLOW HOOK: Member 2 wraps this function with the Cascadeflow
    SDK's budget gate. Replace the budget check block below with:
        from agents.cascadeflow.budget_harness import gate_llm_call
        await gate_llm_call(state, model, max_tokens)

    Returns:
        (response_text, cost_inr)

    Raises:
        BudgetExhaustedError: if the ₹5 cap would be exceeded.
        RuntimeError: if Groq API call fails after retries.
    """
    # ── Budget pre-check ────────────────────────────────────────────────────
    if state.budget_status.is_exhausted:
        raise BudgetExhaustedError(
            f"Budget exhausted before {task_label} for dispute {state.dispute_id}"
        )

    # Estimate cost of this call — if it would exceed budget, downgrade model
    estimated_tokens = max_tokens + 500  # rough prompt estimate
    estimated_cost = _estimate_cost_inr(500, max_tokens, model)
    remaining = state.budget_status.remaining_inr

    if estimated_cost > remaining and model == LLM_HEAVY_MODEL:
        log.warning(
            "budget_pressure_downgrade",
            dispute_id=state.dispute_id,
            task=task_label,
            estimated_cost=estimated_cost,
            remaining=remaining,
        )
        model = LLM_LIGHT_MODEL   # Downgrade to stay within budget
        state.add_audit(
            AuditEventType.BUDGET_WARNING,
            f"Downgraded {task_label} from 70b→8b to stay within budget",
            metadata={"estimated_cost": estimated_cost, "remaining": remaining},
        )

    # ── Groq API Call ────────────────────────────────────────────────────────
    llm = _get_llm(model, max_tokens)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    t0 = time.monotonic()
    response = await llm.ainvoke(messages)
    latency_ms = round((time.monotonic() - t0) * 1000)

    response_text = response.content
    usage = getattr(response, "usage_metadata", None)

    if usage:
        prompt_tokens = usage.get("input_tokens", 300)
        completion_tokens = usage.get("output_tokens", max_tokens // 2)
    else:
        # Fallback estimate if usage metadata not returned
        prompt_tokens = len(system_prompt.split()) + len(user_prompt.split())
        completion_tokens = len(response_text.split())

    actual_cost = _estimate_cost_inr(prompt_tokens, completion_tokens, model)

    log.info(
        "llm_call_complete",
        dispute_id=state.dispute_id,
        task=task_label,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_inr=actual_cost,
        latency_ms=latency_ms,
    )

    state.budget_status.llm_calls += 1

    return response_text, actual_cost


# ---------------------------------------------------------------------------
# Prompt Loader
# ---------------------------------------------------------------------------

def _load_prompt(filename: str) -> str:
    """Load a system prompt from agents/prompts/. Falls back to inline default."""
    prompt_path = os.path.join(_REPO_ROOT, "agents", "prompts", filename)
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    # Inline fallback — safe to run before Task 7 prompts are written
    return _INLINE_PROMPTS.get(filename, "You are an ONDC arbitration assistant.")


_INLINE_PROMPTS: dict[str, str] = {
    "arbitrator_system.txt": """You are NyayaNode, an AI arbitrator for ONDC (Open Network for Digital Commerce) disputes in India.

You must:
1. Apply ONDC Buyer Grievance & Dispute Resolution Policy v2.0 strictly.
2. Be factual, impartial, and base decisions only on submitted evidence.
3. Never invent policy clauses or cite non-existent regulations.
4. Always output valid JSON when asked for structured output.
5. Consider Indian consumer protection law (Consumer Protection Act 2019).
6. Respond in English unless the buyer's language preference is Hindi.

You must NOT:
- Make decisions based on unverified claims alone.
- Issue full refunds without at least one corroborating evidence piece.
- Auto-resolve disputes above ₹50,000 — always escalate these.
""",
    "evidence_collector.txt": """You are an evidence analysis assistant for ONDC dispute arbitration.

Analyse the submitted evidence and return a JSON object with:
{
  "evidence_quality": "strong" | "moderate" | "weak" | "insufficient",
  "confidence_score": 0.0-1.0,
  "key_findings": ["finding 1", "finding 2"],
  "supports_buyer_claim": true | false,
  "reasoning": "brief explanation",
  "missing_evidence": ["what would strengthen the case"]
}

Be objective. Consider: photo clarity, timestamp consistency, description specificity.
Output ONLY the JSON object, no preamble or markdown fences.
""",
    "negotiator.txt": """You are a settlement negotiation assistant for ONDC disputes.

Given the evidence analysis and dispute details, generate a fair settlement proposal.
Return a JSON object:
{
  "proposed_refund_inr": 0.0,
  "refund_percentage": 0.0,
  "rationale": "explanation",
  "settlement_terms": ["term 1", "term 2"],
  "confidence": 0.0-1.0,
  "final_decision": "FULL_REFUND" | "PARTIAL_REFUND" | "REJECTED"
}

Output ONLY the JSON object, no preamble or markdown fences.
""",
}


# ---------------------------------------------------------------------------
# LangGraph Node Functions
# ---------------------------------------------------------------------------

async def intake_node(state: ArbitrationState) -> ArbitrationState:
    """
    Node 1 — Intake & Validation.
    Validates the incoming dispute request and initialises the state machine.
    Immediately escalates disputes above the ₹50,000 threshold.
    """
    log.info("node_enter", node="intake", dispute_id=state.dispute_id)

    sm = create_state_machine(state)

    # Immediate escalation for high-value disputes
    from shared.constants import ESCALATION_THRESHOLD_INR
    if state.request.dispute_amount_inr > ESCALATION_THRESHOLD_INR:
        sm.force_escalate(
            f"Dispute amount ₹{state.request.dispute_amount_inr:,.2f} exceeds "
            f"auto-resolution threshold ₹{ESCALATION_THRESHOLD_INR:,.2f}"
        )
        return state

    sm.transition(
        DisputeStatus.EVIDENCE_COLLECTION,
        reason=f"Dispute accepted: {state.request.dispute_type.value} "
               f"for ₹{state.request.dispute_amount_inr}",
    )

    state.iteration_count += 1
    return state


async def evidence_node(state: ArbitrationState) -> ArbitrationState:
    """
    Node 2 — Evidence Collection & Analysis.
    Calls the evidence tool stub and uses the LLM to assess evidence quality.
    Sets state.evidence_sufficient and state.confidence_score.
    """
    log.info("node_enter", node="evidence", dispute_id=state.dispute_id)

    if state.status == DisputeStatus.ESCALATED:
        return state  # Already escalated — pass through

    sm = create_state_machine(state)

    # ── Call evidence tool ──────────────────────────────────────────────────
    try:
        from agents.tools.evidence_tool import process_evidence
        processed = await process_evidence(
            dispute_id=state.dispute_id,
            evidence_items=state.request.evidence,
            dispute_type=state.request.dispute_type,
        )
        state.processed_evidence = processed
    except ImportError:
        # Tool not yet written (Tasks 1-2 phase) — use raw evidence
        state.processed_evidence = [
            {"type": e.type.value, "content": e.content, "processed": True}
            for e in state.request.evidence
        ]

    state.add_audit(
        AuditEventType.EVIDENCE_COLLECTED,
        f"Processed {len(state.processed_evidence)} evidence item(s)",
        metadata={"item_count": len(state.processed_evidence)},
    )

    # ── LLM evidence analysis ───────────────────────────────────────────────
    if not state.processed_evidence:
        # No evidence at all — escalate
        sm.force_escalate("No evidence submitted by buyer")
        return state

    evidence_summary = "\n".join(
        f"- [{item.get('type', 'unknown')}]: {str(item.get('content', ''))[:300]}"
        for item in state.processed_evidence
    )

    user_prompt = f"""Dispute Type: {state.request.dispute_type.value}
Dispute Amount: ₹{state.request.dispute_amount_inr}
Order ID: {state.request.order_id}
Buyer ID: {state.request.buyer_id}

Evidence Submitted:
{evidence_summary}

Analyse this evidence and return your assessment as JSON."""

    try:
        system_prompt = _load_prompt("evidence_collector.txt")
        response_text, cost = await _route_llm_call(
            state=state,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=LLM_HEAVY_MODEL,
            max_tokens=MAX_TOKENS_EVIDENCE_ANALYSIS,
            task_label="evidence_analysis",
        )
        state.add_audit(
            AuditEventType.EVIDENCE_COLLECTED,
            "LLM evidence analysis complete",
            cost_inr=cost,
        )

        # Parse LLM response
        analysis = _safe_parse_json(response_text, task="evidence_analysis")
        state.confidence_score = float(analysis.get("confidence_score", 0.5))
        quality = analysis.get("evidence_quality", "moderate")
        state.evidence_sufficient = quality in ("strong", "moderate")

        # Store analysis in processed evidence metadata
        state.processed_evidence.append({
            "type": "llm_analysis",
            "content": analysis,
            "processed": True,
        })

    except BudgetExhaustedError:
        sm.force_escalate("Budget exhausted during evidence analysis")
        return state
    except Exception as e:
        log.warning("evidence_llm_failed", error=str(e), dispute_id=state.dispute_id)
        # Graceful degradation: use heuristic confidence
        state.confidence_score = 0.5 if state.processed_evidence else 0.0
        state.evidence_sufficient = len(state.processed_evidence) > 0

    state.iteration_count += 1
    return state


async def logistics_node(state: ArbitrationState) -> ArbitrationState:
    """
    Node 3 — Logistics Data Pull.
    Queries the logistics tool for tracking history.
    Adjusts confidence score based on delivery evidence.
    Uses the lightweight 8b model for simple classification.
    """
    log.info("node_enter", node="logistics", dispute_id=state.dispute_id)

    if state.status == DisputeStatus.ESCALATED:
        return state

    # ── Call logistics tool ─────────────────────────────────────────────────
    try:
        from agents.tools.logistics_tool import fetch_tracking_data
        snapshot = await fetch_tracking_data(
            logistics_id=state.request.logistics_id,
            order_id=state.request.order_id,
            dispute_type=state.request.dispute_type,
        )
        state.logistics_snapshot = snapshot
    except ImportError:
        # Tool stub not yet available — create minimal mock snapshot
        from shared.schemas import LogisticsSnapshot
        state.logistics_snapshot = LogisticsSnapshot(
            logistics_id=state.request.logistics_id,
            current_status="DELIVERED",
            delivery_attempts=1,
            raw_response={"mock": True, "note": "logistics_tool not yet implemented"},
        )

    state.add_audit(
        AuditEventType.LOGISTICS_QUERIED,
        f"Logistics snapshot fetched: status={state.logistics_snapshot.current_status}",
        metadata={
            "carrier": state.logistics_snapshot.carrier,
            "status": state.logistics_snapshot.current_status,
            "delivered_at": str(state.logistics_snapshot.delivered_at),
        },
    )

    # ── LLM: Does logistics data support or contradict buyer claim? ──────────
    if state.logistics_snapshot:
        logistics_summary = json.dumps(
            state.logistics_snapshot.model_dump(exclude={"raw_response"}),
            indent=2,
            default=str,
        )
        user_prompt = f"""Dispute type: {state.request.dispute_type.value}
Buyer claims: evidence shows {state.request.dispute_type.value.lower().replace('_', ' ')}.
Current confidence: {state.confidence_score:.2f}

Logistics data:
{logistics_summary}

Does this logistics data SUPPORT or CONTRADICT the buyer's claim?
Return JSON: {{"supports_claim": true/false, "adjustment": -0.2 to +0.2, "reason": "..."}}
Output ONLY the JSON, no preamble."""

        try:
            response_text, cost = await _route_llm_call(
                state=state,
                system_prompt=_load_prompt("arbitrator_system.txt"),
                user_prompt=user_prompt,
                model=LLM_LIGHT_MODEL,   # Cheap model for simple classification
                max_tokens=256,
                task_label="logistics_classification",
            )
            state.add_audit(
                AuditEventType.LOGISTICS_QUERIED,
                "LLM logistics classification complete",
                cost_inr=cost,
            )
            result = _safe_parse_json(response_text, task="logistics_classification")
            adjustment = float(result.get("adjustment", 0.0))
            state.confidence_score = max(0.0, min(1.0, state.confidence_score + adjustment))

        except BudgetExhaustedError:
            sm = create_state_machine(state)
            sm.force_escalate("Budget exhausted during logistics analysis")
            return state
        except Exception as e:
            log.warning("logistics_llm_failed", error=str(e))
            # No adjustment — carry forward existing confidence

    state.iteration_count += 1
    return state


async def decision_node(state: ArbitrationState) -> ArbitrationState:
    """
    Node 4 — Arbitration Decision Drafting.
    Uses the heavy 70b model to draft the binding arbitration decision.
    Determines FULL_REFUND / PARTIAL_REFUND / REJECTED and sets reasoning.
    """
    log.info("node_enter", node="decision", dispute_id=state.dispute_id)

    if state.status == DisputeStatus.ESCALATED:
        return state

    sm = create_state_machine(state)

    # Check if we should escalate before deciding
    if sm.should_escalate():
        sm.force_escalate(
            f"Escalation criteria met: confidence={state.confidence_score:.2f}, "
            f"budget_remaining=₹{state.budget_status.remaining_inr:.4f}"
        )
        return state

    # Build comprehensive decision prompt
    evidence_summary = "\n".join(
        f"- {item.get('type', 'unknown')}: {str(item.get('content', ''))[:200]}"
        for item in state.processed_evidence
        if item.get("type") != "llm_analysis"
    )

    logistics_text = "No logistics data available."
    if state.logistics_snapshot:
        logistics_text = (
            f"Status: {state.logistics_snapshot.current_status}, "
            f"Carrier: {state.logistics_snapshot.carrier}, "
            f"Attempts: {state.logistics_snapshot.delivery_attempts}"
        )

    user_prompt = f"""=== ARBITRATION DECISION REQUEST ===

Dispute ID: {state.dispute_id}
Dispute Type: {state.request.dispute_type.value}
Dispute Amount: ₹{state.request.dispute_amount_inr:,.2f}
Order ID: {state.request.order_id}
Buyer: {state.request.buyer_id}
Seller: {state.request.seller_id}

Evidence Quality Assessment:
- Confidence Score: {state.confidence_score:.2f}
- Evidence Items: {len([e for e in state.processed_evidence if e.get('type') != 'llm_analysis'])}

Evidence Summary:
{evidence_summary if evidence_summary else "No evidence items processed."}

Logistics:
{logistics_text}

Based on ONDC policy and the evidence above, issue your arbitration decision.
Return ONLY this JSON:
{{
  "decision": "FULL_REFUND" | "PARTIAL_REFUND" | "REJECTED",
  "refund_amount_inr": 0.0,
  "refund_percentage": 0.0,
  "confidence_score": 0.0,
  "reasoning": "detailed explanation referencing specific evidence",
  "policy_basis": "ONDC policy clause or principle applied",
  "conditions": ["any conditions attached to the refund"]
}}"""

    try:
        response_text, cost = await _route_llm_call(
            state=state,
            system_prompt=_load_prompt("arbitrator_system.txt"),
            user_prompt=user_prompt,
            model=LLM_HEAVY_MODEL,
            max_tokens=MAX_TOKENS_DECISION,
            task_label="arbitration_decision",
        )
        state.add_audit(
            AuditEventType.DECISION_DRAFTED,
            "LLM arbitration decision drafted",
            cost_inr=cost,
        )

        decision_data = _safe_parse_json(response_text, task="arbitration_decision")

        # Apply decision to state
        decision_str = decision_data.get("decision", "REJECTED")
        try:
            state.decision = DecisionType(decision_str)
        except ValueError:
            state.decision = DecisionType.REJECTED

        state.refund_amount_inr = float(decision_data.get("refund_amount_inr", 0.0))
        state.confidence_score = float(decision_data.get("confidence_score", state.confidence_score))
        state.reasoning = decision_data.get("reasoning", "Insufficient evidence for refund.")

        # Cap refund at dispute amount
        state.refund_amount_inr = min(
            state.refund_amount_inr, state.request.dispute_amount_inr
        )

    except BudgetExhaustedError:
        sm.force_escalate("Budget exhausted during decision drafting")
        return state
    except Exception as e:
        log.error("decision_node_failed", error=str(e), dispute_id=state.dispute_id)
        sm.force_escalate(f"Decision node error: {str(e)[:100]}")
        return state

    state.iteration_count += 1
    return state


async def negotiation_node(state: ArbitrationState) -> ArbitrationState:
    """
    Node 5 — Seller Negotiation.
    Sends the drafted decision to the seller system and attempts settlement.
    Uses the negotiation tool and light model for counter-proposal analysis.
    Runs up to MAX_NEGOTIATION_ROUNDS rounds.
    """
    log.info("node_enter", node="negotiation", dispute_id=state.dispute_id)

    if state.status == DisputeStatus.ESCALATED:
        return state

    sm = create_state_machine(state)

    # Transition to NEGOTIATION state
    try:
        sm.transition(
            DisputeStatus.NEGOTIATION,
            reason=f"Initiating seller negotiation — decision: {state.decision.value}",
        )
    except (InsufficientEvidenceError, DisputeTransitionError) as e:
        sm.force_escalate(f"Cannot enter negotiation: {e}")
        return state

    # ── Call negotiation tool ───────────────────────────────────────────────
    try:
        from agents.tools.negotiation_tool import send_proposal, receive_response
        proposal = NegotiationProposal(
            proposed_by="arbitrator",
            refund_amount_inr=state.refund_amount_inr,
            reasoning=state.reasoning,
        )
        state.negotiation_history.append(proposal)
        state.add_audit(
            AuditEventType.NEGOTIATION_SENT,
            f"Sent proposal to seller: ₹{proposal.refund_amount_inr}",
            metadata={"proposal_id": proposal.proposal_id},
        )

        seller_response = await send_proposal(
            seller_id=state.request.seller_id,
            proposal=proposal,
            dispute_id=state.dispute_id,
        )

    except ImportError:
        # Tool not yet available — simulate seller acceptance for happy path
        seller_response = {
            "accepted": True,
            "counter_amount_inr": None,
            "response": "mock_acceptance",
        }

    # ── Analyse seller response ─────────────────────────────────────────────
    seller_accepted = seller_response.get("accepted", False)
    state.negotiation_attempted = True

    if seller_accepted:
        state.add_audit(
            AuditEventType.NEGOTIATION_RECEIVED,
            "Seller accepted the arbitration proposal",
            metadata={"seller_response": seller_response},
        )
    else:
        # Seller rejected — use LLM to assess counter-proposal
        counter_amount = seller_response.get("counter_amount_inr", 0)
        user_prompt = f"""Seller rejected the arbitration proposal of ₹{state.refund_amount_inr}.
Seller counter-proposes: ₹{counter_amount}
Original dispute amount: ₹{state.request.dispute_amount_inr}
Evidence confidence: {state.confidence_score:.2f}
Dispute type: {state.request.dispute_type.value}

Should we accept the counter-proposal or maintain our original decision?
Return JSON: {{"accept_counter": true/false, "final_amount_inr": 0.0, "reasoning": "..."}}
Output ONLY JSON."""

        try:
            response_text, cost = await _route_llm_call(
                state=state,
                system_prompt=_load_prompt("negotiator.txt"),
                user_prompt=user_prompt,
                model=LLM_LIGHT_MODEL,
                max_tokens=MAX_TOKENS_NEGOTIATION,
                task_label="counter_proposal_analysis",
            )
            state.add_audit(
                AuditEventType.NEGOTIATION_RECEIVED,
                "LLM counter-proposal analysis complete",
                cost_inr=cost,
            )
            counter_analysis = _safe_parse_json(response_text, task="counter_proposal")
            if counter_analysis.get("accept_counter", False):
                state.refund_amount_inr = float(
                    counter_analysis.get("final_amount_inr", state.refund_amount_inr)
                )
                state.decision = DecisionType.PARTIAL_REFUND
                state.reasoning += f" [Negotiated settlement: ₹{state.refund_amount_inr}]"

        except BudgetExhaustedError:
            sm.force_escalate("Budget exhausted during negotiation")
            return state
        except Exception as e:
            log.warning("negotiation_llm_failed", error=str(e))
            # Maintain original decision if analysis fails

    state.iteration_count += 1
    return state


async def resolve_node(state: ArbitrationState) -> ArbitrationState:
    """
    Node 6 — Final Resolution.
    Transitions state to RESOLVED, computes final refund, logs final audit.
    """
    log.info("node_enter", node="resolve", dispute_id=state.dispute_id)

    if state.status == DisputeStatus.ESCALATED:
        return state

    sm = create_state_machine(state)

    try:
        sm.transition(
            DisputeStatus.RESOLVED,
            reason=f"Arbitration complete: {state.decision.value} "
                   f"— ₹{state.refund_amount_inr:,.2f} "
                   f"(confidence: {state.confidence_score:.2f})",
        )
        state.add_audit(
            AuditEventType.DECISION_FINALISED,
            f"Dispute resolved: {state.decision.value} for ₹{state.refund_amount_inr}",
            metadata={
                "decision": state.decision.value,
                "refund_inr": state.refund_amount_inr,
                "confidence": state.confidence_score,
                "total_cost_inr": state.budget_status.consumed_inr,
                "llm_calls": state.budget_status.llm_calls,
            },
        )
    except (ConfidenceTooLowError, DisputeTransitionError) as e:
        sm.force_escalate(str(e))

    return state


async def escalate_node(state: ArbitrationState) -> ArbitrationState:
    """
    Node 7 — Human Escalation.
    Finalises the ESCALATED state and writes the escalation audit entry.
    Called when guards fail or should_escalate() returns True.
    """
    log.info("node_enter", node="escalate", dispute_id=state.dispute_id)

    if state.status != DisputeStatus.ESCALATED:
        sm = create_state_machine(state)
        sm.force_escalate(state.error_message or "Escalation triggered by routing logic")

    state.add_audit(
        AuditEventType.ESCALATED_TO_HUMAN,
        f"Dispute escalated to human arbitrator. Reason: {state.error_message or 'routing decision'}",
        metadata={
            "confidence_score": state.confidence_score,
            "budget_consumed_inr": state.budget_status.consumed_inr,
            "iteration_count": state.iteration_count,
        },
    )
    return state


# ---------------------------------------------------------------------------
# Routing Functions (LangGraph conditional edges)
# ---------------------------------------------------------------------------

def route_after_intake(state: ArbitrationState) -> Literal["evidence", "escalate"]:
    """Route after intake: escalate immediately if high-value or already escalated."""
    if state.status == DisputeStatus.ESCALATED:
        return "escalate"
    return "evidence"


def route_after_evidence(state: ArbitrationState) -> Literal["logistics", "escalate"]:
    """Route after evidence: continue if evidence is usable, else escalate."""
    if state.status == DisputeStatus.ESCALATED:
        return "escalate"
    if state.budget_status.is_exhausted:
        return "escalate"
    return "logistics"


def route_after_logistics(state: ArbitrationState) -> Literal["decision", "escalate"]:
    """Route after logistics: continue to decision, unless budget gone."""
    if state.status == DisputeStatus.ESCALATED:
        return "escalate"
    if state.budget_status.is_exhausted:
        return "escalate"
    return "decision"


def route_after_decision(state: ArbitrationState) -> Literal["negotiation", "escalate"]:
    """Route after decision: go to negotiation unless should_escalate."""
    if state.status == DisputeStatus.ESCALATED:
        return "escalate"
    sm = create_state_machine(state)
    if sm.should_escalate():
        return "escalate"
    return "negotiation"


def route_after_negotiation(state: ArbitrationState) -> Literal["resolve", "escalate"]:
    """Route after negotiation: resolve unless something went wrong."""
    if state.status == DisputeStatus.ESCALATED:
        return "escalate"
    if state.budget_status.is_exhausted:
        return "escalate"
    sm = create_state_machine(state)
    if sm.should_escalate():
        return "escalate"
    return "resolve"


# ---------------------------------------------------------------------------
# LangGraph Compilation
# ---------------------------------------------------------------------------

def build_arbitration_graph() -> Any:
    """
    Construct and compile the NyayaNode LangGraph StateGraph.

    Uses dict-based state (LangGraph 0.2.x compatible).
    ArbitrationState is serialised to/from dict at graph boundaries.

    Returns a compiled LangGraph graph ready for .ainvoke().
    """
    # LangGraph 0.2.x: use dict annotation for state
    graph = StateGraph(dict)

    # ── Register nodes ──────────────────────────────────────────────────────
    async def _intake(state_dict: dict) -> dict:
        s = ArbitrationState(**state_dict)
        result = await intake_node(s)
        return result.model_dump()

    async def _evidence(state_dict: dict) -> dict:
        s = ArbitrationState(**state_dict)
        result = await evidence_node(s)
        return result.model_dump()

    async def _logistics(state_dict: dict) -> dict:
        s = ArbitrationState(**state_dict)
        result = await logistics_node(s)
        return result.model_dump()

    async def _decision(state_dict: dict) -> dict:
        s = ArbitrationState(**state_dict)
        result = await decision_node(s)
        return result.model_dump()

    async def _negotiation(state_dict: dict) -> dict:
        s = ArbitrationState(**state_dict)
        result = await negotiation_node(s)
        return result.model_dump()

    async def _resolve(state_dict: dict) -> dict:
        s = ArbitrationState(**state_dict)
        result = await resolve_node(s)
        return result.model_dump()

    async def _escalate(state_dict: dict) -> dict:
        s = ArbitrationState(**state_dict)
        result = await escalate_node(s)
        return result.model_dump()

    graph.add_node("intake", _intake)
    graph.add_node("evidence", _evidence)
    graph.add_node("logistics", _logistics)
    graph.add_node("decision", _decision)
    graph.add_node("negotiation", _negotiation)
    graph.add_node("resolve", _resolve)
    graph.add_node("escalate", _escalate)

    # ── Register edges ──────────────────────────────────────────────────────
    graph.set_entry_point("intake")

    graph.add_conditional_edges(
        "intake",
        lambda d: route_after_intake(ArbitrationState(**d)),
        {"evidence": "evidence", "escalate": "escalate"},
    )
    graph.add_conditional_edges(
        "evidence",
        lambda d: route_after_evidence(ArbitrationState(**d)),
        {"logistics": "logistics", "escalate": "escalate"},
    )
    graph.add_conditional_edges(
        "logistics",
        lambda d: route_after_logistics(ArbitrationState(**d)),
        {"decision": "decision", "escalate": "escalate"},
    )
    graph.add_conditional_edges(
        "decision",
        lambda d: route_after_decision(ArbitrationState(**d)),
        {"negotiation": "negotiation", "escalate": "escalate"},
    )
    graph.add_conditional_edges(
        "negotiation",
        lambda d: route_after_negotiation(ArbitrationState(**d)),
        {"resolve": "resolve", "escalate": "escalate"},
    )

    graph.add_edge("resolve", END)
    graph.add_edge("escalate", END)

    return graph.compile()


# Singleton compiled graph — built once at startup
_COMPILED_GRAPH = None


def get_graph() -> Any:
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = build_arbitration_graph()
    return _COMPILED_GRAPH


# ---------------------------------------------------------------------------
# Core Arbitration Runner
# ---------------------------------------------------------------------------

async def run_arbitration(request: DisputeRequest) -> DisputeResponse:
    """
    Main entry point — runs the full arbitration graph for a dispute.
    Called by the FastAPI endpoint below.

    Args:
        request: Validated DisputeRequest from Member 3's backend.

    Returns:
        DisputeResponse with decision, refund amount, and full audit trail.
    """
    log.info(
        "arbitration_start",
        dispute_id=request.dispute_id,
        dispute_type=request.dispute_type.value,
        amount_inr=request.dispute_amount_inr,
    )

    # Initialise state
    budget = BudgetStatus(
        dispute_id=request.dispute_id,
        budget_cap_inr=BUDGET_CAP_INR,
    )
    initial_state = ArbitrationState(
        dispute_id=request.dispute_id,
        request=request,
        budget_status=budget,
    )
    initial_state.add_audit(
        AuditEventType.DISPUTE_INITIATED,
        f"Arbitration initiated for {request.dispute_type.value} — ₹{request.dispute_amount_inr}",
        metadata={"buyer_id": request.buyer_id, "seller_id": request.seller_id},
    )

    # Run graph
    graph = get_graph()
    try:
        final_dict = await graph.ainvoke(initial_state.model_dump())
        final_state = ArbitrationState(**final_dict)
    except Exception as e:
        log.error("graph_execution_failed", error=str(e), dispute_id=request.dispute_id)
        # Return a safe escalation response on unexpected error
        initial_state.should_escalate = True
        initial_state.status = DisputeStatus.ESCALATED
        initial_state.error_message = f"Graph execution failed: {str(e)[:200]}"
        initial_state.add_audit(
            AuditEventType.ESCALATED_TO_HUMAN,
            f"System error — escalated: {str(e)[:100]}",
        )
        return initial_state.to_response()

    response = final_state.to_response()
    log.info(
        "arbitration_complete",
        dispute_id=request.dispute_id,
        status=response.status.value,
        decision=response.decision.value,
        refund_inr=response.refund_amount_inr,
        cost_inr=response.total_inference_cost_inr,
    )
    return response


# ---------------------------------------------------------------------------
# JSON Safety Helper
# ---------------------------------------------------------------------------

def _safe_parse_json(text: str, task: str = "") -> dict:
    """
    Safely parse JSON from LLM output.
    Strips markdown fences, handles partial JSON, returns empty dict on failure.
    """
    # Strip common markdown fences
    text = text.strip()
    for fence in ("```json", "```JSON", "```"):
        if text.startswith(fence):
            text = text[len(fence):]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try extracting first {...} block
        import re
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        log.warning("json_parse_failed", task=task, raw_text=text[:200])
        return {}


# ---------------------------------------------------------------------------
# In-memory dispute store (replace with Supabase in production)
# ---------------------------------------------------------------------------
# Member 3: wire these to your Supabase client instead
_dispute_store: dict[str, DisputeResponse] = {}


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="NyayaNode Agent Service",
    description="AI arbitration micro-service for ONDC disputes",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    """Health check — Member 3 and Railway use this for liveness probe."""
    return {
        "status": "ok",
        "service": "nyayanode-agent",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/agents/arbitrate", response_model=DisputeResponse)
async def arbitrate(request: DisputeRequest) -> DisputeResponse:
    """
    Main arbitration endpoint.
    Member 3 posts DisputeRequest here, receives DisputeResponse.
    """
    try:
        response = await run_arbitration(request)
        _dispute_store[request.dispute_id] = response
        return response
    except Exception as e:
        log.error("arbitrate_endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Arbitration failed: {str(e)}")


@app.get("/agents/dispute/{dispute_id}/status", response_model=DisputeStatusResponse)
async def get_status(dispute_id: str) -> DisputeStatusResponse:
    """
    Lightweight status poll for Member 4's frontend.
    Member 3 proxies this; frontend polls every 3 seconds.
    """
    result = _dispute_store.get(dispute_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found")

    last_event = None
    if result.audit_trail:
        last_event = result.audit_trail[-1].description

    return DisputeStatusResponse(
        dispute_id=dispute_id,
        status=result.status,
        decision=result.decision,
        refund_amount_inr=result.refund_amount_inr,
        confidence_score=result.confidence_score,
        total_inference_cost_inr=result.total_inference_cost_inr,
        last_event=last_event,
    )


@app.get("/agents/dispute/{dispute_id}/audit_trail")
async def get_audit_trail(dispute_id: str) -> list:
    """
    Full audit trail for a dispute.
    Member 4 renders this as a timeline in the UI.
    """
    result = _dispute_store.get(dispute_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Dispute {dispute_id} not found")
    return [entry.model_dump() for entry in result.audit_trail]


# ---------------------------------------------------------------------------
# Self-test (no Groq API key needed — tests graph structure only)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    async def _self_test():
        print("=" * 60)
        print("NyayaNode — Arbitrator Self-Test (no API key required)")
        print("=" * 60)

        from shared.schemas import DisputeType, EvidenceItem, EvidenceType

        # ── Test 1: Graph compiles without errors ─────────────────────────
        print("\n[1] Compiling LangGraph...")
        graph = build_arbitration_graph()
        print("   ✅ Graph compiled successfully")

        # ── Test 2: State initialisation ─────────────────────────────────
        print("\n[2] State initialisation...")
        req = DisputeRequest(
            buyer_id="buyer_001",
            seller_id="seller_042",
            logistics_id="lsp_007",
            order_id="order_xyz",
            dispute_type=DisputeType.DAMAGED_ITEM,
            evidence=[EvidenceItem(type=EvidenceType.TEXT, content="Package crushed on arrival")],
            dispute_amount_inr=500.0,
        )
        budget = BudgetStatus(dispute_id=req.dispute_id, budget_cap_inr=BUDGET_CAP_INR)
        state = ArbitrationState(dispute_id=req.dispute_id, request=req, budget_status=budget)
        print(f"   ✅ State initialised: {state.dispute_id}")

        # ── Test 3: Individual node functions (no LLM) ───────────────────
        print("\n[3] Testing intake_node (no LLM)...")
        result = await intake_node(state)
        assert result.status == DisputeStatus.EVIDENCE_COLLECTION
        print(f"   ✅ intake_node: status={result.status.value}")

        # ── Test 4: High-value immediate escalation ───────────────────────
        print("\n[4] High-value dispute immediate escalation...")
        req2 = DisputeRequest(
            buyer_id="buyer_001",
            seller_id="seller_042",
            logistics_id="lsp_007",
            order_id="order_xyz2",
            dispute_type=DisputeType.REFUND_DENIED,
            evidence=[],
            dispute_amount_inr=75_000.0,
        )
        budget2 = BudgetStatus(dispute_id=req2.dispute_id, budget_cap_inr=BUDGET_CAP_INR)
        state2 = ArbitrationState(dispute_id=req2.dispute_id, request=req2, budget_status=budget2)
        result2 = await intake_node(state2)
        assert result2.status == DisputeStatus.ESCALATED
        print(f"   ✅ High-value escalated immediately: {result2.status.value}")

        # ── Test 5: Route functions ──────────────────────────────────────
        print("\n[5] Testing routing functions...")
        assert route_after_intake(result) == "evidence"
        assert route_after_intake(result2) == "escalate"
        print("   ✅ Routing functions correct")

        # ── Test 6: JSON parsing helper ──────────────────────────────────
        print("\n[6] Testing _safe_parse_json...")
        cases = [
            ('{"decision": "FULL_REFUND"}', "decision", "FULL_REFUND"),
            ('```json\n{"decision": "REJECTED"}\n```', "decision", "REJECTED"),
            ('   {"confidence_score": 0.85}  ', "confidence_score", 0.85),
        ]
        for raw, key, expected in cases:
            parsed = _safe_parse_json(raw)
            assert parsed.get(key) == expected, f"Failed: {raw!r}"
        print("   ✅ JSON parser handles fences and whitespace")

        # ── Test 7: FastAPI app loads ────────────────────────────────────
        print("\n[7] FastAPI app structure...")
        routes = [r.path for r in app.routes]
        assert "/agents/arbitrate" in routes
        assert "/agents/dispute/{dispute_id}/status" in routes
        assert "/agents/dispute/{dispute_id}/audit_trail" in routes
        assert "/health" in routes
        print(f"   ✅ FastAPI routes registered: {routes}")

        print("\n" + "=" * 60)
        print("🎉 ALL ARBITRATOR SELF-TESTS PASSED")
        print("   Run with GROQ_API_KEY set to test full LLM flow.")
        print("=" * 60)

    asyncio.run(_self_test())
