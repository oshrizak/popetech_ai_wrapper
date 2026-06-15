# Using Pope Tech as an MCP server

The package ships an [MCP](https://modelcontextprotocol.io) server that exposes
the `ptq` agent layer as tools, so an MCP-capable assistant (Claude Desktop,
Cursor, Continue, Zed, …) can inspect Pope Tech accessibility data **natively** —
no shelling out to the CLI and parsing text.

It wraps the same read-only `Agent` facade the `ptq` CLI uses, so it inherits
fuzzy name→slug resolution, trimmed payloads, and cross-org fan-out.

## Install

The server needs the `mcp` SDK, which requires **Python 3.10+**. It's an optional
extra so the base library still supports 3.9:

```bash
pip install -e ".[mcp]"
```

## Authenticate

Same as the rest of the package — put your token in `.env` at the project root:

```
POPE_TECH_API_KEY="your-bearer-token"
```

Optional environment variables:

| Variable                  | Effect                                                          |
| ------------------------- | -------------------------------------------------------------- |
| `POPE_TECH_API_KEY`       | Bearer token (required).                                        |
| `POPE_TECH_DEFAULT_ORG`   | Default org slug when a tool's `org` is omitted.               |
| `POPE_TECH_MCP_WRITABLE`  | Set to `1` to allow non-GET requests. **Off by default.**       |

## Run

```bash
pope-tech-mcp           # stdio transport (what desktop clients expect)
# or
python -m pope_tech.mcp_server
```

## Tools

| Tool               | What it answers                                                        |
| ------------------ | --------------------------------------------------------------------- |
| `catalog`          | Self-describing: tools, queryable resources, issue categories.        |
| `list_orgs`        | Which orgs the token can reach (slug, name, plan).                    |
| `org_summary`      | One org: plan, website/user totals, issue totals.                     |
| `all_orgs_summary` | The above for every accessible org.                                   |
| `find_websites`    | Websites matching a name/URL fragment, worst-first, with metrics.     |
| `website_overview` | One site: details + latest-scan issue totals.                         |
| `aggregates`       | Dashboard issue totals per category, one org or all.                  |
| `query_resource`   | Generic list with field projection, `--where` filters, sort, top-N.   |
| `raw_request`      | Escape hatch to any API path (GET unless writable).                   |

## Safety

The server runs the client in `safe_mode` — read-only. The only tool that can
change state is `raw_request`, and it refuses any non-GET verb unless you start
the server with `POPE_TECH_MCP_WRITABLE=1`. Starting scans/crawls and generating
reports consume your org's quota, so writes are deliberately opt-in.

Errors from the API (auth, 404, validation, rate-limit) are returned to the model
as structured `{"error", "message", "status_code"}` objects rather than crashing
the tool call.

## Claude Desktop config

Add this to `claude_desktop_config.json`
(macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`,
Windows: `%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "pope-tech": {
      "command": "pope-tech-mcp",
      "env": {
        "POPE_TECH_API_KEY": "your-bearer-token"
      }
    }
  }
}
```

If `pope-tech-mcp` isn't on the client's PATH, use the interpreter form:

```json
{
  "mcpServers": {
    "pope-tech": {
      "command": "python",
      "args": ["-m", "pope_tech.mcp_server"],
      "env": {
        "POPE_TECH_API_KEY": "your-bearer-token",
        "POPE_TECH_DEFAULT_ORG": "san-francisco-state-university"
      }
    }
  }
}
```

## Cursor / Continue / Zed

Any client that speaks MCP over stdio works — point it at the `pope-tech-mcp`
command (or `python -m pope_tech.mcp_server`) with `POPE_TECH_API_KEY` in the
environment. Example questions once connected:

- "Which of my Pope Tech orgs has the most errors per page?"
- "Show the 10 worst websites across all orgs by errors per page."
- "What are the top contrast issues for www.sonoma.edu?"
