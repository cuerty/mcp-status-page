import pytest
from helpers import mock_client

from mcp_status_page.models import Level, Service
from mcp_status_page.providers import instatus

URL = "https://instatus.instatus.com"


async def test_incidents_components_and_maintenance():
    service = Service(key="demo", provider="instatus", url=URL, name="Demo")
    routes = {f"{URL}/summary.json": "instatus_summary.json", f"{URL}/v2/components.json": "instatus_components.json"}
    async with mock_client(routes) as client:
        s = await instatus.fetch(client, service)

    # "IT Dept" is a group row without a status: skipped.
    assert [(c.name, c.level, c.group) for c in s.components] == [
        ("Website", Level.DEGRADED, "IT Dept"),
        ("App", Level.MAINTENANCE, "IT Dept"),
    ]
    assert [(i.title, i.level) for i in s.incidents] == [
        ("partial", Level.PARTIAL_OUTAGE),
        ("degraded", Level.DEGRADED),
    ]
    assert s.incidents[0].components == ["Website", "App"]
    assert s.incidents[0].latest_update == "We are currently investigating this incident."
    assert [(m.title, m.level) for m in s.maintenance] == [("Testing maintenance notifications", Level.MAINTENANCE)]
    assert s.level is Level.PARTIAL_OUTAGE
    assert s.summary == "Partial outage: Website, App (2 incidents)"


def test_healthy_page_without_incident_keys_is_operational():
    service = Service(key="demo", provider="instatus", url=URL, name="Demo")
    s = instatus.parse({"page": {"name": "x", "status": "UP"}}, {"components": []}, service)
    assert s.level.value == "operational"


def test_instatus_schema_change_raises():
    service = Service(key="demo", provider="instatus", url=URL, name="Demo")
    with pytest.raises(KeyError):
        instatus.parse({"page": {}}, {"items": []}, service)
    with pytest.raises(KeyError):
        instatus.parse({}, {"components": []}, service)
