from helpers import mock_client

from mcp_status_page.models import Level, Service
from mcp_status_page.providers import gcp

SERVICE = Service(key="gcp", provider="gcp", url=gcp.PAGE, name="Google Cloud")


async def get_status():
    async with mock_client({gcp.FEED: "gcp_incidents.json"}) as client:
        return await gcp.fetch(client, SERVICE)


async def test_only_open_incidents_count():
    s = await get_status()
    [incident] = s.incidents  # the second fixture incident has an `end` and is skipped
    assert incident.title == "Multiple services were experiencing issues in the europe-west2 region."
    assert incident.level is Level.PARTIAL_OUTAGE
    assert incident.url == "https://status.cloud.google.com/incidents/Xs2XTHzAVC9YnafnPyzj"
    assert incident.latest_update == "We are investigating elevated error rates for multiple services in europe-west2."
    assert "europe-west2" in incident.components
    assert len(s.components) == 38
    assert {c.group for c in s.components} == {"europe-west2"}
    assert s.level is Level.PARTIAL_OUTAGE


async def test_filter_by_product_and_region():
    s = await get_status()
    assert [c.name for c in s.filtered("cloud run").components] == ["Cloud Run"]
    assert s.filtered("us-central1").level is Level.OPERATIONAL
