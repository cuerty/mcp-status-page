import httpx
import pytest
from helpers import mock_client

from mcp_status_page.models import Level, Service
from mcp_status_page.providers import statuspage


async def fetch(url: str, fixture: str, provider: str = "statuspage"):
    service = Service(key="x", provider=provider, url=url, name="X")
    async with mock_client({f"{url}/api/v2/summary.json": fixture}) as client:
        return await statuspage.fetch(client, service)


async def test_github_outage():
    s = await fetch("https://www.githubstatus.com", "statuspage_github.json")
    assert s.level is Level.MAJOR_OUTAGE
    assert [c.name for c in s.components] == [
        "Issues", "Pull Requests", "Actions", "Packages", "Pages", "Git Operations", "Webhooks", "API Requests",
    ]
    [incident] = s.incidents
    assert incident.title == "Investigating degraded experiences across GitHub products"
    assert incident.level is Level.MAJOR_OUTAGE
    assert incident.status == "investigating"
    assert incident.latest_update.startswith("API Requests is experiencing degraded performance")
    assert "Pull Requests" in incident.components
    assert incident.url == "https://stspg.io/5qj9j0p5g4cr"
    assert s.maintenance == []
    assert s.summary == "Major outage: Issues, Pull Requests, Actions, Packages, Pages +3 more (1 incident)"


async def test_github_component_filter():
    s = (await fetch("https://www.githubstatus.com", "statuspage_github.json")).filtered("actions")
    assert [(c.name, c.level) for c in s.components] == [("Actions", Level.PARTIAL_OUTAGE)]
    assert len(s.incidents) == 1  # the incident lists Actions among its components


async def test_major_impact_incident_maps_to_partial_outage():
    s = await fetch("https://status.claude.com", "statuspage_anthropic.json")
    assert [(c.name, c.level) for c in s.components] == [("claude.ai", Level.DEGRADED)]
    assert [i.title for i in s.incidents] == ["Claude for Microsoft 365 add-in missing for some users"]
    assert s.level is Level.PARTIAL_OUTAGE


async def test_incidentio_compat_endpoint():
    s = await fetch("https://status.openai.com", "incidentio_openai.json", provider="incidentio")
    assert s.provider == "incidentio"
    assert s.components == []
    assert [i.title for i in s.incidents] == ["Elevated errors with Codex GitHub reviews and pull request merges"]
    assert s.level is Level.DEGRADED
    assert s.maintenance == []


async def test_http_error_raises():
    service = Service(key="x", provider="statuspage", url="https://status.example.com", name="X")
    async with mock_client({}) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await statuspage.fetch(client, service)
