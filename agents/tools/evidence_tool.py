"""
agents/tools/evidence_tool.py
─────────────────────────────
NyayaNode — Evidence Collection Tool
Analyses buyer-submitted evidence (photos, text, order data) and
produces a structured EvidenceReport for the arbitrator's evidence_node.

Integration points
──────────────────
• Called by  agents/core/arbitrator.py :: _evidence_node()
• Input  : ArbitrationState  (shared/schemas.py)
• Output : dict  merged back into ArbitrationState.evidence_report
• LLM    : routed through budget_harness.gate_llm_call()

Mock mode (default, no API key needed):
  EVIDENCE_BACKEND=mock   ← default
Real ONDC evidence API:
  EVIDENCE_BACKEND=real   ← Member 6 fills _RealEvidenceClient
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# ── Enums ─────────────────────────────────────────────────────────────────────

class EvidenceStrength(str, Enum):
    STRONG   = "STRONG"    # Clear proof, high confidence
    MODERATE = "MODERATE"  # Partial proof, medium confidence
    WEAK     = "WEAK"      # Ambiguous, low confidence
    NONE     = "NONE"      # No usable evidence

class EvidenceType(str, Enum):
    PHOTO       = "photo"
    TEXT        = "text"
    INVOICE     = "invoice"
    TRACKING    = "tracking"
    VIDEO       = "video"
    SCREENSHOT  = "screenshot"

# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class EvidenceItem:
    type: str
    content: str
    hash: str = field(default="")
    analyzed: bool = False
    relevance_score: float = 0.0
    notes: str = ""

    def __post_init__(self):
        if not self.hash:
            self.hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]

@dataclass
class EvidenceReport:
    session_id: str
    dispute_type: str
    items_analyzed: int
    strength: EvidenceStrength
    confidence: float                   # 0.0 – 1.0
    buyer_claim_supported: bool
    key_findings: list[str]
    red_flags: list[str]                # inconsistencies or fraud signals
    recommended_action: str
    evidence_sufficient: bool           # gates NEGOTIATION transition
    raw_items: list[EvidenceItem]
    analyzed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "dispute_type": self.dispute_type,
            "items_analyzed": self.items_analyzed,
            "strength": self.strength.value,
            "confidence": self.confidence,
            "buyer_claim_supported": self.buyer_claim_supported,
            "key_findings": self.key_findings,
            "red_flags": self.red_flags,
            "recommended_action": self.recommended_action,
            "evidence_sufficient": self.evidence_sufficient,
            "analyzed_at": self.analyzed_at,
        }

# ── Mock Client ───────────────────────────────────────────────────────────────

# Realistic mock responses keyed by dispute type
_MOCK_RESPONSES: dict[str, dict] = {
    "DAMAGED_ITEM": {
        "strength": EvidenceStrength.STRONG,
        "confidence": 0.88,
        "buyer_claim_supported": True,
        "key_findings": [
            "Photo evidence shows crushed packaging consistent with mishandling",
            "Item serial number matches order invoice",
            "Damage pattern inconsistent with manufacturing defect — logistics fault",
        ],
        "red_flags": [],
        "recommended_action": "APPROVE_FULL_REFUND",
        "evidence_sufficient": True,
    },
    "WRONG_ITEM": {
        "strength": EvidenceStrength.STRONG,
        "confidence": 0.91,
        "buyer_claim_supported": True,
        "key_findings": [
            "Photo shows item SKU does not match ordered SKU",
            "Invoice confirms ordered SKU: discrepancy confirmed",
            "Seller dispatch record shows correct SKU — possible fulfilment mix-up",
        ],
        "red_flags": [],
        "recommended_action": "APPROVE_FULL_REFUND_AND_REPLACEMENT",
        "evidence_sufficient": True,
    },
    "NOT_DELIVERED": {
        "strength": EvidenceStrength.MODERATE,
        "confidence": 0.71,
        "buyer_claim_supported": True,
        "key_findings": [
            "Tracking shows 'delivered' but buyer disputes receipt",
            "No delivery photo proof from logistics partner",
            "GPS coordinates of delivery attempt not within buyer address radius",
        ],
        "red_flags": ["Tracking marked delivered — possible misdelivery or theft"],
        "recommended_action": "ESCALATE_TO_LOGISTICS_INVESTIGATION",
        "evidence_sufficient": True,
    },
    "QUALITY_ISSUE": {
        "strength": EvidenceStrength.MODERATE,
        "confidence": 0.62,
        "buyer_claim_supported": True,
        "key_findings": [
            "Photos show item condition below described quality grade",
            "Seller product listing images do not match received item",
        ],
        "red_flags": ["No independent quality certificate available"],
        "recommended_action": "APPROVE_PARTIAL_REFUND",
        "evidence_sufficient": True,
    },
}

_WEAK_FALLBACK = {
    "strength": EvidenceStrength.WEAK,
    "confidence": 0.38,
    "buyer_claim_supported": False,
    "key_findings": ["Insufficient evidence submitted to make a determination"],
    "red_flags": ["Claim unsubstantiated — possible buyer error"],
    "recommended_action": "REQUEST_MORE_EVIDENCE",
    "evidence_sufficient": False,
}


class _MockEvidenceClient:
    """
    Simulates evidence analysis without live ONDC APIs.
    Deterministic for given (dispute_type, evidence_count) inputs.
    """

    async def analyse(
        self,
        session_id: str,
        dispute_type: str,
        evidence_items: list[dict],
        dispute_amount_inr: float,
    ) -> EvidenceReport:
        # Simulate async network latency
        await asyncio.sleep(random.uniform(0.05, 0.15))

        items = []
        for e in evidence_items:
            if isinstance(e, dict):
                items.append(EvidenceItem(
                    type=e.get("type", "text"),
                    content=e.get("content", ""),
                    metadata={
                        "relevance_score": round(random.uniform(0.5, 1.0), 2),
                        "analyzed": True
                    }
                ))
            else:
                e.metadata["relevance_score"] = round(random.uniform(0.5, 1.0), 2)
                e.metadata["analyzed"] = True
                items.append(e)

        # If no evidence submitted → weak
        if not items:
            template = _WEAK_FALLBACK
        else:
            template = _MOCK_RESPONSES.get(dispute_type, _WEAK_FALLBACK)

        # Large amounts get slightly lower confidence (more scrutiny)
        confidence = template["confidence"]
        if dispute_amount_inr > 10_000:
            confidence = round(max(0.40, confidence - 0.08), 2)

        return EvidenceReport(
            session_id=session_id,
            dispute_type=dispute_type,
            items_analyzed=len(items),
            strength=template["strength"],
            confidence=confidence,
            buyer_claim_supported=template["buyer_claim_supported"],
            key_findings=list(template["key_findings"]),
            red_flags=list(template["red_flags"]),
            recommended_action=template["recommended_action"],
            evidence_sufficient=template["evidence_sufficient"],
            raw_items=items,
        )


# ── Real Client Stub (TODO: Member 6) ─────────────────────────────────────────

class _RealEvidenceClient:
    """
    TODO (Member 6): Replace mock with live ONDC evidence API.

    Steps:
    1. Set EVIDENCE_BACKEND=real and ONDC_EVIDENCE_API_KEY in .env
    2. Implement analyse() to call the real endpoint
    3. Map the API response to EvidenceReport fields
    4. Run: PYTHONPATH=. python agents/tools/evidence_tool.py  — all tests must still pass
    """

    async def analyse(
        self,
        session_id: str,
        dispute_type: str,
        evidence_items: list[dict],
        dispute_amount_inr: float,
    ) -> EvidenceReport:
        raise NotImplementedError(
            "Real evidence client not yet implemented. "
            "See TODO comments above."
        )


# ── Singleton Factory ──────────────────────────────────────────────────────────

_client_instance: _MockEvidenceClient | _RealEvidenceClient | None = None

def _get_client() -> _MockEvidenceClient | _RealEvidenceClient:
    global _client_instance
    if _client_instance is None:
        backend = os.getenv("EVIDENCE_BACKEND", "mock").lower()
        _client_instance = _RealEvidenceClient() if backend == "real" else _MockEvidenceClient()
        logger.info("EvidenceTool initialised with backend=%s", backend)
    return _client_instance


# ── Public Interface (called by arbitrator.py) ────────────────────────────────

async def collect_and_analyse_evidence(
    session_id: str,
    dispute_type: str,
    evidence_items: list[dict[str, Any]],
    dispute_amount_inr: float,
) -> dict[str, Any]:
    """
    Main entry point for evidence_node in arbitrator.py.

    Returns a dict suitable for merging into ArbitrationState:
        state.evidence_report  = result["report"]
        state.evidence_sufficient = result["evidence_sufficient"]
        state.confidence_score    = result["confidence"]
    """
    client = _get_client()
    report = await client.analyse(
        session_id=session_id,
        dispute_type=dispute_type,
        evidence_items=evidence_items,
        dispute_amount_inr=dispute_amount_inr,
    )
    return {
        "report": report.to_dict(),
        "evidence_sufficient": report.evidence_sufficient,
        "confidence": report.confidence,
        "strength": report.strength.value,
        "recommended_action": report.recommended_action,
    }


# ── Self-Test ──────────────────────────────────────────────────────────────────

async def _run_tests():
    print("=" * 60)
    print("NyayaNode — Evidence Tool Self-Test")
    print("=" * 60)
    passed = 0

    async def check(label, coro, assertion):
        nonlocal passed
        result = await coro
        try:
            assertion(result)
            print(f"✅ [{passed+1}] {label}")
            passed += 1
        except AssertionError as e:
            print(f"❌ [{passed+1}] {label} — {e}")

    evidence = [{"type": "photo", "content": "crushed_box.jpg"}]

    # 1. DAMAGED_ITEM returns strong evidence
    await check(
        "DAMAGED_ITEM → STRONG evidence",
        collect_and_analyse_evidence("s1", "DAMAGED_ITEM", evidence, 500.0),
        lambda r: assert_true(r["strength"] == "STRONG", f"got {r['strength']}"),
    )

    # 2. evidence_sufficient=True for known dispute types
    await check(
        "evidence_sufficient=True for WRONG_ITEM",
        collect_and_analyse_evidence("s2", "WRONG_ITEM", evidence, 800.0),
        lambda r: assert_true(r["evidence_sufficient"], "should be sufficient"),
    )

    # 3. Empty evidence → weak
    await check(
        "Empty evidence → evidence_sufficient=False",
        collect_and_analyse_evidence("s3", "DAMAGED_ITEM", [], 200.0),
        lambda r: assert_true(not r["evidence_sufficient"], "should be insufficient"),
    )

    # 4. Large amount lowers confidence
    await check(
        "Amount > ₹10k reduces confidence",
        collect_and_analyse_evidence("s4", "DAMAGED_ITEM", evidence, 15_000.0),
        lambda r: assert_true(r["confidence"] < 0.88, f"expected <0.88, got {r['confidence']}"),
    )

    # 5. NOT_DELIVERED returns correct recommendation
    await check(
        "NOT_DELIVERED → ESCALATE recommendation",
        collect_and_analyse_evidence("s5", "NOT_DELIVERED", evidence, 300.0),
        lambda r: assert_true("ESCALATE" in r["recommended_action"], f"got {r['recommended_action']}"),
    )

    # 6. Unknown dispute type → weak fallback (no crash)
    await check(
        "Unknown dispute type → graceful fallback",
        collect_and_analyse_evidence("s6", "MYSTERY_TYPE", evidence, 100.0),
        lambda r: assert_true(r["strength"] == "WEAK", f"got {r['strength']}"),
    )

    # 7. Report dict has all required keys for arbitrator.py
    result = await collect_and_analyse_evidence("s7", "QUALITY_ISSUE", evidence, 700.0)
    async def _mock_coro(val):
        return val

    await check(
        "Result dict has all required keys",
        _mock_coro(result),
        lambda r: assert_true(
            all(k in r for k in ["report", "evidence_sufficient", "confidence", "strength", "recommended_action"]),
            f"missing keys in {list(r.keys())}",
        ),
    )

    print("-" * 60)
    print(f"{'🎉 ALL EVIDENCE TOOL TESTS PASSED' if passed == 7 else f'⚠️  {passed}/7 passed'}")
    return passed == 7


def assert_true(condition: bool, msg: str = ""):
    if not condition:
        raise AssertionError(msg)


if __name__ == "__main__":
    asyncio.run(_run_tests())
