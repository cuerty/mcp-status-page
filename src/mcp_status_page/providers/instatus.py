"""Instatus pages: `/summary.json` (incidents, maintenances) + `/v2/components.json`."""

import httpx

from ..models import Component, Incident, Level, Service, ServiceStatus, parse_dt

LEVEL = {
    "OPERATIONAL": Level.OPERATIONAL,
    "UNDERMAINTENANCE": Level.MAINTENANCE,
    "DEGRADEDPERFORMANCE": Level.DEGRADED,
    "PARTIALOUTAGE": Level.PARTIAL_OUTAGE,
    "MAJOROUTAGE": Level.MAJOR_OUTAGE,
}


async def fetch(client: httpx.AsyncClient, service: Service) -> ServiceStatus:
    summary = await client.get(f"{service.url}/summary.json")
    summary.raise_for_status()
    components = await client.get(f"{service.url}/v2/components.json")
    components.raise_for_status()
    return parse(summary.json(), components.json(), service)


def parse(summary: dict, components: dict, service: Service) -> ServiceStatus:
    raw = components.get("components") or []
    affected: dict[str, list[str]] = {}
    for c in raw:
        for item in [*(c.get("activeIncidents") or []), *(c.get("activeMaintenances") or [])]:
            affected.setdefault(item["id"], []).append(c["name"])
    return ServiceStatus.for_service(
        service,
        components=[
            Component(
                name=c["name"],
                level=LEVEL.get(c["status"], Level.DEGRADED),
                group=(c.get("group") or {}).get("name"),
            )
            for c in raw
            if c.get("status")  # group rows have no status
        ],
        incidents=[
            _item(i, LEVEL.get(i.get("impact"), Level.DEGRADED), affected)
            for i in summary.get("activeIncidents") or []
        ],
        maintenance=[
            _item(m, Level.MAINTENANCE if m.get("status") == "INPROGRESS" else Level.OPERATIONAL, affected)
            for m in summary.get("activeMaintenances") or []
        ],
    )


def _item(raw: dict, level: Level, affected: dict[str, list[str]]) -> Incident:
    return Incident(
        title=raw["name"],
        level=level,
        status=raw.get("status"),
        started_at=parse_dt(raw.get("started") or raw.get("start")),
        updated_at=parse_dt(raw.get("updatedAt")),
        latest_update=(raw.get("lastUpdate") or {}).get("message"),
        url=raw.get("url"),
        components=affected.get(raw["id"], []),
    )
