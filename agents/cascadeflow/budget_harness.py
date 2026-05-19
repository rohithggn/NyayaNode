"""
agents/cascadeflow/budget_harness.py
=====================================
Cascadeflow SDK integration for NyayaNode — per-dispute ₹5 inference
budget enforcement, model routing, and cost telemetry.

WHO USES THIS:
  - Member 2 (Cascadeflow Integration): owns the _RealCascadeflowClient
    class below. Wire the real SDK into the stub methods marked TODO.
  - Member 1 (Lead AI Architect): calls gate_llm_call() from
    arbitrator.py._route_llm_call() — the hook is already in place.
  - Member 5 (QA): imports BudgetHarness and MockCascadeflowClient
    to test budget exhaustion and model downgrade scenarios.

HOW IT WORKS:
  Every LangGraph LLM call goes through gate_llm_call() BEFORE hitting
  Groq. The gate:
    1. Estimates cost of the pending call
    2. Checks remaining budget
    3. Downgrades model (70b → 8b) if cost would exceed budget
    4. Blocks call entirely if even 8b would exceed budget
    5. Records actual cost after call completes
    6. Emits BUDGET_WARNING audit event at 80% consumption
    7. Emits BUDGET_EXHAUSTED and raises BudgetExhaustedError at 100%

CASCADEFLOW SDK STATUS:
  Real SDK provided at hackathon. Until then:
    - LocalCascadeflowClient runs as a fully functional local harness
    - Set CASCADEFLOW_BACKEND=real in .env when SDK arrives
    - All method signatures are identical — zero other changes needed

MEMBER 2 INTEGRATION CHECKLIST:
  [ ] pip install cascadeflow-sdk (when available)
  [ ] Set CASCADEFLOW_API_KEY, CASCADEFLOW_PROJECT_ID in .env
  [ ] Set CASCADEFLOW_BACKEND=real in .env
  [ ] Fill in _RealCascadeflowClient methods (marked TODO below)
  [ ] Run: PYTHONPATH=. python agents/cascadeflow/budget_harness.py
  [ ] All 10 self-tests should pass unchanged

BUDGET POLICY (per ONDC cost constraint):
  ┌─────────────────────────────────────────────────────┐
  │  Per-dispute budget cap:  ₹5.00                     │
  │  Warning threshold:       ₹4.00 (80%)               │
  │  Model routing:           70b → 8b at ₹3.50 (70%)   │
  │  Hard stop:               ₹5.00 — escalate dispute   │
  └─────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import structlog
from dotenv import load_dotenv

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

load_dotenv(os.path.join(_REPO_ROOT, ".env"))

from shared.constants import (
    BUDGET_CAP_INR,
    BUDGET_WARNING_THRESHOLD,
    GROQ_INR_PER_1K_70B,
    GROQ_INR_PER_1K_8B,
    LLM_HEAVY_MODEL,
    LLM_LIGHT_MODEL,
    MAX_TOKENS_DECISION,
)
from shared.schemas import (
    ArbitrationState,
    AuditEventType,
    BudgetStatus,
)
from agents.core.state_machine import BudgetExhaustedError

log = structlog.get_logger("nyayanode.cascadeflow")

# Model downgrade threshold — switch to 8b when 70% of budget consumed
_DOWNGRADE_THRESHOLD = 0.70


# ---------------------------------------------------------------------------
# Cost Records
# ---------------------------------------------------------------------------

@dataclass
class CostRecord:
    """Immutable record of a single LLM call's cost. Stored in Cascadeflow."""
    record_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    dispute_id: str = ""
    task_label: str = ""
    model_requested: str = ""
    model_used: str = ""       # may differ if downgraded
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_inr: float = 0.0
    was_downgraded: bool = False
    was_blocked: bool = False
    latency_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "dispute_id": self.dispute_id,
            "task_label": self.task_label,
            "model_requested": self.model_requested,
            "model_used": self.model_used,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_inr": self.cost_inr,
            "was_downgraded": self.was_downgraded,
            "was_blocked": self.was_blocked,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
        }


@dataclass
class BudgetSnapshot:
    """Point-in-time view of a dispute's budget consumption."""
    dispute_id: str
    budget_cap_inr: float
    consumed_inr: float
    remaining_inr: float
    pct_consumed: float
    llm_calls: int
    is_exhausted: bool
    is_warning: bool
    is_downgrade_zone: bool
    records: list[CostRecord] = field(default_factory=list)

    @classmethod
    def from_budget_status(
        cls,
        status: BudgetStatus,
        records: list[CostRecord] | None = None,
    ) -> "BudgetSnapshot":
        pct = status.consumed_inr / status.budget_cap_inr if status.budget_cap_inr else 0.0
        return cls(
            dispute_id=status.dispute_id,
            budget_cap_inr=status.budget_cap_inr,
            consumed_inr=status.consumed_inr,
            remaining_inr=status.remaining_inr,
            pct_consumed=round(pct, 4),
            llm_calls=status.llm_calls,
            is_exhausted=status.is_exhausted,
            is_warning=pct >= BUDGET_WARNING_THRESHOLD,
            is_downgrade_zone=pct >= _DOWNGRADE_THRESHOLD,
            records=records or [],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dispute_id": self.dispute_id,
            "budget_cap_inr": self.budget_cap_inr,
            "consumed_inr": round(self.consumed_inr, 4),
            "remaining_inr": round(self.remaining_inr, 4),
            "pct_consumed": self.pct_consumed,
            "llm_calls": self.llm_calls,
            "is_exhausted": self.is_exhausted,
            "is_warning": self.is_warning,
            "is_downgrade_zone": self.is_downgrade_zone,
            "record_count": len(self.records),
        }


# ---------------------------------------------------------------------------
# Routing Decision
# ---------------------------------------------------------------------------

@dataclass
class RoutingDecision:
    """
    The output of gate_llm_call() — tells arbitrator.py exactly what to do.

    If blocked=True → raise BudgetExhaustedError, force escalate.
    If downgraded=True → use model_to_use (8b) instead of requested model.
    Otherwise → proceed with model_to_use (same as requested).
    """
    dispute_id: str
    task_label: str
    model_requested: str
    model_to_use: str
    max_tokens: int
    blocked: bool = False
    downgraded: bool = False
    block_reason: str = ""
    budget_snapshot: BudgetSnapshot | None = None
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def should_proceed(self) -> bool:
        return not self.blocked


# ---------------------------------------------------------------------------
# Abstract Client Interface
# ---------------------------------------------------------------------------

class BaseCascadeflowClient(ABC):
    """
    Abstract interface implemented by both LocalCascadeflowClient and
    RealCascadeflowClient.

    MEMBER 2: implement RealCascadeflowClient using this interface.
    All method signatures must match exactly — arbitrator.py depends on them.
    """

    @abstractmethod
    async def request_routing(
        self,
        dispute_id: str,
        task_label: str,
        model_requested: str,
        estimated_prompt_tokens: int,
        max_completion_tokens: int,
        budget_status: BudgetStatus,
    ) -> RoutingDecision:
        """
        Pre-call gate: decide whether to proceed, downgrade, or block.
        Called BEFORE the Groq API call.
        """
        ...

    @abstractmethod
    async def record_cost(
        self,
        decision: RoutingDecision,
        actual_prompt_tokens: int,
        actual_completion_tokens: int,
        latency_ms: float,
    ) -> CostRecord:
        """
        Post-call accounting: record actual token usage and cost.
        Called AFTER the Groq API call completes.
        """
        ...

    @abstractmethod
    async def get_budget_snapshot(
        self, dispute_id: str
    ) -> BudgetSnapshot | None:
        """Return current budget state for a dispute."""
        ...

    @abstractmethod
    async def get_cost_records(
        self, dispute_id: str
    ) -> list[CostRecord]:
        """Return all CostRecords for a dispute (for audit trail)."""
        ...


# ---------------------------------------------------------------------------
# Local Client (fully functional — runs without real Cascadeflow SDK)
# ---------------------------------------------------------------------------

class LocalCascadeflowClient(BaseCascadeflowClient):
    """
    Production-quality local implementation of Cascadeflow budget gating.

    Applies all routing rules locally:
      - Cost estimation using Groq token rates from constants.py
      - Model downgrade at 70% budget consumption
      - Hard block at 100% budget
      - Warning events at 80%

    No external API calls — safe for demo and testing.
    """

    def __init__(self) -> None:
        # dispute_id → list[CostRecord]
        self._records: dict[str, list[CostRecord]] = {}

    # ── Cost Estimation ─────────────────────────────────────────────────────

    @staticmethod
    def _estimate_cost(
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Estimate INR cost for a given token count and model."""
        rate = GROQ_INR_PER_1K_70B if "70b" in model else GROQ_INR_PER_1K_8B
        return round((prompt_tokens + completion_tokens) / 1000 * rate, 6)

    @staticmethod
    def _select_model(
        model_requested: str,
        pct_consumed: float,
    ) -> tuple[str, bool]:
        """
        Apply routing policy:
          < 70% consumed  → use requested model
          70–100%         → downgrade to 8b if requested is 70b
          100%            → block (handled by caller)

        Returns (model_to_use, was_downgraded).
        """
        if model_requested == LLM_HEAVY_MODEL and pct_consumed >= _DOWNGRADE_THRESHOLD:
            return LLM_LIGHT_MODEL, True
        return model_requested, False

    # ── Interface Implementation ─────────────────────────────────────────────

    async def request_routing(
        self,
        dispute_id: str,
        task_label: str,
        model_requested: str,
        estimated_prompt_tokens: int,
        max_completion_tokens: int,
        budget_status: BudgetStatus,
    ) -> RoutingDecision:
        pct = (
            budget_status.consumed_inr / budget_status.budget_cap_inr
            if budget_status.budget_cap_inr
            else 1.0
        )
        snapshot = BudgetSnapshot.from_budget_status(
            budget_status,
            records=self._records.get(dispute_id, []),
        )

        # ── Hard block: budget exhausted ─────────────────────────────────
        if budget_status.is_exhausted or pct >= 1.0:
            log.warning(
                "cascadeflow_blocked",
                dispute_id=dispute_id,
                task=task_label,
                pct_consumed=pct,
            )
            return RoutingDecision(
                dispute_id=dispute_id,
                task_label=task_label,
                model_requested=model_requested,
                model_to_use=model_requested,
                max_tokens=max_completion_tokens,
                blocked=True,
                block_reason=f"Budget exhausted: {pct*100:.1f}% consumed "
                             f"(₹{budget_status.consumed_inr:.4f} / "
                             f"₹{budget_status.budget_cap_inr:.2f})",
                budget_snapshot=snapshot,
            )

        # ── Soft block: even 8b call would exceed remaining budget ────────
        min_cost = self._estimate_cost(
            LLM_LIGHT_MODEL, estimated_prompt_tokens, max_completion_tokens
        )
        if min_cost > budget_status.remaining_inr:
            log.warning(
                "cascadeflow_soft_blocked",
                dispute_id=dispute_id,
                task=task_label,
                min_cost=min_cost,
                remaining=budget_status.remaining_inr,
            )
            return RoutingDecision(
                dispute_id=dispute_id,
                task_label=task_label,
                model_requested=model_requested,
                model_to_use=model_requested,
                max_tokens=max_completion_tokens,
                blocked=True,
                block_reason=(
                    f"Insufficient budget: cheapest call costs ₹{min_cost:.4f}, "
                    f"only ₹{budget_status.remaining_inr:.4f} remaining"
                ),
                budget_snapshot=snapshot,
            )

        # ── Model routing: downgrade if in downgrade zone ─────────────────
        model_to_use, was_downgraded = self._select_model(model_requested, pct)

        # Recalculate max_tokens if downgraded (8b has smaller context)
        effective_max_tokens = (
            min(max_completion_tokens, 512)
            if was_downgraded
            else max_completion_tokens
        )

        if was_downgraded:
            log.info(
                "cascadeflow_downgrade",
                dispute_id=dispute_id,
                task=task_label,
                from_model=model_requested,
                to_model=model_to_use,
                pct_consumed=round(pct * 100, 1),
            )

        log.debug(
            "cascadeflow_approved",
            dispute_id=dispute_id,
            task=task_label,
            model=model_to_use,
            downgraded=was_downgraded,
            pct_consumed=round(pct * 100, 1),
        )

        return RoutingDecision(
            dispute_id=dispute_id,
            task_label=task_label,
            model_requested=model_requested,
            model_to_use=model_to_use,
            max_tokens=effective_max_tokens,
            blocked=False,
            downgraded=was_downgraded,
            budget_snapshot=snapshot,
        )

    async def record_cost(
        self,
        decision: RoutingDecision,
        actual_prompt_tokens: int,
        actual_completion_tokens: int,
        latency_ms: float,
    ) -> CostRecord:
        actual_cost = self._estimate_cost(
            decision.model_to_use,
            actual_prompt_tokens,
            actual_completion_tokens,
        )
        record = CostRecord(
            dispute_id=decision.dispute_id,
            task_label=decision.task_label,
            model_requested=decision.model_requested,
            model_used=decision.model_to_use,
            prompt_tokens=actual_prompt_tokens,
            completion_tokens=actual_completion_tokens,
            total_tokens=actual_prompt_tokens + actual_completion_tokens,
            cost_inr=actual_cost,
            was_downgraded=decision.downgraded,
            was_blocked=decision.blocked,
            latency_ms=latency_ms,
        )

        if decision.dispute_id not in self._records:
            self._records[decision.dispute_id] = []
        self._records[decision.dispute_id].append(record)

        log.info(
            "cascadeflow_cost_recorded",
            dispute_id=decision.dispute_id,
            task=decision.task_label,
            model=decision.model_to_use,
            tokens=record.total_tokens,
            cost_inr=actual_cost,
            latency_ms=round(latency_ms, 1),
        )
        return record

    async def get_budget_snapshot(
        self, dispute_id: str
    ) -> BudgetSnapshot | None:
        records = self._records.get(dispute_id, [])
        if not records:
            return None
        total_cost = sum(r.cost_inr for r in records)
        consumed = round(total_cost, 6)
        remaining = round(max(0.0, BUDGET_CAP_INR - consumed), 6)
        pct = consumed / BUDGET_CAP_INR if BUDGET_CAP_INR else 0.0
        return BudgetSnapshot(
            dispute_id=dispute_id,
            budget_cap_inr=BUDGET_CAP_INR,
            consumed_inr=consumed,
            remaining_inr=remaining,
            pct_consumed=round(pct, 4),
            llm_calls=len(records),
            is_exhausted=consumed >= BUDGET_CAP_INR,
            is_warning=pct >= BUDGET_WARNING_THRESHOLD,
            is_downgrade_zone=pct >= _DOWNGRADE_THRESHOLD,
            records=records,
        )

    async def get_cost_records(self, dispute_id: str) -> list[CostRecord]:
        return self._records.get(dispute_id, [])


# ---------------------------------------------------------------------------
# Real Cascadeflow SDK Wrapper
# ---------------------------------------------------------------------------

class _RealCascadeflowClient(BaseCascadeflowClient):
    """
    Wraps the real Cascadeflow SDK.

    MEMBER 2 — activate when SDK is provided at the hackathon:
      1. pip install cascadeflow-sdk
      2. Set CASCADEFLOW_BACKEND=real in .env
      3. Fill in each TODO below with the real SDK call
      4. Run self-test: PYTHONPATH=. python agents/cascadeflow/budget_harness.py

    The interface contract is fixed — Member 1's arbitrator.py will not change.
    """

    def __init__(self) -> None:
        api_key = os.getenv("CASCADEFLOW_API_KEY", "")
        project_id = os.getenv("CASCADEFLOW_PROJECT_ID", "nyayanode")
        base_url = os.getenv("CASCADEFLOW_BASE_URL", "https://api.cascadeflow.io/v1")

        if not api_key:
            raise RuntimeError(
                "CASCADEFLOW_API_KEY not set. "
                "Set CASCADEFLOW_BACKEND=local to use local harness."
            )

        # TODO: Replace with real SDK init
        # import cascadeflow
        # self._client = cascadeflow.Client(
        #     api_key=api_key,
        #     project=project_id,
        #     base_url=base_url,
        # )
        self._api_key = api_key
        self._project_id = project_id
        log.info("real_cascadeflow_init", project=project_id)

    async def request_routing(
        self,
        dispute_id: str,
        task_label: str,
        model_requested: str,
        estimated_prompt_tokens: int,
        max_completion_tokens: int,
        budget_status: BudgetStatus,
    ) -> RoutingDecision:
        # TODO: Replace with real SDK routing call, e.g.:
        # result = await self._client.route(
        #     session_id=dispute_id,
        #     model=model_requested,
        #     estimated_tokens=estimated_prompt_tokens + max_completion_tokens,
        #     budget_cap=budget_status.budget_cap_inr,
        #     consumed=budget_status.consumed_inr,
        # )
        # return RoutingDecision(
        #     dispute_id=dispute_id,
        #     task_label=task_label,
        #     model_requested=model_requested,
        #     model_to_use=result.routed_model,
        #     max_tokens=result.max_tokens,
        #     blocked=result.blocked,
        #     downgraded=result.routed_model != model_requested,
        # )
        raise NotImplementedError(
            "Wire real Cascadeflow SDK here. "
            "See TODO comments above for the expected call signature."
        )

    async def record_cost(
        self,
        decision: RoutingDecision,
        actual_prompt_tokens: int,
        actual_completion_tokens: int,
        latency_ms: float,
    ) -> CostRecord:
        # TODO:
        # await self._client.record(
        #     session_id=decision.dispute_id,
        #     model=decision.model_to_use,
        #     prompt_tokens=actual_prompt_tokens,
        #     completion_tokens=actual_completion_tokens,
        # )
        raise NotImplementedError("Wire real Cascadeflow SDK here.")

    async def get_budget_snapshot(self, dispute_id: str) -> BudgetSnapshot | None:
        # TODO: return self._client.budget.get(session_id=dispute_id)
        raise NotImplementedError("Wire real Cascadeflow SDK here.")

    async def get_cost_records(self, dispute_id: str) -> list[CostRecord]:
        # TODO: return self._client.records.list(session_id=dispute_id)
        raise NotImplementedError("Wire real Cascadeflow SDK here.")


# ---------------------------------------------------------------------------
# Client Factory
# ---------------------------------------------------------------------------

_client_instance: BaseCascadeflowClient | None = None


def get_cascadeflow_client() -> BaseCascadeflowClient:
    """
    Return the appropriate Cascadeflow client.
    Singleton — one client per process.

    CASCADEFLOW_BACKEND=real   → _RealCascadeflowClient
    CASCADEFLOW_BACKEND=local  → LocalCascadeflowClient (default)
    """
    global _client_instance
    if _client_instance is not None:
        return _client_instance

    backend = os.getenv("CASCADEFLOW_BACKEND", "local").lower()
    if backend == "real":
        _client_instance = _RealCascadeflowClient()
        log.info("cascadeflow_backend", mode="real")
    else:
        _client_instance = LocalCascadeflowClient()
        log.info("cascadeflow_backend", mode="local")

    return _client_instance


# ---------------------------------------------------------------------------
# BudgetHarness — High-Level API used by arbitrator.py
# ---------------------------------------------------------------------------

class BudgetHarness:
    """
    High-level API that wraps BaseCascadeflowClient for use in arbitrator.py.

    Usage in arbitrator.py._route_llm_call():

        harness = BudgetHarness()

        # BEFORE the Groq call:
        decision = await harness.gate(
            state=state,
            model=model,
            task_label=task_label,
            estimated_prompt_tokens=500,
            max_completion_tokens=max_tokens,
        )
        if decision.blocked:
            raise BudgetExhaustedError(decision.block_reason)
        model = decision.model_to_use   # use (possibly downgraded) model

        # AFTER the Groq call:
        await harness.charge(
            state=state,
            decision=decision,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )
    """

    def __init__(self, client: BaseCascadeflowClient | None = None) -> None:
        self._client = client or get_cascadeflow_client()

    async def gate(
        self,
        state: ArbitrationState,
        model: str,
        task_label: str,
        estimated_prompt_tokens: int = 500,
        max_completion_tokens: int = MAX_TOKENS_DECISION,
    ) -> RoutingDecision:
        """
        Pre-call gate. Returns a RoutingDecision.
        If decision.blocked → raise BudgetExhaustedError.
        Always use decision.model_to_use for the actual Groq call.
        """
        decision = await self._client.request_routing(
            dispute_id=state.dispute_id,
            task_label=task_label,
            model_requested=model,
            estimated_prompt_tokens=estimated_prompt_tokens,
            max_completion_tokens=max_completion_tokens,
            budget_status=state.budget_status,
        )

        # Emit warning audit event if in warning zone
        if (
            decision.budget_snapshot
            and decision.budget_snapshot.is_warning
            and not decision.blocked
        ):
            state.add_audit(
                event_type=AuditEventType.BUDGET_WARNING,
                description=(
                    f"Budget warning: {decision.budget_snapshot.pct_consumed*100:.1f}% "
                    f"consumed (₹{decision.budget_snapshot.consumed_inr:.4f} / "
                    f"₹{decision.budget_snapshot.budget_cap_inr:.2f})"
                ),
                metadata=decision.budget_snapshot.to_dict(),
            )

        if decision.blocked:
            state.budget_status.is_exhausted = True
            state.add_audit(
                event_type=AuditEventType.BUDGET_EXHAUSTED,
                description=f"Budget exhausted before {task_label}: {decision.block_reason}",
                metadata={"block_reason": decision.block_reason},
            )

        return decision

    async def charge(
        self,
        state: ArbitrationState,
        decision: RoutingDecision,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float = 0.0,
    ) -> CostRecord:
        """
        Post-call accounting. Updates state.budget_status in-place.
        Must be called after every successful Groq API call.
        """
        record = await self._client.record_cost(
            decision=decision,
            actual_prompt_tokens=prompt_tokens,
            actual_completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )

        # Update the ArbitrationState budget in-place
        state.add_audit(
            event_type=AuditEventType.DECISION_DRAFTED,  # reuse as cost event
            description=(
                f"LLM call: {decision.task_label} "
                f"[{decision.model_to_use}] "
                f"— {record.total_tokens} tokens "
                f"— ₹{record.cost_inr:.4f}"
                + (" [downgraded]" if decision.downgraded else "")
            ),
            metadata=record.to_dict(),
            cost_inr=record.cost_inr,
        )

        # Check if this charge exhausted the budget
        if state.budget_status.is_exhausted:
            state.add_audit(
                event_type=AuditEventType.BUDGET_EXHAUSTED,
                description=(
                    f"Budget cap reached after {state.budget_status.llm_calls} calls. "
                    f"Total: ₹{state.budget_status.consumed_inr:.4f}"
                ),
                metadata={"total_cost_inr": state.budget_status.consumed_inr},
            )

        return record

    async def snapshot(self, state: ArbitrationState) -> BudgetSnapshot:
        """Return a real-time BudgetSnapshot for a dispute."""
        snap = await self._client.get_budget_snapshot(state.dispute_id)
        if snap:
            return snap
        # First call — no records yet
        return BudgetSnapshot.from_budget_status(state.budget_status)

    async def audit_records(self, dispute_id: str) -> list[dict[str, Any]]:
        """Return all cost records as dicts — used by Member 3's audit endpoint."""
        records = await self._client.get_cost_records(dispute_id)
        return [r.to_dict() for r in records]


# ---------------------------------------------------------------------------
# Convenience Function — drop-in for arbitrator.py
# ---------------------------------------------------------------------------

async def gate_llm_call(
    state: ArbitrationState,
    model: str,
    max_tokens: int,
    task_label: str = "llm_call",
    estimated_prompt_tokens: int = 500,
) -> RoutingDecision:
    """
    Drop-in gate function for arbitrator.py._route_llm_call().

    MEMBER 1 INTEGRATION — replace the budget check block in
    arbitrator.py._route_llm_call() with:

        from agents.cascadeflow.budget_harness import gate_llm_call
        decision = await gate_llm_call(state, model, max_tokens, task_label)
        if decision.blocked:
            raise BudgetExhaustedError(decision.block_reason)
        model = decision.model_to_use

    Returns RoutingDecision. If blocked, caller raises BudgetExhaustedError.
    """
    harness = BudgetHarness()
    return await harness.gate(
        state=state,
        model=model,
        task_label=task_label,
        estimated_prompt_tokens=estimated_prompt_tokens,
        max_completion_tokens=max_tokens,
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    async def _self_test() -> None:
        print("=" * 60)
        print("NyayaNode — Cascadeflow Budget Harness Self-Test")
        print("=" * 60)

        from shared.schemas import (
            ArbitrationState, BudgetStatus, DisputeRequest,
            DisputeType, EvidenceItem, EvidenceType,
        )

        def _make_state(cap: float = BUDGET_CAP_INR) -> ArbitrationState:
            req = DisputeRequest(
                buyer_id="buyer_001",
                seller_id="seller_042",
                logistics_id="lsp_007",
                order_id="order_xyz",
                dispute_type=DisputeType.DAMAGED_ITEM,
                evidence=[EvidenceItem(type=EvidenceType.TEXT, content="Broken item")],
                dispute_amount_inr=500.0,
            )
            budget = BudgetStatus(
                dispute_id=req.dispute_id,
                budget_cap_inr=cap,
                consumed_inr=0.0,
                remaining_inr=cap,
            )
            return ArbitrationState(
                dispute_id=req.dispute_id, request=req, budget_status=budget
            )

        client = LocalCascadeflowClient()
        harness = BudgetHarness(client=client)

        # ── Test 1: Fresh dispute — 70b request approved ──────────────────
        print("\n[1] Fresh dispute — heavy model approved...")
        state = _make_state()
        decision = await harness.gate(
            state, LLM_HEAVY_MODEL, "evidence_analysis", 400, 1024
        )
        assert decision.should_proceed
        assert not decision.downgraded
        assert decision.model_to_use == LLM_HEAVY_MODEL
        print(f"   ✅ Approved: {decision.model_to_use}")

        # ── Test 2: Charge and verify budget updated ───────────────────────
        print("\n[2] Charge and verify budget tracking...")
        record = await harness.charge(
            state, decision,
            prompt_tokens=400, completion_tokens=800, latency_ms=340.0,
        )
        assert record.cost_inr > 0
        assert state.budget_status.consumed_inr > 0
        assert state.budget_status.remaining_inr < BUDGET_CAP_INR
        print(f"   ✅ Charged ₹{record.cost_inr:.4f}, remaining: ₹{state.budget_status.remaining_inr:.4f}")

        # ── Test 3: Model downgrade at 70% consumption ────────────────────
        print("\n[3] Model downgrade at 70% budget consumption...")
        state3 = _make_state()
        # Burn 72% of budget
        state3.budget_status.consumed_inr = BUDGET_CAP_INR * 0.72
        state3.budget_status.remaining_inr = BUDGET_CAP_INR * 0.28
        decision3 = await harness.gate(
            state3, LLM_HEAVY_MODEL, "decision_drafting", 400, 1024
        )
        assert decision3.should_proceed
        assert decision3.downgraded
        assert decision3.model_to_use == LLM_LIGHT_MODEL
        assert decision3.max_tokens <= 512
        print(f"   ✅ Downgraded: {LLM_HEAVY_MODEL} → {decision3.model_to_use}")
        print(f"   ✅ Max tokens capped at: {decision3.max_tokens}")

        # ── Test 4: 8b model NOT downgraded at 70% ────────────────────────
        print("\n[4] Light model stays unchanged at 70%...")
        decision4 = await harness.gate(
            state3, LLM_LIGHT_MODEL, "classification", 200, 256
        )
        assert not decision4.downgraded
        assert decision4.model_to_use == LLM_LIGHT_MODEL
        print(f"   ✅ Light model unchanged: {decision4.model_to_use}")

        # ── Test 5: Hard block at 100% budget ─────────────────────────────
        print("\n[5] Hard block when budget exhausted...")
        state5 = _make_state()
        state5.budget_status.consumed_inr = BUDGET_CAP_INR
        state5.budget_status.remaining_inr = 0.0
        state5.budget_status.is_exhausted = True
        decision5 = await harness.gate(
            state5, LLM_HEAVY_MODEL, "negotiation", 400, 512
        )
        assert decision5.blocked
        assert not decision5.should_proceed
        print(f"   ✅ Blocked: {decision5.block_reason[:60]}...")

        # ── Test 6: Soft block — not enough remaining for even 8b ─────────
        print("\n[6] Soft block when remaining too small for 8b...")
        state6 = _make_state()
        state6.budget_status.consumed_inr = BUDGET_CAP_INR - 0.001
        state6.budget_status.remaining_inr = 0.001
        decision6 = await harness.gate(
            state6, LLM_LIGHT_MODEL, "classification", 500, 256
        )
        assert decision6.blocked
        print(f"   ✅ Soft block: ₹0.001 remaining is not enough")

        # ── Test 7: Warning audit event at 80% ────────────────────────────
        print("\n[7] Warning audit event emitted at 80%...")
        state7 = _make_state()
        state7.budget_status.consumed_inr = BUDGET_CAP_INR * 0.82
        state7.budget_status.remaining_inr = BUDGET_CAP_INR * 0.18
        audit_count_before = len(state7.audit_trail)
        decision7 = await harness.gate(
            state7, LLM_LIGHT_MODEL, "classification", 200, 256
        )
        audit_count_after = len(state7.audit_trail)
        assert audit_count_after > audit_count_before
        warning_events = [
            e for e in state7.audit_trail
            if e.event_type == AuditEventType.BUDGET_WARNING
        ]
        assert len(warning_events) > 0
        print(f"   ✅ Warning event emitted: {warning_events[0].description[:60]}...")

        # ── Test 8: BudgetSnapshot reflects reality ───────────────────────
        print("\n[8] BudgetSnapshot accuracy...")
        snap = await harness.snapshot(state)
        assert snap.dispute_id == state.dispute_id
        assert abs(snap.consumed_inr - state.budget_status.consumed_inr) < 0.0001
        assert 0 <= snap.pct_consumed <= 1.0
        print(f"   ✅ Snapshot: {snap.pct_consumed*100:.1f}% consumed, "
              f"₹{snap.remaining_inr:.4f} remaining")

        # ── Test 9: gate_llm_call() convenience function ──────────────────
        print("\n[9] gate_llm_call() convenience function...")
        state9 = _make_state()
        # Temporarily patch singleton for test
        import agents.cascadeflow.budget_harness as harness_mod
        orig = harness_mod._client_instance
        harness_mod._client_instance = client

        decision9 = await gate_llm_call(
            state9, LLM_HEAVY_MODEL, 1024, "test_task"
        )
        assert decision9.should_proceed
        print(f"   ✅ gate_llm_call approved: {decision9.model_to_use}")
        harness_mod._client_instance = orig

        # ── Test 10: Audit records retrievable ────────────────────────────
        print("\n[10] Audit records retrievable...")
        records = await harness.audit_records(state.dispute_id)
        assert isinstance(records, list)
        assert len(records) > 0
        assert "cost_inr" in records[0]
        assert "model_used" in records[0]
        print(f"   ✅ {len(records)} cost record(s) stored and retrievable")

        print("\n" + "=" * 60)
        print("🎉 ALL BUDGET HARNESS TESTS PASSED")
        print()
        print("MEMBER 2 NEXT STEPS:")
        print("  1. pip install cascadeflow-sdk (when SDK is provided)")
        print("  2. Fill in _RealCascadeflowClient methods (marked TODO)")
        print("  3. Set CASCADEFLOW_BACKEND=real in .env")
        print("  4. Re-run this file — all 10 tests should still pass")
        print("=" * 60)

    asyncio.run(_self_test())
