"""Exception hierarchy for the Pope Tech API wrapper.

All errors raised by the wrapper inherit from :class:`PopeTechError`, so callers
can catch everything with a single ``except PopeTechError``. More specific
subclasses are raised based on the HTTP status returned by the API.
"""

from __future__ import annotations

from typing import Any, Optional


class PopeTechError(Exception):
    """Base class for every error raised by the wrapper.

    Attributes:
        message: Human-readable error message.
        status_code: HTTP status code, when the error originated from a response.
        response: The raw ``requests.Response`` object, when available.
        payload: Parsed JSON body of the error response, when available.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        response: Any = None,
        payload: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response = response
        self.payload = payload

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        if self.status_code is not None:
            return f"[{self.status_code}] {self.message}"
        return self.message


class AuthenticationError(PopeTechError):
    """Raised on HTTP 401 - missing, invalid, or expired token."""


class ForbiddenError(PopeTechError):
    """Raised on HTTP 403 - authenticated but not permitted."""


class NotFoundError(PopeTechError):
    """Raised on HTTP 404 - resource does not exist."""


class ValidationError(PopeTechError):
    """Raised on HTTP 422 - the request body failed validation.

    The field-level errors returned by the API (when present) are available on
    the :attr:`errors` attribute.
    """

    def __init__(self, message: str, *, errors: Any = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.errors = errors


class RateLimitError(PopeTechError):
    """Raised on HTTP 429 once retries are exhausted."""

    def __init__(self, message: str, *, retry_after: Optional[float] = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ServerError(PopeTechError):
    """Raised on HTTP 5xx once retries are exhausted."""


class SafeModeError(PopeTechError):
    """Raised when a state-changing request is attempted while safe_mode is on."""


def error_for_status(status_code: int, message: str, **kwargs: Any) -> PopeTechError:
    """Map an HTTP status code to the most specific exception class."""
    mapping = {
        401: AuthenticationError,
        403: ForbiddenError,
        404: NotFoundError,
        422: ValidationError,
        429: RateLimitError,
    }
    if status_code in mapping:
        return mapping[status_code](message, status_code=status_code, **kwargs)
    if 500 <= status_code < 600:
        return ServerError(message, status_code=status_code, **kwargs)
    return PopeTechError(message, status_code=status_code, **kwargs)
