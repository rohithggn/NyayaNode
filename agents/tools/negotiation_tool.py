"""
agents/tools/negotiation_tool.py
─────────────────────────────────
NyayaNode — Negotiation Tool
Sends the arbitrator's provisional decision to the seller,
handles counter-offers, and returns a NegotiationResult
that the arbitrator uses to finalize the dispute.

Integration points
──────────────────
• Called by  agents/core/arbitrator.py :: _negotiation_node()
• Input  : ArbitrationState  (session_id, decision, refund_amount, dispute_type)
• Output : dict  merged into ArbitrationState (final_decision, seller_accepted)
• LLM    : 8b model for counter-offer evaluation via budget_harness

Mock mode (default):
  NEGOTIATION_BACKEND=mock   ← default
Real ONDC seller messaging:
  NEGOTIATION_BACKEND=real   ← Member 6 fills _RealNegotiationClient
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ── Enums ─────────────────────────────────────────────────────────────────────

class NegotiationOutcome(str, Enum):
    SELLER_ACCEPTED       = "SELLER_ACCEPTED"      # Seller agreed to arbitrator's proposal
    COUNTER_OFFER_ACCEPTED = "COUNTER_OFFER_ACCEPTED"  # Arbitrator accepted a counter
    SELLER_REJECTED       = "SELLER_REJECTED"      # Seller refused — arbitrator decides
    TIMED_OUT             = "TIMED_OUT"            # No response within SLA window
    ESCALATED             = "ESCALATED"            # Beyond arbitrator — needs human review

class SellerResponse(str, Enum):
    ACCEPT         = "ACCEPT"
    COUNTER        = "COUNTER"
    REJECT         = "REJECT"
    NO_RESPONSE    = "NO_RESPONSE"

# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class CounterOffer:
    offered_refund_inr: float
    seller_reasoning: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class NegotiationResult:
    session_id: str
    dispute_type: str
    initial_proposal_inr: float
    seller_response: SellerResponse
    counter_offer: CounterOffer | None
    outcome: NegotiationOutcome
    final_refund_inr: float
    seller_accepted: bool
    rounds: int
    resolution_notes: str
    negotiated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "dispute_type": self.dispute_type,
            "initial_proposal_inr": self.initial_proposal_inr,
            "seller_response": self.seller_response.value,
            "counter_offer": {
                "offered_refund_inr": self.counter_offer.offered_refund_inr,
                "seller_reasoning": self.counter_offer.seller_reasoning,
            } if self.counter_offer else None,
            "outcome": self.outcome.value,
            "final_refund_inr": self.final_refund_inr,
            "seller_accepted": self.seller_accepted,
            "rounds": self.rounds,
            "resolution_notes": self.resolution_notes,
            "negotiated_at": self.negotiated_at,
        }

# ── Mock Scenarios ─────────────────────────────────────────────────────────────

# Seller behaviour probabilities by dispute type (mock only)
_SELLER_BEHAVIOUR: dict[str, dict] = {
    "DAMAGED_ITEM": {
        # Seller usually accepts — logistics fault, not their cost
        "accept_prob": 0.70,
        "counter_prob": 0.20,
        "reject_prob": 0.10,
        "counter_ratio": 0.90,    # Seller offers 90% of arbitrator's proposal
        "counter_reasoning": "We accept partial liability; logistics partner should bear remainder.",
    },
    "WRONG_ITEM": {
        # Seller usually accepts (clear their fault)
        "accept_prob": 0.80,
        "counter_prob": 0.10,
        "reject_prob": 0.10,
        "counter_ratio": 0.85,
        "counter_reasoning": "We shipped wrong SKU. Offering refund minus return shipping cost.",
    },
    "NOT_DELIVERED": {
        # Seller pushes back (logistics grey area)
        "accept_prob": 0.50,
        "counter_prob": 0.35,
        "reject_prob": 0.15,
        "counter_ratio": 0.75,
        "counter_reasoning": "Tracking shows delivered. Offering goodwill credit, not full refund.",
    },
    "QUALITY_ISSUE": {
        # Most contested — quality is subjective
        "accept_prob": 0.40,
        "counter_prob": 0.45,
        "reject_prob": 0.15,
        "counter_ratio": 0.60,
        "counter_reasoning": "Item met product description. Offering partial goodwill refund only.",
    },
}

_DEFAULT_BEHAVIOUR = {
    "accept_prob": 0.60,
    "counter_prob": 0.30,
    "reject_prob": 0.10,
    "counter_ratio": 0.80,
    "counter_reasoning": "Seller proposes partial settlement.",
}

# Arbitrator accepts counter if it's >= 70% of original proposal
_COUNTER_ACCEPT_THRESHOLD = 0.70


class _MockNegotiationClient:

    async def negotiate(
        self,
        session_id: str,
        dispute_type: str,
        proposed_refund_inr: float,
        decision: str,
        confidence: float,
    ) -> NegotiationResult:
        await asyncio.sleep(random.uniform(0.08, 0.18))

        behaviour = _SELLER_BEHAVIOUR.get(dispute_type, _DEFAULT_BEHAVIOUR)
        rand = random.random()

        if rand < behaviour["accept_prob"]:
            # Seller accepts
            return NegotiationResult(
                session_id=session_id,
                dispute_type=dispute_type,
                initial_proposal_inr=proposed_refund_inr,
                seller_response=SellerResponse.ACCEPT,
                counter_offer=None,
                outcome=NegotiationOutcome.SELLER_ACCEPTED,
                final_refund_inr=proposed_refund_inr,
                seller_accepted=True,
                rounds=1,
                resolution_notes="Seller accepted arbitrator's proposal without counter.",
            )

        elif rand < behaviour["accept_prob"] + behaviour["counter_prob"]:
            # Seller counters
            counter_amount = round(proposed_refund_inr * behaviour["counter_ratio"], 2)
            counter = CounterOffer(
                offered_refund_inr=counter_amount,
                seller_reasoning=behaviour["counter_reasoning"],
            )
            # Arbitrator evaluates counter
            counter_ratio = counter_amount / proposed_refund_inr if proposed_refund_inr > 0 else 0
            arbitrator_accepts_counter = counter_ratio >= _COUNTER_ACCEPT_THRESHOLD and confidence >= 0.65

            if arbitrator_accepts_counter:
                return NegotiationResult(
                    session_id=session_id,
                    dispute_type=dispute_type,
                    initial_proposal_inr=proposed_refund_inr,
                    seller_response=SellerResponse.COUNTER,
                    counter_offer=counter,
                    outcome=NegotiationOutcome.COUNTER_OFFER_ACCEPTED,
                    final_refund_inr=counter_amount,
                    seller_accepted=True,
                    rounds=2,
                    resolution_notes=f"Counter offer of ₹{counter_amount} accepted (≥{int(_COUNTER_ACCEPT_THRESHOLD*100)}% threshold).",
                )
            else:
                # Arbitrator rejects counter — enforces original decision
                return NegotiationResult(
                    session_id=session_id,
                    dispute_type=dispute_type,
                    initial_proposal_inr=proposed_refund_inr,
                    seller_response=SellerResponse.COUNTER,
                    counter_offer=counter,
                    outcome=NegotiationOutcome.SELLER_REJECTED,
                    final_refund_inr=proposed_refund_inr,
                    seller_accepted=False,
                    rounds=2,
                    resolution_notes=f"Counter ₹{counter_amount} below {int(_COUNTER_ACCEPT_THRESHOLD*100)}% threshold. Arbitrator enforces original decision.",
                )

        else:
            # Seller rejects
            return NegotiationResult(
                session_id=session_id,
                dispute_type=dispute_type,
                initial_proposal_inr=proposed_refund_inr,
                seller_response=SellerResponse.REJECT,
                counter_offer=None,
                outcome=NegotiationOutcome.SELLER_REJECTED,
                final_refund_inr=proposed_refund_inr,
                seller_accepted=False,
                rounds=1,
                resolution_notes="Seller rejected proposal. Arbitrator's decision is binding.",
            )


# ── Real Client Stub (TODO: Member 6) ─────────────────────────────────────────

class _RealNegotiationClient:
    """
    TODO (Member 6): Connect to live ONDC seller messaging API.

    Steps:
    1. Set NEGOTIATION_BACKEND=real and ONDC_SELLER_API_KEY in .env
    2. Implement negotiate() to send proposal to seller's ONDC endpoint
    3. Poll or webhook for seller response within SLA (default 24h, mocked as instant)
    4. Map response to NegotiationResult fields
    5. Run: PYTHONPATH=. python agents/tools/negotiation_tool.py  — all tests must pass
    """

    async def negotiate(self, session_id, dispute_type, proposed_refund_inr, decision, confidence) -> NegotiationResult:
        raise NotImplementedError("Real negotiation client not yet implemented.")


# ── Singleton Factory ──────────────────────────────────────────────────────────

_client_instance = None

def _get_client():
    global _client_instance
    if _client_instance is None:
        backend = os.getenv("NEGOTIATION_BACKEND", "mock").lower()
        _client_instance = _RealNegotiationClient() if backend == "real" else _MockNegotiationClient()
        logger.info("NegotiationTool initialised with backend=%s", backend)
    return _client_instance


# ── Public Interface ───────────────────────────────────────────────────────────

async def run_negotiation(
    session_id: str,
    dispute_type: str,
    proposed_refund_inr: float,
    decision: str,
    confidence: float,
) -> dict[str, Any]:
    """
    Main entry point for negotiation_node in arbitrator.py.

    Returns dict for merging into ArbitrationState:
        state.negotiation_result  = result["report"]
        state.final_refund_inr    = result["final_refund_inr"]
        state.seller_accepted     = result["seller_accepted"]
        state.negotiation_outcome = result["outcome"]
    """
    client = _get_client()
    result = await client.negotiate(
        session_id=session_id,
        dispute_type=dispute_type,
        proposed_refund_inr=proposed_refund_inr,
        decision=decision,
        confidence=confidence,
    )
    return {
        "report": result.to_dict(),
        "final_refund_inr": result.final_refund_inr,
        "seller_accepted": result.seller_accepted,
        "outcome": result.outcome.value,
        "rounds": result.rounds,
        "resolution_notes": result.resolution_notes,
    }


# ── Self-Test ──────────────────────────────────────────────────────────────────

async def _run_tests():
    print("=" * 60)
    print("NyayaNode — Negotiation Tool Self-Test")
    print("=" * 60)
    passed = 0

    def ok(label: str, condition: bool, detail: str = ""):
        nonlocal passed
        if condition:
            print(f"✅ [{passed+1}] {label}")
            passed += 1
        else:
            print(f"❌ [{passed+1}] {label} — {detail}")

    # Run multiple times to get deterministic coverage
    random.seed(42)

    # Test 1: Result always has required keys
    r = await run_negotiation("s1", "DAMAGED_ITEM", 500.0, "FULL_REFUND", 0.88)
    ok("Result has all required keys", all(
        k in r for k in ["report", "final_refund_inr", "seller_accepted", "outcome", "rounds"]
    ))

    # Test 2: Final refund never exceeds proposed amount
    r2 = await run_negotiation("s2", "QUALITY_ISSUE", 800.0, "PARTIAL_REFUND", 0.62)
    ok("Final refund ≤ proposed amount", r2["final_refund_inr"] <= 800.0, str(r2["final_refund_inr"]))

    # Test 3: Final refund is always positive
    r3 = await run_negotiation("s3", "WRONG_ITEM", 300.0, "FULL_REFUND", 0.91)
    ok("Final refund > 0", r3["final_refund_inr"] > 0, str(r3["final_refund_inr"]))

    # Test 4: Outcome is a valid NegotiationOutcome value
    r4 = await run_negotiation("s4", "NOT_DELIVERED", 600.0, "FULL_REFUND", 0.74)
    valid_outcomes = {e.value for e in NegotiationOutcome}
    ok("Outcome is valid enum value", r4["outcome"] in valid_outcomes, r4["outcome"])

    # Test 5: Unknown dispute type doesn't crash
    r5 = await run_negotiation("s5", "UNKNOWN", 200.0, "PARTIAL_REFUND", 0.55)
    ok("Unknown dispute type → no crash", "outcome" in r5)

    # Test 6: rounds is always ≥ 1
    r6 = await run_negotiation("s6", "DAMAGED_ITEM", 1000.0, "FULL_REFUND", 0.85)
    ok("rounds ≥ 1", r6["rounds"] >= 1, str(r6["rounds"]))

    # Test 7: resolution_notes is non-empty
    r7 = await run_negotiation("s7", "DAMAGED_ITEM", 750.0, "FULL_REFUND", 0.88)
    ok("resolution_notes is non-empty", bool(r7["resolution_notes"]))

    print("-" * 60)
    print(f"{'🎉 ALL NEGOTIATION TOOL TESTS PASSED' if passed == 7 else f'⚠️  {passed}/7 passed'}")
    return passed == 7


if __name__ == "__main__":
    asyncio.run(_run_tests())
