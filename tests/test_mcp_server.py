"""Offline tests for the MCP server.

These never touch the network: the Agent is replaced with a stub. They cover
tool registration, happy-path pass-through, structured error handling, and the
read-only guard on ``raw_request``.
"""

from __future__ import annotations

import asyncio

import pytest

# The server depends on the optional `mcp` SDK (Python 3.10+). Skip cleanly if
# it isn't installed so the rest of the suite still runs.
mcp_server = pytest.importorskip(
    "pope_tech.mcp_server",
    reason="install the [mcp] extra to test the MCP server",
)

from pope_tech.exceptions import NotFoundError


class _StubAgent:
    """Stand-in for Agent that records calls and returns canned data."""

    def __init__(self):
        self.calls = []

    def orgs(self):
        self.calls.append(("orgs", (), {}))
        return [{"slug": "sfsu", "name": "SF State", "plan": "pro"}]

    def find_websites(self, query=None, *, org=None, all_orgs=False, limit=None):
        self.calls.append(("find_websites", (query,), {"org": org, "all_orgs": all_orgs, "limit": limit}))
        return [{"name": "www.sfsu.edu", "org": org or "sfsu"}]

    def website_overview(self, name_or_id, *, org=None):
        raise NotFoundError("no such website", status_code=404)

    def raw(self, method, path, **kwargs):
        self.calls.append(("raw", (method, path), kwargs))
        return {"ok": True, "method": method, "path": path}


@pytest.fixture
def stub(monkeypatch):
    agent = _StubAgent()
    monkeypatch.setattr(mcp_server, "_get_agent", lambda: agent)
    # default to read-only
    monkeypatch.delenv("POPE_TECH_MCP_WRITABLE", raising=False)
    return agent


def _registered_tool_names():
    mgr = getattr(mcp_server.mcp, "_tool_manager", None)
    if mgr is not None and hasattr(mgr, "list_tools"):
        return {t.name for t in mgr.list_tools()}
    return {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}


def test_expected_tools_registered():
    names = _registered_tool_names()
    expected = {
        "catalog",
        "list_orgs",
        "org_summary",
        "all_orgs_summary",
        "find_websites",
        "website_overview",
        "aggregates",
        "query_resource",
        "raw_request",
    }
    assert expected <= names


def test_list_orgs_passthrough(stub):
    assert mcp_server.list_orgs() == [
        {"slug": "sfsu", "name": "SF State", "plan": "pro"}
    ]


def test_find_websites_forwards_args(stub):
    rows = mcp_server.find_websites("sfsu", all_orgs=True, limit=5)
    assert rows == [{"name": "www.sfsu.edu", "org": "sfsu"}]
    name, args, kwargs = stub.calls[-1]
    assert name == "find_websites"
    assert kwargs == {"org": None, "all_orgs": True, "limit": 5}


def test_api_error_becomes_structured_dict(stub):
    out = mcp_server.website_overview("nope")
    assert out["error"] == "NotFoundError"
    assert out["status_code"] == 404
    assert "no such website" in out["message"]


def test_catalog_reports_read_only_by_default(stub):
    cat = mcp_server.catalog()
    assert cat["mode"] == "read-only"
    assert "errors" in cat["issue_categories"]
    assert "websites" in cat["queryable_resources"]


def test_raw_request_blocks_writes_when_read_only(stub):
    out = mcp_server.raw_request("POST", "/scans")
    assert out["error"] == "ReadOnly"
    # The stub's raw() must never have been called.
    assert all(c[0] != "raw" for c in stub.calls)


def test_raw_request_allows_get_when_read_only(stub):
    out = mcp_server.raw_request("get", "/organizations/sfsu/groups")
    assert out == {"ok": True, "method": "GET", "path": "/organizations/sfsu/groups"}


def test_raw_request_allows_writes_when_writable(stub, monkeypatch):
    monkeypatch.setenv("POPE_TECH_MCP_WRITABLE", "1")
    out = mcp_server.raw_request("POST", "/scans")
    assert out["method"] == "POST"
    assert any(c[0] == "raw" for c in stub.calls)
