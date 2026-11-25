"""Hits every built-in status page. Run with `uv run pytest -m live`. Catches moved or changed pages."""

import httpx
import pytest

from mcp_status_page import __version__
from mcp_status_page.registry import PROVIDERS, load_registry

SERVICES = load_registry()


@pytest.mark.live
@pytest.mark.parametrize("key", sorted(SERVICES))
async def test_builtin_service_is_readable(key):
    service = SERVICES[key]
    headers = {"User-Agent": f"mcp-status-page/{__version__}"}
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=headers) as client:
        status = await PROVIDERS[service.provider](client, service)
    assert status.error is None
