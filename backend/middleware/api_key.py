"""API key gate for /api/v1/* routes."""

import os

import env_loader  # noqa: F401
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

PROBLEM_BASE = "https://nyayanode.dev/problems"


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Require X-API-Key header on all /api/v1/* paths."""

    async def dispatch(self, request: Request, call_next):
        """Validate API key before forwarding to route handlers."""
        if request.url.path.startswith("/api/v1/"):
            # SSE stream endpoint is exempt — browser EventSource cannot send custom headers
            if request.url.path.endswith("/stream"):
                return await call_next(request)
            expected = os.environ.get("BACKEND_API_KEY", "")
            provided = request.headers.get("X-API-Key", "")
            if not expected or provided != expected:
                return JSONResponse(
                    status_code=401,
                    content={
                        "type": f"{PROBLEM_BASE}/unauthorized",
                        "title": "Unauthorized",
                        "status": 401,
                        "detail": "Missing or invalid X-API-Key header",
                    },
                )
        return await call_next(request)
