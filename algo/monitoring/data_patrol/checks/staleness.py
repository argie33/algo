#!/usr/bin/env python3
"""Data staleness check - ensures data is fresh within expected windows."""

import logging
from datetime import date as _date
from datetime import datetime
from typing import Any

from algo.infrastructure.market_calendar import MarketCalendar
from utils.db import assert_safe_column, assert_safe_table, safe_select_count

from ..base import BaseCheck, CheckResult
from ..config import CRIT, ERROR, INFO, WARN

logger = logging.getLogger(__name__)


class StalenessChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        """Execute staleness checks."""
        self.results = []

        # EXPLICIT FRESHNESS THRESHOLDS: These are operational requirements, not configurable
        # Based on data load schedules and trading requirements from steering/GOVERNANCE.md's
        # Schedule section (OPERATIONS.md, referenced here originally, was deleted 2026-07-26
        # as AWS-only/unused for local dev - see steering/DATA_LOADERS.md's own note on this)
        staleness_thresholds = {
            "price_daily": 1,  # Loaded 2:15 AM + 4:05 PM, max 1 day old
            "technical_data_daily": 1,  # Computed from prices, max 1 day old
            "buy_sell_daily": 1,  # Generated signals, max 1 day old
            "trend_template_data": 1,  # Daily calculation, max 1 day old
            "market_health_daily": 1,  # VIX and market indicators, max 1 day old
            "sector_ranking": 7,  # Sector analysis, warning if >7 days old
            "industry_ranking": 7,  # Industry analysis, warning if >7 days old
            "insider_transactions": 30,  # Insider data, warning if >30 days old
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
                # FIXED (real-money-readiness goal session, 2026-08-24): "insider_transactions"
                # is a real table in the schema (passes assert_safe_table) but has been
                # permanently empty (0 rows) - live-confirmed. Real insider-transaction data is
                # written to insider_transaction_velocity by
                # loaders/load_insider_transaction_velocity.py (21,722 rows, refreshed daily).
                # This check has therefore never actually verified insider-data freshness -
                # every run silently logged "EMPTY table insider_transactions" at INFO and
                # moved on, since the code already handles an empty table gracefully rather
                # than crashing (which is exactly why this went unnoticed rather than erroring).
                "insider_transaction_velocity",
                "updated_at",
                "daily",
                staleness_thresholds["insider_transactions"],
                INFO,
            ),
            (
                # BUG FIX (goal 2026-08-24: "scores stale but loader health OK"
                # investigation): was "created_at" - stock_scores is one row per symbol,
                # refreshed via `ON CONFLICT (symbol) DO UPDATE` (loaders/load_stock_scores.py),
                # which never touches created_at after the initial insert. MAX(created_at)
                # across the table reflects only when the newest *symbol* was first added,
                # not when scores were last refreshed - on a stable universe this stays
                # old indefinitely and would WARN-stale forever regardless of real refresh
                # recency, or falsely read fresh off one new symbol insert while every other
                # row is actually stale. Same bug class already fixed for this exact table in
                # lambda/api/routes/algo_handlers/signals.py:610 ("created_at is a static
                # one-time insert stamp, not a freshness signal - updated_at is"), just never
                # applied here. updated_at is written on every refresh - see
                # load_stock_scores.py's `SET updated_at = CURRENT_TIMESTAMP`.
                "stock_scores",
                "updated_at",
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
                # BUG FIX (goal 2026-08-24, same pass as stock_scores above): growth_metrics
                # is also one row per symbol via `ON CONFLICT (symbol) DO UPDATE` (see
                # loaders/load_value_quality_growth_metrics.py's _insert_growth_metrics -
                # created_at isn't even in the UPDATE SET list, only updated_at is), so
                # created_at is the same static insert-time stamp, not a freshness signal.
                "growth_metrics",
                "updated_at",
                "monthly",
                staleness_thresholds["growth_metrics"],
                INFO,
            ),
            (
                # FIXED (real-money-readiness goal session, 2026-08-24): same bug class as
                # insider_transactions above - "earnings_history" is a real, permanently-empty
                # (0-row) table. Real earnings-calendar data is written to earnings_calendar_sec
                # by loaders/load_earnings_calendar_sec.py (81,211 rows, refreshed daily; no
                # earnings_date column exists on this table, filing_date is the real per-row
                # SEC filing date). This check has never verified earnings-data freshness.
                "earnings_calendar_sec",
                "filing_date",
                "quarterly",
                staleness_thresholds["earnings_history"],
                INFO,
            ),
        ]

        today = _date.today()
        critical_signal_tables = {
            "buy_sell_daily",
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

                # Trading-day-aware for daily-freq tables (fixed 2026-09-08, goal: score-sanity
                # sweep): a plain calendar-day diff false-positives CRIT across any weekend or
                # holiday (Fri->Mon is already 3 calendar days > the 1-day threshold; a Friday
                # before a Monday holiday is 4) even though only 1 trading session has actually
                # elapsed - live-caught 2026-09-08 (Tuesday after Labor Day): latest=2026-09-04
                # (Friday, the correct latest trading day) read as 4 calendar days old, which
                # would fire CRIT and halt Phase 1 (CLAUDE.md's _check_data_patrol_results rule)
                # despite the data being exactly as fresh as it should be. Weekly/monthly/
                # quarterly freqs keep calendar-day math - their thresholds already comfortably
                # absorb a holiday's worth of skew and MarketCalendar has no such periodicity.
                age = MarketCalendar.trading_days_elapsed(latest, today) if freq == "daily" else (today - latest).days
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

        # PER-SYMBOL FROZEN-SCORE CHECK (added 2026-09-08, goal session score-sanity sweep):
        # the table-level stock_scores staleness check above only looks at MAX(updated_at)
        # across the whole table, so it stays "fresh" even when a subpopulation of active
        # symbols never gets refreshed again. Live-caught exactly this: utils/loaders/
        # helpers.py's get_active_symbols() started excluding 29 BDCs (MAIN, HTGC, GAIN, TSLX,
        # ...) from every metrics/scores loader on 2026-09-03, so their stock_scores rows froze
        # permanently that day while `ss.active` stayed true and the table-level check kept
        # reporting fresh - a fresh --now signals reload live-confirmed this population never
        # self-heals (see lambda/api/routes/scores_handlers/stock_scores.py's matching fix,
        # same day). This check generalizes the guard: any future population silently dropped
        # from get_active_symbols() (a new exclusion list, a new entity-type carve-out) freezes
        # the same way and would otherwise go undetected until someone happens to spot-check
        # symbols by hand again. WARN only (not CRIT/ERROR) - a handful of legitimately-excluded
        # symbols (BDCs, CEF/trust exemptions) frozen by design is expected, this is a signal to
        # go investigate WHY a population is stuck, not an automatic halt.
        sp_frozen = "sp_stale_stock_scores_frozen_symbols"
        try:
            cur.execute(f"SAVEPOINT {sp_frozen}")
            cur.execute(
                """
                SELECT COUNT(*)
                FROM stock_symbols sy
                JOIN stock_scores ss ON ss.symbol = sy.symbol
                WHERE sy.active = true
                  AND ss.date < (SELECT MAX(date) - INTERVAL '7 days' FROM stock_scores)
                """
            )
            frozen_count = cur.fetchone()[0]
            if frozen_count > 0:
                self.log(
                    "staleness",
                    WARN,
                    "stock_scores",
                    f"{frozen_count} active symbols have stock_scores rows more than 7 days "
                    f"behind the table's latest date - check whether they were silently "
                    f"dropped from get_active_symbols()",
                    {"frozen_symbol_count": frozen_count},
                )
            else:
                self.log(
                    "staleness",
                    INFO,
                    "stock_scores",
                    "no active symbols frozen more than 7 days behind latest stock_scores date",
                    {"frozen_symbol_count": 0},
                )
        except Exception as e:
            self.log("staleness", ERROR, "stock_scores", f"Frozen-symbol check failed: {e}", None)
            try:
                cur.execute(f"ROLLBACK TO SAVEPOINT {sp_frozen}")
            except Exception as rollback_err:
                logger.error(
                    f"CRITICAL: ROLLBACK TO SAVEPOINT {sp_frozen} failed: {rollback_err}. Connection corrupted."
                )
                raise RuntimeError(
                    f"Database connection corrupted during frozen-symbol check rollback: {rollback_err}"
                ) from rollback_err
        finally:
            try:
                cur.execute(f"RELEASE SAVEPOINT {sp_frozen}")
            except Exception as release_err:
                logger.error(f"CRITICAL: RELEASE SAVEPOINT {sp_frozen} failed: {release_err}. Connection corrupted.")
                raise RuntimeError(
                    f"Database connection corrupted during frozen-symbol check cleanup: {release_err}"
                ) from release_err

        # PER-SYMBOL FROZEN-PRICE CHECK (added 2026-09-08, goal session score-sanity sweep):
        # mirrors the frozen-stock_scores check above for the same underlying gap, one table
        # over. See _check_frozen_price_symbols's own docstring for the full evidence trail.
        # Extracted to a helper (not inlined here like its stock_scores sibling) to keep run()'s
        # cyclomatic complexity under ruff's C901 limit - this method was already near the
        # threshold before this addition would have pushed it over.
        self._check_frozen_price_symbols(cur)

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

    def _check_frozen_price_symbols(self, cur: Any) -> None:
        """PER-SYMBOL FROZEN-PRICE CHECK (added 2026-09-08, goal session score-sanity sweep).

        price_daily's table-level staleness check (top of run()) only looks at MAX(date)
        across the whole table, so it stays "fresh" (satisfying the 1-day CRIT threshold) even
        when a subpopulation of active symbols silently stops getting new rows -
        [[data_loader_status_completed_can_be_stale_from_earlier_partial_run_20260902]]'s same
        bug class, recurring here for price loading specifically. Live-caught 2026-09-06 (see
        price_daily_stale_symbol_cohort_backfilled_20260906 in memory): 107-115 active symbols
        sat 10-20+ days stale - closed-end funds frozen at a handful of shared dates plus
        liquid names with no excuse (AVB, LEG, RMAX, TWO, ISSC) - completely invisible to the
        standard freshness monitor the whole time, found only by a manual spot-check session.
        That session explicitly flagged this as "a real gap worth a future session's
        attention, not touched this session to avoid more churn" - closing it now.

        WARN only, matching the frozen-score check's own reasoning: a residual handful of
        symbols hitting a genuine per-symbol vendor data ceiling (confirmed at the
        yf.download() response level for ~23 names in that same session - not fixable by
        retrying or code changes on our side) is expected, not an automatic halt. This is a
        signal to go investigate WHY a population is stuck (the exact silent-backlog pattern
        documented above), not a guarantee every flagged symbol is actionable.
        """
        sp_frozen_price = "sp_stale_price_daily_frozen_symbols"
        try:
            cur.execute(f"SAVEPOINT {sp_frozen_price}")
            cur.execute(
                """
                SELECT COUNT(*)
                FROM stock_symbols sy
                JOIN (
                    SELECT symbol, MAX(date) AS latest_date
                    FROM price_daily
                    GROUP BY symbol
                ) pd ON pd.symbol = sy.symbol
                WHERE sy.active = true
                  AND pd.latest_date < (SELECT MAX(date) - INTERVAL '7 days' FROM price_daily)
                """
            )
            frozen_price_count = cur.fetchone()[0]
            if frozen_price_count > 0:
                self.log(
                    "staleness",
                    WARN,
                    "price_daily",
                    f"{frozen_price_count} active symbols have price_daily rows more than 7 "
                    f"days behind the table's latest date - check for a silent per-symbol "
                    f"loader backlog (see price_daily_stale_symbol_cohort_backfilled_20260906 "
                    f"in memory for the last confirmed occurrence and known vendor-ceiling "
                    f"exceptions)",
                    {"frozen_price_symbol_count": frozen_price_count},
                )
            else:
                self.log(
                    "staleness",
                    INFO,
                    "price_daily",
                    "no active symbols frozen more than 7 days behind latest price_daily date",
                    {"frozen_price_symbol_count": 0},
                )
        except Exception as e:
            self.log("staleness", ERROR, "price_daily", f"Frozen-price check failed: {e}", None)
            try:
                cur.execute(f"ROLLBACK TO SAVEPOINT {sp_frozen_price}")
            except Exception as rollback_err:
                logger.error(
                    f"CRITICAL: ROLLBACK TO SAVEPOINT {sp_frozen_price} failed: {rollback_err}. Connection corrupted."
                )
                raise RuntimeError(
                    f"Database connection corrupted during frozen-price check rollback: {rollback_err}"
                ) from rollback_err
        finally:
            try:
                cur.execute(f"RELEASE SAVEPOINT {sp_frozen_price}")
            except Exception as release_err:
                logger.error(
                    f"CRITICAL: RELEASE SAVEPOINT {sp_frozen_price} failed: {release_err}. Connection corrupted."
                )
                raise RuntimeError(
                    f"Database connection corrupted during frozen-price check cleanup: {release_err}"
                ) from release_err
