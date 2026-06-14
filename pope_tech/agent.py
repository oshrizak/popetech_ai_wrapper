"""Agent facade: a query-oriented layer over :class:`PopeTechClient`.

This is the interface an assistant uses to answer open-ended questions about the
Pope Tech data. It adds the things that make ad-hoc querying efficient:

- fuzzy resolution of org / website names to slugs and public IDs,
- trimming of the very large aggregate payloads down to the numbers that matter,
- cross-organization fan-out (the token here spans several CSU campuses),
- a generic analytical list with field projection, filtering, sorting, top-N.

It is read-only by default (``safe_mode=True``); construct with
``writable=True`` only when a query is explicitly meant to change state.
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .client import PopeTechClient
from .projection import apply_filters, pluck, project, sort_items

# The six WAVE result categories Pope Tech reports.
CATEGORIES = ("errors", "contrast", "alerts", "features", "structural", "aria")

# Compact field set for website listings (keeps payloads small).
WEBSITE_FIELDS = (
    "public_id",
    "name",
    "full_url",
    "group_name",
    "scan_count",
    "active_pages_count",
    "all_pages_count",
    "latest_scan_errors_per_page",
    "latest_scan_alerts_per_page",
)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-", re.IGNORECASE)


def _unwrap(value: Any) -> Any:
    return value["data"] if isinstance(value, Mapping) and "data" in value else value


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class Agent:
    def __init__(
        self,
        *,
        token: Optional[str] = None,
        writable: bool = False,
        default_org: Optional[str] = None,
        client: Optional[PopeTechClient] = None,
    ) -> None:
        self.client = client or PopeTechClient(
            token=token, default_org=default_org, safe_mode=not writable
        )
        self._org_cache: Optional[List[Dict[str, Any]]] = None

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "Agent":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- organizations -----------------------------------------------------

    def orgs(self) -> List[Dict[str, Any]]:
        """Compact list of accessible organizations: slug, name, plan."""
        if self._org_cache is None:
            self._org_cache = self.client.account.organizations()
        return [
            {"slug": o.get("slug"), "name": o.get("name"), "plan": o.get("plan")}
            for o in self._org_cache
        ]

    def _org_slugs(self) -> List[str]:
        return [o["slug"] for o in self.orgs() if o.get("slug")]

    def resolve_org(self, text: Optional[str]) -> str:
        """Map a slug, name fragment, or abbreviation to an exact org slug."""
        if not text:
            if self.client.default_org:
                return self.client.default_org
            slugs = self._org_slugs()
            if len(slugs) == 1:
                return slugs[0]
            raise ValueError(
                f"Ambiguous org; specify one of: {', '.join(slugs)}"
            )
        needle = text.strip().lower()
        orgs = self.orgs()
        for o in orgs:  # exact slug
            if o["slug"] == needle:
                return o["slug"]
        for o in orgs:  # substring on slug or name
            if needle in o["slug"].lower() or needle in (o["name"] or "").lower():
                return o["slug"]
        # fuzzy fallback
        names = {o["slug"]: f"{o['slug']} {o['name']}".lower() for o in orgs}
        best = difflib.get_close_matches(needle, list(names.values()), n=1, cutoff=0.3)
        if best:
            for slug, blob in names.items():
                if blob == best[0]:
                    return slug
        raise ValueError(f"No organization matches {text!r}. Have: {self._org_slugs()}")

    def _orgs_for(self, org: Optional[str], all_orgs: bool) -> List[str]:
        return self._org_slugs() if all_orgs else [self.resolve_org(org)]

    # -- websites ----------------------------------------------------------

    def find_websites(
        self,
        query: Optional[str] = None,
        *,
        org: Optional[str] = None,
        all_orgs: bool = False,
        limit: Optional[int] = None,
        sort_by: str = "latest_scan_errors_per_page",
        fields: Sequence[str] = WEBSITE_FIELDS,
    ) -> List[Dict[str, Any]]:
        """Find websites by name/URL fragment, with key metrics attached.

        Searches one org (or all). With no ``query`` it returns everything.
        Results carry an ``org`` key and are sorted by ``sort_by`` descending.
        """
        needle = (query or "").strip().lower()
        rows: List[Dict[str, Any]] = []
        for slug in self._orgs_for(org, all_orgs):
            for site in self.client.websites.iterate(org=slug):
                hay = f"{site.get('name','')} {site.get('full_url','')}".lower()
                if needle and needle not in hay:
                    continue
                row = project(site, fields)
                row["org"] = slug
                rows.append(row)
        if sort_by:
            rows = sort_items(rows, sort_by, descending=True)
        if limit:
            rows = rows[:limit]
        return rows

    def resolve_website(self, name_or_id: str, org: str) -> Dict[str, Any]:
        """Return the website dict for a public_id or best name/URL match."""
        if _UUID_RE.match(name_or_id.strip()):
            return _unwrap(self.client.websites.get(name_or_id.strip(), org=org))
        matches = self.find_websites(name_or_id, org=org)
        if not matches:
            raise ValueError(f"No website matches {name_or_id!r} in {org}")
        return _unwrap(self.client.websites.get(matches[0]["public_id"], org=org))

    def website_overview(
        self, name_or_id: str, *, org: Optional[str] = None
    ) -> Dict[str, Any]:
        """Full picture of one website: core details + latest scan totals.

        Merges the list-view row (which carries scan/page-count metrics) with the
        detail endpoint (notes/config), since neither alone has everything.
        """
        slug = self.resolve_org(org)
        row: Dict[str, Any] = {}
        if _UUID_RE.match(name_or_id.strip()):
            site = _unwrap(self.client.websites.get(name_or_id.strip(), org=slug))
        else:
            matches = self.find_websites(name_or_id, org=slug)
            if not matches:
                raise ValueError(f"No website matches {name_or_id!r} in {slug}")
            row = matches[0]
            site = _unwrap(self.client.websites.get(row["public_id"], org=slug))
        wid = site.get("public_id") or row.get("public_id")

        def pick(key: str) -> Any:
            value = site.get(key)
            return value if value is not None else row.get(key)

        overview: Dict[str, Any] = {
            "org": slug,
            "public_id": wid,
            "name": pick("name"),
            "full_url": pick("full_url"),
            "group_name": pick("group_name"),
            "scan_count": pick("scan_count"),
            "active_pages_count": pick("active_pages_count"),
            "all_pages_count": pick("all_pages_count"),
            "notes": pick("notes"),
        }
        try:
            agg = self.client.websites.latest_scan_container_aggregates(wid, org=slug)
            overview["latest_scan"] = self.summarize_aggregates(agg)
        except Exception as exc:  # noqa: BLE001 - absence of scans is fine
            overview["latest_scan"] = {"error": str(exc)}
        return overview

    # -- aggregates --------------------------------------------------------

    @staticmethod
    def summarize_aggregates(raw: Any, *, top: int = 3) -> Dict[str, Any]:
        """Trim a giant aggregates payload to per-category totals (+ top items)."""
        results = pluck(raw, "data.results")
        if results is None:
            results = pluck(raw, "results", {})
        summary: Dict[str, Any] = {}
        if not isinstance(results, Mapping):
            return summary
        for cat, block in results.items():
            if not isinstance(block, Mapping):
                continue
            total = block.get("total")
            items = block.get("items")
            if total is None and not items:
                continue  # skip empty/placeholder blocks (e.g. "totals": null)
            entry: Dict[str, Any] = {"total": total}
            if top and isinstance(items, Mapping):
                ranked = sorted(
                    (i for i in items.values() if isinstance(i, Mapping)),
                    key=lambda i: _num(i.get("count")),
                    reverse=True,
                )[:top]
                entry["top"] = [
                    {
                        "name": i.get("name"),
                        "count": i.get("count"),
                        "pages": i.get("pages"),
                    }
                    for i in ranked
                ]
            summary[cat] = entry
        return summary

    def aggregates(
        self,
        *,
        org: Optional[str] = None,
        all_orgs: bool = False,
        top: int = 3,
        **filters: Any,
    ) -> Dict[str, Any]:
        """Dashboard result totals, trimmed. One org or all, keyed by slug."""
        out: Dict[str, Any] = {}
        for slug in self._orgs_for(org, all_orgs):
            raw = self.client.dashboard.aggregates(org=slug, **filters)
            out[slug] = self.summarize_aggregates(raw, top=top)
        return out if (all_orgs or len(out) != 1) else next(iter(out.values()))

    # -- per-org snapshot --------------------------------------------------

    def org_summary(self, org: Optional[str] = None) -> Dict[str, Any]:
        """One-glance org snapshot: plan, website/user totals, issue totals."""
        slug = self.resolve_org(org)
        detail = _unwrap(self.client.organizations.get(slug))
        snapshot: Dict[str, Any] = {
            "slug": slug,
            "name": detail.get("name"),
            "plan": detail.get("plan"),
            "websites": self._total(self.client.websites.list, slug),
            "users": self._total(self.client.users.list, slug),
        }
        snapshot["issues"] = self.summarize_aggregates(
            self.client.dashboard.aggregates(org=slug), top=0
        )
        return snapshot

    def all_orgs_summary(self) -> List[Dict[str, Any]]:
        return [self.org_summary(slug) for slug in self._org_slugs()]

    @staticmethod
    def _total(list_fn: Any, slug: str) -> Optional[int]:
        """Cheaply read meta.pagination.total without walking every page."""
        try:
            resp = list_fn(slug, limit=1)
        except TypeError:
            resp = list_fn(org=slug)
        if isinstance(resp, Mapping):
            total = pluck(resp, "meta.pagination.total")
            if total is not None:
                return total
            data = resp.get("data")
            if isinstance(data, list):
                return len(data)
        if isinstance(resp, list):
            return len(resp)
        return None

    # -- generic analytical list ------------------------------------------

    _LISTABLE = {
        "websites": "websites",
        "scans": "scans",
        "scan-containers": "scan_containers",
        "scan_containers": "scan_containers",
        "crawls": "crawls",
        "reports": "reports",
        "users": "users",
    }

    def query(
        self,
        resource: str,
        *,
        org: Optional[str] = None,
        all_orgs: bool = False,
        fields: Optional[Sequence[str]] = None,
        where: Sequence[str] = (),
        sort_by: Optional[str] = None,
        descending: bool = True,
        top: Optional[int] = None,
        paginate: bool = True,
        **params: Any,
    ) -> List[Dict[str, Any]]:
        """Generic list across a resource with projection/filter/sort/top-N.

        Example: ``query("websites", all_orgs=True, where=["scan_count>0"],
        sort_by="latest_scan_errors_per_page", top=10)``.
        """
        key = self._LISTABLE.get(resource)
        if not key:
            raise ValueError(
                f"Unknown resource {resource!r}. Choose from: "
                f"{sorted(set(self._LISTABLE))}"
            )
        ns = getattr(self.client, key)
        rows: List[Dict[str, Any]] = []
        for slug in self._orgs_for(org, all_orgs):
            if paginate and hasattr(ns, "iterate"):
                items = list(ns.iterate(org=slug, **params))
            else:
                items = _unwrap(ns.list(org=slug, **params)) or []
            for item in items:
                if isinstance(item, Mapping):
                    item = {**item, "org": slug}
                rows.append(item)
        if where:
            rows = apply_filters(rows, list(where))
        if sort_by:
            rows = sort_items(rows, sort_by, descending=descending)
        if top:
            rows = rows[:top]
        if fields:
            projected = list(fields)
            if "org" not in projected:
                projected = projected + ["org"]
            rows = [project(r, projected) for r in rows]
        return rows

    # -- escape hatch ------------------------------------------------------

    def raw(self, method: str, path: str, **kwargs: Any) -> Any:
        return self.client.request(method, path, **kwargs)
