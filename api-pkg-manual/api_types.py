"""Type definitions for Lambda API routes.

Provides TypedDict definitions for improved type safety in route handlers,
allowing mypy and IDE type checkers to validate parameter usage.
"""

from __future__ import annotations

from typing import Any, TypedDict


class RouteParams(TypedDict, total=False):
    """Query string parameters passed to route handlers.

    Fields are optional (total=False) because different endpoints use different params.
    """

    page: int
    limit: int
    symbol: str
    date: str
    sort: str
    status: str


class RouteBody(TypedDict, total=False):
    """Request body parameters passed to route handlers.

    Fields are optional because different POST endpoints have different schemas.
    """

    id: str
    value: Any
    action: str
    symbol: str
    quantity: int | float
    price: float


class JWTClaims(TypedDict, total=False):
    """JWT token claims from Cognito.

    Fields are optional because token content depends on Cognito configuration.
    """

    sub: str
    email: str
    email_verified: bool
    iss: str
    aud: str
    token_use: str
    auth_time: int
    exp: int
    iat: int


class RouteResponse(TypedDict):
    """Standard route response format."""

    statusCode: int
    body: str
    headers: dict[str, str] | None
