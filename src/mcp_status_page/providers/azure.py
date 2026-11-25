"""Azure status RSS feed. It lists active incidents only and carries no severity."""

import re
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import httpx

from ..models import Incident, Level, Service, ServiceStatus

PAGE = "https://azure.status.microsoft/en-us/status"
FEED = "https://azure.status.microsoft/en-us/status/feed/"
_TAG = re.compile(r"<[^>]+>")


async def fetch(client: httpx.AsyncClient, service: Service) -> ServiceStatus:
    response = await client.get(FEED)
    response.raise_for_status()
    return parse(response.content, service)


def parse(xml: bytes, service: Service) -> ServiceStatus:
    incidents = []
    root = ElementTree.fromstring(xml)
    if root.find("channel") is None:
        raise ValueError("Azure feed has no RSS <channel>")
    for item in root.iter("item"):
        published = item.findtext("pubDate")
        text = " ".join(_TAG.sub(" ", item.findtext("description") or "").split())
        incidents.append(
            Incident(
                title=(item.findtext("title") or "Azure incident").strip(),
                level=Level.DEGRADED,  # no severity in the feed: lower bound
                started_at=parsedate_to_datetime(published) if published else None,
                latest_update=text or None,
                url=item.findtext("link"),
            )
        )
    return ServiceStatus.for_service(service, incidents=incidents)
