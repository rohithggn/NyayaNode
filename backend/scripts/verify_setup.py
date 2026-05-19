"""Smoke-test imports, health, and optional Supabase connectivity."""

import asyncio
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_DIR))


def check_env() -> None:
    url = os.getenv("SUPABASE_URL", "")
    if not url or "supabase.co" not in url:
        print("WARN: SUPABASE_URL not set in backend/.env")
    else:
        print(f"SUPABASE_URL: {url}")


async def smoke_test() -> None:
    from httpx import ASGITransport, AsyncClient

    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        assert health.status_code == 200, health.text
        print("health:", health.json())

        api_key = os.getenv("BACKEND_API_KEY", "nyayanode-internal-secret-key")
        stats = await client.get("/api/v1/stats", headers={"X-API-Key": api_key})
        if stats.status_code == 503:
            print("stats: skipped (configure Supabase + run migration)")
        else:
            assert stats.status_code == 200, stats.text
            print("stats:", stats.json())


def main() -> int:
    import env_loader  # noqa: F401

    print("Checking imports...")
    from main import app  # noqa: F401

    print(f"OK: {len(app.routes)} routes registered")
    check_env()
    asyncio.run(smoke_test())
    print("VERIFY OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
