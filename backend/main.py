"""
NyayaNode FastAPI application — decentralized multi-agent dispute arbitration
for India's ONDC network.
"""

import asyncio
import importlib
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import env_loader  # noqa: F401 — load backend/.env before other imports

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.utils import get_openapi
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from core.schemas import HealthResponse, StatsResponse
from core.problem_details import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from middleware.api_key import APIKeyMiddleware
from routers import agent_bridge, audit, disputes, mock_parties, ondc_webhook
from services.supabase_client import get_client, test_connection

APP_VERSION = "1.0.0"
_agent_module_status = "not_loaded"

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ---------------------------------------------------------------------------
# Request ID middleware
# ---------------------------------------------------------------------------

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique X-Request-ID header to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

def _load_agent_module() -> None:
    """Attempt to import the configured arbitrator agent module."""
    global _agent_module_status
    module_path = os.environ.get("AGENT_MODULE_PATH", "agents.core.arbitrator")
    try:
        importlib.import_module(module_path)
        _agent_module_status = "loaded"
    except ImportError:
        _agent_module_status = "not_loaded"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: log, connect Supabase, probe agent module. Shutdown: log."""
    port = os.environ.get("PORT", "8000")
    logger.info("NyayaNode backend starting on port %s", port)
    _load_agent_module()
    try:
        await get_client()
    except Exception:
        pass
    yield
    logger.info("NyayaNode backend shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="NyayaNode API",
    description="Decentralized multi-agent dispute arbitration for ONDC",
    version=APP_VERSION,
    lifespan=lifespan,
    swagger_ui_parameters={"persistAuthorization": True},
)


def custom_openapi():
    """Attach X-API-Key security scheme so Swagger UI shows Authorize."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema["components"]["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "Must match BACKEND_API_KEY in .env (default dev: nyayanode-internal-secret-key)",
        }
    }
    for path, path_item in schema["paths"].items():
        if path.startswith("/api/v1/"):
            for operation in path_item.values():
                if isinstance(operation, dict) and "operationId" in operation:
                    operation["security"] = [{"ApiKeyAuth": []}]
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi

# ---------------------------------------------------------------------------
# Middleware (order matters — outermost first)
# ---------------------------------------------------------------------------

# Gzip compress responses larger than 1000 bytes
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Attach X-Request-ID to every response
app.add_middleware(RequestIDMiddleware)

# Build CORS origins: static list + optional FRONTEND_URL env var
_cors_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
]
_frontend_url = os.environ.get("FRONTEND_URL", "").strip()
if _frontend_url:
    _cors_origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(APIKeyMiddleware)

# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------

app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(disputes.router, prefix="/api/v1/disputes", tags=["Disputes"])
app.include_router(ondc_webhook.router, prefix="/api/v1/ondc", tags=["ONDC Webhook"])
app.include_router(agent_bridge.router, prefix="/api/v1/disputes", tags=["Agent Bridge"])
app.include_router(mock_parties.router, prefix="/mock/ondc", tags=["Mock ONDC Parties"])
app.include_router(audit.router, prefix="/api/v1/disputes", tags=["Audit"])

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"], response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Liveness probe with Supabase connectivity (3s timeout) and agent module status."""
    try:
        supabase_ok = await asyncio.wait_for(test_connection(), timeout=3.0)
    except asyncio.TimeoutError:
        supabase_ok = False
    except Exception:
        supabase_ok = False

    return HealthResponse(
        status="healthy",
        supabase="connected" if supabase_ok else "error",
        agent_module=_agent_module_status,
        version=APP_VERSION,
    )

# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def _to_decimal(value: Any) -> Decimal:
    """Coerce a PostgREST value to Decimal for INR-safe math."""
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


@app.get("/api/v1/stats", tags=["Stats"], response_model=StatsResponse)
async def get_stats() -> StatsResponse:
    """Aggregate dispute metrics for the dashboard."""
    try:
        client = await get_client()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database unavailable: {exc}",
        ) from exc

    try:
        total_resp = await client.table("disputes").select("id", count="exact").limit(0).execute()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to query disputes: {exc}",
        ) from exc

    total_disputes = total_resp.count or 0

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    resolved_resp = (
        await client.table("disputes")
        .select("id", count="exact")
        .eq("status", "RESOLVED")
        .gte("updated_at", today_start)
        .limit(0)
        .execute()
    )
    resolved_today = resolved_resp.count or 0

    escalated_resp = (
        await client.table("disputes")
        .select("id", count="exact")
        .eq("status", "ESCALATED")
        .limit(0)
        .execute()
    )
    escalated_count = escalated_resp.count or 0

    cost_rows = (
        await client.table("disputes")
        .select("total_cost_inr, created_at, updated_at, status")
        .not_.is_("total_cost_inr", "null")
        .execute()
    ).data or []

    cost_sum = Decimal("0")
    resolution_seconds: list[float] = []
    for row in cost_rows:
        cost_sum += _to_decimal(row.get("total_cost_inr"))
        if row.get("status") == "RESOLVED":
            created = row.get("created_at")
            updated = row.get("updated_at")
            if created and updated:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                resolution_seconds.append((updated_dt - created_dt).total_seconds())

    row_count = len(cost_rows)
    avg_cost_inr = float(cost_sum / row_count) if row_count else 0.0
    avg_resolution_time_seconds = (
        int(sum(resolution_seconds) / len(resolution_seconds))
        if resolution_seconds
        else 0
    )

    return StatsResponse(
        total_disputes=total_disputes,
        resolved_today=resolved_today,
        avg_cost_inr=round(avg_cost_inr, 4),
        avg_resolution_time_seconds=avg_resolution_time_seconds,
        escalated_count=escalated_count,
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
