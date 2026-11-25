"""Normalized status model shared by every provider adapter."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, computed_field, field_validator

MAX_UPDATE_CHARS = 500
MAX_COMPONENTS = 25
MAINTENANCE_HORIZON = timedelta(hours=24)


class Level(StrEnum):
    """Severity, declared from best to worst. `unknown` means we could not check."""

    OPERATIONAL = "operational"
    MAINTENANCE = "maintenance"
    DEGRADED = "degraded"
    PARTIAL_OUTAGE = "partial_outage"
    MAJOR_OUTAGE = "major_outage"
    UNKNOWN = "unknown"


_RANK = {level: rank for rank, level in enumerate(Level)}


def worst(levels: Iterable[Level]) -> Level:
    return max(levels, key=_RANK.__getitem__, default=Level.OPERATIONAL)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class Service(BaseModel):
    """One configured status page."""

    key: str
    provider: str
    url: str
    name: str
    aliases: list[str] = []
    domains: list[str] = []


class Component(BaseModel):
    name: str
    level: Level
    group: str | None = None


class Incident(BaseModel):
    title: str
    level: Level
    status: str | None = None
    started_at: datetime | None = None
    updated_at: datetime | None = None
    latest_update: str | None = None
    url: str | None = None
    components: list[str] = []

    @field_validator("latest_update")
    @classmethod
    def _truncate(cls, value: str | None) -> str | None:
        if value and len(value) > MAX_UPDATE_CHARS:
            return value[: MAX_UPDATE_CHARS - 1] + "…"
        return value


class ServiceStatus(BaseModel):
    service: str
    name: str
    provider: str
    page_url: str
    fetched_at: datetime
    components: list[Component] = []  # non-operational only, worst first
    incidents: list[Incident] = []  # active only
    maintenance: list[Incident] = []  # in progress, or starting within 24h
    error: str | None = None
    more_components: int = 0  # components cut by the output cap

    @classmethod
    def for_service(
        cls,
        service: Service,
        *,
        components: Iterable[Component] = (),
        incidents: Iterable[Incident] = (),
        maintenance: Iterable[Incident] = (),
        error: str | None = None,
        now: datetime | None = None,
    ) -> ServiceStatus:
        now = now or datetime.now(UTC)
        merged: dict[tuple[str, str | None], Component] = {}
        for c in components:
            if c.level is Level.OPERATIONAL:
                continue
            prev = merged.get((c.name, c.group))
            if prev is None or _RANK[c.level] > _RANK[prev.level]:
                merged[(c.name, c.group)] = c
        horizon = now + MAINTENANCE_HORIZON
        return cls(
            service=service.key,
            name=service.name,
            provider=service.provider,
            page_url=service.url,
            fetched_at=now,
            components=sorted(merged.values(), key=lambda c: -_RANK[c.level]),
            incidents=list(incidents),
            maintenance=[
                m
                for m in maintenance
                if m.level is Level.MAINTENANCE or (m.started_at is not None and m.started_at <= horizon)
            ],
            error=error,
        )

    @computed_field
    @property
    def level(self) -> Level:
        if self.error:
            return Level.UNKNOWN
        return worst(
            [c.level for c in self.components] + [i.level for i in (*self.incidents, *self.maintenance)]
        )

    @computed_field
    @property
    def summary(self) -> str:
        if self.error:
            return f"Status unknown: {self.error}"
        level = self.level
        if level is Level.OPERATIONAL:
            text = "All systems operational"
            if self.maintenance:
                text += f"; upcoming maintenance: {self.maintenance[0].title}"
            return text
        shown = list(dict.fromkeys(c.name for c in self.components))[:5]
        if shown:
            what = ", ".join(shown)
            extra = len(self.components) + self.more_components - len(shown)
            if extra > 0:
                what += f" +{extra} more"
        else:
            what = "; ".join(i.title for i in (self.incidents or self.maintenance)[:2])
        n = len(self.incidents)
        tail = f" ({n} incident{'s' if n != 1 else ''})" if n else ""
        return f"{level.value.replace('_', ' ').capitalize()}: {what}{tail}"

    def filtered(self, term: str) -> ServiceStatus:
        """Keep only items mentioning `term` (case-insensitive); level and summary follow."""
        needle = term.lower()

        def hit(*texts: str | None) -> bool:
            return any(needle in t.lower() for t in texts if t)

        return self.model_copy(
            update={
                "components": [c for c in self.components if hit(c.name, c.group)],
                "incidents": [i for i in self.incidents if hit(i.title, *i.components)],
                "maintenance": [m for m in self.maintenance if hit(m.title, *m.components)],
            }
        )

    def capped(self, limit: int = MAX_COMPONENTS) -> ServiceStatus:
        if len(self.components) <= limit:
            return self
        return self.model_copy(
            update={
                "components": self.components[:limit],
                "more_components": self.more_components + len(self.components) - limit,
            }
        )
