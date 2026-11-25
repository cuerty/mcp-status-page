"""Atlassian Statuspage `/api/v2/summary.json`.

incident.io status pages serve a compatible endpoint at the same path (without
`scheduled_maintenances`), so the `incidentio` provider uses this adapter too.
"""

import httpx

from ..models import Component, Incident, Level, Service, ServiceStatus, parse_dt

COMPONENT_LEVEL = {
    "operational": Level.OPERATIONAL,
    "degraded_performance": Level.DEGRADED,
    "partial_outage": Level.PARTIAL_OUTAGE,
    "major_outage": Level.MAJOR_OUTAGE,
    "under_maintenance": Level.MAINTENANCE,
}
IMPACT_LEVEL = {
    "none": Level.DEGRADED,
    "minor": Level.DEGRADED,
    "major": Level.PARTIAL_OUTAGE,
    "critical": Level.MAJOR_OUTAGE,
}
IN_PROGRESS = {"in_progress", "verifying"}


async def fetch(client: httpx.AsyncClient, service: Service) -> ServiceStatus:
    response = await client.get(f"{service.url}/api/v2/summary.json")
    response.raise_for_status()
    return parse(response.json(), service)


def parse(data: dict, service: Service) -> ServiceStatus:
    raw = data["components"]
    groups = {c["id"]: c["name"] for c in raw if c.get("group")}
    components = [
        Component(
            name=c["name"],
            level=COMPONENT_LEVEL.get(c.get("status"), Level.DEGRADED),
            group=groups.get(c.get("group_id")),
        )
        for c in raw
        if not c.get("group")  # group rows only aggregate their children
    ]
    incidents = [
        _incident(i, IMPACT_LEVEL.get(i.get("impact"), Level.DEGRADED)) for i in data["incidents"]
    ]
    maintenance = [
        _incident(m, Level.MAINTENANCE if m.get("status") in IN_PROGRESS else Level.OPERATIONAL)
        for m in data.get("scheduled_maintenances") or []
    ]
    return ServiceStatus.for_service(service, components=components, incidents=incidents, maintenance=maintenance)


def _incident(raw: dict, level: Level) -> Incident:
    updates = raw.get("incident_updates") or []
    latest = updates[0] if updates else {}  # Statuspage lists updates newest first
    affected = raw.get("components") or latest.get("affected_components") or []
    return Incident(
        title=raw["name"],
        level=level,
        status=raw.get("status"),
        started_at=parse_dt(raw.get("scheduled_for") or raw.get("started_at") or raw.get("created_at")),
        updated_at=parse_dt(raw.get("updated_at")),
        latest_update=latest.get("body"),
        url=raw.get("shortlink"),
        components=[c["name"] for c in affected],
    )
