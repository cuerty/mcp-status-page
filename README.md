# mcp-status-page

An MCP server that checks the public status pages of common developer services, so your agent can tell when a failing API call, build or deploy is caused by an upstream outage and not by your code.

It reads GitHub, AWS, Azure, Google Cloud, Cloudflare, OpenAI, Anthropic, npm, PyPI, Docker, Vercel, Slack and 17 more. You can add any Statuspage, incident.io or Instatus page.

## Install

Claude Code:

```bash
claude mcp add status-page -- uvx mcp-status-page
```

Any MCP client (Cursor, Claude Desktop, ...):

```json
{
  "mcpServers": {
    "status-page": { "command": "uvx", "args": ["mcp-status-page"] }
  }
}
```

To run one shared instance over HTTP (Streamable HTTP):

```bash
uvx mcp-status-page --transport http --host 0.0.0.0 --port 8000
```

The HTTP transport has no authentication; bind it to a private network.

## Tools

| Tool | What it does |
|---|---|
| `list_services()` | Known services with aliases and domains. |
| `get_status(service, component=None)` | Status of one service. `service` can be a name, alias, hostname or URL (`api.github.com` → GitHub). `component` narrows to matching components, regions or incidents (`actions`, `s3`, `us-east-1`). |
| `check_services(services=None)` | Checks many services at once and returns only the ones with problems. |

Every status has a `level`: `operational`, `maintenance`, `degraded`, `partial_outage`, `major_outage` or `unknown`. `unknown` means the status page could not be read; it never counts as operational.

## Add your own services

Create a TOML file and pass it with `--config path.toml` or `MCP_STATUS_PAGE_CONFIG=path.toml`:

```toml
[services.mycompany]
provider = "statuspage"            # statuspage | incidentio | instatus | aws | azure | gcp | slack
url = "https://status.mycompany.com"
name = "My Company"                # optional
aliases = ["myco"]                 # optional
domains = ["mycompany.com"]        # optional; also matches subdomains
```

An entry with the same key as a built-in service replaces it. The built-in list is in [`src/mcp_status_page/services.toml`](https://github.com/cuerty/mcp-status-page/blob/main/src/mcp_status_page/services.toml).

## Options

| Flag | Default | |
|---|---|---|
| `--transport` | `stdio` | `stdio` or `http` |
| `--host`, `--port` | `127.0.0.1`, `8000` | HTTP transport only |
| `--config` | `$MCP_STATUS_PAGE_CONFIG` | Extra services file |
| `--cache-ttl` | `60` | Seconds to cache each status (failed fetches: 10s) |

## Limits

- **Azure** publishes only an RSS feed of active incidents, with no severity. Every Azure incident shows as `degraded`, even when it is worse.
- **AWS** uses the Health Dashboard's undocumented public feed. It can change without notice.
- Not supported (no readable public API): GitLab, Datadog, Heroku, Stripe.

## Development

```bash
uv sync
uv run pytest            # offline tests with recorded fixtures
uv run pytest -m live    # hits every built-in status page
```

## License

MIT
