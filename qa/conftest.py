"""
qa/conftest.py
Master pytest configuration for NyayaNode QA suite.
"""

import os
from collections.abc import AsyncGenerator

import httpx
import pytest
import respx
from dotenv import load_dotenv

from qa.synthetic.dispute_generator import DisputeFactory
from qa.synthetic.scenarios import ALL_SCENARIOS

# ---------------------------------------------------------------------------
# Environment bootstrap
# ---------------------------------------------------------------------------

# Walk up from qa/ to find the project root .env
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")


# ---------------------------------------------------------------------------
# Reachability helper
# ---------------------------------------------------------------------------


def backend_reachable() -> bool:
    """Returns True if the FastAPI backend is reachable."""
    try:
        response = httpx.get(f"{BACKEND_URL}/health", timeout=2.0)
        return response.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def backend_url() -> str:
    """Return BACKEND_URL from env."""
    return BACKEND_URL


@pytest.fixture(scope="session")
def frontend_url() -> str:
    """Return FRONTEND_URL from env."""
    return FRONTEND_URL


# ---------------------------------------------------------------------------
# Function-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def async_client(backend_url: str) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client pointed at the live backend."""
    async with httpx.AsyncClient(base_url=backend_url, timeout=30.0) as client:
        yield client


@pytest.fixture
def dispute_factory() -> DisputeFactory:
    """Returns a seeded DisputeFactory for reproducible test data."""
    return DisputeFactory(seed=42)


@pytest.fixture
def mock_groq():
    """
    Mocks all Groq API calls using respx.
    Prevents real API calls during unit/integration tests.
    Returns a deterministic FULL_REFUND decision.
    """
    _mock_response_body = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"decision": "FULL_REFUND", '
                        '"reasoning": "Logistics data confirms package damage at delivery scan '
                        'TS-2024-001. Seller rejection is not supported by evidence. '
                        'Full refund of disputed amount is warranted.", '
                        '"confidence_score": 0.92}'
                    )
                }
            }
        ],
        "usage": {
            "prompt_tokens": 312,
            "completion_tokens": 89,
            "total_tokens": 401,
        },
        "model": "llama-3.1-8b-instant",
    }

    with respx.mock(base_url="https://api.groq.com") as groq_mock:
        groq_mock.post("/openai/v1/chat/completions").respond(
            status_code=200,
            json=_mock_response_body,
        )
        yield groq_mock


@pytest.fixture
def all_scenarios() -> list[dict]:
    """Returns all 5 canonical demo scenarios."""
    return ALL_SCENARIOS
