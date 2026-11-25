import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from helpers import mock_client

from mcp_status_page.models import Service
from mcp_status_page.providers import slack
from mcp_status_page.server import build_server, main

GH = "https://www.githubstatus.com"
AN = "https://status.claude.com"
REGISTRY = {
    "github": Service(key="github", provider="statuspage", url=GH, name="GitHub", aliases=["gh"], domains=["github.com"]),
    "anthropic": Service(key="anthropic", provider="statuspage", url=AN, name="Anthropic"),
    "slack": Service(key="slack", provider="slack", url=slack.PAGE, name="Slack"),
    "broken": Service(key="broken", provider="statuspage", url="https://status.broken.example", name="Broken"),
}
ROUTES = {
    f"{GH}/api/v2/summary.json": "statuspage_github.json",
    f"{AN}/api/v2/summary.json": "statuspage_anthropic.json",
    slack.FEED: "slack_ok.json",
}


@pytest.fixture
async def client():
    async with mock_client(ROUTES) as http, Client(build_server(REGISTRY, client=http)) as c:
        yield c


async def test_list_services(client):
    result = await client.call_tool("list_services", {})
    rows = result.structured_content["result"]
    assert [r["service"] for r in rows] == ["github", "anthropic", "slack", "broken"]
    assert rows[0]["domains"] == ["github.com"]


async def test_get_status_by_domain_with_component_filter(client):
    result = await client.call_tool("get_status", {"service": "api.github.com", "component": "actions"})
    data = result.structured_content
    assert data["service"] == "github"
    assert data["level"] == "major_outage"
    assert [c["name"] for c in data["components"]] == ["Actions"]


async def test_unknown_service_suggests(client):
    with pytest.raises(ToolError, match="Did you mean: github"):
        await client.call_tool("get_status", {"service": "githb"})


async def test_check_services_reports_problems_including_unknown(client):
    result = await client.call_tool("check_services", {})
    data = result.structured_content
    assert data["checked"] == 4
    assert data["all_operational"] is False
    levels = {p["service"]: p["level"] for p in data["problems"]}
    assert levels == {"github": "major_outage", "anthropic": "partial_outage", "broken": "unknown"}
    broken = next(p for p in data["problems"] if p["service"] == "broken")
    assert broken["error"].startswith("HTTPStatusError")


async def test_check_selected_services_all_operational(client):
    result = await client.call_tool("check_services", {"services": ["slack", "slack"]})
    assert result.structured_content == {"checked": 1, "all_operational": True, "problems": []}


async def test_check_services_rejects_unknown_names(client):
    with pytest.raises(ToolError, match="Unknown service 'nope'"):
        await client.call_tool("check_services", {"services": ["github", "nope"]})


async def test_results_are_cached():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"components": [], "incidents": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        async with Client(build_server({"github": REGISTRY["github"]}, client=http)) as c:
            await c.call_tool("get_status", {"service": "github"})
            await c.call_tool("get_status", {"service": "gh"})
    assert calls == 1


def test_cli_rejects_bad_config(tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text('[services.x]\nprovider = "nope"\n')
    with pytest.raises(SystemExit) as exc:
        main(["--config", str(bad)])
    assert exc.value.code == 2
    assert "config error" in capsys.readouterr().err


async def test_check_services_empty_list_checks_all(client):
    result = await client.call_tool("check_services", {"services": []})
    assert result.structured_content["checked"] == 4


async def test_non_http_adapter_error_is_unknown():
    reg = {"odd": Service(key="odd", provider="statuspage", url="https://odd.example", name="Odd")}
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"unexpected": True}))
    async with httpx.AsyncClient(transport=transport) as http, Client(build_server(reg, client=http)) as c:
        data = (await c.call_tool("get_status", {"service": "odd"})).structured_content
    assert data["level"] == "unknown"
    assert data["error"].startswith("KeyError")
