from __future__ import annotations

import json
from typing import Any

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

# See circuit_breaker_portfolio_risk.py's top-of-file comment for why this qualified
# `import ... as _cb` (not `from ... import logger`) is used instead of a plain module-level
# import.
import algo.risk.circuit_breaker as _cb


class CircuitBreakerAlertingMixin:
    """Circuit-breaker halt audit-logging and notification - split out of
    circuit_breaker.py's CircuitBreaker God-class (bloater decomposition, mechanical/
    no-behavior-change split, see git log 2026-09-05).
    """

    def _log_halt(self, results: dict[str, Any], cur: PsycopgCursor[Any]) -> None:
        try:
            cur.execute(
                """
                INSERT INTO algo_audit_log (action_type, action_date, details, actor, status, created_at)
                VALUES ('circuit_breaker_halt', CURRENT_TIMESTAMP, %s, 'circuit_breaker', 'halt', CURRENT_TIMESTAMP)
                """,
                # BUG FOUND 2026-08-17: `results` is loosely typed (dict[str, Any]) and this is
                # called from many different _check_* methods throughout this file - all
                # currently return plain str/float/bool, but nothing prevents a future caller
                # from including a raw Decimal/datetime, which would raise TypeError here and
                # be lost (only DatabaseError/OperationalError are caught below). Same bug class
                # already found and fixed in phase9_reconciliation.py's audit log insert -
                # default=str is the same standard, safe fallback for an archival JSON column.
                (json.dumps(results, default=str),),
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            _cb.logger.critical(f"[AUDIT_FAILURE] Could not log circuit breaker halt to audit log: {e}")
            raise
        # Surface to notifications for UI (non-critical, warn only)
        try:
            from algo.reporting import notify

            if "halt_reasons" not in results:
                _cb.logger.error("Circuit breaker results missing 'halt_reasons' field")
                halt_msg = "Trading halted (reason unavailable)"
            else:
                halt_reasons = results["halt_reasons"]
                if not isinstance(halt_reasons, list):
                    _cb.logger.error(f"halt_reasons is not a list: {type(halt_reasons)}")
                    halt_msg = "Trading halted (reason unavailable)"
                elif not halt_reasons:
                    halt_msg = "Trading halted (no specific reason provided)"
                else:
                    halt_msg = "; ".join(halt_reasons)

            notify(
                severity="critical",
                title="Trading Halted by Circuit Breaker",
                message=halt_msg,
                details=results.get("checks"),
            )
        except (ValueError, ZeroDivisionError, TypeError) as e:
            _cb.logger.warning(f"Warning: Could not send circuit breaker notification: {e}")
