"""Model Context Protocol (MCP) server for the Pope Tech API.

This exposes the query-oriented :class:`~pope_tech.agent.Agent` facade as MCP
tools, so an MCP-capable assistant (Claude Desktop, Cursor, Continue, etc.) can
inspect Pope Tech accessibility data natively instead of shelling out to the
``ptq`` CLI and parsing text.

Run it::

    pip install -e ".[mcp]"
    pope-tech-mcp                 # stdio transport (default)
    # or
    python -m pope_tech.mcp_server

Authentication is identical to the rest of the package: the token is read from
``POPE_TECH_API_KEY`` (a ``.env`` file is loaded automatically).

Safety
------
The server is **read-only by default**: the underlying client runs in
``safe_mode`` and only the ``raw_request`` tool can issue non-GET verbs -- and
only when ``POPE_TECH_MCP_WRITABLE=1`` is set in the environment. Starting
scans/crawls and generating reports consume your org's quota, so writes stay
opt-in and out of band.
"""

from __future__ import annotations

import functools
import os
import threading
from typing import Any, Callable, Dict, List, Optional, TypeVar

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - surfaced as a clear runtime error
    raise ImportError(
        "The MCP server needs the 'mcp' package (Python 3.10+). "
        "Install it with:  pip install -e \".[mcp]\"  "
        "or  pip install mcp"
    ) from exc

from .agent import CATEGORIES, Agent
from .exceptions import PopeTechError

mcp = FastMCP(
    "pope-tech",
    instructions=(
        "Query Pope Tech accessibility data (WAVE scan results) across one or "
        "more organizations. Read-only by default. Typical flow: call "
        "`list_orgs` to see accessible orgs, `find_websites` to locate a site, "
        "then `website_overview` or `aggregates` for issue counts. Use "
        "`query_resource` for filtered/sorted/top-N lists. Issue categories are: "
        "errors, contrast, alerts, features, structural, aria."
    ),
)

# --------------------------------------------------------------------------- #
# Lazily-constructed, shared Agent.
# --------------------------------------------------------------------------- #

_agent: Optional[Agent] = None
_agent_lock = threading.Lock()


def _writable() -> bool:
    return os.environ.get("POPE_TECH_MCP_WRITABLE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _get_agent() -> Agent:
    """Return the process-wide Agent, building it on first use."""
    global _agent
    if _agent is None:
        with _agent_lock:
            if _agent is None:
                _agent = Agent(
                    writable=_writable(),
                    default_org=os.environ.get("POPE_TECH_DEFAULT_ORG") or None,
                )
    return _agent


# --------------------------------------------------------------------------- #
# Error handling: turn wrapper exceptions into structured tool output instead
# of unhandled crashes, so the model gets a usable message.
# --------------------------------------------------------------------------- #

F = TypeVar("F", bound=Callable[..., Any])


def _safe(fn: F) -> F:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except PopeTechError as err:
            return {
                "error": type(err).__name__,
                "message": str(err),
                "status_code": getattr(err, "status_code", None),
            }
        except (ValueError, KeyError) as err:  # bad args / resolution misses
            return {"error": type(err).__name__, "message": str(err)}

    return wrapper  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #


@mcp.tool()
@_safe
def catalog() -> Dict[str, Any]:
    """Describe what this server can do: tools, queryable resources, categories.

    Call this first if you are unsure which tool to use.
    """
    return {
        "mode": "read-write" if _writable() else "read-only",
        "issue_categories": list(CATEGORIES),
        "queryable_resources": [
            "websites",
            "scans",
            "scan_containers",
            "crawls",
            "reports",
            "users",
        ],
        "tools": {
            "list_orgs": "Accessible organizations (slug, name, plan).",
            "org_summary": "One org snapshot: plan, website/user totals, issue totals.",
            "all_orgs_summary": "org_summary for every accessible org.",
            "find_websites": "Find websites by name/URL fragment, with key metrics.",
            "website_overview": "One website: details + latest-scan issue totals.",
            "aggregates": "Dashboard issue totals per category, one org or all.",
            "query_resource": "Generic list: project/filter/sort/top-N over a resource.",
            "raw_request": "Escape hatch to any API path (GET unless writable).",
        },
    }


@mcp.tool()
@_safe
def list_orgs() -> List[Dict[str, Any]]:
    """List the organizations the configured token can access (slug, name, plan)."""
    return _get_agent().orgs()


@mcp.tool()
@_safe
def org_summary(org: Optional[str] = None) -> Dict[str, Any]:
    """One-glance snapshot for a single org: plan, website/user counts, issue totals.

    Args:
        org: Org slug, name fragment, or abbreviation (fuzzy-matched). Omit to
            use the default org when the token only has one.
    """
    return _get_agent().org_summary(org)


@mcp.tool()
@_safe
def all_orgs_summary() -> List[Dict[str, Any]]:
    """Snapshot of every accessible org (plan, website/user counts, issue totals)."""
    return _get_agent().all_orgs_summary()


@mcp.tool()
@_safe
def find_websites(
    query: Optional[str] = None,
    org: Optional[str] = None,
    all_orgs: bool = False,
    limit: Optional[int] = 25,
) -> List[Dict[str, Any]]:
    """Find websites by name/URL fragment, with scan/page metrics attached.

    Results are sorted by ``latest_scan_errors_per_page`` (worst first) and each
    row carries its ``org`` slug.

    Args:
        query: Substring to match against site name or URL. Omit to list all.
        org: Limit to one org (fuzzy-matched). Ignored when ``all_orgs`` is true.
        all_orgs: Search across every accessible org.
        limit: Cap the number of rows returned (None for no cap).
    """
    return _get_agent().find_websites(
        query, org=org, all_orgs=all_orgs, limit=limit
    )


@mcp.tool()
@_safe
def website_overview(
    name_or_id: str, org: Optional[str] = None
) -> Dict[str, Any]:
    """Full picture of one website: core details plus latest-scan issue totals.

    Args:
        name_or_id: A website ``public_id`` (UUID) or a name/URL fragment to match.
        org: Org slug or fuzzy name. Omit to use the default org.
    """
    return _get_agent().website_overview(name_or_id, org=org)


@mcp.tool()
@_safe
def aggregates(
    org: Optional[str] = None,
    all_orgs: bool = False,
    top: int = 3,
) -> Dict[str, Any]:
    """Dashboard issue totals per category, trimmed to what matters.

    Args:
        org: One org (fuzzy-matched). Ignored when ``all_orgs`` is true.
        all_orgs: Aggregate across every accessible org (keyed by slug).
        top: Include this many top offending items per category (0 for totals only).
    """
    return _get_agent().aggregates(org=org, all_orgs=all_orgs, top=top)


@mcp.tool()
@_safe
def query_resource(
    resource: str,
    org: Optional[str] = None,
    all_orgs: bool = False,
    fields: Optional[List[str]] = None,
    where: Optional[List[str]] = None,
    sort_by: Optional[str] = None,
    descending: bool = True,
    top: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Generic analytical list over a resource: project, filter, sort, top-N.

    Args:
        resource: One of websites, scans, scan_containers, crawls, reports, users.
        org: One org (fuzzy-matched). Ignored when ``all_orgs`` is true.
        all_orgs: Run across every accessible org.
        fields: Dot-path fields to keep (e.g. ["name", "latest_scan_errors_per_page"]).
        where: Filter expressions like ["scan_count>0"]. Ops: = != ~ > < >= <=.
        sort_by: Dot-path to sort on.
        descending: Sort direction (default highest-first).
        top: Keep only the first N rows after sorting.
    """
    return _get_agent().query(
        resource,
        org=org,
        all_orgs=all_orgs,
        fields=fields,
        where=tuple(where or ()),
        sort_by=sort_by,
        descending=descending,
        top=top,
    )


@mcp.tool()
@_safe
def raw_request(
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
) -> Any:
    """Escape hatch: call any Pope Tech API path directly.

    GET is always allowed. Other verbs require the server to be started with
    ``POPE_TECH_MCP_WRITABLE=1`` and consume org quota -- use deliberately.

    Args:
        method: HTTP verb (GET, POST, ...).
        path: API path, e.g. "/organizations/<slug>/groups".
        params: Optional query-string parameters.
    """
    verb = method.strip().upper()
    if verb != "GET" and not _writable():
        return {
            "error": "ReadOnly",
            "message": (
                f"Refusing {verb} {path}: server is read-only. Restart with "
                "POPE_TECH_MCP_WRITABLE=1 to allow state changes."
            ),
        }
    return _get_agent().raw(verb, path, params=params)


def main() -> None:
    """Console-script entry point. Runs the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
