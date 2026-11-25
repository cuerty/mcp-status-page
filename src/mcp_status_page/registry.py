"""Service definitions: bundled services.toml merged with an optional user TOML file."""

import difflib
import tomllib
from collections.abc import Awaitable, Callable
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .models import Service, ServiceStatus
from .providers import aws, azure, gcp, instatus, slack, statuspage

PROVIDERS: dict[str, Callable[[httpx.AsyncClient, Service], Awaitable[ServiceStatus]]] = {
    "statuspage": statuspage.fetch,
    "incidentio": statuspage.fetch,  # incident.io serves a Statuspage-compatible summary.json
    "instatus": instatus.fetch,
    "aws": aws.fetch,
    "azure": azure.fetch,
    "gcp": gcp.fetch,
    "slack": slack.fetch,
}
# Single-feed providers: any configured `url` is ignored.
FIXED_URLS = {"aws": aws.PAGE, "azure": azure.PAGE, "gcp": gcp.PAGE, "slack": slack.PAGE}


class ConfigError(Exception):
    """Invalid service configuration. The message names the file, service and field."""


def load_registry(user_config: str | Path | None = None) -> dict[str, Service]:
    builtin = files("mcp_status_page").joinpath("services.toml").read_text(encoding="utf-8")
    services = _parse(tomllib.loads(builtin), "built-in services.toml")
    if user_config:
        path = Path(user_config).expanduser()
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigError(f"{path}: cannot read file ({exc.strerror})") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{path}: invalid TOML ({exc})") from exc
        services |= _parse(data, str(path))
    return services


def _parse(data: dict, source: str) -> dict[str, Service]:
    table = data.get("services", {})
    if not isinstance(table, dict):
        raise ConfigError(f"{source}: 'services' must be a table")
    return {key: _service(key, raw, f"{source}: services.{key}") for key, raw in table.items()}


def _service(key: str, raw: object, where: str) -> Service:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: must be a table")
    provider = raw.get("provider")
    if provider not in PROVIDERS:
        raise ConfigError(f"{where}.provider: expected one of {', '.join(sorted(PROVIDERS))}, got {provider!r}")
    url = FIXED_URLS.get(provider) or raw.get("url")
    parsed = urlparse(url) if isinstance(url, str) else None
    if parsed is None or parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ConfigError(f"{where}.url: expected an http(s) URL, got {url!r}")
    name = raw.get("name", key)
    if not isinstance(name, str):
        raise ConfigError(f"{where}.name: expected a string, got {name!r}")
    lists: dict[str, list[str]] = {}
    for field in ("aliases", "domains"):
        value = raw.get(field, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ConfigError(f"{where}.{field}: expected a list of strings, got {value!r}")
        lists[field] = [v.lower() for v in value]
    return Service(key=key, provider=provider, url=url.rstrip("/"), name=name, **lists)


def resolve(services: dict[str, Service], query: str) -> Service | None:
    """Find a service by key or alias, else by a hostname or URL matching its domains."""
    q = query.strip().lower()
    for service in services.values():
        if q == service.key.lower() or q in service.aliases:
            return service
    host = urlparse(q).hostname if "://" in q else q.split("/")[0].split(":")[0]
    if not host:
        return None
    for service in services.values():
        if any(host == d or host.endswith("." + d) for d in service.domains):
            return service
    return None


def suggest(services: dict[str, Service], query: str, n: int = 3) -> list[str]:
    names = [*services, *(a for s in services.values() for a in s.aliases)]
    return difflib.get_close_matches(query.strip().lower(), names, n=n)
