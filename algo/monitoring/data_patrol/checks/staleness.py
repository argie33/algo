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
                logger.warning(f"Failed to create SAVEPOINT {sp}: {e} — staleness check will run without transaction protection")
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
                    self.log(
                        "staleness",
                        WARN,
                        tbl,
                        f"{tbl} timestamp parse failed: {latest_str}",
                        {"latest": latest_str},
                    )
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
                except Exception:
                    pass
            finally:
                try:
                    cur.execute(f"RELEASE SAVEPOINT {sp}")
                except Exception:
                    pass

        # Alert on stale critical signals
        if stale_critical_signals:
            try:
                from algo.reporting.notifications import notify_signal_staleness

                notify_signal_staleness(stale_critical_signals)
            except Exception as e:
                logger.error(f"Failed to notify staleness: {e}")

        return self.results
