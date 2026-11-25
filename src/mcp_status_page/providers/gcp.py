"""Google Cloud status: `incidents.json` lists recent incidents; open ones have no `end`."""

import httpx

from ..models import Component, Incident, Level, Service, ServiceStatus, parse_dt

PAGE = "https://status.cloud.google.com"
FEED = f"{PAGE}/incidents.json"
IMPACT = {
    "SERVICE_INFORMATION": Level.DEGRADED,
    "SERVICE_DISRUPTION": Level.PARTIAL_OUTAGE,
    "SERVICE_OUTAGE": Level.MAJOR_OUTAGE,
}


async def fetch(client: httpx.AsyncClient, service: Service) -> ServiceStatus:
    response = await client.get(FEED)
    response.raise_for_status()
    return parse(response.json(), service)


def parse(data: list[dict], service: Service) -> ServiceStatus:
    components: list[Component] = []
    incidents: list[Incident] = []
    for raw in data:
        if raw.get("end"):
            continue
        level = IMPACT.get(raw.get("status_impact"), Level.DEGRADED)
        products = [p["title"] for p in raw.get("affected_products") or []]
        locations = [loc["id"] for loc in raw.get("currently_affected_locations") or []]
        update = raw.get("most_recent_update") or {}
        incidents.append(
            Incident(
                title=raw.get("external_desc") or raw.get("service_name") or "Google Cloud incident",
                level=level,
                status=update.get("status"),
                started_at=parse_dt(raw.get("begin")),
                updated_at=parse_dt(raw.get("modified")),
                latest_update=update.get("text"),
                url=f"{PAGE}/{raw['uri']}" if raw.get("uri") else None,
                components=products + locations,
            )
        )
        where = ", ".join(locations) or "global"
        components += [Component(name=p, level=level, group=where) for p in products]
    return ServiceStatus.for_service(service, components=components, incidents=incidents)
