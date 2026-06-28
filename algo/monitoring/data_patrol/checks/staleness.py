#!/usr/bin/env python3
"""Data staleness check - ensures data is fresh within expected windows."""

import logging
from datetime import date as _date
from datetime import datetime
from typing import Any, cast

from utils.db import assert_safe_column, assert_safe_table, safe_select_count

from ..base import BaseCheck, CheckResult
from ..config import CRIT, ERROR, INFO, WARN

logger = logging.getLogger(__name__)


class StalenessChecker(BaseCheck):
    """Check that latest data is within expected staleness windows."""

    def run(self, cur: Any) -> list[CheckResult]:
        """Execute staleness checks."""
        self.results = []

        # Table configurations: (table, date_column, freq, config_key, severity_on_stale)
        sources = [
            ("price_daily", "date", "daily", "patrol_staleness_price_daily", CRIT),
            (
                "technical_data_daily",
                "date",
                "daily",
                "patrol_staleness_technical_daily",
                CRIT,
            ),
            (
                "buy_sell_daily",
                "date",
                "daily",
                "patrol_staleness_buy_sell_daily",
                CRIT,
            ),
            (
                "trend_template_data",
                "date",
                "daily",
                "patrol_staleness_trend_data",
                CRIT,
            ),
            (
                "signal_quality_scores",
                "date",
                "daily",
                "patrol_staleness_signal_quality_scores",
                WARN,
            ),
            (
                "market_health_daily",
                "date",
                "daily",
                "patrol_staleness_market_health",
                ERROR,
            ),
            (
                "sector_ranking",
                "date",
                "daily",
                "patrol_staleness_sector_ranking",
                WARN,
            ),
            (
                "industry_ranking",
                "date_recorded",
                "daily",
                "patrol_staleness_industry_ranking",
                WARN,
            ),
            (
                "insider_transactions",
                "trade_date",
                "daily",
                "patrol_staleness_insider_transactions",
                INFO,
            ),
            (
                "analyst_upgrade_downgrade",
                "action_date",
                "daily",
                "patrol_staleness_analyst_upgrades",
                INFO,
            ),
            (
                "stock_scores",
                "created_at",
                "weekly",
                "patrol_staleness_stock_scores",
                WARN,
            ),
            (
                "aaii_sentiment",
                "date",
                "weekly",
                "patrol_staleness_aaii_sentiment",
                INFO,
            ),
            (
                "growth_metrics",
                "created_at",
                "monthly",
                "patrol_staleness_growth_metrics",
                INFO,
            ),
            (
                "earnings_history",
                "earnings_date",
                "quarterly",
                "patrol_staleness_earnings_history",
                INFO,
            ),
        ]

        today = _date.today()
        critical_signal_tables = {
            "buy_sell_daily",
            "signal_quality_scores",
            "trend_template_data",
        }
        stale_critical_signals = []

        for tbl, col, freq, config_key, sev_on_stale in sources:
            sp = f"sp_stale_{tbl}"
            try:
                cur.execute(f"SAVEPOINT {sp}")
            except Exception as e:
                # CRITICAL: Cannot create SAVEPOINT — transaction protection required for data patrol integrity
                raise RuntimeError(
                    f"[DATA_PATROL CRITICAL] Cannot create SAVEPOINT {sp} for staleness check: {e}. "
                    f"Database transaction safety is required. Data patrol checks must run with rollback "
                    f"capability to prevent partial state corruption. Check database connection and retry."
                ) from e
            try:
                max_days = cast(int, self.config.get(config_key, 7))
                tbl_safe = assert_safe_table(tbl)
                col_safe = assert_safe_column(col)

                count, latest_str = safe_select_count(cur, tbl_safe, date_column=col_safe)

                if not latest_str:
                    empty_severity = INFO if sev_on_stale == CRIT else sev_on_stale
                    self.log(
                        "staleness",
                        empty_severity,
                        tbl,
                        f"EMPTY table {tbl}",
                        {"count": count},
                    )
                    continue

                # Parse date
                latest = None
                try:
                    latest = datetime.strptime(latest_str.split()[0], "%Y-%m-%d").date()
                except (ValueError, IndexError, AttributeError):
                    try:
                        latest = datetime.fromisoformat(latest_str.replace("Z", "+00:00")).date()
                    except (ValueError, AttributeError):
                        latest = None

                if not latest:
                    # CRITICAL: Cannot parse timestamp — data freshness cannot be verified
                    # Staleness check failure is fatal for critical signal tables
                    severity_on_parse_fail = CRIT if tbl in critical_signal_tables else ERROR
                    error_msg = (
                        f"[DATA_PATROL CRITICAL] {tbl}: Cannot parse timestamp ({latest_str}). "
                        f"Data freshness cannot be verified. Staleness check must fail for "
                        f"incomplete/corrupted timestamp data. Cannot assume data is fresh without validation."
                    )
                    self.log(
                        "staleness",
                        severity_on_parse_fail,
                        tbl,
                        error_msg,
                        {"latest": latest_str},
                    )
                    # For critical tables, raise immediately to halt algo
                    if tbl in critical_signal_tables:
                        raise RuntimeError(error_msg)

                age = (today - latest).days
                if age > max_days:
                    self.log(
                        "staleness",
                        sev_on_stale,
                        tbl,
                        f"{tbl} stale: {age}d > {max_days}d threshold",
                        {
                            "latest": str(latest),
                            "age_days": age,
                            "freq": freq,
                            "threshold_days": max_days,
                        },
                    )
                    if tbl in critical_signal_tables:
                        stale_critical_signals.append(tbl)
                else:
                    self.log(
                        "staleness",
                        INFO,
                        tbl,
                        f"{tbl} fresh ({age}d old, threshold {max_days}d)",
                        {"latest": str(latest), "age_days": age},
                    )
            except Exception as e:
                self.log("staleness", ERROR, tbl, f"Check failed: {e}", None)
                # Roll back to the per-table savepoint so subsequent table checks can run.
                # psycopg2 leaves the connection in an aborted state after any error;
                # without rollback, every following query fails with InFailedSqlTransaction.
                try:
                    cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                except Exception as rollback_err:
                    logger.error(f"CRITICAL: ROLLBACK TO SAVEPOINT {sp} failed: {rollback_err}. Connection corrupted—data patrol must halt.")
                    raise RuntimeError(f"Database connection corrupted during staleness check rollback: {rollback_err}") from rollback_err
            finally:
                try:
                    cur.execute(f"RELEASE SAVEPOINT {sp}")
                except Exception as release_err:
                    logger.error(f"CRITICAL: RELEASE SAVEPOINT {sp} failed: {release_err}. Connection corrupted—data patrol must halt.")
                    raise RuntimeError(f"Database connection corrupted during staleness check cleanup: {release_err}") from release_err

        # Alert on stale critical signals
        if stale_critical_signals:
            from algo.reporting.notifications import notify_signal_staleness

            try:
                notify_signal_staleness(stale_critical_signals)
            except Exception as e:
                logger.critical(f"CRITICAL: Stale signal notification FAILED for {stale_critical_signals}: {e}. Operators unaware of stale signals.")
                raise RuntimeError(f"Stale signal notification failed—halting data patrol. Stale signals must be reported immediately: {stale_critical_signals}") from e

        return self.results
