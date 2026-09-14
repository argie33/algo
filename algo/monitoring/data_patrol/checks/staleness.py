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


def build_staleness_sources() -> list[tuple[str, str, str, int, str]]:
    """Table configurations: (table, date_column, freq, max_days_allowed, severity_on_stale).

    Extracted from StalenessChecker.run() (2026-09-13, goal session: table-organizing-fields
    follow-up) so /api/scores/correctness-coverage can read the SAME per-table cadence
    (`freq`) this checker actually enforces, instead of a second hand-maintained copy of
    these thresholds drifting out of sync with this one - exactly the class of gap that
    produced the naaim/value_metrics/quality_metrics/momentum_metrics blind spots
    documented in the comments below in the first place. No behavior change: run() calls
    this same function.
    """
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
        # ADDED (goal session 2026-09-13, "data integrity gaps galore" meta-gap sweep):
        # value_metrics/quality_metrics are written by the SAME loader run as
        # growth_metrics (load_value_quality_growth_metrics.py, one process, one pass -
        # see that file's INSERT INTO value_metrics/quality_metrics/growth_metrics, all
        # three ON CONFLICT (symbol) DO UPDATE SET updated_at = EXCLUDED.updated_at) but
        # had no table-level staleness entry at all - a structural blind spot, not an
        # oversight in this dict: growth_metrics was added here 2026-08-24 for the exact
        # same table-level staleness reasoning, its two same-run siblings were simply
        # never carried along. Same 30-day/INFO treatment as growth_metrics (new/
        # uncharacterized check, matching that precedent) until a production run
        # establishes the real false-positive rate.
        "value_metrics": 30,
        "quality_metrics": 30,
        # momentum_metrics is written by load_risk_metrics_daily.py (separate loader,
        # terraform "stability_metrics" pipeline step) and feeds the Momentum pillar
        # directly (load_stock_scores.py reads FROM momentum_metrics) - same
        # never-had-a-staleness-entry gap, independently confirmed live 2026-09-13: 34
        # active symbols already >7d stale and 92 active symbols with zero row at all.
        "momentum_metrics": 7,
        # ADDED (goal session 2026-09-13, closing the gaps the new /api/scores/
        # correctness-coverage data_patrol_log-backed panel surfaced): these 5 tables are
        # all real, actively-loaded pillar-input tables (confirmed via LOADER_TABLES/
        # PSEUDO_LOADER_TABLES membership) that had ZERO data_patrol_log rows EVER - not
        # just no staleness entry, no DataPatrol check of any kind had ever run against
        # them. Same "new/uncharacterized check" INFO-severity treatment as value_metrics/
        # quality_metrics/momentum_metrics above until a production run establishes the
        # real false-positive rate - not proven-safe enough yet for WARN/ERROR/CRIT.
        #
        # analyst_sentiment_analysis: load_analyst_sentiment_analysis.py's own
        # primary_key=("symbol","date")/watermark_field="date" writes one new row per
        # active symbol per trading day (same shape as price_daily), so a short
        # trading-day-aware threshold is safe.
        "analyst_sentiment_analysis": 3,
        # dividend_data: primary_key=("symbol","ex_dividend_date") - per-symbol dividend
        # events are inherently sparse (quarterly/semi-annual), but load_dividend_data.py
        # writes a new row whenever ANY symbol in the ~4,900-symbol universe goes
        # ex-dividend, so MAX(ex_dividend_date) across the whole table should stay recent
        # in aggregate even though no single symbol updates often - live-confirmed 2026-09-13:
        # 27,708 rows with ex_dividend_date in the last 14 days alone. Calendar-day math
        # (not trading-day), same as the other non-"daily"-freq entries below.
        "dividend_data": 14,
        # earnings_metrics: load_earnings_metrics.py's own watermark_field="updated_at"
        # (not report_date, part of its primary key but not the refresh signal) - this
        # loader continuously revises rows as new estimates/actuals arrive, live-confirmed
        # MAX(updated_at) same-day. Same 30-day/INFO treatment as growth_metrics/
        # value_metrics/quality_metrics above (siblings written by the same class of
        # per-symbol upsert loader).
        "earnings_metrics": 30,
        # current_reports_8k: load_current_reports_8k.py's own watermark_field=
        # "filing_date" - real SEC 8-K filings happen across the universe on essentially
        # every business day (live-confirmed 2026-09-13: 1,266 filings in the last 14 days
        # alone, latest filing_date 1 day old), so a short threshold is safe.
        "current_reports_8k": 5,
        # price_weekly: load_prices.py's own primary_key=("symbol","date")/
        # watermark_field="date" for weekly bars - same shape as price_daily/
        # technical_data_daily but weekly cadence. 10 days (not the bare 7 sector_ranking/
        # industry_ranking use) gives a deliberate buffer over one calendar week so a
        # single delayed weekly run right after a holiday week doesn't false-positive,
        # while this is still a brand-new/uncharacterized check (INFO, not WARN).
        "price_weekly": 10,
        # ADDED (goal session 2026-09-13, "patrols and checks"/quarantine-backlog audit):
        # naaim had ZERO staleness coverage at all despite load_naaim.py's own docstring
        # calling it "CRITICAL for market regime detection" - live-confirmed 46 days stale
        # (last row 2026-07-29) with data_loader_status still reporting status=COMPLETED,
        # consecutive_failures=0, invisible to every existing check. Root cause is a
        # permanent, already-documented condition (see load_naaim.py's own comments):
        # NAAIM put its Exposure Index behind a paywall 2026-08-01, so the loader
        # gracefully returns a no-op data_unavailable marker forever instead of erroring -
        # a real, standing gap operators should see, not a transient blip. WARN (not
        # INFO) since this is a known-permanent condition worth surfacing on every run
        # rather than a new/uncharacterized check still building a false-positive track
        # record - 14 days (double aaii_sentiment's weekly-cadence threshold) to tolerate
        # NAAIM's normal Wednesday publish cadence without false-positiving on a single
        # delayed week, back when the feed was still live.
        "naaim": 14,
        # ADDED (goal session 2026-09-13, follow-up to the naaim fix above - closing the
        # remaining 4 tables the correctness-coverage panel's new `cadence` field surfaced as
        # None): stability_metrics/sec_valuations/analyst_upgrade_downgrade/
        # analyst_earnings_estimates are all real, actively-loaded pillar-input tables with no
        # staleness entry at all - same structural blind spot as value_metrics/quality_metrics/
        # momentum_metrics above, just not caught until the cadence field made "no entry" visible
        # in the UI instead of only in this file's own history.
        #
        # stability_metrics: written by the SAME loader run as momentum_metrics
        # (loaders/load_risk_metrics_daily.py's RiskMetricsLoader, output_tables =
        # ["momentum_metrics", "stability_metrics"], one process, one pass - see that file's
        # `ON CONFLICT (symbol) DO UPDATE SET ... updated_at = CURRENT_TIMESTAMP`, refreshed on
        # every run same as its sibling). Same weekly/7-day/INFO treatment as momentum_metrics
        # for the exact same reason: a same-run sibling of an already-covered table, not a
        # separately-characterized check. Live-confirmed 2026-09-13: MAX(updated_at) is today,
        # 5148/5152 rows updated in the last 3 days.
        "stability_metrics": 7,
        # sec_valuations: loaders/load_sec_valuations.py's own primary_key=("symbol",)/
        # watermark_field="computed_at" (a plain date, set to date.today() on every write, not
        # a static insert stamp - same "use the loader's own declared watermark, not whichever
        # generic timestamp column happens to exist" reasoning as the stock_scores/
        # growth_metrics fixes above). Live-confirmed 2026-09-13: MAX(computed_at) is today,
        # 5029/5336 rows recomputed in the last 3 days - a near-universe-wide daily recompute,
        # so a short threshold is safe. "daily" freq (trading-day-aware), matching
        # analyst_sentiment_analysis's reasoning below rather than the bare calendar-day
        # sector_ranking/industry_ranking entries.
        "sec_valuations": 3,
        # analyst_upgrade_downgrade: loaders/load_analyst_upgrade_downgrade.py's own
        # primary_key=("symbol","action_date","firm")/watermark_field="action_date" - real
        # analyst rating actions happen across the ~4,900-symbol universe on essentially every
        # business day (live-confirmed 2026-09-13: 10,809 rows with action_date in the last 14
        # days alone), same shape as current_reports_8k's real-SEC-filing-cadence reasoning
        # above. "daily" freq (trading-day-aware).
        "analyst_upgrade_downgrade": 5,
        # analyst_earnings_estimates: loaders/load_analyst_earnings_estimates.py's own
        # primary_key=("symbol","date")/watermark_field="date" - continuously revised as new
        # forward estimates arrive, live-confirmed 2026-09-13: MAX(date) is today, 122,075 rows
        # (essentially universe-wide) with date in the last 30 days. "daily" freq
        # (trading-day-aware), same shape as analyst_sentiment_analysis below.
        "analyst_earnings_estimates": 3,
        # ADDED (goal session 2026-09-13, "patrols and checks" comprehensiveness audit):
        # systematic diff of every loaders/loader_registry.py LOADER_TABLES entry against
        # every DataPatrol checker's covered-table set (staleness/coverage/quality/tie-out/
        # everything) found 19 more real, actively-loaded tables with ZERO coverage of any
        # kind - not just no staleness entry, no check at all. All live-confirmed fresh as
        # of 2026-09-13 before adding. Same "new/uncharacterized check" INFO-severity
        # treatment as every batch above until a production run establishes the real
        # false-positive rate.
        "algo_metrics_daily": 3,  # daily capital-routing input, same cadence as market_health_daily
        "capital_routing_daily": 3,  # daily, same reasoning
        "company_info_sec": 30,  # per-symbol SEC company master data, slow-changing
        "company_profile": 30,  # per-symbol company metadata, slow-changing
        "earnings_calendar": 5,  # real analyst-estimate earnings dates, updated most business days
        "economic_calendar": 10,  # macro calendar events, sparse but real cadence
        "economic_data": 5,  # daily macro series (rates/inflation/etc.)
        "etf_price_daily": 3,  # daily ETF bars, same shape as price_daily but lower criticality
        "etf_price_monthly": 45,  # monthly bars, generous buffer over 30
        "etf_price_weekly": 10,  # weekly bars, same buffer reasoning as price_weekly
        "etf_symbols": 30,  # ETF universe membership/metadata, slow-changing
        # institutional_holdings_13f: 13F filings are quarterly with a 45-day SEC deadline
        # after quarter-end - same order-of-magnitude threshold as earnings_history.
        "institutional_holdings_13f": 100,
        "market_exposure_daily": 3,  # daily risk-exposure input
        "price_monthly": 45,  # monthly bars, same buffer as etf_price_monthly
        "sec_segment_info": 30,  # SEC XBRL segment disclosures, filed alongside financials
        "sec_segment_metrics": 30,  # derived from sec_segment_info, same cadence
        "sector_performance": 5,  # daily sector return series
        "sector_rotation_signal": 3,  # daily signal input
        # short_interest_finra: FINRA short-interest settlement dates publish bi-monthly
        # (twice a month) - a threshold under the ~15-day cadence would false-positive
        # every cycle.
        "short_interest_finra": 20,
        # ADDED (goal session 2026-09-13, staleness-coverage re-audit follow-up to the naaim/
        # 19-table batch above): fresh diff of every loader_registry.py LOADER_TABLES entry
        # against build_staleness_sources() found 3 more real, actively-loaded tables with
        # zero staleness coverage. All live-confirmed fresh as of 2026-09-13 before adding.
        # market_sentiment: written by load_market_status_daily.py alongside
        # market_health_daily/market_exposure_daily/capital_routing_daily/sector_rotation_signal
        # - all four siblings already have a staleness entry above, this one was missed.
        "market_sentiment": 3,
        # stock_symbols: universe membership table, same loader (load_market_constituents.py)
        # and same slow-changing shape as its sibling etf_symbols above, which already has a
        # staleness entry - this one was missed.
        "stock_symbols": 30,
        # signal_quality_scores: "Required by Phase 1 data freshness check as tier-2 gate for
        # filtering" per its own loader docstring - already freshness-gated by
        # phase1_data_completeness.py directly, but never checked via DataPatrol/
        # data_patrol_log, so it showed as a false "never checked" gap on the
        # correctness-coverage panel despite being one of the most operationally load-bearing
        # tables in the whole pipeline. Daily cadence, same as buy_sell_daily/technical_data_daily
        # which it's derived from.
        "signal_quality_scores": 3,
        # ADDED (goal session 2026-09-13, follow-up to the market_sentiment/stock_symbols/
        # signal_quality_scores batch above): the 6 core financial-statement tables
        # (load_financial_statements.py's real output, per-symbol incremental on each filer's
        # own filing cadence) had ZERO staleness coverage of any kind despite being the tables
        # this whole session's quarantine-backlog work revolves around, and despite being
        # actively written to continuously (36,834 annual_income_statement rows updated on
        # 2026-09-13 alone). A per-symbol "days since this filer's own last update" threshold
        # would be wrong here (a company's own quarterly filing being 80 days old between
        # real filings is normal, not stale - unlike every other table above with a genuine
        # daily/near-daily per-symbol cadence) - this is instead a coarse, TABLE-LEVEL "is the
        # loader still running at all" signal, the same role institutional_holdings_13f's
        # entry above plays for its own irregular SEC-driven cadence. Live-checked: this
        # table's daily row count never once hit zero over the last 10 days (min 12 rows on
        # 2026-09-08) even before today's flurry of quarantine-backlog fixes, so a short
        # threshold has real margin without false-positiving on a normal quiet day.
        "annual_income_statement": 5,
        "annual_balance_sheet": 5,
        "annual_cash_flow": 5,
        "quarterly_income_statement": 5,
        "quarterly_balance_sheet": 5,
        "quarterly_cash_flow": 5,
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
        (
            "value_metrics",
            "updated_at",
            "monthly",
            staleness_thresholds["value_metrics"],
            INFO,
        ),
        (
            "quality_metrics",
            "updated_at",
            "monthly",
            staleness_thresholds["quality_metrics"],
            INFO,
        ),
        (
            "momentum_metrics",
            "updated_at",
            "weekly",
            staleness_thresholds["momentum_metrics"],
            INFO,
        ),
        (
            # "daily" freq (trading-day-aware math, same reasoning as price_daily above) -
            # a new row per active symbol per trading day, so a plain calendar-day gap over
            # a 3-day weekend would sit right at this table's 3-day threshold.
            "analyst_sentiment_analysis",
            "date",
            "daily",
            staleness_thresholds["analyst_sentiment_analysis"],
            INFO,
        ),
        (
            "dividend_data",
            "ex_dividend_date",
            "monthly",
            staleness_thresholds["dividend_data"],
            INFO,
        ),
        (
            "earnings_metrics",
            "updated_at",
            "monthly",
            staleness_thresholds["earnings_metrics"],
            INFO,
        ),
        (
            # "daily" freq - real SEC 8-K filings cluster on business/trading days.
            "current_reports_8k",
            "filing_date",
            "daily",
            staleness_thresholds["current_reports_8k"],
            INFO,
        ),
        (
            "price_weekly",
            "date",
            "weekly",
            staleness_thresholds["price_weekly"],
            INFO,
        ),
        (
            "naaim",
            "date",
            "weekly",
            staleness_thresholds["naaim"],
            WARN,
        ),
        (
            "stability_metrics",
            "updated_at",
            "weekly",
            staleness_thresholds["stability_metrics"],
            INFO,
        ),
        (
            "sec_valuations",
            "computed_at",
            "daily",
            staleness_thresholds["sec_valuations"],
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
            "analyst_earnings_estimates",
            "date",
            "daily",
            staleness_thresholds["analyst_earnings_estimates"],
            INFO,
        ),
        ("algo_metrics_daily", "date", "daily", staleness_thresholds["algo_metrics_daily"], INFO),
        ("annual_balance_sheet", "updated_at", "daily", staleness_thresholds["annual_balance_sheet"], INFO),
        ("annual_cash_flow", "updated_at", "daily", staleness_thresholds["annual_cash_flow"], INFO),
        ("annual_income_statement", "updated_at", "daily", staleness_thresholds["annual_income_statement"], INFO),
        ("capital_routing_daily", "date", "daily", staleness_thresholds["capital_routing_daily"], INFO),
        ("company_info_sec", "updated_at", "monthly", staleness_thresholds["company_info_sec"], INFO),
        ("company_profile", "updated_at", "monthly", staleness_thresholds["company_profile"], INFO),
        ("earnings_calendar", "updated_at", "daily", staleness_thresholds["earnings_calendar"], INFO),
        ("economic_calendar", "updated_at", "weekly", staleness_thresholds["economic_calendar"], INFO),
        ("economic_data", "date", "daily", staleness_thresholds["economic_data"], INFO),
        ("etf_price_daily", "date", "daily", staleness_thresholds["etf_price_daily"], INFO),
        ("etf_price_monthly", "date", "monthly", staleness_thresholds["etf_price_monthly"], INFO),
        ("etf_price_weekly", "date", "weekly", staleness_thresholds["etf_price_weekly"], INFO),
        ("etf_symbols", "updated_at", "monthly", staleness_thresholds["etf_symbols"], INFO),
        (
            "institutional_holdings_13f",
            "updated_at",
            "quarterly",
            staleness_thresholds["institutional_holdings_13f"],
            INFO,
        ),
        ("market_exposure_daily", "date", "daily", staleness_thresholds["market_exposure_daily"], INFO),
        ("market_sentiment", "date", "daily", staleness_thresholds["market_sentiment"], INFO),
        ("price_monthly", "date", "monthly", staleness_thresholds["price_monthly"], INFO),
        ("quarterly_balance_sheet", "updated_at", "daily", staleness_thresholds["quarterly_balance_sheet"], INFO),
        ("quarterly_cash_flow", "updated_at", "daily", staleness_thresholds["quarterly_cash_flow"], INFO),
        (
            "quarterly_income_statement",
            "updated_at",
            "daily",
            staleness_thresholds["quarterly_income_statement"],
            INFO,
        ),
        ("sec_segment_info", "updated_at", "monthly", staleness_thresholds["sec_segment_info"], INFO),
        ("sec_segment_metrics", "updated_at", "monthly", staleness_thresholds["sec_segment_metrics"], INFO),
        ("sector_performance", "date", "daily", staleness_thresholds["sector_performance"], INFO),
        ("sector_rotation_signal", "date", "daily", staleness_thresholds["sector_rotation_signal"], INFO),
        ("short_interest_finra", "updated_at", "monthly", staleness_thresholds["short_interest_finra"], INFO),
        ("signal_quality_scores", "date", "daily", staleness_thresholds["signal_quality_scores"], INFO),
        ("stock_symbols", "updated_at", "monthly", staleness_thresholds["stock_symbols"], INFO),
    ]
    return sources


class StalenessChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        """Execute staleness checks."""
        self.results = []

        # Table configurations: (table, date_column, freq, max_days_allowed,
        # severity_on_stale) - see build_staleness_sources() above, the single source of
        # truth this method and the correctness-coverage API endpoint both read from.
        sources = build_staleness_sources()

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
                    # FIXED 2026-09-13 (goal: patrol/quarantine comprehensiveness audit): this
                    # used to `raise RuntimeError(error_msg)` here for critical tables, with a
                    # comment claiming it would "raise immediately to halt algo" - but this
                    # raise sits inside the per-table `try` whose own `except Exception` below
                    # catches everything, so it was dead code: silently swallowed, re-logged as
                    # a generic "Check failed" ERROR, rolled back, and the loop moved on to the
                    # next table anyway. Even if it HAD propagated, that would have been worse,
                    # not better - Phase 1 halts based on CRIT/ERROR rows in data_patrol_log
                    # (_check_data_patrol_results), not on this process crashing, and the CRIT
                    # log write two lines above already satisfies that. Letting the exception
                    # escape this checker would only have aborted every table AFTER this one in
                    # `sources`, silently losing their staleness coverage for the run - the
                    # opposite of the intended effect. Removed; the log write above already does
                    # everything the raise was trying to do, without the coverage loss.
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
        self._check_frozen_technical_symbols(cur)
        self._check_frozen_trend_template_symbols(cur)

        # PER-SYMBOL FROZEN/MISSING PILLAR-METRICS CHECK (added 2026-09-13, goal session
        # "data integrity gaps galore... gaps in our approach" meta-gap sweep). The
        # frozen-subpopulation blind spot above was fixed pointwise for stock_scores
        # (2026-09-08) and price_daily (2026-09-08) after each was live-caught separately -
        # but never generalized, so the same blind spot was still wide open for every other
        # single-row-per-symbol pillar-input table (growth_metrics/momentum_metrics/
        # value_metrics/quality_metrics all upsert via ON CONFLICT (symbol) DO UPDATE, the
        # exact shape that lets a silently-dropped subpopulation go undetected forever).
        # None of these four had ANY per-symbol coverage: CoverageChecker.check_loader_coverage
        # structurally can't see them either (its UNION query requires a `date` column these
        # tables don't have - they're single-row-per-symbol via `updated_at`, not date-keyed).
        # Live-confirmed on the local DB before adding this: momentum_metrics had 34 active
        # symbols already >7d frozen AND 92 active symbols with zero row at all; value_metrics/
        # quality_metrics each had 90 active symbols with zero row, and growth_metrics itself
        # (despite already having a table-level check above) had 2 frozen + 90 missing -
        # proof the table-level check alone was never enough for any of these four.
        # WARN only, same reasoning as every other frozen-subpopulation check in this file: a
        # residual handful of symbols with a real per-symbol data ceiling is expected, this is
        # a signal to investigate WHY a population is stuck/missing, not an automatic halt.
        #
        # EXTENDED (same session, immediately after landing the four above): the "generalized"
        # fix above was itself still pointwise - stability_metrics (loaders/
        # load_risk_metrics_daily.py's secondary output, ON CONFLICT (symbol) - confirmed via
        # `grep -oE "FROM [a-z_]+" loaders/load_stock_scores.py`, it's a real, current Risk-
        # pillar scoring input) is the exact same shape and was left off this list.
        # Live-confirmed before adding: 133 active symbols with zero stability_metrics row at
        # all. positioning_metrics (loaders/load_positioning_metrics.py, also ON CONFLICT
        # (symbol)) is included too even though it was explicitly REMOVED as a stock_scores
        # scoring dependency 2026-08-27 (see load_stock_scores.py's own comments at that date) -
        # it's still a real, currently-populated table surfaced directly via the scores API's
        # positioning_inputs field (load_stock_scores.py:1044/1170), so silent staleness there
        # degrades what the API/dashboard shows even though it no longer feeds a pillar score.
        # Live-confirmed: 37 active symbols frozen >7d behind AND 101 with zero row at all.
        # Lesson: a "generalized" fix built by reasoning from one bug's evidence trail can still
        # miss same-shape siblings that weren't part of that trail - checked
        # `grep -oE "FROM [a-z_]+" loaders/load_stock_scores.py` afterward to confirm no further
        # ON CONFLICT (symbol) sibling was still missing from this list.
        for pillar_table in (
            "growth_metrics",
            "momentum_metrics",
            "value_metrics",
            "quality_metrics",
            "stability_metrics",
            "positioning_metrics",
        ):
            self._check_frozen_pillar_metrics_symbols(cur, pillar_table)

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

    def _check_frozen_technical_symbols(self, cur: Any) -> None:
        """PER-SYMBOL FROZEN-TECHNICAL-INDICATOR CHECK (added 2026-09-13, goal: "data
        integrity gaps galore... gaps in our approach" session).

        Same underlying gap as `_check_frozen_price_symbols`/the frozen-stock_scores check
        above, a third table over: technical_data_daily's table-level staleness check (top of
        run()) only looks at MAX(date) across the whole table, so it stays "fresh" even when a
        subpopulation of active symbols silently stops getting new technical-indicator rows.
        Live-caught 2026-09-13: 136 active symbols (a cluster of BlackRock closed-end funds -
        BBN/BCAT/BCX/BDJ/BGR/BGT/BGY/BHK/BHV/BIT/BKT/BLW/BME/BMEZ/BOE/BST/BSTZ - plus others
        like ACHV/AFBI/ALOT/AVNS/EFA) had CURRENT price_daily data (today's close present) but
        technical_data_daily frozen anywhere from 5 trading days to 5+ weeks stale (some as far
        back as 2026-08-03), invisible to both the table-level MAX(date) check and to
        coverage.py's threshold check (which only sees an aggregate percentage, not which
        specific symbols or how stale). This is what was silently driving
        technical_data_daily/trend_template_data's coverage ERROR (96.0% < 96% threshold) - a
        real, currently-live gap, not noise.

        Compares each symbol's OWN technical_data_daily watermark against its OWN price_daily
        watermark (not the table-wide MAX like the price/score siblings) - the right comparison
        here, since technical indicators are *derived from* price and can never be fresher than
        their own price input. A symbol whose price_daily is itself stale is correctly excluded
        (nothing frozen to blame on the indicator loader) - this is deliberately not
        `_check_frozen_price_symbols`'s frozen-price population re-surfacing here, it isolates
        the "price is fine, indicators aren't" signature that's specific to this loader.

        WARN only - same reasoning as its two siblings: a signal to investigate a silent
        per-symbol backlog, not an automatic halt.
        """
        sp_frozen_technical = "sp_stale_technical_data_daily_frozen_symbols"
        try:
            cur.execute(f"SAVEPOINT {sp_frozen_technical}")
            cur.execute(
                """
                SELECT COUNT(*)
                FROM stock_symbols sy
                JOIN (
                    SELECT symbol, MAX(date) AS latest_date
                    FROM price_daily
                    GROUP BY symbol
                ) pd ON pd.symbol = sy.symbol
                LEFT JOIN (
                    SELECT symbol, MAX(date) AS latest_date
                    FROM technical_data_daily
                    GROUP BY symbol
                ) td ON td.symbol = sy.symbol
                WHERE sy.active = true
                  AND pd.latest_date >= (SELECT MAX(date) - INTERVAL '1 day' FROM price_daily)
                  AND (td.latest_date IS NULL OR td.latest_date < pd.latest_date - INTERVAL '7 days')
                """
            )
            frozen_technical_count = cur.fetchone()[0]
            if frozen_technical_count > 0:
                self.log(
                    "staleness",
                    WARN,
                    "technical_data_daily",
                    f"{frozen_technical_count} active symbols have current price_daily data but "
                    f"technical_data_daily rows more than 7 days behind their own price_daily "
                    f"watermark (or no technical_data_daily row at all) - check for a silent "
                    f"per-symbol loader backlog in load_technical_indicators.py",
                    {"frozen_technical_symbol_count": frozen_technical_count},
                )
            else:
                self.log(
                    "staleness",
                    INFO,
                    "technical_data_daily",
                    "no active symbols with current price_daily frozen on technical_data_daily",
                    {"frozen_technical_symbol_count": 0},
                )
        except Exception as e:
            self.log("staleness", ERROR, "technical_data_daily", f"Frozen-technical check failed: {e}", None)
            try:
                cur.execute(f"ROLLBACK TO SAVEPOINT {sp_frozen_technical}")
            except Exception as rollback_err:
                logger.error(
                    f"CRITICAL: ROLLBACK TO SAVEPOINT {sp_frozen_technical} failed: {rollback_err}. Connection corrupted."
                )
                raise RuntimeError(
                    f"Database connection corrupted during frozen-technical check rollback: {rollback_err}"
                ) from rollback_err
        finally:
            try:
                cur.execute(f"RELEASE SAVEPOINT {sp_frozen_technical}")
            except Exception as release_err:
                logger.error(
                    f"CRITICAL: RELEASE SAVEPOINT {sp_frozen_technical} failed: {release_err}. Connection corrupted."
                )
                raise RuntimeError(
                    f"Database connection corrupted during frozen-technical-cleanup check: {release_err}"
                ) from release_err

    def _check_frozen_trend_template_symbols(self, cur: Any) -> None:
        """PER-SYMBOL FROZEN-TREND-TEMPLATE CHECK (added 2026-09-13, same session as
        `_check_frozen_technical_symbols` - see that method's own docstring for the full
        evidence trail this mirrors).

        trend_template_data (computed by loaders/load_trend_analysis.py from price_daily, a
        separate loader from technical_data_daily though correlated in practice - both
        derive from the same price input) showed the identical shape live-checked 2026-09-13:
        40 active symbols with current price_daily but trend_template_data frozen >7 days
        behind their own price watermark - the same population size as the technical_data_daily
        gap this session already fixed, consistent with a shared root cause upstream in price
        data rather than two independent bugs, but this table's own coverage ERROR
        (technical_data_daily/trend_template_data both flagged 96.0% < 96% in the same run)
        needs its own per-symbol visibility - coverage.py's aggregate check can't tell which of
        the two tables (or both) a given frozen symbol belongs to.

        WARN only, matching every other frozen-symbol check in this file.
        """
        sp_frozen_trend = "sp_stale_trend_template_data_frozen_symbols"
        try:
            cur.execute(f"SAVEPOINT {sp_frozen_trend}")
            cur.execute(
                """
                SELECT COUNT(*)
                FROM stock_symbols sy
                JOIN (
                    SELECT symbol, MAX(date) AS latest_date
                    FROM price_daily
                    GROUP BY symbol
                ) pd ON pd.symbol = sy.symbol
                LEFT JOIN (
                    SELECT symbol, MAX(date) AS latest_date
                    FROM trend_template_data
                    GROUP BY symbol
                ) tt ON tt.symbol = sy.symbol
                WHERE sy.active = true
                  AND pd.latest_date >= (SELECT MAX(date) - INTERVAL '1 day' FROM price_daily)
                  AND (tt.latest_date IS NULL OR tt.latest_date < pd.latest_date - INTERVAL '7 days')
                """
            )
            frozen_trend_count = cur.fetchone()[0]
            if frozen_trend_count > 0:
                self.log(
                    "staleness",
                    WARN,
                    "trend_template_data",
                    f"{frozen_trend_count} active symbols have current price_daily data but "
                    f"trend_template_data rows more than 7 days behind their own price_daily "
                    f"watermark (or no trend_template_data row at all) - check for a silent "
                    f"per-symbol loader backlog in load_trend_analysis.py",
                    {"frozen_trend_template_symbol_count": frozen_trend_count},
                )
            else:
                self.log(
                    "staleness",
                    INFO,
                    "trend_template_data",
                    "no active symbols with current price_daily frozen on trend_template_data",
                    {"frozen_trend_template_symbol_count": 0},
                )
        except Exception as e:
            self.log("staleness", ERROR, "trend_template_data", f"Frozen-trend-template check failed: {e}", None)
            try:
                cur.execute(f"ROLLBACK TO SAVEPOINT {sp_frozen_trend}")
            except Exception as rollback_err:
                logger.error(
                    f"CRITICAL: ROLLBACK TO SAVEPOINT {sp_frozen_trend} failed: {rollback_err}. Connection corrupted."
                )
                raise RuntimeError(
                    f"Database connection corrupted during frozen-trend-template check rollback: {rollback_err}"
                ) from rollback_err
        finally:
            try:
                cur.execute(f"RELEASE SAVEPOINT {sp_frozen_trend}")
            except Exception as release_err:
                logger.error(
                    f"CRITICAL: RELEASE SAVEPOINT {sp_frozen_trend} failed: {release_err}. Connection corrupted."
                )
                raise RuntimeError(
                    f"Database connection corrupted during frozen-trend-template check cleanup: {release_err}"
                ) from release_err

    def _check_frozen_pillar_metrics_symbols(self, cur: Any, table: str) -> None:
        """Generalized frozen/missing-row check for single-row-per-symbol pillar tables.

        See the call site's comment in run() for the full evidence trail (2026-09-13). Covers
        both failure shapes in one pass, since they're the same underlying loader-side
        subpopulation-drop bug: a symbol whose row exists but hasn't been refreshed
        (frozen), and a symbol with no row at all (missing) - the latter is invisible to a
        pure MAX(updated_at)-per-symbol frozen check and wasn't caught by CoverageChecker
        either (its coverage query requires a `date` column these tables don't have).
        """
        table_safe = assert_safe_table(table)
        sp = f"sp_stale_{table_safe}_frozen_symbols"
        try:
            cur.execute(f"SAVEPOINT {sp}")
            cur.execute(
                f"""
                SELECT
                    COUNT(*) FILTER (
                        WHERE t.updated_at < (SELECT MAX(updated_at) - INTERVAL '7 days' FROM {table_safe})
                    ) AS frozen_count,
                    COUNT(*) FILTER (WHERE t.symbol IS NULL) AS missing_count
                FROM stock_symbols sy
                LEFT JOIN {table_safe} t ON t.symbol = sy.symbol
                WHERE sy.active = true
                """
            )
            row = cur.fetchone()
            frozen_count = row[0] or 0
            missing_count = row[1] or 0
            if frozen_count > 0 or missing_count > 0:
                self.log(
                    "staleness",
                    WARN,
                    table,
                    f"{table}: {frozen_count} active symbols frozen more than 7 days behind "
                    f"the table's latest updated_at, {missing_count} active symbols have no "
                    f"row at all - check for a silent per-symbol loader backlog/exclusion",
                    {"frozen_symbol_count": frozen_count, "missing_symbol_count": missing_count},
                )
            else:
                self.log(
                    "staleness",
                    INFO,
                    table,
                    f"no active symbols frozen or missing in {table}",
                    {"frozen_symbol_count": 0, "missing_symbol_count": 0},
                )
        except Exception as e:
            self.log("staleness", ERROR, table, f"Frozen/missing-symbol check failed: {e}", None)
            try:
                cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            except Exception as rollback_err:
                logger.error(f"CRITICAL: ROLLBACK TO SAVEPOINT {sp} failed: {rollback_err}. Connection corrupted.")
                raise RuntimeError(
                    f"Database connection corrupted during {table} frozen-symbol check rollback: {rollback_err}"
                ) from rollback_err
        finally:
            try:
                cur.execute(f"RELEASE SAVEPOINT {sp}")
            except Exception as release_err:
                logger.error(f"CRITICAL: RELEASE SAVEPOINT {sp} failed: {release_err}. Connection corrupted.")
                raise RuntimeError(
                    f"Database connection corrupted during {table} frozen-symbol check cleanup: {release_err}"
                ) from release_err
