"""The public client object for the Pope Tech API."""

from __future__ import annotations

from typing import Any, Optional

try:  # Load a local .env automatically if python-dotenv is available.
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass

from .http import DEFAULT_BASE_URL, DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT, Transport
from .resources import (
    Account,
    Crawls,
    Dashboard,
    Groups,
    Organizations,
    Reports,
    Scans,
    ScanContainers,
    Tokens,
    Users,
    Websites,
)


class PopeTechClient:
    """High-level entry point to the Pope Tech API.

    Example::

        from pope_tech import PopeTechClient

        client = PopeTechClient()                  # token from POPE_TECH_API_KEY
        client.default_org = "san-francisco-state-university"

        print(client.account.me())
        for site in client.websites.iterate():
            print(site["name"])

        # Reach any endpoint directly, documented or not:
        client.request("GET", "/organizations/{org}/groups".format(
            org=client.default_org))

    Args:
        token: Bearer token. Falls back to ``POPE_TECH_API_KEY`` (and a few
            aliases) from the environment / a loaded ``.env``.
        default_org: Organization slug used when a method's ``org`` is omitted.
        base_url: API root.
        timeout: Per-request timeout in seconds.
        max_retries: Retry attempts for 429/5xx responses.
        safe_mode: When True, block every state-changing request (read-only).
    """

    def __init__(
        self,
        token: Optional[str] = None,
        *,
        default_org: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        safe_mode: bool = False,
    ) -> None:
        self.http = Transport(
            token,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            safe_mode=safe_mode,
        )
        self.default_org = default_org

        # Resource namespaces.
        self.account = Account(self)
        self.organizations = Organizations(self)
        self.groups = Groups(self)
        self.users = Users(self)
        self.websites = Websites(self)
        self.scans = Scans(self)
        self.scan_containers = ScanContainers(self)
        self.crawls = Crawls(self)
        self.reports = Reports(self)
        self.dashboard = Dashboard(self)
        self.tokens = Tokens(self)

    # -- properties --------------------------------------------------------

    @property
    def safe_mode(self) -> bool:
        return self.http.safe_mode

    @safe_mode.setter
    def safe_mode(self, value: bool) -> None:
        self.http.safe_mode = bool(value)

    # -- escape hatches ----------------------------------------------------

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Low-level access to any endpoint. See :meth:`Transport.request`."""
        return self.http.request(method, path, **kwargs)

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.http.get(path, **kwargs)

    def paginate(self, path: str, **kwargs: Any):
        """Iterate items across all pages of any list endpoint."""
        return self.http.paginate(path, **kwargs)

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "PopeTechClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        mode = "safe" if self.safe_mode else "read-write"
        return (
            f"PopeTechClient(base_url={self.http.base_url!r}, "
            f"default_org={self.default_org!r}, mode={mode})"
        )
