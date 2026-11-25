from helpers import mock_client

from mcp_status_page.models import Level, Service
from mcp_status_page.providers import azure, slack

AZURE = Service(key="azure", provider="azure", url=azure.PAGE, name="Azure")
SLACK = Service(key="slack", provider="slack", url=slack.PAGE, name="Slack")


async def azure_status(fixture: str):
    async with mock_client({azure.FEED: fixture}) as client:
        return await azure.fetch(client, AZURE)


async def slack_status(fixture: str):
    async with mock_client({slack.FEED: fixture}) as client:
        return await slack.fetch(client, SLACK)


async def test_azure_item_is_degraded_incident():
    s = await azure_status("azure_feed.xml")
    [incident] = s.incidents
    assert incident.title == "Azure Front Door - Connectivity issues in West Europe"
    assert incident.level is Level.DEGRADED
    assert incident.latest_update == "Starting at 14:10 UTC customers may experience timeouts when connecting to resources."
    assert incident.started_at.isoformat() == "2026-11-25T14:30:00+00:00"
    assert s.summary == "Degraded: Azure Front Door - Connectivity issues in West Europe (1 incident)"
    assert s.filtered("west europe").level is Level.DEGRADED
    assert s.filtered("east us").level is Level.OPERATIONAL


async def test_azure_empty_feed_is_operational():
    s = await azure_status("azure_empty.xml")
    assert s.level is Level.OPERATIONAL


async def test_slack_incidents_merge_component_levels():
    s = await slack_status("slack_incident.json")
    assert [(c.name, c.level) for c in s.components] == [
        ("Messaging", Level.PARTIAL_OUTAGE),
        ("Connectivity", Level.PARTIAL_OUTAGE),
        ("Huddles", Level.DEGRADED),
    ]
    assert [(i.title, i.level) for i in s.incidents] == [
        ("Some users can't send messages", Level.PARTIAL_OUTAGE),
        ("Huddles degraded", Level.DEGRADED),
    ]
    assert s.incidents[0].latest_update == "We're investigating reports of messages failing to send."
    assert s.incidents[1].latest_update is None
    assert s.summary == "Partial outage: Messaging, Connectivity, Huddles (2 incidents)"


async def test_slack_ok_is_operational():
    s = await slack_status("slack_ok.json")
    assert s.level is Level.OPERATIONAL
