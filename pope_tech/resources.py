"""Resource namespaces for the Pope Tech API.

Each class groups the endpoints for one resource family and is exposed as an
attribute on :class:`pope_tech.client.PopeTechClient` (e.g. ``client.websites``).

Most endpoints are organization-scoped. Methods accept an ``org`` argument that
falls back to the client's ``default_org`` when omitted, so you can set the org
once and stop repeating it.

Read-only methods are plain GETs and are safe to call anytime. State-changing
methods (create/update/delete/start/cancel) are blocked when the client is in
``safe_mode``.
"""

from __future__ import annotations

from typing import Any, Iterator, List, Mapping, Optional

from .exceptions import PopeTechError
from .http import Transport


def _enc(value: str) -> str:
    """Encode a single path segment."""
    from urllib.parse import quote

    return quote(str(value), safe="")


class _Resource:
    """Base class holding the transport and org-resolution helper."""

    def __init__(self, client: "Any") -> None:
        self._client = client
        self._http: Transport = client.http

    def _org(self, org: Optional[str]) -> str:
        slug = org or self._client.default_org
        if not slug:
            raise PopeTechError(
                "No organization specified. Pass org='your-org-slug' or set "
                "client.default_org. Use client.account.organizations() to list "
                "the slugs your token can access."
            )
        return _enc(slug)


# --------------------------------------------------------------------------
# Account / global
# --------------------------------------------------------------------------


class Account(_Resource):
    """Token identity and service-level endpoints."""

    def status(self) -> Any:
        """GET / - service name, version, environment, maintenance flag."""
        return self._http.get("/")

    def me(self) -> Any:
        """GET /me - the authenticated user, including accessible organizations."""
        return self._http.get("/me")

    def organizations(self) -> List[Mapping[str, Any]]:
        """Convenience: the list of organizations this token can access.

        Derived from ``/me`` (there is no standalone list-orgs endpoint). Each
        item is normalized to include at least ``slug`` and ``name``.
        """
        me = self.me()
        data = me.get("data", me) if isinstance(me, Mapping) else {}
        orgs = data.get("organizations") if isinstance(data, Mapping) else None
        result: List[Mapping[str, Any]] = []
        if isinstance(orgs, Mapping):
            for slug, value in orgs.items():
                entry = dict(value) if isinstance(value, Mapping) else {"name": value}
                entry.setdefault("slug", slug)
                result.append(entry)
        elif isinstance(orgs, list):
            result = [o for o in orgs if isinstance(o, Mapping)]
        return result

    def wave_documentation(self) -> Any:
        """GET /documentation - WAVE accessibility check reference data."""
        return self._http.get("/documentation")


class Organizations(_Resource):
    """Organization-level metadata."""

    def get(self, org: Optional[str] = None) -> Any:
        """GET /organizations/{org} - name, slug, limits, status."""
        return self._http.get(f"/organizations/{self._org(org)}")


class Groups(_Resource):
    """Website groups within an organization."""

    def list(self, org: Optional[str] = None) -> Any:
        """GET /organizations/{org}/groups."""
        return self._http.get(f"/organizations/{self._org(org)}/groups")


class Users(_Resource):
    """Organization users."""

    def list(self, org: Optional[str] = None, **params: Any) -> Any:
        """GET /organizations/{org}/users."""
        return self._http.get(f"/organizations/{self._org(org)}/users", params=params)

    def iterate(self, org: Optional[str] = None, **params: Any) -> Iterator[Any]:
        """Yield every user across all pages."""
        return self._http.paginate(
            f"/organizations/{self._org(org)}/users", params=params
        )

    def get(self, public_id: str, org: Optional[str] = None) -> Any:
        """GET /organizations/{org}/users/{public_id}."""
        return self._http.get(
            f"/organizations/{self._org(org)}/users/{_enc(public_id)}"
        )

    def create(
        self,
        email: str,
        *,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        role_id: Optional[int] = None,
        org: Optional[str] = None,
    ) -> Any:
        """POST /organizations/{org}/users - invite/create a user."""
        body = {
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "role_id": role_id,
        }
        return self._http.post(
            f"/organizations/{self._org(org)}/users",
            json={k: v for k, v in body.items() if v is not None},
        )

    def update(self, public_id: str, org: Optional[str] = None, **fields: Any) -> Any:
        """PUT /organizations/{org}/users/{public_id}."""
        return self._http.put(
            f"/organizations/{self._org(org)}/users/{_enc(public_id)}", json=fields
        )

    def delete(self, public_id: str, org: Optional[str] = None) -> Any:
        """DELETE /organizations/{org}/users/{public_id}."""
        return self._http.delete(
            f"/organizations/{self._org(org)}/users/{_enc(public_id)}"
        )


# --------------------------------------------------------------------------
# Websites & pages
# --------------------------------------------------------------------------


class Websites(_Resource):
    """Websites and their pages."""

    def _base(self, org: Optional[str]) -> str:
        return f"/organizations/{self._org(org)}/websites"

    def list(
        self,
        org: Optional[str] = None,
        *,
        group_filter: Optional[str] = None,
        search: Optional[str] = None,
        zero_pages: Optional[bool] = None,
        zero_scans: Optional[bool] = None,
        sort_by: Optional[str] = None,
        sort_direction: Optional[str] = None,
        page: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Any:
        """GET /organizations/{org}/websites."""
        params = {
            "group_filter": group_filter,
            "search": search,
            "zero_pages": zero_pages,
            "zero_scans": zero_scans,
            "sort_by": sort_by,
            "sort_direction": sort_direction,
            "page": page,
            "limit": limit,
        }
        return self._http.get(self._base(org), params=params)

    def iterate(self, org: Optional[str] = None, **params: Any) -> Iterator[Any]:
        """Yield every website across all pages."""
        return self._http.paginate(self._base(org), params=params)

    def get(self, public_id: str, org: Optional[str] = None) -> Any:
        """GET /organizations/{org}/websites/{public_id}."""
        return self._http.get(f"{self._base(org)}/{_enc(public_id)}")

    def create(
        self,
        full_url: str,
        *,
        name: Optional[str] = None,
        notes: Optional[str] = None,
        skip_url_redirect: Optional[bool] = None,
        crawl_options: Optional[Mapping[str, Any]] = None,
        scan_options: Optional[Mapping[str, Any]] = None,
        authentication_options: Optional[Mapping[str, Any]] = None,
        allow_duplicates: Optional[bool] = None,
        org: Optional[str] = None,
    ) -> Any:
        """POST /organizations/{org}/websites - register a website."""
        body = {
            "full_url": full_url,
            "name": name,
            "notes": notes,
            "skip_url_redirect": skip_url_redirect,
            "crawl_options": crawl_options,
            "scan_options": scan_options,
            "authentication_options": authentication_options,
            "allow_duplicates": allow_duplicates,
        }
        return self._http.post(
            self._base(org), json={k: v for k, v in body.items() if v is not None}
        )

    def update(self, public_id: str, org: Optional[str] = None, **fields: Any) -> Any:
        """PUT /organizations/{org}/websites/{public_id}."""
        return self._http.put(f"{self._base(org)}/{_enc(public_id)}", json=fields)

    def delete(self, public_id: str, org: Optional[str] = None) -> Any:
        """DELETE /organizations/{org}/websites/{public_id}."""
        return self._http.delete(f"{self._base(org)}/{_enc(public_id)}")

    # -- pages -----------------------------------------------------------

    def list_pages(
        self, public_id: str, org: Optional[str] = None, **params: Any
    ) -> Any:
        """GET /organizations/{org}/websites/{public_id}/pages."""
        return self._http.get(
            f"{self._base(org)}/{_enc(public_id)}/pages", params=params
        )

    def iterate_pages(
        self, public_id: str, org: Optional[str] = None, **params: Any
    ) -> Iterator[Any]:
        """Yield every page of a website across all result pages."""
        return self._http.paginate(
            f"{self._base(org)}/{_enc(public_id)}/pages", params=params
        )

    def add_pages(
        self,
        public_id: str,
        pages: List[Mapping[str, Any]],
        org: Optional[str] = None,
    ) -> Any:
        """POST /organizations/{org}/websites/{public_id}/pages.

        ``pages`` is a list of ``{"url": ..., "title": ...}`` dicts.
        """
        return self._http.post(
            f"{self._base(org)}/{_enc(public_id)}/pages", json={"pages": pages}
        )

    def delete_pages(
        self,
        public_id: str,
        *,
        ids: Optional[List[str]] = None,
        filters: Optional[Mapping[str, Any]] = None,
        org: Optional[str] = None,
    ) -> Any:
        """POST /organizations/{org}/websites/{public_id}/deleted-pages.

        Provide either ``ids`` (explicit page public IDs) or ``filters``.
        """
        if ids is not None:
            body = {"type": "ids", "pages": ids}
        elif filters is not None:
            body = {"type": "filters", "filters": dict(filters)}
        else:
            raise PopeTechError("delete_pages requires either ids= or filters=.")
        return self._http.post(
            f"{self._base(org)}/{_enc(public_id)}/deleted-pages", json=body
        )

    # -- per-website scan containers ------------------------------------

    def latest_scan_container(
        self, public_id: str, org: Optional[str] = None
    ) -> Any:
        """GET .../websites/{public_id}/scan-containers/latest."""
        return self._http.get(
            f"{self._base(org)}/{_enc(public_id)}/scan-containers/latest"
        )

    def latest_scan_container_aggregates(
        self, public_id: str, org: Optional[str] = None
    ) -> Any:
        """GET .../websites/{public_id}/scan-containers/latest/aggregates."""
        return self._http.get(
            f"{self._base(org)}/{_enc(public_id)}/scan-containers/latest/aggregates"
        )

    def start_scan(
        self,
        public_id: str,
        *,
        start_crawl: bool,
        start_scan: bool,
        org: Optional[str] = None,
        **options: Any,
    ) -> Any:
        """POST .../websites/{public_id}/scan-containers - start a scan."""
        body = {"start_crawl": start_crawl, "start_scan": start_scan, **options}
        return self._http.post(
            f"{self._base(org)}/{_enc(public_id)}/scan-containers", json=body
        )


# --------------------------------------------------------------------------
# Scans (deprecated family, still functional)
# --------------------------------------------------------------------------


class Scans(_Resource):
    """Individual scans. Most endpoints are deprecated in favor of containers."""

    def _base(self, org: Optional[str]) -> str:
        return f"/organizations/{self._org(org)}/scans"

    def list(self, org: Optional[str] = None, **params: Any) -> Any:
        """GET /organizations/{org}/scans."""
        return self._http.get(self._base(org), params=params)

    def iterate(self, org: Optional[str] = None, **params: Any) -> Iterator[Any]:
        return self._http.paginate(self._base(org), params=params)

    def get(
        self,
        public_id: str,
        org: Optional[str] = None,
        *,
        region_filter: Optional[str] = None,
    ) -> Any:
        """GET /organizations/{org}/scans/{public_id}."""
        return self._http.get(
            f"{self._base(org)}/{_enc(public_id)}",
            params={"region_filter": region_filter},
        )

    def pages(self, public_id: str, org: Optional[str] = None, **params: Any) -> Any:
        """GET /organizations/{org}/scans/{public_id}/pages."""
        return self._http.get(
            f"{self._base(org)}/{_enc(public_id)}/pages", params=params
        )

    def iterate_pages(
        self, public_id: str, org: Optional[str] = None, **params: Any
    ) -> Iterator[Any]:
        return self._http.paginate(
            f"{self._base(org)}/{_enc(public_id)}/pages", params=params
        )

    def page_detail(
        self, scan_public_id: str, page_public_id: str, org: Optional[str] = None
    ) -> Any:
        """GET /organizations/{org}/scans/{scan}/pages/{page}."""
        return self._http.get(
            f"{self._base(org)}/{_enc(scan_public_id)}/pages/{_enc(page_public_id)}"
        )

    def accessibility_report(
        self, public_id: str, org: Optional[str] = None
    ) -> Any:
        """GET /organizations/{org}/scans/{public_id}/accessibility-report."""
        return self._http.get(
            f"{self._base(org)}/{_enc(public_id)}/accessibility-report"
        )

    def start(
        self,
        entity_public_id: str,
        *,
        type: str = "websites",
        org: Optional[str] = None,
        **options: Any,
    ) -> Any:
        """POST /organizations/{org}/scans/{type}/{entity} - deprecated start."""
        return self._http.post(
            f"{self._base(org)}/{_enc(type)}/{_enc(entity_public_id)}", json=options
        )

    def cancel(self, public_id: str, org: Optional[str] = None) -> Any:
        """POST /organizations/{org}/scans/{public_id}/cancel."""
        return self._http.post(f"{self._base(org)}/{_enc(public_id)}/cancel")


# --------------------------------------------------------------------------
# Scan containers (current scan model)
# --------------------------------------------------------------------------


class ScanContainers(_Resource):
    """Scan containers: the current model bundling a crawl + scan."""

    def _base(self, org: Optional[str]) -> str:
        return f"/organizations/{self._org(org)}/scan-containers"

    def list(self, org: Optional[str] = None, **params: Any) -> Any:
        """GET /organizations/{org}/scan-containers."""
        return self._http.get(self._base(org), params=params)

    def iterate(self, org: Optional[str] = None, **params: Any) -> Iterator[Any]:
        return self._http.paginate(self._base(org), params=params)

    def active(self, org: Optional[str] = None) -> Any:
        """GET /organizations/{org}/scan-containers/active."""
        return self._http.get(f"{self._base(org)}/active")

    def get(self, public_id: str, org: Optional[str] = None) -> Any:
        """GET /organizations/{org}/scan-containers/{public_id}."""
        return self._http.get(f"{self._base(org)}/{_enc(public_id)}")

    def aggregates(self, public_id: str, org: Optional[str] = None) -> Any:
        """GET /organizations/{org}/scan-containers/{public_id}/aggregates."""
        return self._http.get(f"{self._base(org)}/{_enc(public_id)}/aggregates")

    def cancel(self, public_id: str, org: Optional[str] = None) -> Any:
        """POST /organizations/{org}/scan-containers/{public_id}/cancel."""
        return self._http.post(f"{self._base(org)}/{_enc(public_id)}/cancel")

    def cancel_active(self, org: Optional[str] = None) -> Any:
        """POST /organizations/{org}/scan-containers/cancelActive."""
        return self._http.post(f"{self._base(org)}/cancelActive")

    def start_group_scan(
        self,
        group_public_id: str,
        *,
        start_crawl: bool,
        start_scan: bool,
        org: Optional[str] = None,
        **options: Any,
    ) -> Any:
        """POST /organizations/{org}/groups/{group}/scan-containers."""
        body = {"start_crawl": start_crawl, "start_scan": start_scan, **options}
        return self._http.post(
            f"/organizations/{self._org(org)}/groups/{_enc(group_public_id)}/scan-containers",
            json=body,
        )


# --------------------------------------------------------------------------
# Crawls (deprecated)
# --------------------------------------------------------------------------


class Crawls(_Resource):
    """Crawls. Deprecated in favor of scan containers, but still queryable."""

    def _base(self, org: Optional[str]) -> str:
        return f"/organizations/{self._org(org)}/crawls"

    def list(self, org: Optional[str] = None, **params: Any) -> Any:
        """GET /organizations/{org}/crawls."""
        return self._http.get(self._base(org), params=params)

    def iterate(self, org: Optional[str] = None, **params: Any) -> Iterator[Any]:
        return self._http.paginate(self._base(org), params=params)

    def get(self, public_id: str, org: Optional[str] = None) -> Any:
        """GET /organizations/{org}/crawls/{public_id}."""
        return self._http.get(f"{self._base(org)}/{_enc(public_id)}")

    def start(self, website_public_id: str, org: Optional[str] = None) -> Any:
        """POST /organizations/{org}/crawls/{website_public_id} - deprecated."""
        return self._http.post(f"{self._base(org)}/{_enc(website_public_id)}")


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------


class Reports(_Resource):
    """Accessibility reports."""

    def _base(self, org: Optional[str]) -> str:
        return f"/organizations/{self._org(org)}/accessibility-reports"

    def list(self, org: Optional[str] = None, **params: Any) -> Any:
        """GET /organizations/{org}/accessibility-reports."""
        return self._http.get(self._base(org), params=params)

    def iterate(self, org: Optional[str] = None, **params: Any) -> Iterator[Any]:
        return self._http.paginate(self._base(org), params=params)

    def create(self, org: Optional[str] = None, **body: Any) -> Any:
        """POST /organizations/{org}/accessibility-reports."""
        return self._http.post(self._base(org), json=body)

    def download(
        self, public_id: str, org: Optional[str] = None, *, raw: bool = True
    ) -> Any:
        """GET /organizations/{org}/accessibility-reports/{public_id}.

        Returns the raw ``requests.Response`` by default so callers can stream
        ``.content`` to a file (reports are typically PDF/CSV/HTML).
        """
        return self._http.get(f"{self._base(org)}/{_enc(public_id)}", raw=raw)

    def rebuild(self, public_id: str, org: Optional[str] = None) -> Any:
        """PUT /organizations/{org}/accessibility-reports/{public_id}."""
        return self._http.put(f"{self._base(org)}/{_enc(public_id)}")

    def delete(self, public_id: str, org: Optional[str] = None) -> Any:
        """DELETE /organizations/{org}/accessibility-reports/{public_id}."""
        return self._http.delete(f"{self._base(org)}/{_enc(public_id)}")


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------


class Dashboard(_Resource):
    """Aggregated, dashboard-style analytics."""

    def aggregates(
        self,
        org: Optional[str] = None,
        *,
        group_filter: Optional[str] = None,
        website_filter: Optional[str] = None,
        region_filter: Optional[str] = None,
        date_filter: Optional[str] = None,
    ) -> Any:
        """GET /organizations/{org}/reports/aggregates - org-wide result totals."""
        params = {
            "group_filter": group_filter,
            "website_filter": website_filter,
            "region_filter": region_filter,
            "date_filter": date_filter,
        }
        return self._http.get(
            f"/organizations/{self._org(org)}/reports/aggregates", params=params
        )


# --------------------------------------------------------------------------
# Personal access tokens
# --------------------------------------------------------------------------


class Tokens(_Resource):
    """Personal access token management."""

    def _base(self, org: Optional[str]) -> str:
        return f"/organizations/{self._org(org)}/personal-access-tokens"

    def info(self, org: Optional[str] = None) -> Any:
        """GET /organizations/{org}/personal-access-tokens."""
        return self._http.get(self._base(org))

    def create(
        self,
        name: str,
        *,
        expires_at: Optional[str] = None,
        org: Optional[str] = None,
    ) -> Any:
        """POST /organizations/{org}/personal-access-tokens.

        The returned token value is shown only once - store it immediately.
        """
        body = {"name": name, "expires_at": expires_at}
        return self._http.post(
            self._base(org), json={k: v for k, v in body.items() if v is not None}
        )

    def revoke_all(self, org: Optional[str] = None) -> Any:
        """DELETE /organizations/{org}/personal-access-tokens - revoke all tokens."""
        return self._http.delete(self._base(org))
