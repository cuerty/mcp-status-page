"""Slack status API v2: `/api/v2.0.0/current`."""

import httpx

from ..models import Component, Incident, Level, Service, ServiceStatus, parse_dt

PAGE = "https://slack-status.com"
FEED = f"{PAGE}/api/v2.0.0/current"
TYPE_LEVEL = {"outage": Level.MAJOR_OUTAGE, "incident": Level.PARTIAL_OUTAGE, "notice": Level.DEGRADED}


async def fetch(client: httpx.AsyncClient, service: Service) -> ServiceStatus:
    response = await client.get(FEED)
    response.raise_for_status()
    return parse(response.json(), service)


def parse(data: dict, service: Service) -> ServiceStatus:
    components: list[Component] = []
    incidents: list[Incident] = []
    for raw in data["active_incidents"]:
        level = TYPE_LEVEL.get(raw.get("type"), Level.DEGRADED)
        names = raw.get("services") or []
        notes = raw.get("notes") or []
        incidents.append(
            Incident(
                title=raw.get("title") or "Slack incident",
                level=level,
                status=raw.get("status"),
                started_at=parse_dt(raw.get("date_created")),
                updated_at=parse_dt(raw.get("date_updated")),
                latest_update=notes[0].get("body") if notes else None,
                url=raw.get("url"),
                components=names,
            )
        )
        components += [Component(name=n, level=level) for n in names]
    return ServiceStatus.for_service(service, components=components, incidents=incidents)
