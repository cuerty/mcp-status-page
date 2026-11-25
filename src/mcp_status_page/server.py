"""FastMCP server exposing service status tools, plus the CLI entry point."""

import argparse
import asyncio
import os
import time

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel

from . import __version__
from .models import Level, Service, ServiceStatus
from .registry import PROVIDERS, ConfigError, load_registry, resolve, suggest

FETCH_TIMEOUT = 10.0
ERROR_TTL = 10.0
WHEN = (
    "Use it when an API call, build, deploy, git operation or package install fails in a way that "
    "may be caused by the upstream service (timeouts, 5xx errors, failed auth, rate limits) and not by your code."
)


class ServiceInfo(BaseModel):
    service: str
    name: str
    provider: str
    page_url: str
    aliases: list[str]
    domains: list[str]


class CheckResult(BaseModel):
    checked: int
    all_operational: bool
    problems: list[ServiceStatus]


def build_server(
    registry: dict[str, Service],
    *,
    client: httpx.AsyncClient | None = None,
    cache_ttl: float = 60.0,
) -> FastMCP:
    mcp = FastMCP("status-page", instructions=f"Live status of common developer services. {WHEN}")
    http = client or httpx.AsyncClient(
        timeout=FETCH_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": f"mcp-status-page/{__version__}"},
    )
    # ponytail: no per-key lock; concurrent misses for one service may fetch it twice.
    cache: dict[str, tuple[float, ServiceStatus]] = {}

    async def status_of(service: Service) -> ServiceStatus:
        hit = cache.get(service.key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        try:
            status = await asyncio.wait_for(PROVIDERS[service.provider](http, service), FETCH_TIMEOUT)
        except Exception as exc:  # one broken page must never fail the tool call
            reason = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            status = ServiceStatus.for_service(service, error=reason[:200])
        cache[service.key] = (time.monotonic() + (ERROR_TTL if status.error else cache_ttl), status)
        return status

    def lookup(name: str) -> Service:
        service = resolve(registry, name)
        if service is None:
            hints = suggest(registry, name)
            hint = f" Did you mean: {', '.join(hints)}?" if hints else ""
            raise ToolError(f"Unknown service {name!r}.{hint} Call list_services for the full list.")
        return service

    @mcp.tool
    def list_services() -> list[ServiceInfo]:
        """List the services this server can check. To find the service behind a failing
        host (e.g. api.github.com), match it against `domains`, or pass the host to get_status."""
        return [
            ServiceInfo(
                service=s.key, name=s.name, provider=s.provider, page_url=s.url, aliases=s.aliases, domains=s.domains
            )
            for s in registry.values()
        ]

    @mcp.tool(
        description=(
            "Get the current status of one service: overall level, non-operational components, active "
            "incidents and maintenance. `service` accepts a name, alias, hostname or URL. `component` "
            "narrows the result to matching components, regions or incidents (e.g. 'actions', 's3', "
            f"'us-east-1'). {WHEN}"
        )
    )
    async def get_status(service: str, component: str | None = None) -> ServiceStatus:
        status = await status_of(lookup(service))
        return (status.filtered(component) if component else status).capped()

    @mcp.tool(
        description=(
            "Check several services at once (all known services when `services` is omitted) and return "
            f"only those that are not operational, including ones whose status page could not be read. {WHEN}"
        )
    )
    async def check_services(services: list[str] | None = None) -> CheckResult:
        targets = list(registry.values()) if services is None else [lookup(name) for name in services]
        unique = list({s.key: s for s in targets}.values())
        results = await asyncio.gather(*(status_of(s) for s in unique))
        problems = [r.capped() for r in results if r.level is not Level.OPERATIONAL]
        return CheckResult(checked=len(results), all_operational=not problems, problems=problems)

    return mcp


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="mcp-status-page",
        description="MCP server reporting live status of developer services.",
    )
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP transport host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="HTTP transport port (default: 8000)")
    parser.add_argument(
        "--config",
        default=os.environ.get("MCP_STATUS_PAGE_CONFIG"),
        help="TOML file with extra services (env: MCP_STATUS_PAGE_CONFIG)",
    )
    parser.add_argument("--cache-ttl", type=float, default=60.0, help="seconds to cache each status (default: 60)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)
    try:
        registry = load_registry(args.config)
    except ConfigError as exc:
        parser.exit(2, f"mcp-status-page: config error: {exc}\n")
    server = build_server(registry, cache_ttl=args.cache_ttl)
    if args.transport == "http":
        server.run(transport="http", host=args.host, port=args.port)
    else:
        server.run()
