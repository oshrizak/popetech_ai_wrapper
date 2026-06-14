"""``ptq`` - the agent-facing query CLI.

Designed to answer one question per invocation and print compact, trimmed JSON
so an assistant can parse it cheaply. Read-only by default; ``--write`` opts in
to state changes.

    ptq orgs
    ptq summary                         # all orgs, one-glance snapshot
    ptq find sonoma                     # websites matching "sonoma" (all orgs)
    ptq site www.sonoma.edu --org sonoma
    ptq aggregates --all-orgs
    ptq list websites --all-orgs --where scan_count>0 \
        --sort latest_scan_errors_per_page --top 10 \
        --fields name,full_url,latest_scan_errors_per_page
    ptq raw GET /organizations/<slug>/groups
    ptq catalog                         # what this tool can do
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, List

from .agent import Agent, WEBSITE_FIELDS
from .exceptions import PopeTechError

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console is cp1252 by default
except Exception:  # pragma: no cover
    pass


def _emit(value: Any, *, compact: bool = False) -> None:
    if hasattr(value, "status_code"):  # raw requests.Response
        print(f"<Response {value.status_code} {value.headers.get('Content-Type','')}>")
        return
    if compact:
        print(json.dumps(value, ensure_ascii=False, default=str))
    else:
        print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _split_fields(value: str) -> List[str]:
    return [f.strip() for f in value.split(",") if f.strip()]


def _unmangle(path: str) -> str:
    """Undo Git-Bash-for-Windows rewriting a leading-slash arg into a file path.

    ``/organizations/x`` becomes ``C:/Program Files/Git/organizations/x`` under
    Git Bash; recover the original path so ``raw`` works in any shell.
    """
    if re.match(r"^[A-Za-z]:[\\/]", path) and "Git" in path and "/" in path:
        idx = path.rfind("/Git")
        if idx == -1:
            idx = path.find("Git")
            rest = path[idx + 3:]
        else:
            rest = path[idx + 4:]
        return rest or "/"
    return path


CATALOG = {
    "tool": "ptq - Pope Tech query CLI",
    "default_mode": "read-only (pass --write to allow changes)",
    "global_flags": {
        "--org": "org slug or fuzzy name fragment (e.g. 'sonoma')",
        "--all-orgs": "fan out across every accessible organization",
        "--write": "allow state-changing requests",
        "--compact": "single-line JSON output",
    },
    "commands": {
        "orgs": "list accessible organizations (slug, name, plan)",
        "summary": "per-org snapshot: plan, website/user totals, issue totals",
        "find <text>": "find websites by name/URL fragment + key metrics",
        "site <name|id>": "one website: details + latest-scan issue totals",
        "aggregates": "dashboard issue totals per category (--top N items)",
        "list <resource>": (
            "generic list with --fields/--where/--sort/--desc/--top; "
            "resources: websites, scans, scan-containers, crawls, reports, users"
        ),
        "users": "list users in an org",
        "raw <METHOD> <path>": "call any endpoint; -q k=v query, -d JSON body",
        "catalog": "print this capability catalog",
    },
    "where_operators": ["=", "!=", "~ (contains)", ">", "<", ">=", "<="],
    "examples": [
        "ptq summary",
        "ptq find sonoma",
        "ptq site www.sonoma.edu --org sonoma",
        "ptq aggregates --all-orgs --top 5",
        "ptq list websites --all-orgs --where scan_count>0 --sort latest_scan_errors_per_page --top 10 --fields name,latest_scan_errors_per_page",
    ],
}


def build_parser() -> argparse.ArgumentParser:
    # Shared flags, accepted *after* the command name (the natural position).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--org", help="Org slug or fuzzy name fragment.")
    common.add_argument("--all-orgs", action="store_true", help="Span all orgs.")
    common.add_argument("--write", action="store_true", help="Allow state changes.")
    common.add_argument("--compact", action="store_true", help="Single-line JSON.")
    common.add_argument("--token", help="Bearer token (default: env POPE_TECH_API_KEY).")

    p = argparse.ArgumentParser(
        prog="ptq", description="Pope Tech query CLI (read-only by default)."
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("orgs", parents=[common], help="List accessible organizations.")
    sub.add_parser("catalog", parents=[common], help="Print capability catalog.")
    sub.add_parser("summary", parents=[common], help="Per-org snapshot.")

    f = sub.add_parser("find", parents=[common], help="Find websites by name/URL.")
    f.add_argument("text", nargs="?", default=None)
    f.add_argument("--top", type=int, default=None)
    f.add_argument("--fields", type=_split_fields, default=list(WEBSITE_FIELDS))
    f.add_argument("--sort", default="latest_scan_errors_per_page")

    s = sub.add_parser("site", parents=[common], help="One website overview.")
    s.add_argument("name")

    a = sub.add_parser("aggregates", parents=[common], help="Dashboard issue totals.")
    a.add_argument("--top", type=int, default=3)
    a.add_argument("-q", "--query", action="append", default=[], metavar="K=V")

    lst = sub.add_parser("list", parents=[common], help="Generic analytical list.")
    lst.add_argument("resource")
    lst.add_argument("--fields", type=_split_fields, default=None)
    lst.add_argument("--where", action="append", default=[], metavar="EXPR")
    lst.add_argument("--sort", default=None)
    lst.add_argument("--desc", action="store_true", default=True)
    lst.add_argument("--asc", dest="desc", action="store_false")
    lst.add_argument("--top", type=int, default=None)
    lst.add_argument("-q", "--query", action="append", default=[], metavar="K=V")

    u = sub.add_parser("users", parents=[common], help="List users in an org.")
    u.add_argument("--fields", type=_split_fields, default=None)

    r = sub.add_parser("raw", parents=[common], help="Call any endpoint directly.")
    r.add_argument("method")
    r.add_argument("path")
    r.add_argument("-q", "--query", action="append", default=[], metavar="K=V")
    r.add_argument("-d", "--data", default=None, help="JSON body for writes.")
    return p


def _kv(pairs: List[str]) -> dict:
    out = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"Invalid k=v pair: {pair!r}")
        k, v = pair.split("=", 1)
        out[k] = v
    return out


def run(argv: List[str]) -> int:
    args = build_parser().parse_args(argv)
    agent = Agent(token=args.token, writable=args.write, default_org=args.org)
    try:
        result = _dispatch(agent, args)
    except (PopeTechError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        if getattr(exc, "errors", None):
            print(json.dumps(exc.errors, indent=2), file=sys.stderr)
        return 1
    finally:
        agent.close()
    _emit(result, compact=args.compact)
    return 0


def _dispatch(agent: Agent, args: argparse.Namespace) -> Any:
    cmd = args.command
    all_orgs = args.all_orgs

    if cmd == "catalog":
        return CATALOG
    if cmd == "orgs":
        return agent.orgs()
    if cmd == "summary":
        if args.org and not all_orgs:
            return agent.org_summary(args.org)
        return agent.all_orgs_summary()
    if cmd == "find":
        return agent.find_websites(
            args.text, org=args.org, all_orgs=all_orgs or not args.org,
            limit=args.top, sort_by=args.sort, fields=args.fields,
        )
    if cmd == "site":
        return agent.website_overview(args.name, org=args.org)
    if cmd == "aggregates":
        return agent.aggregates(
            org=args.org, all_orgs=all_orgs, top=args.top, **_kv(args.query)
        )
    if cmd == "users":
        return agent.query("users", org=args.org, all_orgs=all_orgs, fields=args.fields)
    if cmd == "list":
        return agent.query(
            args.resource, org=args.org, all_orgs=all_orgs,
            fields=args.fields, where=args.where, sort_by=args.sort,
            descending=args.desc, top=args.top, **_kv(args.query),
        )
    if cmd == "raw":
        body = json.loads(args.data) if args.data else None
        return agent.raw(
            args.method, _unmangle(args.path), params=_kv(args.query), json=body
        )
    raise SystemExit(f"unknown command {cmd}")


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
