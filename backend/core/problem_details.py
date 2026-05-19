"""RFC 7807 Problem Details helpers."""

from typing import Any, Optional

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_BASE = "https://nyayanode.dev/problems"


def problem_response(
    *,
    status: int,
    title: str,
    detail: str,
    type_suffix: str = "generic",
    headers: Optional[dict[str, str]] = None,
) -> JSONResponse:
    """Build a JSONResponse conforming to RFC 7807 Problem Details."""
    return JSONResponse(
        status_code=status,
        content={
            "type": f"{PROBLEM_BASE}/{type_suffix}",
            "title": title,
            "status": status,
            "detail": detail,
        },
        headers=headers,
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Map Starlette/FastAPI HTTP exceptions to Problem Details."""
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return problem_response(
        status=exc.status_code,
        title=detail or "Request failed",
        detail=detail,
        type_suffix=str(exc.status_code),
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Map request validation errors to Problem Details."""
    errors: list[dict[str, Any]] = exc.errors()
    detail = "; ".join(
        f"{'.'.join(str(loc) for loc in err.get('loc', []))}: {err.get('msg', '')}"
        for err in errors
    )
    return problem_response(
        status=422,
        title="Validation Error",
        detail=detail or "Request validation failed",
        type_suffix="validation-error",
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map unexpected exceptions to Problem Details."""
    return problem_response(
        status=500,
        title="Internal Server Error",
        detail="An unexpected error occurred",
        type_suffix="internal-error",
    )
