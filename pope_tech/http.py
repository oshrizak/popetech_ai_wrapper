"""Core HTTP transport for the Pope Tech API.

This module contains :class:`Transport`, the low-level layer that every resource
namespace is built on. It handles authentication, retries with backoff,
error-to-exception mapping, pagination, and arbitrary endpoint access.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Iterator, Mapping, Optional, Union
from urllib.parse import urljoin

import requests

from .exceptions import (
    PopeTechError,
    RateLimitError,
    SafeModeError,
    ValidationError,
    error_for_status,
)

DEFAULT_BASE_URL = "https://api.pope.tech"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3
ENV_TOKEN_KEYS = ("POPE_TECH_API_KEY", "POPETECH_API_KEY", "POPE_TECH_TOKEN")

# Verbs that change server state. Blocked when ``safe_mode`` is enabled.
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _resolve_token(token: Optional[str]) -> str:
    if token:
        return token
    for key in ENV_TOKEN_KEYS:
        value = os.environ.get(key)
        if value:
            return value
    raise PopeTechError(
        "No API token provided. Pass token=... or set the POPE_TECH_API_KEY "
        "environment variable (a .env file is loaded automatically)."
    )


class Transport:
    """Thin wrapper over :class:`requests.Session` with Pope Tech conventions.

    Args:
        token: Bearer token. Falls back to the ``POPE_TECH_API_KEY`` env var.
        base_url: API root. Defaults to ``https://api.pope.tech``.
        timeout: Per-request timeout in seconds.
        max_retries: Retry attempts for 429 and 5xx responses.
        safe_mode: When True, any state-changing request raises
            :class:`SafeModeError` before hitting the network.
        session: Optional pre-built ``requests.Session`` (useful for testing).
    """

    def __init__(
        self,
        token: Optional[str] = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        safe_mode: bool = False,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.max_retries = max_retries
        self.safe_mode = safe_mode
        self._token = _resolve_token(token)
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
                "User-Agent": "PopeTechIntegrator/1.0 (+python-requests)",
            }
        )

    # -- internal helpers --------------------------------------------------

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return urljoin(self.base_url, path.lstrip("/"))

    @staticmethod
    def _parse_body(response: requests.Response) -> Any:
        if not response.content:
            return None
        ctype = response.headers.get("Content-Type", "")
        if "application/json" in ctype:
            try:
                return response.json()
            except ValueError:
                return response.text
        return response.text

    def _raise_for_status(self, response: requests.Response, body: Any) -> None:
        if response.ok:
            return
        message = f"{response.request.method} {response.url} failed"
        errors = None
        if isinstance(body, Mapping):
            message = body.get("message") or body.get("error") or message
            errors = body.get("errors")
        kwargs: Dict[str, Any] = {"response": response, "payload": body}
        if response.status_code == 422:
            raise ValidationError(message, errors=errors, status_code=422, **kwargs)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(
                message,
                retry_after=float(retry_after) if retry_after else None,
                status_code=429,
                **kwargs,
            )
        raise error_for_status(response.status_code, message, **kwargs)

    # -- public API --------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json: Any = None,
        data: Any = None,
        files: Any = None,
        headers: Optional[Mapping[str, str]] = None,
        raw: bool = False,
    ) -> Any:
        """Perform an authenticated request against the API.

        This is the escape hatch for reaching *any* endpoint, documented or not.

        Args:
            method: HTTP verb (GET, POST, PUT, DELETE, ...).
            path: Path relative to the base URL, or a full URL.
            params: Query string parameters (``None`` values are dropped).
            json: JSON request body.
            data: Form-encoded body.
            files: Multipart file uploads.
            headers: Extra headers for this request only.
            raw: When True, return the ``requests.Response`` untouched (use this
                for binary downloads such as PDF/CSV reports).

        Returns:
            Parsed JSON (dict/list), response text, or - if ``raw`` - the
            ``requests.Response`` object.
        """
        method = method.upper()
        if self.safe_mode and method in WRITE_METHODS:
            raise SafeModeError(
                f"Refusing {method} {path}: client is in safe_mode "
                f"(read-only). Set safe_mode=False to allow state changes."
            )

        clean_params = (
            {k: v for k, v in params.items() if v is not None} if params else None
        )

        last_exc: Optional[BaseException] = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.request(
                    method,
                    self._url(path),
                    params=clean_params,
                    json=json,
                    data=data,
                    files=files,
                    headers=dict(headers) if headers else None,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:  # network-level failure
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(self._backoff(attempt))
                    continue
                raise PopeTechError(f"Network error calling {path}: {exc}") from exc

            if response.status_code in (429,) or 500 <= response.status_code < 600:
                if attempt < self.max_retries:
                    time.sleep(self._retry_delay(response, attempt))
                    continue

            if raw:
                self._raise_for_status(response, self._safe_peek(response))
                return response

            body = self._parse_body(response)
            self._raise_for_status(response, body)
            return body

        # Loop only exits via return/raise above; this is a safety net.
        raise PopeTechError(  # pragma: no cover
            f"Request to {path} failed after {self.max_retries} retries"
        ) from last_exc

    @staticmethod
    def _safe_peek(response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return None

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(2.0 ** attempt, 30.0)

    def _retry_delay(self, response: requests.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return self._backoff(attempt)

    # -- convenience verbs -------------------------------------------------

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)

    # -- pagination --------------------------------------------------------

    def paginate(
        self,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        page_size: int = 100,
        max_items: Optional[int] = None,
    ) -> Iterator[Any]:
        """Yield items across all pages of a paginated list endpoint.

        Follows the ``meta.pagination`` envelope used by the Pope Tech API,
        incrementing ``page`` until ``last_page`` is reached.

        Args:
            path: List endpoint path.
            params: Base query parameters (``page``/``limit`` are managed here).
            page_size: Value sent as ``limit`` per page.
            max_items: Stop after yielding this many items, if set.
        """
        query: Dict[str, Any] = dict(params or {})
        query.setdefault("limit", page_size)
        page = int(query.get("page", 1) or 1)
        yielded = 0

        while True:
            query["page"] = page
            body = self.get(path, params=query)
            items, pagination = _extract_items(body)
            for item in items:
                yield item
                yielded += 1
                if max_items is not None and yielded >= max_items:
                    return
            if not items:
                return
            last_page = (pagination or {}).get("last_page")
            current = (pagination or {}).get("current_page", page)
            if last_page is None or current >= last_page:
                return
            page = current + 1

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "Transport":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _extract_items(body: Any) -> tuple[list, Optional[Mapping[str, Any]]]:
    """Pull the list of items and pagination block out of a list response."""
    if isinstance(body, list):
        return body, None
    if isinstance(body, Mapping):
        data = body.get("data", body)
        pagination = None
        meta = body.get("meta")
        if isinstance(meta, Mapping):
            pagination = meta.get("pagination") or meta
        if isinstance(data, list):
            return data, pagination
        # Some endpoints nest the list one level deeper.
        if isinstance(data, Mapping):
            for value in data.values():
                if isinstance(value, list):
                    return value, pagination
        return [data] if data is not None else [], pagination
    return [], None
