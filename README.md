# Pope Tech Integrator

A complete Python wrapper **and** command-line interface for the
[Pope Tech](https://pope.tech) accessibility API (`https://api.pope.tech`).

It covers every documented resource — websites, pages, scans, scan containers,
crawls, reports, dashboard analytics, organizations, groups, users, and personal
access tokens — plus a low-level escape hatch so you can reach *any* endpoint,
documented or not.

## Features

- **Full coverage** of the documented API, grouped into intuitive namespaces
  (`client.websites`, `client.scans`, `client.dashboard`, ...).
- **Bearer auth** loaded automatically from `POPE_TECH_API_KEY` (via `.env`).
- **Auto-pagination** — `client.websites.iterate()` walks every page for you.
- **Typed exceptions** — `AuthenticationError`, `NotFoundError`,
  `ValidationError` (with field errors), `RateLimitError`, `ServerError`.
- **Retries with backoff** on `429` and `5xx`, honoring `Retry-After`.
- **`safe_mode`** — a read-only switch that blocks every state-changing request
  before it leaves your machine.
- **CLI** — `python -m pope_tech ...`, read-only by default.

## Two layers

1. **`pope_tech` wrapper** — the engine: typed client, every endpoint, retries,
   pagination, safe-mode. Use it when *building* something.
2. **`ptq` agent query CLI** (`pope_tech.agent` + `pope_tech.query_cli`) — a
   query cockpit built for answering open-ended questions fast: fuzzy
   name→ID resolution, payload trimming, cross-org fan-out, and in-tool
   filter/sort/top-N. This is the layer an assistant drives to answer questions.

## Agent query interface (`ptq`)

One question per command, compact trimmed JSON out. Read-only by default.

```bash
ptq catalog                                  # what this tool can do (self-describing)
ptq orgs                                      # accessible orgs: slug, name, plan
ptq summary                                   # per-org snapshot across ALL orgs
ptq find sonoma                               # websites matching "sonoma" + metrics
ptq site www.sonoma.edu --org sonoma          # one site: details + latest-scan totals
ptq aggregates --all-orgs --top 5             # issue totals per category, all orgs
ptq users --org sfsu                          # users in an org

# Generic analytical list: project + filter + sort + top-N, across one or all orgs.
ptq list websites --all-orgs \
    --where 'scan_count>0' \
    --sort latest_scan_errors_per_page --top 10 \
    --fields name,org,latest_scan_errors_per_page

# Escape hatch — any endpoint:
ptq raw GET /organizations/<slug>/groups
```

**Flags** (work after the command name): `--org <slug-or-fuzzy>`, `--all-orgs`,
`--fields a,b.c`, `--where 'path<op>val'` (ops: `= != ~ > < >= <=`), `--sort path`,
`--asc`/`--desc`, `--top N`, `--compact`, `--write`.

> **Quote `--where`** in bash/zsh: `>` and `<` are shell redirection. Use
> `--where 'scan_count>0'`. (PowerShell: also quote to be safe.)

Same power from Python:

```python
from pope_tech import Agent

with Agent() as a:                       # read-only; Agent(writable=True) to change state
    a.orgs()
    a.find_websites("sonoma", all_orgs=True, limit=10)
    a.website_overview("www.sonoma.edu", org="sonoma")
    a.aggregates(all_orgs=True, top=5)
    a.org_summary("sfsu")
    a.query("websites", all_orgs=True, where=["scan_count>0"],
            sort_by="latest_scan_errors_per_page", top=10,
            fields=["name", "latest_scan_errors_per_page"])
```

## Install

```bash
pip install -r requirements.txt      # requests, python-dotenv
# or, to get the `pope-tech` command on your PATH:
pip install -e .
```

## Authenticate

Put your token in a `.env` file in the project root (see `.env.example`):

```
POPE_TECH_API_KEY="your-bearer-token"
```

It's loaded automatically. You can also pass `token=...` to `PopeTechClient`,
or set the env var another way.

## Quick start (Python)

```python
from pope_tech import PopeTechClient

client = PopeTechClient(default_org="san-francisco-state-university")

# Who am I, and which orgs can I reach?
print(client.account.me())
for org in client.account.organizations():
    print(org["slug"], "-", org["name"])

# List websites (one page) ...
page = client.websites.list(limit=10)

# ... or iterate across every page automatically.
for site in client.websites.iterate():
    print(site["name"], site["full_url"])

# Dashboard totals for the whole org.
print(client.dashboard.aggregates())

# Drill into one website's latest scan.
wid = page["data"][0]["public_id"]
container = client.websites.latest_scan_container(wid)
print(client.websites.latest_scan_container_aggregates(wid))
```

### Reach any endpoint directly

```python
# Generic request — works for undocumented endpoints too.
client.request("GET", "/organizations/<slug>/groups")
client.request("GET", "/organizations/<slug>/websites", params={"limit": 5})

# Generic pagination over any list endpoint.
for item in client.paginate("/organizations/<slug>/users"):
    ...

# Binary downloads (PDF/CSV reports) come back as a raw response.
resp = client.reports.download(report_id)          # raw=True by default
open("report.pdf", "wb").write(resp.content)
```

### Read-only mode

```python
client = PopeTechClient(safe_mode=True)   # or client.safe_mode = True
client.websites.list()                    # OK
client.websites.create("https://x.edu")   # raises SafeModeError, no network call
```

## Command-line interface

Read-only by default; pass `--write` to allow state changes.

```bash
python -m pope_tech status
python -m pope_tech me
python -m pope_tech orgs
python -m pope_tech --org san-francisco-state-university websites -q limit=5
python -m pope_tech --org san-francisco-state-university websites --all   # all pages
python -m pope_tech --org san-francisco-state-university dashboard

# Escape hatch — any method, any path:
python -m pope_tech request GET /organizations/<slug>/groups
python -m pope_tech request GET /organizations/<slug>/scans -q limit=10 -q page=1
```

> On **Git Bash for Windows**, a path argument beginning with `/` gets rewritten
> into a Windows path. Use **PowerShell**/`cmd`, or prefix with `//`, for the
> `request` command. The Python API is unaffected.

## Resource → method map

| Namespace | Methods |
|---|---|
| `client.account` | `status`, `me`, `organizations`, `wave_documentation` |
| `client.organizations` | `get` |
| `client.groups` | `list` |
| `client.users` | `list`, `iterate`, `get`, `create`, `update`, `delete` |
| `client.websites` | `list`, `iterate`, `get`, `create`, `update`, `delete`, `list_pages`, `iterate_pages`, `add_pages`, `delete_pages`, `latest_scan_container`, `latest_scan_container_aggregates`, `start_scan` |
| `client.scans` | `list`, `iterate`, `get`, `pages`, `iterate_pages`, `page_detail`, `accessibility_report`, `start`, `cancel` |
| `client.scan_containers` | `list`, `iterate`, `active`, `get`, `aggregates`, `cancel`, `cancel_active`, `start_group_scan` |
| `client.crawls` | `list`, `iterate`, `get`, `start` |
| `client.reports` | `list`, `iterate`, `create`, `download`, `rebuild`, `delete` |
| `client.dashboard` | `aggregates` |
| `client.tokens` | `info`, `create`, `revoke_all` |

Every org-scoped method takes an `org="slug"` argument that defaults to
`client.default_org`.

## Verifying endpoints

`verify_endpoints.py` exercises **only non-destructive (read-only) endpoints**
against the live API, in `safe_mode`, across every org your token can access:

```bash
python verify_endpoints.py
```

Last run: **39 OK, 4 skipped, 0 failed** across all three CSU organizations.
The skips are two endpoints that return `404` on the live API despite appearing
in the docs (`GET /documentation` and `GET .../personal-access-tokens`).

## Tests

Offline unit tests (no network) cover transport, error mapping, pagination, and
the safe-mode guard:

```bash
python -m pytest -q     # 18 passed
```

## Safety notes

- The wrapper never triggers scans, crawls, creates, updates, deletes, or
  cancels unless you explicitly call those methods with `safe_mode` off.
- Starting scans/crawls and generating reports consume your org's scan/report
  quota — use deliberately.
- Keep `.env` out of version control (it's git-ignored here).

## Project layout

```
pope_tech/
  __init__.py        # exports: PopeTechClient, Agent, exceptions
  http.py            # Transport: auth, retries, pagination, request()
  resources.py       # resource namespaces (one class per family)
  client.py          # PopeTechClient wiring it together
  cli.py             # low-level command-line interface (pope-tech)
  exceptions.py      # exception hierarchy
  projection.py      # dot-path pluck / project / filter / sort
  agent.py           # Agent facade: fuzzy resolve, trim, fan-out, query()
  query_cli.py       # ptq - the agent query CLI
verify_endpoints.py  # live read-only endpoint verification
tests/
  test_smoke.py      # offline tests: transport, errors, pagination, safe-mode
  test_agent.py      # offline tests: projection + Agent facade
```
