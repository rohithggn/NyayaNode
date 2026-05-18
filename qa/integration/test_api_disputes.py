"""
qa/integration/test_api_disputes.py
Integration tests for Member 3's dispute REST endpoints.

ALL tests skip gracefully when the FastAPI backend is unreachable.
Run against a live backend:
    .venv/Scripts/pytest qa/integration/ -v --tb=short

Verify skip behaviour without a backend:
    BACKEND_URL=http://localhost:9999 .venv/Scripts/pytest qa/integration/ -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest

from qa.conftest import backend_reachable
from qa.synthetic.scenarios import SCENARIO_1

# ---------------------------------------------------------------------------
# Module-level skip: every test in this file is skipped when the backend
# is not reachable.  Evaluated once at collection time.
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.skipif(
    not backend_reachable(),
    reason="FastAPI backend not reachable — skipping integration tests",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_DISPUTE_PAYLOAD = {
    "buyer_id":           SCENARIO_1["buyer_id"],
    "seller_id":          SCENARIO_1["seller_id"],
    "logistics_id":       SCENARIO_1["logistics_id"],
    "order_id":           SCENARIO_1["order_id"],
    "dispute_type":       SCENARIO_1["dispute_type"],
    "dispute_amount_inr": SCENARIO_1["dispute_amount_inr"],
    "evidence":           SCENARIO_1["evidence"],
    "description":        SCENARIO_1["description"],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_returns_200(async_client):
    """
    Proves the backend is alive and responding.
    If this fails, all other integration tests are meaningless.
    """
    response = await async_client.get("/health")

    assert response.status_code == 200, (
        f"Expected 200 from /health, got {response.status_code}. "
        f"Body: {response.text}"
    )


@pytest.mark.asyncio
async def test_create_dispute_returns_201(async_client):
    """
    Proves the dispute creation endpoint works with valid data.
    Uses Scenario 1 (Damaged Kurta) as the test payload.
    """
    response = await async_client.post("/disputes", json=_VALID_DISPUTE_PAYLOAD)

    assert response.status_code == 201, (
        f"Expected 201 from POST /disputes, got {response.status_code}. "
        f"Body: {response.text}"
    )

    body = response.json()

    assert "dispute_id" in body, "Response must contain dispute_id"
    assert isinstance(body["dispute_id"], str) and body["dispute_id"], (
        "dispute_id must be a non-empty string"
    )
    assert body.get("status") == "OPEN", (
        f"Newly created dispute must have status=OPEN, got '{body.get('status')}'"
    )
    assert "created_at" in body, "Response must contain created_at"
    # created_at must be a non-empty ISO8601 string
    assert isinstance(body["created_at"], str) and body["created_at"], (
        "created_at must be a non-empty ISO8601 string"
    )


@pytest.mark.asyncio
async def test_create_dispute_invalid_body_returns_422(async_client):
    """
    Proves the API validates input and rejects garbage.
    Returns 422 Unprocessable Entity per FastAPI default.
    """
    # Empty body — all required fields missing
    response_empty = await async_client.post("/disputes", json={})
    assert response_empty.status_code == 422, (
        f"Empty body should return 422, got {response_empty.status_code}"
    )

    # Negative amount — fails field validator
    response_negative = await async_client.post(
        "/disputes",
        json={**_VALID_DISPUTE_PAYLOAD, "dispute_amount_inr": -100.0},
    )
    assert response_negative.status_code == 422, (
        f"Negative amount should return 422, got {response_negative.status_code}"
    )


@pytest.mark.asyncio
async def test_get_dispute_by_id_returns_200(async_client):
    """
    Proves a created dispute can be retrieved by its ID.
    """
    # Create a dispute first
    create_resp = await async_client.post("/disputes", json=_VALID_DISPUTE_PAYLOAD)
    assert create_resp.status_code == 201, (
        f"Setup failed: POST /disputes returned {create_resp.status_code}"
    )
    dispute_id = create_resp.json()["dispute_id"]

    # Retrieve it
    get_resp = await async_client.get(f"/disputes/{dispute_id}")
    assert get_resp.status_code == 200, (
        f"Expected 200 from GET /disputes/{dispute_id}, got {get_resp.status_code}"
    )

    body = get_resp.json()
    assert body.get("dispute_id") == dispute_id, (
        f"Returned dispute_id '{body.get('dispute_id')}' does not match '{dispute_id}'"
    )


@pytest.mark.asyncio
async def test_get_nonexistent_dispute_returns_404(async_client):
    """
    Proves the API returns 404 for unknown dispute IDs.
    RFC 7807 Problem Detail format is preferred but not enforced here.
    """
    response = await async_client.get("/disputes/nonexistent-id-99999")

    assert response.status_code == 404, (
        f"Expected 404 for unknown dispute ID, got {response.status_code}"
    )


@pytest.mark.asyncio
async def test_list_disputes_returns_array(async_client):
    """
    Proves the list endpoint returns a JSON array (or an object with an
    'items' key containing a list — both patterns are accepted).
    """
    response = await async_client.get("/disputes")

    assert response.status_code == 200, (
        f"Expected 200 from GET /disputes, got {response.status_code}"
    )

    body = response.json()

    # Accept either a bare list or a paginated envelope {"items": [...], ...}
    if isinstance(body, list):
        items = body
    elif isinstance(body, dict) and "items" in body:
        items = body["items"]
        assert isinstance(items, list), "'items' key must contain a list"
    else:
        pytest.fail(
            f"GET /disputes must return a JSON array or an object with 'items' key. "
            f"Got: {type(body).__name__}"
        )


@pytest.mark.asyncio
@pytest.mark.slow
async def test_pagination_with_limit_and_offset(async_client):
    """
    Proves pagination parameters work correctly.
    Essential for the frontend dashboard table.

    Creates 3 disputes to ensure there is enough data, then verifies
    that page 1 and page 2 return non-overlapping sets.
    """
    # Seed 3 disputes so pagination has data to work with
    created_ids: list[str] = []
    for i in range(3):
        payload = {**_VALID_DISPUTE_PAYLOAD, "order_id": f"order_pagination_{i:03d}"}
        resp = await async_client.post("/disputes", json=payload)
        assert resp.status_code == 201, f"Seeding dispute {i} failed: {resp.status_code}"
        created_ids.append(resp.json()["dispute_id"])

    def extract_ids(body) -> list[str]:
        items = body if isinstance(body, list) else body.get("items", [])
        return [item["dispute_id"] for item in items]

    # Page 1: first 2 items
    page1_resp = await async_client.get("/disputes", params={"limit": 2, "offset": 0})
    assert page1_resp.status_code == 200
    page1_ids = extract_ids(page1_resp.json())
    assert len(page1_ids) <= 2, f"limit=2 must return at most 2 items, got {len(page1_ids)}"

    # Page 2: next 2 items
    page2_resp = await async_client.get("/disputes", params={"limit": 2, "offset": 2})
    assert page2_resp.status_code == 200
    page2_ids = extract_ids(page2_resp.json())

    # The two pages must not share any dispute_ids
    overlap = set(page1_ids) & set(page2_ids)
    assert not overlap, (
        f"Pages must not overlap. Shared IDs: {overlap}"
    )


@pytest.mark.asyncio
async def test_filter_disputes_by_status(async_client):
    """
    Proves disputes can be filtered by status for the dashboard.
    All items returned when filtering by OPEN must have status=OPEN.
    """
    response = await async_client.get("/disputes", params={"status": "OPEN"})

    assert response.status_code == 200, (
        f"Expected 200 from GET /disputes?status=OPEN, got {response.status_code}"
    )

    body = response.json()
    items = body if isinstance(body, list) else body.get("items", [])

    for item in items:
        assert item.get("status") == "OPEN", (
            f"Filter by status=OPEN returned item with status='{item.get('status')}'"
        )
