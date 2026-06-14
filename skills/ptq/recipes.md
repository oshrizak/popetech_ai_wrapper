# ptq recipes

Question → exact command. All read-only. Drop `--compact` for pretty JSON.
Replace `<slug>` with a fuzzy org (`sonoma`, `sfsu`, `east-bay`) or full slug.

## Snapshots & orientation

| Question | Command |
|---|---|
| What can this tool do? | `ptq catalog` |
| Which orgs can I see? | `ptq orgs` |
| How does every org look right now? | `ptq summary` |
| Snapshot of just one org | `ptq summary --org <slug>` |

## Finding & inspecting sites

| Question | Command |
|---|---|
| Find sites mentioning "library" in one org | `ptq find library --org <slug> --top 10` |
| Find a site across all orgs | `ptq find admissions` |
| Full picture of one site | `ptq site www.sonoma.edu --org sonoma` |
| Look up a site by its public_id | `ptq site <uuid> --org <slug>` |

## Rankings ("worst sites")

| Question | Command |
|---|---|
| Worst 10 sites by errors/page in an org | `ptq list websites --org <slug> --where 'scan_count>0' --sort latest_scan_errors_per_page --top 10 --fields name,full_url,latest_scan_errors_per_page` |
| Worst sites by errors/page across all orgs | `ptq list websites --all-orgs --where 'scan_count>0' --sort latest_scan_errors_per_page --top 25 --fields name,org,latest_scan_errors_per_page` |
| Sites above 5 errors/page | `ptq list websites --org <slug> --where 'latest_scan_errors_per_page>5' --sort latest_scan_errors_per_page --fields name,latest_scan_errors_per_page` |
| Worst by alerts/page | `ptq list websites --org <slug> --sort latest_scan_alerts_per_page --top 10 --fields name,latest_scan_alerts_per_page` |
| Biggest sites by page count | `ptq list websites --org <slug> --sort all_pages_count --top 10 --fields name,all_pages_count,active_pages_count` |
| Sites never scanned | `ptq list websites --org <slug> --where 'scan_count=0' --fields name,full_url` |
| Sites whose URL contains a string | `ptq list websites --org <slug> --where 'full_url~.edu' --top 20 --fields name,full_url` |

## Issue category totals

| Question | Command |
|---|---|
| Issue totals + worst items, one org | `ptq aggregates --org <slug> --top 5` |
| Totals across all orgs | `ptq aggregates --all-orgs --top 3` |
| Just the totals, no item breakdown | `ptq aggregates --org <slug> --top 0` |

## People

| Question | Command |
|---|---|
| Users in an org | `ptq users --org <slug>` |
| Just names/emails | `ptq users --org <slug> --fields name,email` |

## Other resources via `list`

`list` resources: `websites`, `scans`, `scan-containers`, `crawls`, `reports`, `users`.

| Question | Command |
|---|---|
| Recent scans in an org | `ptq list scans --org <slug> --top 10` |
| Crawls in an org | `ptq list crawls --org <slug> --top 10` |
| Reports in an org | `ptq list reports --org <slug> --top 10` |
| Active scan containers | `ptq list scan-containers --org <slug> --top 10` |

## Escape hatch (any endpoint)

| Question | Command |
|---|---|
| Groups in an org | `ptq raw GET /organizations/<full-slug>/groups` |
| Raw scans page | `ptq raw GET /organizations/<full-slug>/scans -q limit=10 -q page=1` |

> On Git Bash for Windows, prefix the path with `//` or use PowerShell.

## Filter (`--where`) cheatsheet

Operators: `=`  `!=`  `~` (contains)  `>`  `<`  `>=`  `<=`. Repeat `--where`
to AND multiple conditions. **Always quote** the expression.

```bash
--where 'scan_count>0'
--where 'latest_scan_errors_per_page>=10'
--where 'full_url~sonoma.edu'
--where 'group_name!=Archived'
```

## Field glossary

Website row fields (from `find` / `list websites` / `site`):

| Field | Meaning |
|---|---|
| `public_id` | UUID; pass to `site` for an exact lookup. |
| `name` | Display name (often the hostname). |
| `full_url` | Canonical URL. |
| `group_name` | Pope Tech group the site belongs to. |
| `scan_count` | Number of scans run (may arrive as a string). |
| `active_pages_count` | Pages currently in scope. |
| `all_pages_count` | All known pages. |
| `latest_scan_errors_per_page` | Avg errors/page, latest scan — the headline quality metric. |
| `latest_scan_alerts_per_page` | Avg alerts/page, latest scan. |

WAVE categories (in `aggregates` and `site.latest_scan`):

| Category | What it is |
|---|---|
| `errors` | Definite accessibility failures. |
| `contrast` | Color-contrast failures. |
| `alerts` | Likely issues needing human review. |
| `features` | Elements that *help* accessibility (e.g. alt text present). |
| `structural` | Structural/semantic elements (headings, regions). |
| `aria` | ARIA attributes in use. |

For each category, `aggregates`/`site` give a `total` and (when `--top > 0`) a
`top` list of the worst named items, each with `name`, `count`, `pages`.

## Turning results into deliverables

1. **Spreadsheet** — get rows, then build with the `xlsx` skill:
   ```bash
   python -m pope_tech.query_cli list websites --all-orgs --where 'scan_count>0' \
     --sort latest_scan_errors_per_page \
     --fields name,org,full_url,scan_count,latest_scan_errors_per_page,latest_scan_alerts_per_page \
     --compact > sites.json
   ```
   One row per site; columns = the `--fields` you chose (plus `org`).
2. **Word report / memo** — pull `summary` + `aggregates`, narrate the totals
   and the worst categories, then build with the `docx` skill.
3. **Slides** — same data, `pptx` skill; one slide per org from `summary`.
4. **Chat table** — render the trimmed JSON directly as a Markdown table.

Keep everything read-only unless the user explicitly asks to start a scan or
build a Pope Tech report (`--write`, consumes quota).
