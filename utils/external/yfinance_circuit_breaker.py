#!/usr/bin/env python3
"""Shared IP Circuit Breaker for yfinance — Coordinates rate limiting across all ECS tasks.

Problem: 6 ECS tasks share the same NAT IP when accessing yfinance. When one task
detects rate limiting, the others don't know and keep making requests, causing Yahoo
to ban the entire IP. This circuit breaker uses PostgreSQL to track ban state across
all tasks so they coordinate backoff.

Implementation:
- Track IP ban state in PostgreSQL (yfinance_ip_ban table)
- When any task detects 429/401, it sets a shared ban flag with exponential cooldown
- Other tasks check this flag and respect the backoff
- Use exponential backoff: initial 10s, then 20s, 40s, 80s, etc (doubles each time)
- Resets counter on successful request; increments on each rate-limit error
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


class YFinanceIPCircuitBreaker:
    """Tracks shared IP ban state across all ECS tasks using PostgreSQL."""

    # Ban state row key
    STATE_KEY = "shared"

    # Exponential backoff configuration
    INITIAL_BACKOFF_SECS = 10  # Start with 10s
    MAX_BACKOFF_SECS = 300  # Cap at 5 minutes
    BACKOFF_MULTIPLIER = 2  # Double on each failure

    def __init__(self) -> None:
        self._last_check_time: float = 0
        self._check_cache_duration_secs = 2  # Cache local checks for 2 seconds
        self._cached_state: dict[str, Any] | None = None

    def is_banned(self) -> bool:
        # Use cached state if recent
        now = time.time()
        if self._cached_state is not None and (now - self._last_check_time) < self._check_cache_duration_secs:
            is_banned = self._cached_state.get("is_banned")
            if is_banned is None:
                raise ValueError("Circuit breaker cached state corrupted: is_banned is None")
            return bool(is_banned)

        # Fetch current state from PostgreSQL
        state = self._get_ban_state()
        self._cached_state = state
        self._last_check_time = now

        if state is None:
            return False  # No ban state yet (first initialization is OK)

        # Validate required 'is_banned' field exists
        if "is_banned" not in state or state["is_banned"] is None:
            raise ValueError("Circuit breaker state missing required 'is_banned' field")

        is_banned = bool(state["is_banned"])

        # If not banned, ban_until can be NULL (it's meaningless when not active)
        if not is_banned:
            return False

        # If banned, ban_until MUST be non-NULL and in the future
        ban_until = state.get("ban_until")
        if ban_until is None:
            raise ValueError("Circuit breaker state corrupted: is_banned=TRUE but ban_until is NULL")

        if ban_until <= datetime.now(timezone.utc):
            # Ban has expired — clear it
            self._clear_ban()
            return False
        return True

    def get_backoff_seconds(self) -> float:
        state = self._get_ban_state()
        if state is None or not self.is_banned():
            return 0.0

        # At this point, is_banned() returned True, so ban_until must exist
        ban_until = state.get("ban_until")
        if ban_until is None:
            raise ValueError("Circuit breaker corrupted: is_banned=TRUE but ban_until is NULL")

        now = datetime.now(timezone.utc)
        remaining = (ban_until - now).total_seconds()
        return float(max(0, remaining))

    def report_rate_limit_error(self) -> None:
        """Report that we hit a rate limit error (429 or 401).

        This increments the failure counter and extends the ban period
        with exponential backoff.
        """
        state = self._get_ban_state()

        if state is None:
            # First rate limit error — create initial state
            failure_count = 1
            backoff = self.INITIAL_BACKOFF_SECS
        else:
            # Validate failure_count exists and is numeric
            if "failure_count" not in state or state["failure_count"] is None:
                raise ValueError("Circuit breaker state missing required 'failure_count' field")
            try:
                prev_count = int(state["failure_count"])
            except (ValueError, TypeError) as e:
                raise ValueError(f"Circuit breaker failure_count is not numeric: {state['failure_count']}") from e
            failure_count = prev_count + 1
            # Exponential backoff: initial 10s, then 20s, 40s, 80s, 160s, 300s, 300s, ...
            backoff = min(
                self.INITIAL_BACKOFF_SECS * (self.BACKOFF_MULTIPLIER ** (failure_count - 1)),
                self.MAX_BACKOFF_SECS,
            )

        ban_until = datetime.now(timezone.utc) + timedelta(seconds=backoff)

        self._set_ban_state(
            is_banned=True,
            failure_count=failure_count,
            ban_until=ban_until,
            last_error_time=datetime.now(timezone.utc),
            reason="Rate limit detected (429/401)",
        )

        logger.warning(
            f"[YFINANCE-CIRCUIT-BREAKER] Rate limit detected. "
            f"Failure count: {failure_count}, backoff: {backoff:.0f}s, "
            f"ban until: {ban_until.isoformat()}"
        )

    def report_success(self) -> None:
        """Report a successful request (resets failure counter)."""
        state = self._get_ban_state()
        if state is None:
            return  # No ban state to reset

        # Validate failure_count exists and is numeric
        if "failure_count" not in state or state["failure_count"] is None:
            raise ValueError("Circuit breaker state missing required 'failure_count' field")
        try:
            failure_count = int(state["failure_count"])
        except (ValueError, TypeError) as e:
            raise ValueError(f"Circuit breaker failure_count is not numeric: {state['failure_count']}") from e

        if failure_count > 0:
            logger.info(
                f"[YFINANCE-CIRCUIT-BREAKER] Successful request after {failure_count} failures. "
                "Resetting failure counter."
            )

        self._set_ban_state(
            is_banned=False,
            failure_count=0,
            ban_until=None,
            last_success_time=datetime.now(timezone.utc),
            reason="Successful request",
        )

    def _get_ban_state(self) -> dict[str, Any] | None:
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT is_banned, failure_count, ban_until, last_error_time, last_success_time, reason "
                    "FROM yfinance_ip_ban WHERE state_key = %s",
                    (self.STATE_KEY,),
                )
                row = cur.fetchone()
                if row is None:
                    logger.debug("[YFINANCE_CIRCUIT_BREAKER] No ban state record found (initial state, not banned)")
                    return None

                # Validate critical fields that must always exist
                is_banned = row[0]
                failure_count = row[1]
                ban_until = row[2]

                if is_banned is None:
                    raise ValueError("Circuit breaker state corrupted: is_banned is NULL in database")
                if failure_count is None:
                    raise ValueError("Circuit breaker state corrupted: failure_count is NULL in database")

                # ban_until can be NULL when is_banned=FALSE (no active ban)
                # but MUST be non-NULL when is_banned=TRUE (active ban)
                if bool(is_banned) and ban_until is None:
                    raise ValueError("Circuit breaker state corrupted: is_banned=TRUE but ban_until is NULL")

                return {
                    "is_banned": bool(is_banned),
                    "failure_count": int(failure_count),
                    "ban_until": ban_until,
                    "last_error_time": row[3],
                    "last_success_time": row[4],
                    "reason": str(row[5]) if row[5] is not None else "",
                }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"CIRCUIT BREAKER INFRASTRUCTURE FAILURE: Cannot read ban state from database: {e}. "
                f"Circuit breaker state is unreliable. Cannot proceed with external API calls."
            ) from e

    def _set_ban_state(
        self,
        is_banned: bool,
        failure_count: int = 0,
        ban_until: datetime | None = None,
        last_error_time: datetime | None = None,
        last_success_time: datetime | None = None,
        reason: str = "",
    ) -> None:
        """Set ban state in PostgreSQL."""
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO yfinance_ip_ban
                    (state_key, is_banned, failure_count, ban_until, last_error_time, last_success_time, reason, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (state_key) DO UPDATE SET
                        is_banned = EXCLUDED.is_banned,
                        failure_count = EXCLUDED.failure_count,
                        ban_until = EXCLUDED.ban_until,
                        last_error_time = EXCLUDED.last_error_time,
                        last_success_time = EXCLUDED.last_success_time,
                        reason = EXCLUDED.reason,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        self.STATE_KEY,
                        is_banned,
                        failure_count,
                        ban_until,
                        last_error_time,
                        last_success_time,
                        reason,
                    ),
                )

            # Invalidate local cache
            self._cached_state = None

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.warning(f"Failed to write ban state to PostgreSQL: {e}")

    def _clear_ban(self) -> None:
        """Clear the ban state (called when ban expires)."""
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    "UPDATE yfinance_ip_ban SET is_banned = FALSE, failure_count = 0, ban_until = NULL, "
                    "reason = 'Ban expired', updated_at = CURRENT_TIMESTAMP WHERE state_key = %s",
                    (self.STATE_KEY,),
                )
            self._cached_state = None
            logger.info("[YFINANCE-CIRCUIT-BREAKER] Ban state cleared (cooldown expired)")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"CIRCUIT BREAKER INFRASTRUCTURE FAILURE: Cannot clear ban state in database: {e}. "
                f"Circuit breaker state is unreliable. Cannot proceed."
            ) from e

    def get_diagnostics(self) -> dict[str, Any]:
        state = self._get_ban_state()

        if state is None:
            return {
                "is_banned": False,
                "failure_count": 0,
                "backoff_secs": 0.0,
                "ban_until": None,
                "last_error_time": None,
                "last_success_time": None,
                "reason": "No ban state",
            }

        # Validate required fields
        is_banned = state.get("is_banned")
        failure_count = state.get("failure_count")
        ban_until = state.get("ban_until")

        if is_banned is None or failure_count is None:
            raise ValueError(f"Circuit breaker state incomplete: is_banned={is_banned}, failure_count={failure_count}")

        # ban_until can be NULL when is_banned=FALSE
        # but if is_banned=TRUE, ban_until must be non-NULL
        if is_banned and ban_until is None:
            raise ValueError("Circuit breaker state corrupted: is_banned=TRUE but ban_until is NULL")

        remaining_secs = 0.0
        if ban_until:
            remaining_secs = (ban_until - datetime.now(timezone.utc)).total_seconds()
            remaining_secs = max(0.0, remaining_secs)

        last_error_time = state.get("last_error_time")
        last_success_time = state.get("last_success_time")
        reason = state.get("reason", "")

        return {
            "is_banned": bool(is_banned),
            "failure_count": int(failure_count),
            "backoff_secs": remaining_secs,
            "ban_until": (ban_until.isoformat() if isinstance(ban_until, datetime) else None),
            "last_error_time": (last_error_time.isoformat() if isinstance(last_error_time, datetime) else None),
            "last_success_time": (last_success_time.isoformat() if isinstance(last_success_time, datetime) else None),
            "reason": str(reason),
        }


# Global instance (shared across module)
_circuit_breaker = YFinanceIPCircuitBreaker()


def get_circuit_breaker() -> YFinanceIPCircuitBreaker:
    return _circuit_breaker
