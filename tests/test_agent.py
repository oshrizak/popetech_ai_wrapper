"""Offline tests for the projection helpers and the Agent facade.

The Agent is tested against a hand-built fake client, so no network is needed.
"""

from __future__ import annotations

import pytest

from pope_tech.agent import Agent
from pope_tech.projection import (
    apply_filters,
    match_condition,
    parse_condition,
    pluck,
    project,
    sort_items,
)


# -- projection ------------------------------------------------------------


def test_pluck_nested_and_index():
    obj = {"a": {"b": [{"c": 7}]}}
    assert pluck(obj, "a.b.0.c") == 7
    assert pluck(obj, "a.b.5.c", default="x") == "x"
    assert pluck(obj, "missing", default=None) is None


def test_project_keeps_only_requested():
    item = {"name": "x", "url": "u", "extra": 1}
    assert project(item, ["name", "url"]) == {"name": "x", "url": "u"}
    assert project(item, None) == item


@pytest.mark.parametrize(
    "expr,parts",
    [
        ("scan_count>0", ("scan_count", ">", "0")),
        ("name~edu", ("name", "~", "edu")),
        ("plan=professional", ("plan", "=", "professional")),
        ("errors>=10", ("errors", ">=", "10")),
    ],
)
def test_parse_condition(expr, parts):
    assert parse_condition(expr) == parts


def test_match_condition_numeric_and_text():
    item = {"scan_count": "9", "name": "www.sonoma.edu"}
    assert match_condition(item, "scan_count", ">", "0")
    assert not match_condition(item, "scan_count", "<", "0")
    assert match_condition(item, "name", "~", "SONOMA")  # case-insensitive
    assert match_condition(item, "name", "=", "www.sonoma.edu")
    assert not match_condition(item, "missing", ">", "0")


def test_apply_filters_and():
    items = [{"n": 5, "t": "a"}, {"n": 1, "t": "a"}, {"n": 9, "t": "b"}]
    out = apply_filters(items, ["n>2", "t=a"])
    assert out == [{"n": 5, "t": "a"}]


def test_sort_items_numeric_desc_missing_last():
    items = [{"v": 3}, {"v": 10}, {"no": 1}, {"v": 1}]
    out = sort_items(items, "v", descending=True)
    assert [i.get("v") for i in out] == [10, 3, 1, None]


# -- fake client -----------------------------------------------------------


class _Ns:
    """A resource namespace stub backed by canned rows."""

    def __init__(self, rows):
        self._rows = rows

    def iterate(self, org=None, **params):
        return iter(self._rows.get(org, []))

    def list(self, org=None, limit=None, **params):
        rows = self._rows.get(org, [])
        return {"data": rows[: (limit or len(rows))],
                "meta": {"pagination": {"total": len(rows)}}}

    def get(self, public_id, org=None):
        for r in self._rows.get(org, []):
            if r.get("public_id") == public_id:
                return {"data": r}
        return {"data": {"public_id": public_id}}

    def latest_scan_container_aggregates(self, public_id, org=None):
        return {"data": {"results": {"errors": {"total": 5},
                                     "aria": {"total": 10, "items": {
                                         "x": {"name": "X", "count": 8, "pages": 2},
                                         "y": {"name": "Y", "count": 2, "pages": 1}}}}}}


class _AccountNs:
    def organizations(self):
        return [
            {"slug": "org-a", "name": "Org A University", "plan": "pro"},
            {"slug": "org-b", "name": "Org B College", "plan": "pro"},
        ]


class _OrgsNs:
    def get(self, slug):
        return {"data": {"name": f"Org {slug}", "plan": "pro"}}


class _DashboardNs:
    def aggregates(self, org=None, **kw):
        return {"data": {"results": {"errors": {"total": 100},
                                     "alerts": {"total": 50}}}}


class FakeClient:
    def __init__(self):
        sites = {
            "org-a": [
                {"public_id": "11111111-1111-1111-1111-111111111111",
                 "name": "www.a.edu", "full_url": "https://www.a.edu",
                 "scan_count": "3", "latest_scan_errors_per_page": 5},
                {"public_id": "22222222-2222-2222-2222-222222222222",
                 "name": "lib.a.edu", "full_url": "https://lib.a.edu",
                 "scan_count": "0", "latest_scan_errors_per_page": 20},
            ],
            "org-b": [
                {"public_id": "33333333-3333-3333-3333-333333333333",
                 "name": "www.b.edu", "full_url": "https://www.b.edu",
                 "scan_count": "7", "latest_scan_errors_per_page": 12},
            ],
        }
        users = {"org-a": [{"name": "U1"}, {"name": "U2"}], "org-b": [{"name": "U3"}]}
        self.websites = _Ns(sites)
        self.users = _Ns(users)
        self.account = _AccountNs()
        self.organizations = _OrgsNs()
        self.dashboard = _DashboardNs()
        self.default_org = None

    def close(self):
        pass


@pytest.fixture
def agent():
    return Agent(client=FakeClient())


# -- agent -----------------------------------------------------------------


def test_orgs_compact(agent):
    assert agent.orgs() == [
        {"slug": "org-a", "name": "Org A University", "plan": "pro"},
        {"slug": "org-b", "name": "Org B College", "plan": "pro"},
    ]


@pytest.mark.parametrize("text,expected", [
    ("org-a", "org-a"),
    ("Org B", "org-b"),
    ("college", "org-b"),
    ("university", "org-a"),
])
def test_resolve_org_fuzzy(agent, text, expected):
    assert agent.resolve_org(text) == expected


def test_resolve_org_unknown_raises(agent):
    with pytest.raises(ValueError):
        agent.resolve_org("nonexistent-place")


def test_find_websites_all_orgs_sorted(agent):
    rows = agent.find_websites(all_orgs=True)
    # sorted by latest_scan_errors_per_page desc: 20, 12, 5
    assert [r["latest_scan_errors_per_page"] for r in rows] == [20, 12, 5]
    assert {r["org"] for r in rows} == {"org-a", "org-b"}


def test_find_websites_query_filters(agent):
    rows = agent.find_websites("lib", all_orgs=True)
    assert len(rows) == 1 and rows[0]["name"] == "lib.a.edu"


def test_query_where_sort_top(agent):
    rows = agent.query(
        "websites", all_orgs=True, where=["scan_count>0"],
        sort_by="latest_scan_errors_per_page", top=1,
        fields=["name", "latest_scan_errors_per_page"],
    )
    assert len(rows) == 1
    assert rows[0]["name"] == "www.b.edu"  # 12 beats 5; lib (0 scans) filtered out
    assert "org" in rows[0]  # org always included


def test_summarize_aggregates_trims_and_ranks():
    raw = {"data": {"results": {
        "errors": {"total": 5},
        "aria": {"total": 10, "items": {
            "x": {"name": "X", "count": 8, "pages": 2},
            "y": {"name": "Y", "count": 2, "pages": 1}}},
        "totals": {"total": None},
    }}}
    out = Agent.summarize_aggregates(raw, top=1)
    assert out["errors"] == {"total": 5}
    assert out["aria"]["total"] == 10
    assert out["aria"]["top"] == [{"name": "X", "count": 8, "pages": 2}]
    assert "totals" not in out  # placeholder dropped


def test_org_summary_counts(agent):
    snap = agent.org_summary("org-a")
    assert snap["websites"] == 2
    assert snap["users"] == 2
    assert snap["issues"]["errors"]["total"] == 100


def test_website_overview_merges_metrics(agent):
    ov = agent.website_overview("www.a.edu", org="org-a")
    assert ov["name"] == "www.a.edu"
    assert ov["scan_count"] == "3"
    assert ov["latest_scan"]["errors"]["total"] == 5
