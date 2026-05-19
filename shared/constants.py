"""
shared/constants.py
===================
Platform-wide constants for NyayaNode.

WHO USES THIS:
  - All 6 members import from here for ONDC dispute codes, budget limits,
    and timeout configuration.
  - Never hardcode these values elsewhere in the codebase.

Source: ONDC Buyer Grievance & Dispute Resolution Policy v2.0
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# ONDC Dispute Codes (as per ONDC specification)
# ---------------------------------------------------------------------------

ONDC_DISPUTE_CODES: dict[str, str] = {
    "DAMAGED_ITEM": "FLM01",     # Item received in damaged condition
    "WRONG_ITEM": "FLM02",       # Wrong item delivered
    "NOT_DELIVERED": "FLM03",    # Item not delivered within SLA
    "REFUND_DENIED": "FLM04",    # Refund request rejected by seller
    "QUALITY_ISSUE": "FLM05",    # Item quality below stated specification
    "QUANTITY_SHORT": "FLM06",   # Partial delivery
    "FAKE_ITEM": "FLM07",        # Counterfeit / fake product
}

# ---------------------------------------------------------------------------
# Dispute Resolution SLA (hours) — ONDC mandated
# ---------------------------------------------------------------------------

DISPUTE_SLA_HOURS: dict[str, int] = {
    "DAMAGED_ITEM": 72,
    "WRONG_ITEM": 72,
    "NOT_DELIVERED": 48,
    "REFUND_DENIED": 96,
    "default": 72,
}

# ---------------------------------------------------------------------------
# Budget & Cost Configuration
# ---------------------------------------------------------------------------

BUDGET_CAP_INR: float = 5.0                    # Cascadeflow per-dispute cap
BUDGET_WARNING_THRESHOLD: float = 0.80          # Warn at 80% consumption
GROQ_COST_PER_1K_TOKENS_70B: float = 0.00059   # USD → converted to INR below
GROQ_COST_PER_1K_TOKENS_8B: float = 0.000059
USD_TO_INR: float = 83.5                        # Update if exchange rate changes

# Pre-computed INR costs per 1k tokens
GROQ_INR_PER_1K_70B: float = GROQ_COST_PER_1K_TOKENS_70B * USD_TO_INR   # ≈ 0.049
GROQ_INR_PER_1K_8B: float = GROQ_COST_PER_1K_TOKENS_8B * USD_TO_INR     # ≈ 0.005

# ---------------------------------------------------------------------------
# LLM Model Configuration
# ---------------------------------------------------------------------------

LLM_HEAVY_MODEL: str = "llama-3.3-70b-versatile"   # For complex reasoning
LLM_LIGHT_MODEL: str = "llama-3.1-8b-instant"       # For simple classifications

# Token budgets per agent task
MAX_TOKENS_EVIDENCE_ANALYSIS: int = 1024
MAX_TOKENS_NEGOTIATION: int = 512
MAX_TOKENS_DECISION: int = 1024
MAX_TOKENS_CLASSIFICATION: int = 256

# Groq API rate limits (requests per minute, free tier)
GROQ_RPM_LIMIT: int = 30

# ---------------------------------------------------------------------------
# Agent Behaviour Limits
# ---------------------------------------------------------------------------

MAX_AGENT_ITERATIONS: int = 10
MAX_NEGOTIATION_ROUNDS: int = 3
MIN_CONFIDENCE_TO_RESOLVE: float = 0.70   # Below this → escalate to human
ESCALATION_THRESHOLD_INR: float = 50_000  # Disputes above this always escalate

# ---------------------------------------------------------------------------
# Hindsight Configuration
# ---------------------------------------------------------------------------

HINDSIGHT_SESSION_TTL_DAYS: int = 90    # Keep dispute memory for 90 days
HINDSIGHT_NAMESPACE: str = "nyayanode"

# ---------------------------------------------------------------------------
# Supabase Table Names
# ---------------------------------------------------------------------------

TABLE_DISPUTES: str = "disputes"
TABLE_AUDIT_LOGS: str = "audit_logs"
TABLE_SESSIONS: str = "hindsight_sessions"

# ---------------------------------------------------------------------------
# ONDC Network Participant Types
# ---------------------------------------------------------------------------

PARTICIPANT_BUYER_APP: str = "BAP"     # Buyer Application Platform
PARTICIPANT_SELLER_APP: str = "BPP"    # Buyer-side Participant Platform (seller)
PARTICIPANT_LOGISTICS: str = "LSP"     # Logistics Service Provider
PARTICIPANT_ARBITRATOR: str = "IGM"    # Issue & Grievance Management node

# ---------------------------------------------------------------------------
# Refund Policy Rules (ONDC mandated percentages)
# ---------------------------------------------------------------------------

REFUND_POLICY: dict[str, dict[str, float]] = {
    "DAMAGED_ITEM": {
        "high_confidence": 1.00,    # 100% refund if strong evidence
        "medium_confidence": 0.75,  # 75% if partial evidence
        "low_confidence": 0.50,     # 50% if weak evidence
    },
    "WRONG_ITEM": {
        "high_confidence": 1.00,
        "medium_confidence": 1.00,  # Wrong item always full refund if confirmed
        "low_confidence": 0.75,
    },
    "NOT_DELIVERED": {
        "high_confidence": 1.00,
        "medium_confidence": 1.00,  # Logistics failure → full refund
        "low_confidence": 0.50,
    },
    "REFUND_DENIED": {
        "high_confidence": 1.00,
        "medium_confidence": 0.50,
        "low_confidence": 0.00,     # Seller has valid grounds → reject
    },
}

# Confidence bands
CONFIDENCE_HIGH: float = 0.80
CONFIDENCE_MEDIUM: float = 0.60
CONFIDENCE_LOW: float = 0.40

# ---------------------------------------------------------------------------
# HTTP Status Codes (for FastAPI responses)
# ---------------------------------------------------------------------------

HTTP_200_OK: int = 200
HTTP_202_ACCEPTED: int = 202
HTTP_400_BAD_REQUEST: int = 400
HTTP_404_NOT_FOUND: int = 404
HTTP_422_UNPROCESSABLE: int = 422
HTTP_429_RATE_LIMITED: int = 429
HTTP_500_INTERNAL: int = 500
HTTP_503_UNAVAILABLE: int = 503
