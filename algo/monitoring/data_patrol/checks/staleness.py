#!/usr/bin/env python3
"""Data staleness check - ensures data is fresh within expected windows."""

import logging
from datetime import date as _date
from datetime import datetime
from typing import Any

from utils.db import assert_safe_column, assert_safe_table, safe_select_count

from ..base import BaseCheck, CheckResult
from ..config import CRIT, ERROR, INFO, WARN

logger = logging.getLogger(__name__)


class StalenessChecker(BaseCheck):

    def run(self, cur: Any) -> list[CheckResult]:
        """Execute staleness checks."""
        self.results = []

        # EXPLICIT FRESHNESS THRESHOLDS: These are operational requirements, not configurable
        # Based on data load schedules and trading requirements from OPERATIONS.md
        staleness_thresholds = {
            "price_daily": 1,  # Loaded 2:15 AM + 4:05 PM, max 1 day old
            "technical_data_daily": 1,  # Computed from prices, max 1 day old
            "buy_sell_daily": 1,  # Generated signals, max 1 day old
            "trend_template_data": 1,  # Daily calculation, max 1 day old
            "signal_quality_scores": 7,  # Quality metrics, warning if >7 days
            "market_health_daily": 1,  # VIX and market indicators, max 1 day old
            "sector_ranking": 7,  # Sector analysis, warning if >7 days old
            "industry_ranking": 7,  # Industry analysis, warning if >7 days old
            "insider_transactions": 30,  # Insider data, warning if >30 days old
            "analyst_upgrade_downgrade": 30,  # Analyst actions, warning if >30 days old
            "stock_scores": 7,  # Weekly stock scores, warning if >7 days old
            "aaii_sentiment": 7,  # Weekly sentiment, warning if >7 days old
            "growth_metrics": 30,  # Monthly growth data, warning if >30 days old
            "earnings_history": 90,  # Quarterly earnings, warning if >90 days old
        }

        # Table configurations: (table, date_column, freq, max_days_allowed, severity_on_stale)
        sources = [
            ("price_daily", "date", "daily", staleness_thresholds["price_daily"], CRIT),
            (
                "technical_data_daily",
                "date",
                "daily",
                staleness_thresholds["technical_data_daily"],
                CRIT,
            ),
            (
                "buy_sell_daily",
                "date",
                "daily",
                staleness_thresholds["buy_sell_daily"],
                CRIT,
            ),
            (
                "trend_template_data",
                "date",
                "daily",
                staleness_thresholds["trend_template_data"],
                CRIT,
            ),
            (
                "signal_quality_scores",
                "date",
                "daily",
                staleness_thresholds["signal_quality_scores"],
                WARN,
            ),
            (
                "market_health_daily",
                "date",
                "daily",
                staleness_thresholds["market_health_daily"],
                ERROR,
            ),
            (
                "sector_ranking",
                "date",
                "daily",
                staleness_thresholds["sector_ranking"],
                WARN,
            ),
            (
                "industry_ranking",
                "date_recorded",
                "daily",
                staleness_thresholds["industry_ranking"],
                WARN,
            ),
            (
                "insider_transactions",
                "trade_date",
                "daily",
                staleness_thresholds["insider_transactions"],
                INFO,
            ),
            (
                "analyst_upgrade_downgrade",
                "action_date",
                "daily",
                staleness_thresholds["analyst_upgrade_downgrade"],
                INFO,
            ),
            (
                "stock_scores",
                "created_at",
                "weekly",
                staleness_thresholds["stock_scores"],
                WARN,
            ),
            (
                "aaii_sentiment",
                "date",
                "weekly",
                staleness_thresholds["aaii_sentiment"],
                INFO,
            ),
            (
                "growth_metrics",
                "created_at",
                "monthly",
                staleness_thresholds["growth_metrics"],
                INFO,
            ),
            (
                "earnings_history",
                "earnings_date",
                "quarterly",
                staleness_thresholds["earnings_history"],
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

        for tbl, col, freq, max_days, sev_on_stale in sources:
            sp = f"sp_stale_{tbl}"
            try:
                cur.execute(f"SAVEPOINT {sp}")
            except Exception as e:
                # CRITICAL: Cannot create SAVEPOINT â€” transaction protection required for data patrol integrity
                raise RuntimeError(
                    f"[DATA_PATROL CRITICAL] Cannot create SAVEPOINT {sp} for staleness check: {e}. "
                    f"Database transaction safety is required. Data patrol checks must run with rollback "
                    f"capability to prevent partial state corruption. Check database connection and retry."
                ) from e
            try:
                # max_days is now an explicit operational requirement, not configurable
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

                if latest is None:
                    # CRITICAL: Cannot parse timestamp â€” data freshness cannot be verified
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
                    continue

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
                    logger.error(
                        f"CRITICAL: ROLLBACK TO SAVEPOINT {sp} failed: {rollback_err}. Connection corruptedâ€”data patrol must halt."
                    )
                    raise RuntimeError(
                        f"Database connection corrupted during staleness check rollback: {rollback_err}"
                    ) from rollback_err
            finally:
                try:
                    cur.execute(f"RELEASE SAVEPOINT {sp}")
                except Exception as release_err:
                    logger.error(
                        f"CRITICAL: RELEASE SAVEPOINT {sp} failed: {release_err}. Connection corruptedâ€”data patrol must halt."
                    )
                    raise RuntimeError(
                        f"Database connection corrupted during staleness check cleanup: {release_err}"
                    ) from release_err

        # Alert on stale critical signals
        if stale_critical_signals:
            from algo.reporting.notifications import notify_signal_staleness

            try:
                notify_signal_staleness(stale_critical_signals)
            except Exception as e:
                logger.critical(
                    f"CRITICAL: Stale signal notification FAILED for {stale_critical_signals}: {e}. Operators unaware of stale signals."
                )
                raise RuntimeError(
                    f"Stale signal notification failedâ€”halting data patrol. Stale signals must be reported immediately: {stale_critical_signals}"
                ) from e

        return self.results
