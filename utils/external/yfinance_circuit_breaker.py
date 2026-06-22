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

    def __init__(self):
        """Initialize circuit breaker."""
        self._last_check_time: float = 0
        self._check_cache_duration_secs = 2  # Cache local checks for 2 seconds
        self._cached_state: dict[str, Any] | None = None

    def is_banned(self) -> bool:
        """Check if the IP is currently banned (with local caching).

        Returns:
            True if IP is banned and we should back off, False otherwise
        """
        # Use cached state if recent
        now = time.time()
        if self._cached_state is not None and (now - self._last_check_time) < self._check_cache_duration_secs:
            return bool(self._cached_state.get("is_banned", False))

        # Fetch current state from PostgreSQL
        state = self._get_ban_state()
        self._cached_state = state
        self._last_check_time = now

        if state is None:
            return False  # No ban state yet

        # Check if ban has expired
        ban_until = state.get("ban_until")
        if ban_until is None:
            return False

        if ban_until <= datetime.now(timezone.utc):
            # Ban has expired — clear it
            self._clear_ban()
            return False
        return True

    def get_backoff_seconds(self) -> float:
        """Get how long to wait before the next request attempt.

        Returns:
            Number of seconds to wait (0 if not banned)
        """
        state = self._get_ban_state()
        if state is None or not self.is_banned():
            return 0.0

        # Calculate remaining backoff time
        ban_until = state.get("ban_until")
        if ban_until is None:
            return 0.0

        now = datetime.now(timezone.utc)
        remaining = (ban_until - now).total_seconds()
        return float(max(0, remaining))

    def report_rate_limit_error(self):
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
            failure_count = (state.get("failure_count", 0) or 0) + 1
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

    def report_success(self):
        """Report a successful request (resets failure counter)."""
        state = self._get_ban_state()
        if state is None:
            return  # No ban state to reset

        failure_count = state.get("failure_count", 0) or 0
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
        """Get current ban state from PostgreSQL.

        Returns:
            Dict with ban state or None if not set
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT is_banned, failure_count, ban_until, last_error_time, last_success_time, reason "
                    "FROM yfinance_ip_ban WHERE state_key = %s",
                    (self.STATE_KEY,),
                )
                row = cur.fetchone()
                if row is None:
                    return None

                return {
                    "is_banned": bool(row[0]),
                    "failure_count": int(row[1]) if row[1] is not None else 0,
                    "ban_until": row[2],
                    "last_error_time": row[3],
                    "last_success_time": row[4],
                    "reason": str(row[5]) if row[5] is not None else "",
                }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Failed to read ban state from PostgreSQL: {e}")
            return None

    def _set_ban_state(
        self,
        is_banned: bool,
        failure_count: int = 0,
        ban_until: datetime | None = None,
        last_error_time: datetime | None = None,
        last_success_time: datetime | None = None,
        reason: str = "",
    ):
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

    def _clear_ban(self):
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
            logger.warning(f"Failed to clear ban state: {e}")

    def get_diagnostics(self) -> dict[str, Any]:
        """Get current circuit breaker state for diagnostics."""
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

        ban_until = state.get("ban_until")
        remaining_secs = 0.0

        if ban_until:
            remaining_secs = (ban_until - datetime.now(timezone.utc)).total_seconds()
            remaining_secs = max(0.0, remaining_secs)

        last_error_time = state.get("last_error_time")
        last_success_time = state.get("last_success_time")

        return {
            "is_banned": state.get("is_banned", False),
            "failure_count": state.get("failure_count", 0),
            "backoff_secs": remaining_secs,
            "ban_until": (ban_until.isoformat() if isinstance(ban_until, datetime) else None),
            "last_error_time": (last_error_time.isoformat() if isinstance(last_error_time, datetime) else None),
            "last_success_time": (last_success_time.isoformat() if isinstance(last_success_time, datetime) else None),
            "reason": state.get("reason", ""),
        }


# Global instance (shared across module)
_circuit_breaker = YFinanceIPCircuitBreaker()


def get_circuit_breaker() -> YFinanceIPCircuitBreaker:
    """Get the global circuit breaker instance."""
    return _circuit_breaker
