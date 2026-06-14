"""Pope Tech API wrapper.

A complete, typed-friendly Python client for the Pope Tech accessibility API
(https://api.pope.tech). Import :class:`PopeTechClient` to get started::

    from pope_tech import PopeTechClient

    client = PopeTechClient(default_org="san-francisco-state-university")
    print(client.account.me())
"""

from __future__ import annotations

from .agent import Agent
from .client import PopeTechClient
from .exceptions import (
    AuthenticationError,
    ForbiddenError,
    NotFoundError,
    PopeTechError,
    RateLimitError,
    SafeModeError,
    ServerError,
    ValidationError,
)
from .http import Transport

__version__ = "1.0.0"

__all__ = [
    "PopeTechClient",
    "Agent",
    "Transport",
    "PopeTechError",
    "AuthenticationError",
    "ForbiddenError",
    "NotFoundError",
    "ValidationError",
    "RateLimitError",
    "ServerError",
    "SafeModeError",
    "__version__",
]
