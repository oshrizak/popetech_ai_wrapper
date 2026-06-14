"""Live verification of all NON-DESTRUCTIVE Pope Tech endpoints.

This script exercises only read-only (GET) endpoints. The client is run in
``safe_mode=True`` so any accidental write call is blocked before it reaches the
network. It never starts scans/crawls, creates/updates/deletes anything, or
cancels running work.

Run::

    python verify_endpoints.py
"""

from __future__ import annotations

import sys
import traceback
from typing import Any, Callable, List, Optional, Tuple

from pope_tech import PopeTechClient, PopeTechError

# Make stdout UTF-8 so output renders on the Windows console (cp1252 default).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass

# ANSI colors, only when attached to a terminal that likely supports them.
if sys.stdout.isatty():
    GREEN, RED, YELLOW, DIM, RESET = (
        "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m",
    )
else:
    GREEN = RED = YELLOW = DIM = RESET = ""


class Verifier:
    def __init__(self) -> None:
        self.client = PopeTechClient(safe_mode=True)
        self.results: List[Tuple[str, str, str]] = []  # (label, status, detail)

    def check(self, label: str, fn: Callable[[], Any], *, optional: bool = False) -> Any:
        """Run a single read-only call, record pass/fail, return the payload."""
        try:
            value = fn()
        except PopeTechError as exc:
            status = "SKIP" if (optional and exc.status_code == 404) else "FAIL"
            self.results.append((label, status, str(exc)))
            return None
        except Exception as exc:  # noqa: BLE001 - report anything unexpected
            self.results.append((label, "FAIL", f"{type(exc).__name__}: {exc}"))
            return None
        self.results.append((label, "OK", _summarize(value)))
        return value

    # -- run ---------------------------------------------------------------

    def run(self) -> int:
        c = self.client

        # 1. Service + identity (no org required).
        self.check("GET /  (status)", c.account.status)
        me = self.check("GET /me", c.account.me)
        self.check("GET /documentation (WAVE)", c.account.wave_documentation, optional=True)

        orgs = []
        try:
            orgs = c.account.organizations()
        except PopeTechError:
            pass

        if not orgs:
            print("No organizations available to this token; stopping.", file=sys.stderr)
            self._print_summary()
            return 1

        print(f"Token can access {len(orgs)} organization(s):")
        for o in orgs:
            print(f"  - {o.get('slug')}  ({o.get('name')})")
        print()

        # 2. Per-organization read-only endpoints.
        drill_org: Optional[str] = None
        drill_website: Optional[str] = None

        for o in orgs:
            slug = o.get("slug")
            if not slug:
                continue
            print(f"{DIM}-- org: {slug} --{RESET}")
            self.check(f"[{slug}] GET org", lambda s=slug: c.organizations.get(s))
            self.check(f"[{slug}] GET groups", lambda s=slug: c.groups.list(s))
            self.check(f"[{slug}] GET users", lambda s=slug: c.users.list(s))
            self.check(f"[{slug}] GET scans", lambda s=slug: c.scans.list(s, limit=5))
            self.check(
                f"[{slug}] GET scan-containers",
                lambda s=slug: c.scan_containers.list(s, limit=5),
            )
            self.check(
                f"[{slug}] GET scan-containers/active",
                lambda s=slug: c.scan_containers.active(s),
            )
            self.check(f"[{slug}] GET crawls", lambda s=slug: c.crawls.list(s, limit=5))
            self.check(
                f"[{slug}] GET accessibility-reports",
                lambda s=slug: c.reports.list(s, limit=5),
            )
            self.check(
                f"[{slug}] GET reports/aggregates (dashboard)",
                lambda s=slug: c.dashboard.aggregates(s),
            )
            self.check(
                f"[{slug}] GET personal-access-tokens",
                lambda s=slug: c.tokens.info(s),
                optional=True,
            )

            websites = self.check(
                f"[{slug}] GET websites", lambda s=slug: c.websites.list(s, limit=5)
            )
            first_site = _first_public_id(websites)
            if first_site and drill_org is None:
                drill_org, drill_website = slug, first_site
            print()

        # 3. Deep-dive on one website + its latest scan, if any exist.
        if drill_org and drill_website:
            slug, wid = drill_org, drill_website
            print(f"{DIM}-- deep dive: {slug} / website {wid} --{RESET}")
            self.check(
                f"[{slug}] GET website detail",
                lambda: c.websites.get(wid, org=slug),
            )
            self.check(
                f"[{slug}] GET website pages",
                lambda: c.websites.list_pages(wid, org=slug, limit=5),
            )
            container = self.check(
                f"[{slug}] GET website latest scan-container",
                lambda: c.websites.latest_scan_container(wid, org=slug),
                optional=True,
            )
            self.check(
                f"[{slug}] GET website latest aggregates",
                lambda: c.websites.latest_scan_container_aggregates(wid, org=slug),
                optional=True,
            )

            cid = _first_public_id(container) or _public_id(container)
            if cid:
                self.check(
                    f"[{slug}] GET scan-container detail",
                    lambda: c.scan_containers.get(cid, org=slug),
                )
                self.check(
                    f"[{slug}] GET scan-container aggregates",
                    lambda: c.scan_containers.aggregates(cid, org=slug),
                )
            print()

        # 4. Prove safe_mode actually blocks writes (no network call made).
        self.check("safe_mode blocks POST", self._expect_safe_mode_block)

        return self._print_summary()

    def _expect_safe_mode_block(self) -> str:
        from pope_tech.exceptions import SafeModeError

        try:
            self.client.request("POST", "/should-never-be-called")
        except SafeModeError:
            return "blocked as expected"
        raise AssertionError("safe_mode did NOT block a POST request")

    def _print_summary(self) -> int:
        ok = sum(1 for _, s, _ in self.results if s == "OK")
        skip = sum(1 for _, s, _ in self.results if s == "SKIP")
        fail = sum(1 for _, s, _ in self.results if s == "FAIL")
        print("\n" + "=" * 70)
        print("VERIFICATION SUMMARY")
        print("=" * 70)
        for label, status, detail in self.results:
            color = {"OK": GREEN, "SKIP": YELLOW, "FAIL": RED}.get(status, "")
            print(f"  {color}{status:4}{RESET}  {label:48}  {DIM}{detail}{RESET}")
        print("-" * 70)
        print(f"  {GREEN}{ok} OK{RESET}   {YELLOW}{skip} skipped{RESET}   {RED}{fail} failed{RESET}")
        return 1 if fail else 0


# -- payload summarizers ---------------------------------------------------


def _unwrap(value: Any) -> Any:
    if isinstance(value, dict) and "data" in value:
        return value["data"]
    return value


def _summarize(value: Any) -> str:
    data = _unwrap(value)
    if isinstance(data, list):
        return f"list[{len(data)}]"
    if isinstance(data, dict):
        keys = list(data.keys())
        preview = ", ".join(keys[:5])
        more = "..." if len(keys) > 5 else ""
        return f"dict{{{preview}{more}}}"
    if hasattr(value, "status_code"):  # raw Response
        return f"Response<{value.status_code}>"
    return str(data)[:60]


def _first_public_id(value: Any) -> Optional[str]:
    data = _unwrap(value)
    if isinstance(data, list) and data:
        return _public_id(data[0])
    return None


def _public_id(value: Any) -> Optional[str]:
    data = _unwrap(value)
    if isinstance(data, dict):
        return data.get("public_id")
    return None


if __name__ == "__main__":
    try:
        sys.exit(Verifier().run())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(2)
