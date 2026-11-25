import pytest
from helpers import mock_client

from mcp_status_page.models import Level, Service
from mcp_status_page.providers import aws

SERVICE = Service(key="aws", provider="aws", url=aws.PAGE, name="AWS")


async def get_status():
    async with mock_client({aws.FEED: "aws_currentevents.json"}) as client:
        return await aws.fetch(client, SERVICE)


async def test_utf16_feed_parsed_into_regional_events():
    s = await get_status()
    assert [i.title for i in s.incidents] == [
        "Multiple services in me-central-1 (UAE): Region Availability",
        "Multiple services in me-south-1 (Bahrain): Region Availability",
    ]
    assert all(i.level is Level.MAJOR_OUTAGE for i in s.incidents)
    assert s.incidents[0].url == aws.PAGE
    assert s.incidents[0].latest_update
    assert len(s.components) == 279  # impacted services with current status != 0
    assert s.level is Level.MAJOR_OUTAGE


async def test_filter_by_service_and_region():
    s = await get_status()
    s3 = s.filtered("Simple Storage Service")
    assert sorted(c.group for c in s3.components) == ["me-central-1 (UAE)", "me-south-1 (Bahrain)"]
    bahrain = s.filtered("me-south-1")
    assert len(bahrain.components) == 144
    assert len(bahrain.incidents) == 1
    assert s.filtered("us-east-1").level is Level.OPERATIONAL


async def test_output_cap():
    s = (await get_status()).capped()
    assert len(s.components) == 25
    assert s.more_components == 254


def test_event_without_status_raises():
    with pytest.raises(KeyError):
        aws.parse([{"arn": "arn:aws:health:us-east-1::event/x"}], SERVICE)
