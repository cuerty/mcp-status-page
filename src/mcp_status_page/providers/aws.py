"""AWS Health Dashboard public feed (undocumented; UTF-16 JSON list of current events)."""

import json
from datetime import UTC, datetime

import httpx

from ..models import Component, Incident, Level, Service, ServiceStatus

PAGE = "https://health.aws.amazon.com/health/status"
FEED = "https://health.aws.amazon.com/public/currentevents"
# Dashboard codes: 0 resolved, 1 informational, 2 degradation, 3 disruption.
STATUS = {"0": Level.OPERATIONAL, "1": Level.DEGRADED, "2": Level.PARTIAL_OUTAGE, "3": Level.MAJOR_OUTAGE}


async def fetch(client: httpx.AsyncClient, service: Service) -> ServiceStatus:
    response = await client.get(FEED)
    response.raise_for_status()
    return parse(json.loads(response.content), service)  # json.loads detects UTF-16 from the bytes


def _level(code: object) -> Level:
    return STATUS.get(str(code), Level.DEGRADED)


def _ts(value: object) -> datetime | None:
    return datetime.fromtimestamp(int(value), UTC) if value else None


def parse(events: list[dict], service: Service) -> ServiceStatus:
    components: list[Component] = []
    incidents: list[Incident] = []
    for event in events:
        level = _level(event["status"])
        if level is Level.OPERATIONAL:
            continue
        arn = event.get("arn", "").split(":")
        region = arn[3] if len(arn) > 3 and arn[3] else "global"
        group = f"{region} ({event['region_name']})" if event.get("region_name") else region
        name = event.get("service_name") or "AWS"
        affected = [
            Component(name=s["service_name"], level=_level(s.get("current")), group=group)
            for s in (event.get("impacted_services") or {}).values()
        ] or [Component(name=name, level=level, group=group)]
        components += affected
        log = event.get("event_log") or []
        last = max(log, key=lambda entry: entry.get("timestamp", 0), default={})
        incidents.append(
            Incident(
                title=f"{name} in {group}: {event.get('summary') or 'Service event'}",
                level=level,
                started_at=_ts(event.get("date")),
                updated_at=_ts(last.get("timestamp")),
                latest_update=last.get("message"),
                url=PAGE,
                components=[c.name for c in affected if c.level is not Level.OPERATIONAL],
            )
        )
    return ServiceStatus.for_service(service, components=components, incidents=incidents)
