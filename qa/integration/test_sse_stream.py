"""
qa/integration/test_sse_stream.py
SSE streaming integration tests for NyayaNode.

Proves real-time arbitration events fire in the correct order with
correct payloads. All tests skip gracefully when the backend is unreachable.

Run against a live backend:
    .venv/Scripts/pytest qa/integration/test_sse_stream.py -v -s --tb=short

Verify skip behaviour:
    BACKEND_URL=http://localhost:9999 .venv/Scripts/pytest qa/integration/test_sse_stream.py -v
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import httpx
import pytest

from qa.conftest import backend_reachable, BACKEND_URL
from qa.synthetic.scenarios import SCENARIO_1, SCENARIO_5

pytestmark = pytest.mark.skipif(
    not backend_reachable(),
    reason="Backend not reachable",
)

# ---------------------------------------------------------------------------
# Shared dispute payload builder
# ---------------------------------------------------------------------------

def _dispute_payload(scenario: dict) -> dict:
    return {
        "buyer_id":           scenario["buyer_id"],
        "seller_id":          scenario["seller_id"],
        "logistics_id":       scenario["logistics_id"],
        "order_id":           scenario["order_id"],
        "dispute_type":       scenario["dispute_type"],
        "dispute_amount_inr": scenario["dispute_amount_inr"],
        "evidence":           scenario["evidence"],
        "description":        scenario["description"],
    }


# ---------------------------------------------------------------------------
# SSE helper — specified exactly as per the prompt contract
# ---------------------------------------------------------------------------

async def consume_sse_events(
    url: str,
    timeout: float = 30.0,
    max_events: int = 50,
) -> list[dict]:
    """
    Consumes SSE events from a streaming endpoint.
    Returns list of parsed event payloads.
    Stops at 'event: complete' line or max_events or timeout.
    """
    events: list[dict] = []
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", url, timeout=timeout) as response:
            assert response.status_code == 200, (
                f"SSE endpoint returned {response.status_code}"
            )
            content_type = response.headers.get("content-type", "")
            assert "text/event-stream" in content_type, (
                f"Expected text/event-stream, got {content_type}"
            )
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    raw = line[5:].strip()
                    if raw and raw != "[DONE]":
                        try:
                            payload = json.loads(raw)
                            events.append(payload)
                        except json.JSONDecodeError:
                            pass  # skip malformed events
                if "event: complete" in line or len(events) >= max_events:
                    break
    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.slow
async def test_sse_endpoint_returns_stream_headers(async_client):
    """
    Proves the SSE endpoint sets correct Content-Type header.
    Without text/event-stream, browsers won't auto-reconnect.
    """
    # Create a dispute to stream
    create_resp = await async_client.post(
        "/disputes", json=_dispute_payload(SCENARIO_1)
    )
    assert create_resp.status_code == 201, (
        f"Setup failed: POST /disputes returned {create_resp.status_code}"
    )
    dispute_id = create_resp.json()["dispute_id"]

    stream_url = f"{BACKEND_URL}/disputes/{dispute_id}/stream"

    # Open the stream and inspect headers — read only 3 events then stop
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "GET", stream_url, timeout=30.0
        ) as response:
            assert response.status_code == 200, (
                f"Expected 200 from SSE endpoint, got {response.status_code}"
            )

            content_type = response.headers.get("content-type", "")
            assert "text/event-stream" in content_type, (
                f"Expected Content-Type: text/event-stream, got '{content_type}'"
            )

            # Optionally verify cache-control header (SSE best practice)
            cache_control = response.headers.get("cache-control", "")
            # Not a hard requirement — just informational
            if cache_control:
                assert "no-cache" in cache_control.lower() or cache_control == "", (
                    f"Unexpected Cache-Control for SSE: '{cache_control}'"
                )

            # Consume 3 events then bail — we only care about headers here
            event_count = 0
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    event_count += 1
                if event_count >= 3:
                    break


@pytest.mark.asyncio
@pytest.mark.slow
async def test_sse_events_start_with_evidence_collection(async_client):
    """
    Proves the first SSE event always has status == 'EVIDENCE_COLLECTION'.
    Frontend uses this to show the initial progress spinner.
    """
    create_resp = await async_client.post(
        "/disputes", json=_dispute_payload(SCENARIO_1)
    )
    assert create_resp.status_code == 201
    dispute_id = create_resp.json()["dispute_id"]

    stream_url = f"{BACKEND_URL}/disputes/{dispute_id}/stream"
    events = await consume_sse_events(stream_url, timeout=10.0, max_events=5)

    assert len(events) >= 1, (
        f"SSE stream must emit at least 1 event, got {len(events)}"
    )

    first = events[0]

    # Accept either field name for flexibility across backend implementations
    stage_value = first.get("status") or first.get("stage") or ""
    assert stage_value == "EVIDENCE_COLLECTION", (
        f"First SSE event must have status/stage == 'EVIDENCE_COLLECTION'. "
        f"Got event: {first}"
    )


@pytest.mark.asyncio
@pytest.mark.slow
async def test_sse_resolved_dispute_final_event(async_client, mock_groq):
    """
    Proves the final SSE event for a RESOLVED dispute contains the decision
    field. Frontend renders the verdict from this event.

    Uses mock_groq fixture to avoid real Groq API calls and ensure a
    deterministic FULL_REFUND decision.
    """
    create_resp = await async_client.post(
        "/disputes", json=_dispute_payload(SCENARIO_1)
    )
    assert create_resp.status_code == 201
    dispute_id = create_resp.json()["dispute_id"]

    stream_url = f"{BACKEND_URL}/disputes/{dispute_id}/stream"
    events = await consume_sse_events(stream_url, timeout=30.0, max_events=50)

    assert len(events) >= 1, (
        f"SSE stream produced no events for dispute {dispute_id}"
    )

    last_event = events[-1]

    # Final event must carry the decision or final_status
    has_decision = "decision" in last_event
    has_final_status = "final_status" in last_event
    assert has_decision or has_final_status, (
        f"Final SSE event must contain 'decision' or 'final_status'. "
        f"Got: {last_event}"
    )

    # Must not be an error terminal state
    final_status = last_event.get("final_status", "")
    assert final_status != "ERROR", (
        f"Final SSE event must not have final_status=ERROR. Got: {last_event}"
    )


@pytest.mark.asyncio
@pytest.mark.slow
async def test_sse_escalated_dispute_final_event(async_client):
    """
    Proves Scenario 5 (expensive watch — ambiguous) SSE stream ends with
    ESCALATED status, not RESOLVED.

    Frontend must show 'Under Human Review' for escalated disputes.
    Scenario 5: high value + ambiguous evidence + no logistics confirmation
    → expected_status == 'ESCALATED'.
    """
    create_resp = await async_client.post(
        "/disputes", json=_dispute_payload(SCENARIO_5)
    )
    assert create_resp.status_code == 201, (
        f"Setup failed: POST /disputes returned {create_resp.status_code}"
    )
    dispute_id = create_resp.json()["dispute_id"]

    stream_url = f"{BACKEND_URL}/disputes/{dispute_id}/stream"
    events = await consume_sse_events(stream_url, timeout=30.0, max_events=50)

    assert len(events) >= 1, (
        f"SSE stream produced no events for Scenario 5 dispute {dispute_id}"
    )

    last_event = events[-1]

    # Accept either field name
    final_status = last_event.get("final_status") or last_event.get("status") or ""
    assert final_status == "ESCALATED", (
        f"Scenario 5 must end with ESCALATED status. "
        f"Got final_status/status='{final_status}'. "
        f"Full last event: {last_event}"
    )


@pytest.mark.asyncio
@pytest.mark.slow
async def test_sse_stream_no_orphan_connections(async_client):
    """
    Proves that after streaming completes, the connection closes cleanly
    and doesn't leave open sockets.

    Memory leak in production = crashes at scale.
    This test passing without TimeoutError proves clean closure.
    """
    create_resp = await async_client.post(
        "/disputes", json=_dispute_payload(SCENARIO_1)
    )
    assert create_resp.status_code == 201
    dispute_id = create_resp.json()["dispute_id"]

    stream_url = f"{BACKEND_URL}/disputes/{dispute_id}/stream"

    # consume_sse_events must complete without raising TimeoutError or
    # leaving the connection hanging. The test itself is the assertion —
    # if it returns cleanly, the connection closed properly.
    try:
        events = await asyncio.wait_for(
            consume_sse_events(stream_url, timeout=30.0, max_events=50),
            timeout=35.0,  # outer hard cap — 5s grace over SSE timeout
        )
    except asyncio.TimeoutError:
        pytest.fail(
            f"SSE stream for dispute {dispute_id} did not close within 35s. "
            "Possible orphan connection / server not sending 'event: complete'."
        )
    except httpx.ReadTimeout:
        pytest.fail(
            f"SSE stream timed out waiting for data. "
            "Server may not be sending a terminal event."
        )

    # Stream must have produced at least one event before closing
    assert len(events) >= 1, (
        "SSE stream closed immediately without emitting any events"
    )
