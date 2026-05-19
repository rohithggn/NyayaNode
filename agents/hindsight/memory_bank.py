"""
agents/hindsight/memory_bank.py
================================
Hindsight SDK integration for NyayaNode — session persistence and
multi-week memory for arbitration state.

WHO USES THIS:
  - Member 1 (Lead AI Architect): called from arbitrator.py before and
    after every LangGraph graph execution.
  - Member 2 (Cascadeflow): reads session_id from HindsightSession to
    correlate cost records with memory checkpoints.
  - Member 5 (QA): imports MockHindsightClient for isolated unit tests
    without requiring real Hindsight credentials.

HOW IT WORKS:
  1. Before graph runs   → create_session()   stores initial state
  2. After every node    → save_checkpoint()  saves intermediate state
  3. After graph ends    → finalise_session() marks session complete
  4. On retrieval        → load_session()     hydrates ArbitrationState
  5. For rollback        → list_checkpoints() + load_checkpoint()

HINDSIGHT SDK STATUS:
  The real Hindsight SDK (hindsight-sdk) is provided at the hackathon.
  Until then, this module ships with a full LocalHindsightClient that
  stores sessions in Supabase (or local dict fallback) with identical
  interface. Swap by setting HINDSIGHT_BACKEND=real in .env.

STORAGE SCHEMA (Supabase table: hindsight_sessions):
  session_id     TEXT PRIMARY KEY
  dispute_id     TEXT NOT NULL
  namespace      TEXT DEFAULT 'nyayanode'
  state_snapshot JSONB
  checkpoints    JSONB[]
  created_at     TIMESTAMPTZ
  updated_at     TIMESTAMPTZ
  ttl_days       INT DEFAULT 90
  finalised      BOOL DEFAULT FALSE
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Optional

import structlog
from dotenv import load_dotenv

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

load_dotenv(os.path.join(_REPO_ROOT, ".env"))

from shared.constants import HINDSIGHT_NAMESPACE, HINDSIGHT_SESSION_TTL_DAYS
from shared.schemas import (
    ArbitrationState,
    AuditEventType,
    BudgetStatus,
    DisputeRequest,
    DisputeStatus,
)

log = structlog.get_logger("nyayanode.hindsight")


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class HindsightCheckpoint:
    """
    A single point-in-time snapshot of ArbitrationState.
    Immutable once created. Identified by checkpoint_id.
    """

    __slots__ = (
        "checkpoint_id",
        "session_id",
        "dispute_id",
        "sequence",
        "node_name",
        "state_snapshot",
        "state_hash",
        "created_at",
        "metadata",
    )

    def __init__(
        self,
        session_id: str,
        dispute_id: str,
        sequence: int,
        node_name: str,
        state_snapshot: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.checkpoint_id = str(uuid.uuid4())
        self.session_id = session_id
        self.dispute_id = dispute_id
        self.sequence = sequence
        self.node_name = node_name
        self.state_snapshot = state_snapshot
        self.state_hash = self._hash_state(state_snapshot)
        self.created_at = datetime.utcnow()
        self.metadata = metadata or {}

    @staticmethod
    def _hash_state(snapshot: dict[str, Any]) -> str:
        """SHA-256 of the serialised state — used to detect duplicate saves."""
        raw = json.dumps(snapshot, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "session_id": self.session_id,
            "dispute_id": self.dispute_id,
            "sequence": self.sequence,
            "node_name": self.node_name,
            "state_snapshot": self.state_snapshot,
            "state_hash": self.state_hash,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HindsightCheckpoint":
        cp = cls.__new__(cls)
        cp.checkpoint_id = data["checkpoint_id"]
        cp.session_id = data["session_id"]
        cp.dispute_id = data["dispute_id"]
        cp.sequence = data["sequence"]
        cp.node_name = data["node_name"]
        cp.state_snapshot = data["state_snapshot"]
        cp.state_hash = data["state_hash"]
        cp.created_at = datetime.fromisoformat(data["created_at"])
        cp.metadata = data.get("metadata", {})
        return cp


class HindsightSession:
    """
    A complete memory session for one dispute arbitration.
    Contains the initial state, all checkpoints, and final state.
    """

    def __init__(
        self,
        dispute_id: str,
        namespace: str = HINDSIGHT_NAMESPACE,
        ttl_days: int = HINDSIGHT_SESSION_TTL_DAYS,
    ) -> None:
        self.session_id = str(uuid.uuid4())
        self.dispute_id = dispute_id
        self.namespace = namespace
        self.ttl_days = ttl_days
        self.checkpoints: list[HindsightCheckpoint] = []
        self.initial_snapshot: dict[str, Any] | None = None
        self.final_snapshot: dict[str, Any] | None = None
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.finalised = False
        self.expires_at = datetime.utcnow() + timedelta(days=ttl_days)

    @property
    def latest_checkpoint(self) -> HindsightCheckpoint | None:
        return self.checkpoints[-1] if self.checkpoints else None

    @property
    def checkpoint_count(self) -> int:
        return len(self.checkpoints)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "dispute_id": self.dispute_id,
            "namespace": self.namespace,
            "ttl_days": self.ttl_days,
            "checkpoints": [cp.to_dict() for cp in self.checkpoints],
            "initial_snapshot": self.initial_snapshot,
            "final_snapshot": self.final_snapshot,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "finalised": self.finalised,
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HindsightSession":
        session = cls.__new__(cls)
        session.session_id = data["session_id"]
        session.dispute_id = data["dispute_id"]
        session.namespace = data.get("namespace", HINDSIGHT_NAMESPACE)
        session.ttl_days = data.get("ttl_days", HINDSIGHT_SESSION_TTL_DAYS)
        session.checkpoints = [
            HindsightCheckpoint.from_dict(cp) for cp in data.get("checkpoints", [])
        ]
        session.initial_snapshot = data.get("initial_snapshot")
        session.final_snapshot = data.get("final_snapshot")
        session.created_at = datetime.fromisoformat(data["created_at"])
        session.updated_at = datetime.fromisoformat(data["updated_at"])
        session.finalised = data.get("finalised", False)
        session.expires_at = datetime.fromisoformat(data["expires_at"])
        return session


# ---------------------------------------------------------------------------
# Abstract Client Interface
# ---------------------------------------------------------------------------


class BaseHindsightClient(ABC):
    """
    Abstract interface that both the real Hindsight SDK wrapper and the
    local fallback client implement.

    REAL SDK SWAP (Member 1, when SDK is available at hackathon):
      1. pip install hindsight-sdk
      2. Set HINDSIGHT_BACKEND=real in .env
      3. RealHindsightClient below will be used automatically.
      4. All method signatures remain identical — zero other changes.
    """

    @abstractmethod
    async def create_session(self, dispute_id: str) -> HindsightSession:
        """Create a new memory session for a dispute."""
        ...

    @abstractmethod
    async def save_checkpoint(
        self,
        session: HindsightSession,
        state: ArbitrationState,
        node_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> HindsightCheckpoint:
        """Save a checkpoint of the current state."""
        ...

    @abstractmethod
    async def load_session(self, session_id: str) -> HindsightSession | None:
        """Load a full session by ID."""
        ...

    @abstractmethod
    async def load_checkpoint(
        self, session_id: str, checkpoint_id: str
    ) -> HindsightCheckpoint | None:
        """Load a specific checkpoint by ID."""
        ...

    @abstractmethod
    async def list_checkpoints(
        self, session_id: str
    ) -> list[HindsightCheckpoint]:
        """List all checkpoints for a session, ordered by sequence."""
        ...

    @abstractmethod
    async def finalise_session(
        self,
        session: HindsightSession,
        final_state: ArbitrationState,
    ) -> HindsightSession:
        """Mark a session as complete with the final state."""
        ...

    @abstractmethod
    async def get_session_by_dispute(
        self, dispute_id: str
    ) -> HindsightSession | None:
        """Find the most recent session for a given dispute_id."""
        ...


# ---------------------------------------------------------------------------
# Local Fallback Client (Supabase-backed or in-memory)
# ---------------------------------------------------------------------------


class LocalHindsightClient(BaseHindsightClient):
    """
    Production-quality local implementation of the Hindsight interface.

    Storage backends (in priority order):
      1. Supabase (if SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY are set)
      2. In-memory dict (safe fallback for demo/testing)

    This client is 100% functional — the hackathon demo runs on this.
    Swap to RealHindsightClient when the Hindsight SDK is available.
    """

    def __init__(self) -> None:
        self._memory: dict[str, HindsightSession] = {}   # session_id → session
        self._dispute_index: dict[str, str] = {}          # dispute_id → session_id
        self._supabase = self._init_supabase()

    def _init_supabase(self) -> Any | None:
        """Attempt to connect to Supabase. Returns None if not configured."""
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
        if not url or not key:
            log.info("hindsight_storage", backend="in_memory",
                     reason="SUPABASE_URL or key not set")
            return None
        try:
            from supabase import create_client
            client = create_client(url, key)
            log.info("hindsight_storage", backend="supabase", url=url[:40])
            return client
        except Exception as e:
            log.warning("supabase_init_failed", error=str(e))
            return None

    # ── Internal Storage Helpers ────────────────────────────────────────────

    async def _persist(self, session: HindsightSession) -> None:
        """Write session to Supabase (if available) and in-memory store."""
        self._memory[session.session_id] = session
        self._dispute_index[session.dispute_id] = session.session_id

        if self._supabase:
            try:
                data = session.to_dict()
                # Supabase upsert — idempotent
                self._supabase.table("hindsight_sessions").upsert(
                    {
                        "session_id": session.session_id,
                        "dispute_id": session.dispute_id,
                        "namespace": session.namespace,
                        "state_snapshot": json.dumps(data),
                        "finalised": session.finalised,
                        "created_at": session.created_at.isoformat(),
                        "updated_at": session.updated_at.isoformat(),
                    }
                ).execute()
            except Exception as e:
                log.warning("supabase_persist_failed", error=str(e))
                # Graceful degradation: in-memory already saved above

    async def _fetch(self, session_id: str) -> HindsightSession | None:
        """Load session from in-memory or Supabase."""
        # Check memory first
        if session_id in self._memory:
            return self._memory[session_id]

        # Try Supabase
        if self._supabase:
            try:
                result = (
                    self._supabase.table("hindsight_sessions")
                    .select("state_snapshot")
                    .eq("session_id", session_id)
                    .single()
                    .execute()
                )
                if result.data:
                    raw = json.loads(result.data["state_snapshot"])
                    session = HindsightSession.from_dict(raw)
                    self._memory[session_id] = session
                    self._dispute_index[session.dispute_id] = session_id
                    return session
            except Exception as e:
                log.warning("supabase_fetch_failed", error=str(e))

        return None

    # ── Public Interface ────────────────────────────────────────────────────

    async def create_session(self, dispute_id: str) -> HindsightSession:
        session = HindsightSession(dispute_id=dispute_id)
        await self._persist(session)
        log.info(
            "session_created",
            session_id=session.session_id,
            dispute_id=dispute_id,
        )
        return session

    async def save_checkpoint(
        self,
        session: HindsightSession,
        state: ArbitrationState,
        node_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> HindsightCheckpoint:
        snapshot = state.model_dump(mode="json")

        # Deduplicate: skip if state hasn't changed since last checkpoint
        cp = HindsightCheckpoint(
            session_id=session.session_id,
            dispute_id=state.dispute_id,
            sequence=len(session.checkpoints),
            node_name=node_name,
            state_snapshot=snapshot,
            metadata=metadata or {},
        )

        if (
            session.latest_checkpoint
            and session.latest_checkpoint.state_hash == cp.state_hash
        ):
            log.debug(
                "checkpoint_skipped_duplicate",
                session_id=session.session_id,
                node=node_name,
            )
            return session.latest_checkpoint

        # Set initial snapshot on first checkpoint
        if session.initial_snapshot is None:
            session.initial_snapshot = snapshot

        session.checkpoints.append(cp)
        session.updated_at = datetime.utcnow()
        await self._persist(session)

        log.info(
            "checkpoint_saved",
            session_id=session.session_id,
            checkpoint_id=cp.checkpoint_id,
            node=node_name,
            sequence=cp.sequence,
            state_hash=cp.state_hash,
        )
        return cp

    async def load_session(self, session_id: str) -> HindsightSession | None:
        return await self._fetch(session_id)

    async def load_checkpoint(
        self, session_id: str, checkpoint_id: str
    ) -> HindsightCheckpoint | None:
        session = await self._fetch(session_id)
        if not session:
            return None
        for cp in session.checkpoints:
            if cp.checkpoint_id == checkpoint_id:
                return cp
        return None

    async def list_checkpoints(self, session_id: str) -> list[HindsightCheckpoint]:
        session = await self._fetch(session_id)
        if not session:
            return []
        return sorted(session.checkpoints, key=lambda c: c.sequence)

    async def finalise_session(
        self,
        session: HindsightSession,
        final_state: ArbitrationState,
    ) -> HindsightSession:
        session.final_snapshot = final_state.model_dump(mode="json")
        session.finalised = True
        session.updated_at = datetime.utcnow()
        await self._persist(session)
        log.info(
            "session_finalised",
            session_id=session.session_id,
            dispute_id=final_state.dispute_id,
            checkpoints=len(session.checkpoints),
            final_status=final_state.status.value,
        )
        return session

    async def get_session_by_dispute(
        self, dispute_id: str
    ) -> HindsightSession | None:
        # Check in-memory index first
        session_id = self._dispute_index.get(dispute_id)
        if session_id:
            return await self._fetch(session_id)

        # Scan Supabase
        if self._supabase:
            try:
                result = (
                    self._supabase.table("hindsight_sessions")
                    .select("state_snapshot")
                    .eq("dispute_id", dispute_id)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    raw = json.loads(result.data[0]["state_snapshot"])
                    session = HindsightSession.from_dict(raw)
                    self._memory[session.session_id] = session
                    self._dispute_index[dispute_id] = session.session_id
                    return session
            except Exception as e:
                log.warning("supabase_dispute_lookup_failed", error=str(e))

        return None


# ---------------------------------------------------------------------------
# Real Hindsight SDK Wrapper (plug in when SDK is available)
# ---------------------------------------------------------------------------


class RealHindsightClient(BaseHindsightClient):
    """
    Wraps the real Hindsight SDK with the same interface as LocalHindsightClient.

    ACTIVATE: Set HINDSIGHT_BACKEND=real in .env once SDK is provided.

    TODO (Member 1 — when SDK arrives at hackathon):
      1. pip install hindsight-sdk
      2. Replace the stub methods below with real SDK calls
      3. Test with: HINDSIGHT_BACKEND=real python -m agents.hindsight.memory_bank
    """

    def __init__(self) -> None:
        api_key = os.getenv("HINDSIGHT_API_KEY", "")
        project_id = os.getenv("HINDSIGHT_PROJECT_ID", "nyayanode")
        base_url = os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.ai/v1")

        if not api_key:
            raise RuntimeError(
                "HINDSIGHT_API_KEY not set. Check .env or use LocalHindsightClient."
            )

        # TODO: Replace with real SDK initialisation
        # import hindsight
        # self._client = hindsight.Client(api_key=api_key, project=project_id)
        self._api_key = api_key
        self._project_id = project_id
        self._base_url = base_url
        log.info("real_hindsight_client_init", project=project_id)

    async def create_session(self, dispute_id: str) -> HindsightSession:
        # TODO: return self._client.sessions.create(namespace=HINDSIGHT_NAMESPACE, ...)
        raise NotImplementedError("Wire real Hindsight SDK here")

    async def save_checkpoint(self, session, state, node_name, metadata=None):
        raise NotImplementedError("Wire real Hindsight SDK here")

    async def load_session(self, session_id):
        raise NotImplementedError("Wire real Hindsight SDK here")

    async def load_checkpoint(self, session_id, checkpoint_id):
        raise NotImplementedError("Wire real Hindsight SDK here")

    async def list_checkpoints(self, session_id):
        raise NotImplementedError("Wire real Hindsight SDK here")

    async def finalise_session(self, session, final_state):
        raise NotImplementedError("Wire real Hindsight SDK here")

    async def get_session_by_dispute(self, dispute_id):
        raise NotImplementedError("Wire real Hindsight SDK here")


# ---------------------------------------------------------------------------
# Client Factory
# ---------------------------------------------------------------------------

_client_instance: BaseHindsightClient | None = None


def get_hindsight_client() -> BaseHindsightClient:
    """
    Return the appropriate Hindsight client based on HINDSIGHT_BACKEND env var.
    Singleton — one client per process.

    HINDSIGHT_BACKEND=real  → RealHindsightClient (when SDK is provided)
    HINDSIGHT_BACKEND=local → LocalHindsightClient (default, Supabase-backed)
    """
    global _client_instance
    if _client_instance is not None:
        return _client_instance

    backend = os.getenv("HINDSIGHT_BACKEND", "local").lower()
    if backend == "real":
        _client_instance = RealHindsightClient()
    else:
        _client_instance = LocalHindsightClient()

    return _client_instance


# ---------------------------------------------------------------------------
# High-Level Memory Bank API (used by arbitrator.py)
# ---------------------------------------------------------------------------


class MemoryBank:
    """
    High-level API that arbitrator.py uses to persist arbitration state.

    Usage in arbitrator.py:
        bank = MemoryBank()
        session = await bank.open(dispute_id)
        state.hindsight_session_id = session.session_id

        # After each LangGraph node:
        await bank.checkpoint(session, state, node_name="intake")

        # After graph completes:
        await bank.close(session, state)
    """

    def __init__(self, client: BaseHindsightClient | None = None) -> None:
        self._client = client or get_hindsight_client()

    async def open(self, dispute_id: str) -> HindsightSession:
        """
        Open a new memory session for a dispute.
        Resumes existing session if one already exists for this dispute_id.
        """
        existing = await self._client.get_session_by_dispute(dispute_id)
        if existing and not existing.finalised:
            log.info(
                "session_resumed",
                session_id=existing.session_id,
                dispute_id=dispute_id,
                checkpoints=existing.checkpoint_count,
            )
            return existing

        return await self._client.create_session(dispute_id)

    async def checkpoint(
        self,
        session: HindsightSession,
        state: ArbitrationState,
        node_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> HindsightCheckpoint:
        """Save a checkpoint after a LangGraph node completes."""
        return await self._client.save_checkpoint(
            session=session,
            state=state,
            node_name=node_name,
            metadata=metadata,
        )

    async def close(
        self,
        session: HindsightSession,
        final_state: ArbitrationState,
    ) -> HindsightSession:
        """Finalise and seal the session after graph execution completes."""
        return await self._client.finalise_session(session, final_state)

    async def recall(self, session_id: str) -> HindsightSession | None:
        """Retrieve a full session — used by rollback.py."""
        return await self._client.load_session(session_id)

    async def checkpoints(self, session_id: str) -> list[HindsightCheckpoint]:
        """List all checkpoints for a session — used by rollback.py."""
        return await self._client.list_checkpoints(session_id)

    async def get_checkpoint(
        self, session_id: str, checkpoint_id: str
    ) -> HindsightCheckpoint | None:
        """Fetch a specific checkpoint by ID."""
        return await self._client.load_checkpoint(session_id, checkpoint_id)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    async def _self_test():
        print("=" * 60)
        print("NyayaNode — Hindsight Memory Bank Self-Test")
        print("=" * 60)

        from shared.schemas import (
            ArbitrationState, BudgetStatus, DisputeRequest,
            DisputeType, EvidenceItem, EvidenceType,
        )

        def _make_state(dispute_id: str | None = None) -> ArbitrationState:
            req = DisputeRequest(
                buyer_id="buyer_001",
                seller_id="seller_042",
                logistics_id="lsp_007",
                order_id="order_xyz",
                dispute_type=DisputeType.DAMAGED_ITEM,
                evidence=[EvidenceItem(type=EvidenceType.TEXT, content="Broken package")],
                dispute_amount_inr=500.0,
            )
            if dispute_id:
                req = req.model_copy(update={"dispute_id": dispute_id})
            budget = BudgetStatus(dispute_id=req.dispute_id)
            return ArbitrationState(
                dispute_id=req.dispute_id, request=req, budget_status=budget
            )

        client = LocalHindsightClient()
        bank = MemoryBank(client=client)

        # ── Test 1: Create session ────────────────────────────────────────
        print("\n[1] Create session...")
        state = _make_state()
        session = await bank.open(state.dispute_id)
        assert session.session_id
        assert session.dispute_id == state.dispute_id
        state.hindsight_session_id = session.session_id
        print(f"   ✅ Session created: {session.session_id[:16]}...")

        # ── Test 2: Save checkpoints ──────────────────────────────────────
        print("\n[2] Save checkpoints across nodes...")
        cp1 = await bank.checkpoint(session, state, "intake")
        state.status = DisputeStatus.EVIDENCE_COLLECTION
        cp2 = await bank.checkpoint(session, state, "evidence")
        state.status = DisputeStatus.NEGOTIATION
        cp3 = await bank.checkpoint(session, state, "negotiation")
        assert len(session.checkpoints) == 3
        assert cp1.sequence == 0
        assert cp2.sequence == 1
        assert cp3.sequence == 2
        print(f"   ✅ {len(session.checkpoints)} checkpoints saved")

        # ── Test 3: Deduplication ─────────────────────────────────────────
        print("\n[3] Duplicate checkpoint is skipped...")
        count_before = len(session.checkpoints)
        cp_dup = await bank.checkpoint(session, state, "negotiation_retry")
        assert len(session.checkpoints) == count_before   # unchanged
        print("   ✅ Duplicate skipped correctly")

        # ── Test 4: Round-trip load ───────────────────────────────────────
        print("\n[4] Load session back from storage...")
        loaded = await bank.recall(session.session_id)
        assert loaded is not None
        assert loaded.session_id == session.session_id
        assert loaded.checkpoint_count == 3
        print(f"   ✅ Session loaded: {loaded.checkpoint_count} checkpoints")

        # ── Test 5: List checkpoints in order ─────────────────────────────
        print("\n[5] List checkpoints in sequence order...")
        cps = await bank.checkpoints(session.session_id)
        assert [cp.sequence for cp in cps] == [0, 1, 2]
        assert [cp.node_name for cp in cps] == ["intake", "evidence", "negotiation"]
        print(f"   ✅ Checkpoints in order: {[cp.node_name for cp in cps]}")

        # ── Test 6: Resume existing session (idempotent open) ─────────────
        print("\n[6] Resuming existing open session...")
        resumed = await bank.open(state.dispute_id)
        assert resumed.session_id == session.session_id
        print(f"   ✅ Resumed same session: {resumed.session_id[:16]}...")

        # ── Test 7: Finalise session ──────────────────────────────────────
        print("\n[7] Finalise session...")
        state.status = DisputeStatus.RESOLVED
        finalised = await bank.close(session, state)
        assert finalised.finalised is True
        assert finalised.final_snapshot is not None
        print("   ✅ Session finalised")

        # ── Test 8: New session created after finalisation ────────────────
        print("\n[8] Opening a new dispute creates a fresh session...")
        state2 = _make_state()
        session2 = await bank.open(state2.dispute_id)
        assert session2.session_id != session.session_id
        print(f"   ✅ New session: {session2.session_id[:16]}...")

        # ── Test 9: State round-trip through checkpoint ───────────────────
        print("\n[9] State round-trip through checkpoint snapshot...")
        cp = await bank.get_checkpoint(session.session_id, cp2.checkpoint_id)
        assert cp is not None
        restored = ArbitrationState(**cp.state_snapshot)
        assert restored.status == DisputeStatus.EVIDENCE_COLLECTION
        assert restored.dispute_id == state.dispute_id
        print(f"   ✅ Restored status: {restored.status.value}")

        print("\n" + "=" * 60)
        print("🎉 ALL MEMORY BANK TESTS PASSED")
        print("=" * 60)

    asyncio.run(_self_test())
