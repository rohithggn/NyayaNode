"""Async Supabase client singleton for NyayaNode."""

import os
from typing import Any, Optional, Union

import env_loader  # noqa: F401

import httpx
from postgrest import AsyncPostgrestClient
from supabase import AsyncClient, acreate_client

_client: Optional[Union[AsyncClient, "_PostgrestWrapper"]] = None


class _PostgrestWrapper:
    """Thin wrapper so sb_publishable / sb_secret keys work like AsyncClient.table()."""

    def __init__(self, postgrest: AsyncPostgrestClient) -> None:
        self._postgrest = postgrest

    def table(self, name: str) -> Any:
        return self._postgrest.from_(name)

    def rpc(self, name: str, params: Optional[dict[str, Any]] = None) -> Any:
        return self._postgrest.rpc(name, params or {})


def _api_key() -> str:
    return os.environ.get("SUPABASE_SERVICE_KEY") or os.environ["SUPABASE_ANON_KEY"]


def _uses_new_api_keys() -> bool:
    key = _api_key()
    return key.startswith("sb_publishable_") or key.startswith("sb_secret_")


async def get_client() -> Union[AsyncClient, _PostgrestWrapper]:
    """Return the shared async Supabase client, creating it on first use."""
    global _client
    if _client is not None:
        return _client

    url = os.environ["SUPABASE_URL"].rstrip("/")
    key = _api_key()

    if _uses_new_api_keys():
        postgrest = AsyncPostgrestClient(
            f"{url}/rest/v1",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
            },
        )
        _client = _PostgrestWrapper(postgrest)
        return _client

    _client = await acreate_client(url, key)
    return _client


async def test_connection() -> bool:
    """Run SELECT 1 against Supabase via the nyaya_select_one RPC."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = _api_key()
    if not url or not key:
        return False

    try:
        client = await get_client()
        response = await client.rpc("nyaya_select_one").execute()
        data = response.data
        if data == 1:
            return True
        if isinstance(data, list) and len(data) == 1 and data[0] == 1:
            return True
    except Exception:
        pass

    try:
        client = await get_client()
        await client.table("disputes").select("id").limit(1).execute()
        return True
    except Exception:
        pass

    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.get(
                f"{url}/rest/v1/",
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                },
            )
            return response.status_code < 500
    except Exception:
        return False
