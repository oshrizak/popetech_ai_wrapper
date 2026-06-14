"""Command-line interface for the Pope Tech API wrapper.

Defaults to read-only (``safe_mode``). Pass ``--write`` to allow state changes.

Examples::

    python -m pope_tech status
    python -m pope_tech me
    python -m pope_tech orgs
    python -m pope_tech websites --org san-francisco-state-university
    python -m pope_tech dashboard --org san-francisco-state-university

    # Escape hatch: call ANY endpoint directly.
    python -m pope_tech request GET /organizations/<slug>/groups
    python -m pope_tech request GET /organizations/<slug>/websites -q limit=5 -q page=1
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

from . import PopeTechClient, PopeTechError, __version__


def _print_json(value: Any) -> None:
    if hasattr(value, "status_code"):  # raw requests.Response
        print(f"<Response {value.status_code} {value.headers.get('Content-Type','')}>")
        return
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _parse_kv(pairs: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"Invalid key=value pair: {pair!r}")
        key, value = pair.split("=", 1)
        out[key] = value
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pope_tech",
        description="Pope Tech API command-line interface (read-only by default).",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--org", help="Organization slug (default for org-scoped commands).")
    p.add_argument("--token", help="Bearer token (default: POPE_TECH_API_KEY env).")
    p.add_argument(
        "--write",
        action="store_true",
        help="Allow state-changing requests (disables safe_mode).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="GET / service status")
    sub.add_parser("me", help="GET /me authenticated identity")
    sub.add_parser("orgs", help="List organizations this token can access")

    for name, help_text in [
        ("websites", "List websites"),
        ("scans", "List scans"),
        ("scan-containers", "List scan containers"),
        ("crawls", "List crawls"),
        ("reports", "List accessibility reports"),
        ("groups", "List groups"),
        ("users", "List users"),
        ("dashboard", "Org-wide aggregate results"),
        ("org", "Organization details"),
    ]:
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("-q", "--query", action="append", default=[], metavar="K=V")
        sp.add_argument("--all", action="store_true", help="Follow pagination.")

    req = sub.add_parser("request", help="Call ANY endpoint directly.")
    req.add_argument("method", help="HTTP method (GET, POST, PUT, DELETE, ...).")
    req.add_argument("path", help="Path, e.g. /organizations/<slug>/groups")
    req.add_argument("-q", "--query", action="append", default=[], metavar="K=V")
    req.add_argument(
        "-d", "--data", help="JSON request body (string) for write requests."
    )
    return p


def run(argv: List[str]) -> int:
    args = build_parser().parse_args(argv)
    client = PopeTechClient(
        token=args.token, default_org=args.org, safe_mode=not args.write
    )

    try:
        result = _dispatch(client, args)
    except PopeTechError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if getattr(exc, "errors", None):
            print(json.dumps(exc.errors, indent=2), file=sys.stderr)
        return 1
    finally:
        client.close()

    if result is not None:
        _print_json(result)
    return 0


def _dispatch(client: PopeTechClient, args: argparse.Namespace) -> Any:
    cmd = args.command
    query = _parse_kv(getattr(args, "query", []))

    if cmd == "status":
        return client.account.status()
    if cmd == "me":
        return client.account.me()
    if cmd == "orgs":
        return client.account.organizations()

    if cmd == "request":
        body = json.loads(args.data) if args.data else None
        return client.request(args.method, args.path, params=query, json=body)

    # Org-scoped list/detail commands.
    follow_all = getattr(args, "all", False)
    if cmd == "org":
        return client.organizations.get()
    if cmd == "dashboard":
        return client.dashboard.aggregates(**query)

    resource = {
        "websites": client.websites,
        "scans": client.scans,
        "scan-containers": client.scan_containers,
        "crawls": client.crawls,
        "reports": client.reports,
        "groups": client.groups,
        "users": client.users,
    }[cmd]

    if follow_all and hasattr(resource, "iterate"):
        return list(resource.iterate(**query))
    return resource.list(**query)


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
