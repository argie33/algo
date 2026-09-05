"""Authentication/authorization helpers for the API Lambda handler.

Split out of lambda_function.py (bloater decomposition, mechanical move, no behavior
change): Bearer token extraction, Cognito JWKS fetch/cache, JWT validation, and the
require_auth() routing gate. AUTH/SECURITY-CRITICAL - moved verbatim, no logic changes.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import psycopg2
import requests

logger = logging.getLogger()

_JWKS_CACHE: dict[str, Any] = {}
_JWKS_CACHE_TIME = None
_JWKS_CACHE_LOCK = threading.Lock()  # Protects JWKS cache updates
_JWKS_CACHE_TTL_SECONDS = 3600  # Refresh JWKS keys hourly

_COGNITO_ENABLED: bool | None = None  # Determined at module load (set by lambda_function package __init__)
_COGNITO_ENABLED_LOCK = threading.Lock()  # Protects Cognito enabled flag


def get_bearer_token(event: dict[str, Any]) -> str | None:
    """Extract Bearer token from Authorization header. CRITICAL: Missing auth header must be explicit None."""
    headers = event.get("headers")
    if headers is None:
        logger.debug("No headers in event (no auth)")
        return None
    auth_header = headers.get("Authorization")
    if auth_header is None:
        auth_header = headers.get("authorization")
    if not auth_header:
        logger.debug("No Authorization header found")
        return None

    if not auth_header.startswith("Bearer "):
        logger.warning("Authorization header does not start with 'Bearer '")
        return None

    return str(auth_header[7:])  # Remove 'Bearer ' prefix


def _get_cognito_jwks() -> dict[str, Any] | None:
    """Fetch and cache Cognito JWKS (JSON Web Key Set) - cached for 10 minutes.

    Short TTL allows rapid key rotation in emergencies (max 10min delay).
    Thread-safe: Uses double-check locking pattern to prevent race conditions.
    """
    global _JWKS_CACHE, _JWKS_CACHE_TIME

    cognito_region = os.getenv("COGNITO_REGION", "us-east-1")
    cognito_user_pool_id = os.getenv("COGNITO_USER_POOL_ID")

    if not cognito_user_pool_id:
        logger.warning("COGNITO_USER_POOL_ID not set - JWT signature verification disabled")
        return None

    now = datetime.now(timezone.utc)
    cache_ttl = timedelta(minutes=10)

    if _JWKS_CACHE and _JWKS_CACHE_TIME and (now - _JWKS_CACHE_TIME) < cache_ttl:
        return _JWKS_CACHE

    with _JWKS_CACHE_LOCK:
        # Double-check pattern after acquiring lock
        if _JWKS_CACHE and _JWKS_CACHE_TIME and (now - _JWKS_CACHE_TIME) < cache_ttl:
            return _JWKS_CACHE

        try:
            from requests.adapters import HTTPAdapter

            url = f"https://cognito-idp.{cognito_region}.amazonaws.com/{cognito_user_pool_id}/.well-known/jwks.json"
            session = requests.Session()
            session.mount("https://", HTTPAdapter(max_retries=0))
            response = session.get(url, timeout=3)
            response.raise_for_status()
            _JWKS_CACHE = response.json()
            _JWKS_CACHE_TIME = now
            return _JWKS_CACHE
        except (requests.RequestException, requests.Timeout) as e:
            logger.critical(
                "Cognito JWKS fetch failed (%s). "
                "Cannot authenticate users without live JWKS from Cognito. "
                "Enable NAT Gateway or add cognito-idp VPC endpoint to restore JWKS access. "
                "Failing fast to prevent authentication with potentially stale or invalid keys.",
                e,
            )
            raise RuntimeError(
                f"Cognito JWKS unavailable - authentication cannot proceed: {e}. "
                "Ensure NAT Gateway or VPC endpoint is configured for cognito-idp.us-east-1.amazonaws.com."
            ) from e


def validate_bearer_token(token: str | None) -> tuple[bool, dict[str, Any] | None, str | None]:
    if not token:
        return (False, None, "No token provided")

    # CRITICAL: Check for dev tokens FIRST before JWT validation
    # Dev mode is only active in local development (not Lambda, no Cognito configured)
    from dev_auth import validate_dev_token

    is_dev_valid, dev_claims, dev_error = validate_dev_token(token)
    if is_dev_valid:
        return (True, dev_claims, None)
    elif dev_error and "Dev mode not enabled" not in dev_error:
        # Token looks like dev token but mode is disabled - reject it
        return (False, None, dev_error)
    # If dev mode not enabled, continue with JWT validation

    if len(token) < 50:
        return (False, None, "Token too short")
    if token.count(".") != 2:
        return (False, None, "Invalid token structure")

    try:
        parts = token.split(".")

        # Verify Cognito is configured - fail hard if not (no dev fallback)
        cognito_region = os.getenv("COGNITO_REGION", "us-east-1")
        cognito_user_pool_id = os.getenv("COGNITO_USER_POOL_ID")
        if not cognito_user_pool_id:
            logger.error("FATAL: COGNITO_USER_POOL_ID not configured in Lambda environment")
            return (
                False,
                None,
                "Authentication system not configured - contact administrator",
            )

        # Decode header to get key ID
        header = json.loads(base64.urlsafe_b64decode(parts[0] + "=="))

        # Production: verify signature with Cognito public keys
        jwks = _get_cognito_jwks()
        if not jwks:
            return (False, None, "Unable to fetch Cognito keys")

        kid = header.get("kid")
        if not kid:
            return (False, None, "Token has no key ID")

        # Find matching key
        keys = jwks.get("keys")
        if keys is None:
            logger.error("Cognito JWKS response missing required 'keys' field - cannot verify token")
            return (False, None, "JWKS validation failed: missing keys field")

        if not isinstance(keys, list):
            logger.error(f"Cognito JWKS 'keys' field must be list, got {type(keys).__name__}")
            return (False, None, "JWKS validation failed: keys field is not a list")

        key_data = None
        for key in keys:
            if key.get("kid") == kid:
                key_data = key
                break

        if not key_data:
            logger.warning(f"Key {kid} not found in Cognito JWKS")
            return (False, None, "Key not found")

        # Verify signature and claims
        cognito_client_id = os.getenv("COGNITO_CLIENT_ID", "").strip()
        if not cognito_client_id:
            logger.error(
                "FATAL: COGNITO_CLIENT_ID not configured - JWT audience validation will be skipped (SECURITY H-01)"
            )
            return (
                False,
                None,
                "Authentication system misconfigured - COGNITO_CLIENT_ID missing",
            )

        # Cognito access tokens use `client_id` claim (not `aud`).
        # ID tokens use `aud` = client_id. Skip PyJWT audience validation
        # and check whichever claim is present to support both token types.
        rsa_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))
        # Type: from_jwk() returns RSAPublicKey | RSAPrivateKey, but jwt.decode() expects RSAPublicKey
        # Cognito JWK is always a public key, safe to cast
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            issuer=f"https://cognito-idp.{cognito_region}.amazonaws.com/{cognito_user_pool_id}",
            options={"verify_exp": True, "verify_aud": False},
        )

        # SECURITY FIX S-21: Validate required JWT claims are present
        # Cognito tokens MUST have 'sub' (subject/user ID) claim
        required_claims = ["sub"]
        missing_claims = [claim for claim in required_claims if not payload.get(claim)]
        if missing_claims:
            logger.warning(f"JWT missing required claims: {missing_claims}")
            return (
                False,
                None,
                f"Token missing required claims: {', '.join(missing_claims)}",
            )

        # Manually verify client identity from either claim
        actual_client = payload.get("client_id")
        if actual_client is None:
            actual_client = payload.get("aud")
        if not actual_client:
            logger.warning("JWT missing both client_id and aud claims")
            return (False, None, "Token missing client identity claim")
        if isinstance(actual_client, list):
            actual_client = actual_client[0] if actual_client else None
        if not actual_client:
            logger.warning("JWT aud claim is empty list")
            return (False, None, "Token client identity empty")
        if actual_client != cognito_client_id:
            logger.warning(f"JWT client_id/aud mismatch: expected {cognito_client_id}, got {actual_client}")
            return (False, None, "Token client mismatch")

        # SECURITY FIX S-21: Explicit expiration validation
        # (PyJWT checks via verify_exp=True, but explicit check adds defense-in-depth)
        exp = payload.get("exp")
        if not exp:
            logger.warning("JWT missing 'exp' (expiration) claim")
            return (False, None, "Token missing expiration claim")

        now = datetime.now(timezone.utc)
        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
        if now > exp_dt:
            logger.warning(f"Token expired at {exp_dt.isoformat()}, current time {now.isoformat()}")
            return (False, None, "Token expired")

        # O-1: Check server-side revocation (user called POST /api/logout)
        # SECURITY FIX S-22: Token revocation must NOT silently fail. If we can't verify
        # revocation status, we must reject the token to prevent bypass via blocklist unavailability.
        jti = payload.get("jti")
        if jti:
            try:
                from api_utils.token_blocklist import is_revoked

                if is_revoked(jti):
                    return (False, None, "Token has been revoked")
            except (ImportError, AttributeError) as e:
                # Blocklist module unavailable - FAIL CLOSED: revocation cannot be verified
                logger.critical(
                    f"[TOKEN_REVOCATION_FAILED] Blocklist module import failed: {e}. Rejecting token to prevent bypass."
                )
                return (False, None, "Token revocation verification failed (security check unavailable)")
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                # Database unavailable - fail secure by rejecting token
                logger.error(
                    f"[TOKEN_REVOCATION_FAILED] Database error checking revocation: {type(e).__name__}: {e} - rejecting token"
                )
                return (False, None, "Token revocation verification failed (database unavailable)")
            except OSError as e:
                # Cache/network errors - fail secure by rejecting token
                logger.error(
                    f"[TOKEN_REVOCATION_FAILED] Cache/network error checking revocation: {e} - rejecting token"
                )
                return (False, None, "Token revocation verification failed (cache unavailable)")

        logger.info(f"JWT validated: user={payload.get('sub')}, valid until {payload.get('exp')}")

        # SECURITY FIX S-08: Validate JWT scope claim (if present)
        # Scope is optional, but if Cognito is configured to issue scopes, validate them
        scope_str = payload.get("scope")
        token_scope = scope_str.split() if scope_str else []
        if token_scope:
            logger.info(f"Token scopes: {token_scope}")
            # Example: if a user has read-only scope, they shouldn't be able to modify data
            # For now, just log it. In future: reject write operations for read-only users
            logger.debug(f"JWT scopes: {token_scope}")

        return (True, payload, None)

    except jwt.ExpiredSignatureError:
        logger.warning("Token has expired")
        return (False, None, "Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return (False, None, f"Token invalid: {e!s}")
    except (json.JSONDecodeError, ValueError) as e:
        if isinstance(e, json.JSONDecodeError):
            return (False, None, f"Invalid token format: {e!s}")
        logger.error(f"Token validation error: {e}", exc_info=True)
        return (False, None, "Token validation failed")


def require_auth(event: dict[str, Any], path: str) -> tuple[bool, bool, str | None, dict[str, Any] | None]:
    # Public endpoints (no auth required) - only aggregate market data (no strategy/trading info)
    # SECURITY FIX: Strategy and trading endpoints require authentication
    PUBLIC_PREFIXES = {  # noqa: N806
        "/api/health",  # Basic health check (no auth required for uptime monitoring)
        "/api/health/cognito",  # Cognito client ID check (public for frontend config)
        # SECURITY FIX: /api/health/detailed and /api/health/pipeline require authentication
        # (they expose DB table names, loader names, row counts, freshness ages).
        # These are handled specially in the auth check below.
        "/api/market",  # Market breadth, distribution (aggregate only - no strategy)
        "/api/algo/markets",  # Market regime data (public market conditions)
        "/api/algo/scores",  # Stock scores (needed for dashboard signals panel - growth/composite scores)
        "/api/algo/swing-scores",  # Swing trader scores (used by TradingSignals page for all users)
        "/api/algo/swing-scores-history",  # Historical swing scores (public market analysis)
        "/api/algo/sector-rotation",  # Sector rotation analysis (public market analysis)
        "/api/algo/sector-breadth",  # Sector breadth analysis (public market data)
        "/api/algo/sector-stage2",  # Stage 2 sector stocks (public market analysis)
        "/api/algo/status",  # Algorithm execution status (public system metadata for dashboard)
        "/api/algo/last-run",  # Orchestrator run status (public system metadata for dashboard health panel)
        "/api/algo/data-status",  # Data loader status and freshness (public metadata)
        "/api/algo/health",  # System health check (public metadata for dashboard health panel)
        "/api/algo/config",  # Algorithm configuration (public strategy parameters)
        # SECURITY FIX (2026-07-26): The endpoints formerly listed here (portfolio, positions,
        # trades, performance, dashboard-signals, risk-metrics, circuit-breakers, and the
        # execution/notification/patrol/audit-log/performance-analytics/rejection-funnel/
        # *-distribution/*-histogram/equity-curve group) exposed live trading positions, entry
        # prices, portfolio value, and trade history to the entire internet with zero
        # authentication - `is_public=True` returns before any token (Cognito or dev) is ever
        # checked, so the "accept either Cognito auth OR dev tokens" comment that used to sit
        # here was aspirational, not enforced: nothing downstream re-checked auth for these
        # paths. This directly contradicted this function's own header comment ("Strategy and
        # trading endpoints require authentication") and the API Gateway layer's terraform
        # comment ("all routes use NONE auth, Lambda enforces auth via require_auth()") - Lambda
        # is the *only* auth boundary for these routes, so a gap here is a full unauthenticated
        # information-disclosure hole, not defense-in-depth degradation.
        #
        # These endpoints are NOT public. Falling through to the `cognito_enabled` check below:
        # local dev (dev_server.py, COGNITO_USER_POOL_ID unset) still gets frictionless access
        # via the existing dev-claims fallback; production (Cognito configured) now correctly
        # requires a valid Bearer token, same as every other protected /api/algo/* endpoint.
        "/api/algo/sentiment",  # Market sentiment (dashboard)
        "/api/algo/economic-calendar",  # Economic calendar (dashboard)
        "/api/algo/metrics",  # Algo metrics (dashboard)
        "/api/algo/market-factors",  # Market factors + put/call ratio (dashboard)
        "/api/algo/signals",  # Trading signals (dashboard)
        "/api/diagnostics",  # Data sync diagnostics (public for debugging)
        "/api/economic",  # Economic indicators (public data)
        "/api/sectors",  # Sector analysis (aggregate market data only)
        "/api/sentiment",  # Market sentiment (aggregate only)
        "/api/industries",  # Industry analysis (aggregate market data)
        "/api/prices",  # Historical prices (public market data)
        "/api/stocks",  # Stock metadata/list (public data)
        "/api/signals",  # Trading signals (public dashboard data)
        "/api/financials",  # Company financials (public data)
        "/api/earnings",  # Earnings data (public data)
        "/api/market/sentiment",  # Market sentiment analysis (public aggregated data)
        "/api/market/fear-greed",  # Fear & Greed Index (public market sentiment)
        # /api/research intentionally NOT public: exposes backtest strategy names, returns, trade history
        "/api/data-coverage",  # Data freshness status (public metadata)
        "/api/contact",  # Public contact form (no auth required)
        "/api/logs",  # Frontend error log ingest (intentionally unauthenticated - called by error boundaries)
        # NOTE: /api/portfolio and /api/positions (aliases for /api/algo/portfolio and
        # /api/algo/positions) were removed from here for the same reason as the block above -
        # they're aliases for now-protected endpoints and must not bypass that protection.
    }

    # Protected endpoints requiring authentication (strategy/trading data)
    # STALE COMMENT FIXED (2026-07-27): this used to claim "/api/algo/*" and "/api/signals/*"
    # are uniformly protected - false, and directly contradicted by PUBLIC_PREFIXES above,
    # which deliberately lists many /api/algo/* endpoints (scores, swing-scores,
    # sector-rotation/-breadth/-stage2, status, last-run, data-status, health, config,
    # sentiment, economic-calendar, metrics, market-factors, signals) and bare /api/signals as
    # public - real algo-generated buy/sell signals with quality scores, per
    # lambda/api/routes/signals.py's actual query. That's a deliberate product choice (the
    # 2026-07-26 SECURITY FIX above precisely enumerated what got locked down - portfolio,
    # positions, trades, performance, dashboard-signals, risk-metrics, circuit-breakers,
    # audit-log, etc. - and never included plain "signals" in that list), not an oversight;
    # this comment was just never updated to match. What's actually NOT in PUBLIC_PREFIXES,
    # confirmed against the set above:
    # - /api/scores/* (bare, distinct from the public /api/algo/scores) - trading scores
    # - /api/audit/* - audit logs (sensitive)
    # - /api/trades/* - trade history (user-specific)
    # - /api/admin/* - admin functions (sensitive)
    # - /api/settings/* - user settings (user-specific)
    # - most other /api/algo/* endpoints not explicitly listed above (portfolio, positions,
    #   trades, performance, notifications, dashboard-signals, risk-metrics, circuit-breakers)

    # Protected endpoints (requires authentication)
    # /api/trades - user-specific trade history
    # /api/audit - system audit logs (sensitive)
    # /api/admin - administrative functions
    # /api/settings - user-specific settings

    # SECURITY FIX: Explicitly exclude protected health endpoints before prefix matching
    # /api/health/detailed and /api/health/pipeline require authentication
    if path in ("/api/health/detailed", "/api/health/pipeline") or path.startswith(
        ("/api/health/detailed?", "/api/health/pipeline?")
    ):
        is_public = False
    else:
        # Check if path matches any public prefix
        # Match: exact route or /path/subpath (strict matching to prevent auth bypass)
        def matches_prefix(p: str, prefix: str) -> bool:
            if p == prefix:
                return True
            if p.startswith(prefix + "/"):
                return True
            if p.startswith(prefix + "?"):
                return True
            return False

        is_public = any(matches_prefix(path, prefix) for prefix in PUBLIC_PREFIXES)
    if is_public:
        return (False, True, None, None)  # No auth required, so authorized

    if not path.startswith("/api/"):
        return (False, True, None, None)  # Non-API paths don't need auth

    # This is an /api path that requires authentication
    # SECURITY FIX: Authentication must be enforced for protected endpoints
    # In production, Cognito MUST be configured (COGNITO_USER_POOL_ID set)
    # Thread-safe read of _COGNITO_ENABLED flag
    with _COGNITO_ENABLED_LOCK:
        cognito_enabled = _COGNITO_ENABLED

    logger.debug(
        f"[AUTH_DEBUG] cognito_enabled={cognito_enabled}, env_COGNITO_USER_POOL_ID={bool(os.getenv('COGNITO_USER_POOL_ID'))}"
    )

    if not cognito_enabled:
        # SECURITY FIX S-02: Dev mode only in local development (dev_server.py), never in Lambda
        # In production Lambda, Cognito MUST be configured (this code is unreachable if properly configured)

        try:
            from dev_auth import get_dev_claims, validate_dev_token

            token = get_bearer_token(event)
            if token:
                is_valid, claims, error = validate_dev_token(token)
                if is_valid:
                    logger.info("[DEV_AUTH] Development token accepted (local dev mode)")
                    return (True, True, None, claims)
            else:
                # In local dev mode, allow unauthenticated access with default admin claims for dashboard
                # Dashboard requires admin access for positions, portfolio, trades, etc.
                claims = get_dev_claims("dev-admin")
                if claims:
                    logger.info(
                        "[DEV_AUTH] Local dev mode: allowing unauthenticated access with default dev-admin claims"
                    )
                    return (True, True, None, claims)
        except ImportError:
            pass  # dev_auth not available - continue to error

        logger.error(f"[AUTH_FAILURE] Protected endpoint {path} accessed but Cognito not configured")
        return (
            True,
            False,
            "Authentication system not configured. Contact administrator.",
            None,
        )

    token = get_bearer_token(event)

    if not token:
        return (True, False, "Missing Authorization: Bearer token", None)

    is_valid, claims, error = validate_bearer_token(token)
    if not is_valid:
        # CRITICAL FIX: Always return actual validation error per GOVERNANCE.md
        # Never mask with generic fallback-operators must see why auth failed
        if error is None:
            logger.error("[CRITICAL] validate_bearer_token returned is_valid=False but error=None. This is a bug.")
            return (True, False, "Token validation failed (internal error: no error message)", None)
        return (True, False, error, None)

    # Token is valid - return claims for routing
    return (True, True, None, claims)
