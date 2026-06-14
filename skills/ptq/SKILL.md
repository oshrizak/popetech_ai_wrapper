---
name: ptq
description: Query and format Pope Tech accessibility web-scan data via the ptq CLI (pope_tech.query_cli). Use whenever Daniel asks about Pope Tech scans, WAVE accessibility results, websites, pages, scans, crawls, reports, issue totals (errors, contrast, alerts, ARIA, features, structural), per-org or cross-org snapshots, worst sites, errors-per-page rankings, or wants a Pope Tech report or spreadsheet. Trigger terms include pope tech, ptq, accessibility scan, WAVE, errors per page, scan results, and org names like SF State, Sonoma, and CSU East Bay. Read-only by default.
---

# ptq — Pope Tech query interface

`ptq` answers one question per invocation against the Pope Tech accessibility
API and prints compact, trimmed JSON. It is the layer to drive for **reading and
formatting** scan data. It is **read-only by default**; state changes require an
explicit `--write` flag and consume scan/report quota.

This skill lives in the `PopeTechIntegrator` project, which wraps the
[Pope Tech](https://pope.tech) API (`https://api.pope.tech`). The token is loaded
automatically from the project's `.env` (`POPE_TECH_API_KEY`).

## How to run it

Run from the **project root** (so `.env` is picked up). Two equivalent forms:

```bash
ptq <command> [args] [flags]              # after `pip install -e .`
python -m pope_tech.query_cli <command>   # always works, no install needed
```

When **you (the assistant)** run this via the workspace shell, use the
module form from the project mount and cap the timeout — cross-org commands fan
out over many API pages and can take 20–40s:

```bash
cd <project-root> && python3 -m pope_tech.query_cli <command> --compact
```

One-time setup to put `ptq` on the user's PATH (their terminal; not required for
the module form):

```bash
.venv\Scripts\activate    # Windows PowerShell
pip install -e .
```

## Golden rules

1. **Read-only by default.** Never add `--write` unless the user explicitly asks
   to change state (create/update/delete, start a scan/crawl, build a report).
   Writes consume quota — confirm first.
2. **Always quote `--where`.** `>` and `<` are shell redirection in bash/zsh.
   Use `--where 'scan_count>0'`. Quote in PowerShell too, to be safe.
3. **Start narrow.** Prefer `--org <slug>` over `--all-orgs` for speed; only fan
   out when the question is genuinely cross-org.
4. **`--compact`** for single-line JSON when you'll parse it yourself.
5. **`list` auto-paginates** (walks every page of the resource). It is the
   powerful path but also the slow/large one — always pair with `--top` and
   `--fields` to keep payloads small.

## Choosing the command

| The user wants… | Command |
|---|---|
| What can this tool do? | `ptq catalog` |
| Which orgs can I reach? | `ptq orgs` |
| One-glance snapshot of every org | `ptq summary` |
| Snapshot of one org | `ptq summary --org <slug>` |
| Find sites by name/URL fragment | `ptq find <text> [--org <slug>]` |
| Everything about one site | `ptq site <name\|id> --org <slug>` |
| Issue totals per category (+ worst items) | `ptq aggregates [--org <slug>] [--top N]` |
| Ranked / filtered list of any resource | `ptq list <resource> --where … --sort … --top …` |
| Users in an org | `ptq users --org <slug>` |
| Any endpoint, documented or not | `ptq raw <METHOD> <path>` |

## Command reference (verified examples)

```bash
# Orientation
ptq catalog
ptq orgs

# Snapshots — issue totals, website/user counts
ptq summary                                   # all orgs
ptq summary --org sonoma                       # one org

# Find websites (no --org ⇒ searches ALL orgs); sorted by errors/page desc
ptq find library --org sonoma --top 5
ptq find sonoma                                # fuzzy, across all orgs

# One website: details + trimmed latest-scan totals
ptq site library.sonoma.edu --org sonoma
ptq site adc1e085-194f-428d-a2ef-7c94ef33088b --org sonoma   # by public_id

# Dashboard aggregates: per-category totals; --top adds the worst N named items
ptq aggregates --org east-bay --top 5
ptq aggregates --all-orgs --top 3

# Generic analytical list — the workhorse
ptq list websites --org sonoma \
    --where 'scan_count>0' \
    --sort latest_scan_errors_per_page --top 10 \
    --fields name,full_url,latest_scan_errors_per_page
ptq list websites --all-orgs --where 'latest_scan_errors_per_page>5' --top 20
ptq users --org sfsu

# Escape hatch — any endpoint
ptq raw GET /organizations/sonoma-state-university/groups
ptq raw GET /organizations/sonoma-state-university/scans -q limit=10 -q page=1
```

## Flags

Place flags **after** the command name.

| Flag | Meaning |
|---|---|
| `--org <slug-or-fuzzy>` | Target one org. Accepts a slug, a name fragment, or an abbreviation (`sonoma`, `sfsu`, `east-bay`). |
| `--all-orgs` | Fan out across every accessible org. |
| `--write` | Allow state-changing requests (off by default). |
| `--compact` | Single-line JSON output. |
| `--token <t>` | Override the bearer token (default: `POPE_TECH_API_KEY`). |
| `--fields a,b.c` | Project only these dot-path fields (commas separate; `org` is always kept). |
| `--where 'path<op>val'` | Filter (repeatable). Ops: `=  !=  ~ (contains)  >  <  >=  <=`. |
| `--sort path` | Sort by a dot-path field. |
| `--desc` / `--asc` | Sort direction (default `--desc`). |
| `--top N` | Keep the first N rows. |
| `-q k=v` | Query-string param (repeatable; `aggregates`, `list`, `raw`). |
| `-d '<json>'` | JSON request body for `raw` writes. |

## Field & category vocabulary

The six WAVE result categories Pope Tech reports:
**`errors`**, **`contrast`**, **`alerts`**, **`features`**, **`structural`**, **`aria`**.
`errors` and `contrast` are genuine accessibility failures; `alerts` are
potential issues needing human review; `features`/`structural`/`aria` are largely
element counts (context, not defects).

Default website fields (used by `find`; available to `list`/`site`):
`public_id`, `name`, `full_url`, `group_name`, `scan_count`,
`active_pages_count`, `all_pages_count`, `latest_scan_errors_per_page`,
`latest_scan_alerts_per_page`.

`list` resources: `websites`, `scans`, `scan-containers`, `crawls`, `reports`,
`users`.

## Output shape notes

- Every `find`/`list` row gets an added **`org`** key (the slug it came from).
- Some count fields arrive as **strings** (`"scan_count": "10"`), but numeric
  `--where`/`--sort` still work — values are coerced. Don't assume types when
  post-processing.
- `aggregates` and `site`'s `latest_scan` are **trimmed**: a `total` per
  category, plus a `top` list of the worst named items when `--top > 0`.
- `summary` returns a list (all orgs) or a single object (`--org`).

## Accessible organizations

| Fuzzy | Slug |
|---|---|
| `sfsu`, `san francisco` | `san-francisco-state-university` |
| `sonoma` | `sonoma-state-university` |
| `east-bay`, `east bay` | `california-state-university-east-bay` |

All three are on the `professional` plan. The token spans all three.

## Safety & quota

- Read-only is the default. `--write` is required for `create`/`update`/`delete`
  and for starting scans/crawls or building reports.
- Starting scans/crawls and generating reports **consume the org's quota** — only
  do so on explicit instruction, and confirm the org first.
- Keep `.env` out of version control (already git-ignored).

## Gotchas

- **`--where` quoting** (see Golden rules) — the most common mistake.
- **Git Bash on Windows** rewrites a `raw` path beginning with `/` into a
  Windows file path. Use PowerShell/`cmd`, or prefix with `//`
  (`ptq raw GET //organizations/...`). The CLI also tries to auto-unmangle it.
- **`list` cost** — it walks every page of the resource across the chosen orgs.
  Scope with `--org` and bound with `--top`/`--fields`.
- **Slow cross-org commands** — `summary`, `aggregates --all-orgs`, and
  `find` with no `--org` hit several APIs; allow 20–40s.

## Formatting results into reports

This project exists to **access and format** Pope Tech reports. After querying:

- For a quick comparison in chat, render the trimmed JSON as a Markdown table.
- For a deliverable spreadsheet, pipe `list … --compact` JSON into the **xlsx**
  skill (one row per site/scan, columns from `--fields`).
- For a written report or memo, use the **docx** skill; for slides, **pptx**.
- See `recipes.md` (next to this file) for question→command recipes, a fuller
  field glossary, and report-building patterns.
