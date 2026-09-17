#!/usr/bin/env python3
"""Consolidated Risk Metrics Loader - Momentum + Stability (single pass, parallel write).

Consolidates load_momentum_metrics.py + load_stability_metrics.py into single invocation:
- Computes momentum (1m/3m/6m/12m) from price_daily
- Computes stability (30d/60d/252d vol + beta) from price_daily (SPY correlation)
- Writes to momentum_metrics table AND stability_metrics table in parallel
- Eliminates redundant symbol iteration and error handling boilerplate

Consolidation savings:
- 25-30% reduction in parallelism overhead (one loader instead of two parallel)
- Single database connection per symbol instead of two
- Unified watermark tracking (faster incremental updates)
- 734 lines of consolidated code

Error handling: Returns explicit data_unavailable markers for any metric that fails.
"""

import sys

import psycopg2

from loaders.loader_helper import setup_imports

setup_imports()

import logging  # noqa: E402
import math  # noqa: E402
from datetime import date, datetime, timezone  # noqa: E402
from typing import Any  # noqa: E402

from algo.infrastructure import MarketCalendar  # noqa: E402
from loaders.runner import run_loader  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.infrastructure.timezone import EASTERN_TZ  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402
from utils.type_conversion import safe_float  # noqa: E402

logger = logging.getLogger(__name__)

# DASTD_HALFLIFE_DAYS: Barra USE4's own published half-life for its Volatility descriptor's
# EWMA (exponentially weighted daily standard deviation) input - 42 trading days. See
# _calculate_volatility's own docstring for the full citation and rationale; not a value
# tuned against this repo's data, it's the literature's own published constant.
DASTD_HALFLIFE_DAYS = 42.0
DASTD_DECAY_FACTOR = 0.5 ** (1.0 / DASTD_HALFLIFE_DAYS)

# STALE_PRICE FIX 2026-09-01 (/goal session - user live-questioned FBRX ranking #1 in
# Momentum despite, per the user, apparently not even trading). Root cause: FBRX was
# acquired by argenx via a $77/share tender offer that completed 2026-08-27 (8-K on file:
# item_2_01 Completion of Acquisition + item_3_01 Notice of Delisting, both true) - real
# trading stopped after 2026-08-26's close. `_compute_momentum_row` below sets
# `today = sorted_dates[-1]` (whatever the SYMBOL's own latest price_daily row happens to
# be) with no check against the actual current date, so a symbol whose price feed has gone
# silent (delisted, halted, or a persistent per-symbol fetch failure) keeps having its last
# real close treated as "current" forever - momentum/ROC computed off an increasingly stale
# window, with no gate, no flag, nothing to distinguish it from a live, actively-traded
# stock. table-level DataAgeValidator checks (see load_technical_indicators.py) don't catch
# this either: the universe as a whole is fresh, only this one symbol has gone dark. A
# 3-trading-day threshold tolerates the normal 1-day pipeline-timing gap (self-heals per
# technical_data_daily_price_daily_load_order_race_20260824 in memory) while still catching
# a genuinely-stopped-trading symbol well before it can dominate momentum rankings the way
# FBRX did here (roc_60d=303%, roc_252d=331%, top momentum leader, five calendar days after
# it stopped trading).
STALE_PRICE_TRADING_DAYS_THRESHOLD = 3


class RiskMetricsLoader(OptimalLoader):
    """Consolidated momentum + stability metrics loader.

    Computes both metrics in single symbol pass, writes to both tables.
    Uses OptimalLoader's parallelism but processes all metrics per symbol.
    """

    # SESSION 113 FIX: Declare all output tables so runner.py marks them all COMPLETED/FAILED
    # This loader writes to both momentum_metrics (primary) and stability_metrics (secondary).
    # Without this, runner.py would only mark momentum_metrics, leaving stability_metrics stuck FAILED.
    output_tables = ["momentum_metrics", "stability_metrics"]

    table_name = "momentum_metrics"  # Primary table for watermark tracking
    primary_key = ("symbol",)
    watermark_field = "created_at"
    exclude_etfs_from_symbols = True
    # ADDED 2026-09-13 (composite-score structural audit): both momentum_metrics and
    # stability_metrics (this loader's two output tables, feeding stock_scores' Momentum and
    # Risk pillars) are computed purely from price/technical data - no financial-statement
    # dependency at all (see _compute_momentum_row/_compute_stability_row below). The
    # exclude_etfs_from_symbols=True above was, via get_active_symbols()'s implicit-default
    # coupling, ALSO silently excluding BDCs/CEFs/trusts - real, tradeable securities that need
    # Risk/Momentum scoring same as any other stock, same reasoning already established for
    # load_prices.py's own exclude_non_operating=False fix. See
    # frozen_subpopulation_real_root_cause_and_live_gap_20260913 in memory for the live-confirmed
    # 124-symbol gap this closes (partially - value/quality/growth-derived pillars for these
    # symbols remain gated at their own loaders pending the same review).
    exclude_non_operating_from_symbols = False

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute momentum and stability metrics for symbol in single pass.

        Returns momentum_metrics row (this loader's primary table).
        Side effect: Also writes to stability_metrics table for same symbol.
        """
        momentum_row = self._compute_momentum_row(symbol)
        stability_row = self._compute_stability_row(symbol)

        # Write stability metrics to its table (side effect during fetch)
        self._persist_stability_metrics(stability_row)

        # Return momentum row for OptimalLoader to persist to momentum_metrics
        return [momentum_row]

    def _compute_momentum_row(self, symbol: str) -> dict[str, Any]:
        try:
            with DatabaseContext("read") as cur:
                # SPLIT_ADJUSTED FIX 2026-09-15 (see _compute_stability_row's own docstring note
                # for the 2026-09-01 adj_close evidence trail this supersedes): adj_close alone
                # doesn't cover Alpaca-sourced rows, since Alpaca's raw adjustment mode writes
                # adj_close == close (no split adjustment at all) - exactly the AKTS-class bug
                # cited above (69,200% "return" from an unadjusted reverse split) can still occur
                # for any Alpaca-primary symbol. price_daily_split_adjusted (migration 1298)
                # computes the correct split-adjusted value at read time from price_daily joined
                # against stock_splits, covering both vendors uniformly - see that view's own
                # docstring for why raw price_daily can't just be mutated in place instead.
                cur.execute(
                    "SELECT date, adj_close_adjusted FROM price_daily_split_adjusted "
                    "WHERE symbol = %s ORDER BY date DESC LIMIT 253",
                    (symbol,),
                )
                rows = cur.fetchall()

                # FIX 2026-07-20: Previously required the full 252 days (needed only
                # for 12m momentum) before computing ANYTHING, discarding real 1m/3m/6m
                # momentum for the ~2,400 symbols with partial history (recent IPOs,
                # newly-listed names). The per-period loop below already handles partial
                # windows gracefully (target_idx < 0 -> None for that period only); the
                # downstream consumer (_score_momentum in load_stock_scores.py) is
                # explicitly documented to work from "≥1 momentum field" and normalizes
                # by the weight of whichever timeframes are available. 22 days is the
                # floor: the shortest window (1m = 21 days back) needs a day-0 anchor.
                if len(rows) < 22:
                    raise RuntimeError(
                        f"Insufficient price history: {len(rows)} days (need at least 22 for 1m momentum)"
                    )

                prices = {row[0]: safe_float(row[1], f"{symbol}.close[{row[0]}]", allow_none=False) for row in rows}
                sorted_dates = sorted(prices.keys())

                today = sorted_dates[-1]

                # STALE_PRICE FIX 2026-09-01: see module-level STALE_PRICE_TRADING_DAYS_THRESHOLD
                # comment - don't compute momentum off a frozen close as if it were current.
                now_et = datetime.now(EASTERN_TZ).date()
                days_stale = MarketCalendar.trading_days_elapsed(today, now_et)
                if days_stale > STALE_PRICE_TRADING_DAYS_THRESHOLD:
                    raise RuntimeError(
                        f"Stale price data: last close {today} is {days_stale} trading days old "
                        f"(threshold {STALE_PRICE_TRADING_DAYS_THRESHOLD}) - symbol likely halted/"
                        "delisted/acquired, not computing momentum from a frozen price"
                    )

                momentum: dict[str, float | None] = {}
                # FIX 2026-08-28 (goal: repo-wide data-coverage audit, same "NULL with no
                # reason recorded" bug class already fixed for growth_metrics/quality_metrics/
                # value_metrics - see growth_metrics_66_symbol_unknown_reason_fixed_20260828 in
                # memory): every branch below that nulls a single period used to do so silently -
                # this table has only one row-level reason/reason_type pair (unlike
                # stability_metrics's per-field *_unavailable_reason columns), which stayed None
                # on this success path even when a period was nulled. Live-confirmed root cause
                # for AKTS (2,197 days of price history, momentum_12m NULL, reason NULL): its
                # 12mo-ago close was $0.0372 vs today's $25.78 (~69,200% raw return) - an
                # unadjusted reverse split hitting the overflow guard below, not a data gap.
                # 240/272 universe-wide momentum_12m NULLs hit this exact silent-reason gap.
                period_null_reasons: dict[str, str] = {}
                for period_name, days_back in [("1m", 21), ("3m", 63), ("6m", 126), ("12m", 252)]:
                    target_idx = len(sorted_dates) - days_back - 1
                    if target_idx < 0:
                        momentum[f"momentum_{period_name}"] = None
                        period_null_reasons[f"momentum_{period_name}"] = "insufficient_price_history"
                        continue

                    price_old = prices[sorted_dates[target_idx]]
                    price_new = prices[today]

                    if price_old is None or price_old == 0:
                        momentum[f"momentum_{period_name}"] = None
                        period_null_reasons[f"momentum_{period_name}"] = "zero_or_missing_anchor_price"
                        continue

                    ret_pct = ((price_new - price_old) / price_old) * 100
                    # FIX 2026-08-19: momentum_metrics.momentum_{1m,3m,6m,12m} are NUMERIC(8,4)
                    # (max magnitude 9999.9999). Live-confirmed DFNS crashed this loader's write
                    # every run with "numeric field overflow" - an extreme micro-cap price move
                    # (reverse split, near-worthless-to-recovered, etc.) over the lookback window
                    # produces a >=10,000% return, same "extreme micro-cap volatility" failure
                    # mode already guarded for roc_Xd via ROC_OVERFLOW_SKIP in load_prices.py.
                    # Null out just this one implausible period instead of crashing DFNS's whole
                    # row - the other momentum periods and technical fields are still real data.
                    # NOTE 2026-09-01: this guard only catches the extreme (>=9999%) tail - see
                    # `prices` above (now built from adj_close, not raw close) for the actual
                    # root-cause fix. AKTS's cited case (an unadjusted reverse split) is exactly
                    # the class this magnitude-only guard was papering over without fixing: a
                    # smaller-magnitude split (e.g. 2:1, 3:1) stays well under 9999% and would
                    # have silently corrupted this period instead of nulling it. Left in place as
                    # defense-in-depth for genuinely extreme real moves, not removed.
                    if abs(ret_pct) >= 9999.0:
                        logger.warning(
                            f"[RISK_METRICS] {symbol}: momentum_{period_name}={ret_pct:.2f}% exceeds "
                            "NUMERIC(8,4) range - extreme micro-cap volatility (possibly delisted/"
                            "reverse-split security). Marking this period unavailable."
                        )
                        momentum[f"momentum_{period_name}"] = None
                        period_null_reasons[f"momentum_{period_name}"] = (
                            f"extreme_return_overflow(ret_pct={ret_pct:.2f})"
                        )
                        continue
                    momentum[f"momentum_{period_name}"] = round(ret_pct, 4)

                if all(v is None for v in momentum.values()):
                    raise RuntimeError("No momentum timeframe could be computed from available price history")

                partial_null_reason = (
                    "; ".join(f"{k}:{v}" for k, v in period_null_reasons.items())[:150] if period_null_reasons else None
                )

                # Fetch latest technical indicators from technical_data_daily (already computed by load_technical_indicators.py)
                technical = self._fetch_technical_indicators(symbol, today)

                return {
                    "symbol": symbol,
                    "momentum_1m": momentum.get("momentum_1m"),
                    "momentum_3m": momentum.get("momentum_3m"),
                    "momentum_6m": momentum.get("momentum_6m"),
                    "momentum_12m": momentum.get("momentum_12m"),
                    "rsi_14": technical.get("rsi_14"),
                    "macd_line": technical.get("macd_line"),
                    "macd_signal": technical.get("macd_signal"),
                    "price_vs_sma_50": technical.get("price_vs_sma_50"),
                    "price_vs_sma_200": technical.get("price_vs_sma_200"),
                    "roc_20d": technical.get("roc_20d"),
                    "roc_60d": technical.get("roc_60d"),
                    "roc_120d": technical.get("roc_120d"),
                    "roc_252d": technical.get("roc_252d"),
                    "data_unavailable": False,
                    "reason": partial_null_reason,
                    "reason_type": "partial_momentum_nulls" if partial_null_reason else None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

        except RuntimeError as e:
            logger.warning(f"[RISK_METRICS] {symbol}: momentum unavailable - {e}")
            return {
                "symbol": symbol,
                "momentum_1m": None,
                "momentum_3m": None,
                "momentum_6m": None,
                "momentum_12m": None,
                "rsi_14": None,
                "macd_line": None,
                "macd_signal": None,
                "price_vs_sma_50": None,
                "price_vs_sma_200": None,
                "roc_20d": None,
                "roc_60d": None,
                "roc_120d": None,
                "roc_252d": None,
                "data_unavailable": True,
                "reason": str(e)[:150],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.warning(f"[RISK_METRICS] Unexpected error for {symbol}: {type(e).__name__}: {e}")
            return {
                "symbol": symbol,
                "momentum_1m": None,
                "momentum_3m": None,
                "momentum_6m": None,
                "momentum_12m": None,
                "rsi_14": None,
                "macd_line": None,
                "macd_signal": None,
                "price_vs_sma_50": None,
                "price_vs_sma_200": None,
                "roc_20d": None,
                "roc_60d": None,
                "roc_120d": None,
                "roc_252d": None,
                "data_unavailable": True,
                "reason": f"unexpected_error: {type(e).__name__}",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

    def _fetch_technical_indicators(self, symbol: str, date_val: Any) -> dict[str, float | None]:
        """Fetch latest technical indicators from technical_data_daily table.

        These are pre-computed by load_technical_indicators.py. Just copy them
        into momentum_metrics so all momentum/technical data is in one place.
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT rsi_14, macd, macd_signal,
                           (close - sma_50) / sma_50 * 100 as price_vs_sma_50,
                           (close - sma_200) / sma_200 * 100 as price_vs_sma_200,
                           roc_20d, roc_60d, roc_120d, roc_252d
                    FROM technical_data_daily
                    WHERE symbol = %s AND date = %s
                    """,
                    (symbol, date_val),
                )
                row = cur.fetchone()
                if row:
                    return {
                        "rsi_14": safe_float(row[0], f"{symbol}.rsi_14", allow_none=True),
                        "macd_line": safe_float(row[1], f"{symbol}.macd_line", allow_none=True),
                        "macd_signal": safe_float(row[2], f"{symbol}.macd_signal", allow_none=True),
                        "price_vs_sma_50": safe_float(row[3], f"{symbol}.price_vs_sma_50", allow_none=True),
                        "price_vs_sma_200": safe_float(row[4], f"{symbol}.price_vs_sma_200", allow_none=True),
                        "roc_20d": safe_float(row[5], f"{symbol}.roc_20d", allow_none=True),
                        "roc_60d": safe_float(row[6], f"{symbol}.roc_60d", allow_none=True),
                        "roc_120d": safe_float(row[7], f"{symbol}.roc_120d", allow_none=True),
                        "roc_252d": safe_float(row[8], f"{symbol}.roc_252d", allow_none=True),
                    }
            return {
                "rsi_14": None,
                "macd_line": None,
                "macd_signal": None,
                "price_vs_sma_50": None,
                "price_vs_sma_200": None,
                "roc_20d": None,
                "roc_60d": None,
                "roc_120d": None,
                "roc_252d": None,
            }
        except Exception as e:
            logger.debug(f"[RISK_METRICS] {symbol}: technical indicators fetch failed: {e}")
            return {
                "rsi_14": None,
                "macd_line": None,
                "macd_signal": None,
                "price_vs_sma_50": None,
                "price_vs_sma_200": None,
                "roc_20d": None,
                "roc_60d": None,
                "roc_120d": None,
                "roc_252d": None,
            }

    def _get_debt_to_assets(self, symbol: str) -> float | None:
        """Fetch pre-computed debt_to_assets from quality_metrics (total_liabilities/total_assets).

        Independent of price history, so this is fetched regardless of whether the
        price-based volatility/beta computation below succeeds - stock_scores._score_stability
        has a standing 10%-weight slot for it (docstring: "MINIMUM DATA REQUIREMENT: At least
        one of volatility_252d/volatility_60d/beta/debt_to_assets must be non-NULL"), but no
        loader ever populated stability_metrics.debt_to_assets (confirmed 2026-07-20: 0/7155
        rows filled) even though quality_metrics already computes the identical ratio.
        """
        try:
            with DatabaseContext("read") as cur:
                # NOTE: Removed data_unavailable = FALSE filter to allow fetching debt_to_assets
                # even if quality_metrics is marked unavailable for other reasons
                cur.execute(
                    "SELECT debt_to_assets FROM quality_metrics WHERE symbol = %s",
                    (symbol,),
                )
                row = cur.fetchone()
            return safe_float(row[0], f"{symbol}.debt_to_assets", allow_none=True) if row else None
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"[RISK_METRICS] {symbol}: debt_to_assets lookup failed: {e}")
            return None

    def _compute_stability_row(self, symbol: str) -> dict[str, Any]:
        debt_to_assets = self._get_debt_to_assets(symbol)
        try:
            with DatabaseContext("read") as cur:
                # ADJ_CLOSE FIX 2026-09-01 (goal session - user live-questioned why scores
                # weren't matching expectations; dug into raw data rather than trusting prior
                # formula-level conclusions). Root cause, confirmed directly: price_daily.close
                # is NOT a reliable point-in-time historical price - Yahoo Finance retroactively
                # split-adjusts its "Close" field once a real split is processed on their
                # backend, REGARDLESS of yfinance's auto_adjust parameter (that flag only
                # controls dividend adjustment; splits get backward-applied to "Close" either
                # way, a well-documented yfinance/Yahoo quirk). Since this loader's ingestion
                # re-fetches/re-writes price_daily rows on different days, a historical date's
                # stored `close` can silently flip depending on WHEN it was last written
                # relative to any later-discovered split for that symbol. Live-confirmed on
                # MNST (a real 2:1 split ~2026-08-08/10): 4 pre-split dates (7/21, 7/22, 7/31,
                # 8/6) show the ALREADY-halved close while the surrounding dates correctly show
                # the true ~$95-99 pre-split price - not a one-time step, an oscillating
                # inconsistency. Result: volatility_60d read as 3.7450 (374.5% annualized) and
                # beta as 0.1123 for a large, stable consumer-staples company. `adj_close`
                # (fetched from yfinance's "Adj Close", split+dividend adjusted, see
                # utils/data/source_router.py) does NOT have this instability - it is the
                # correct series for return-math per standard finance practice (never compute
                # returns from a source that can retroactively rewrite history).
                # SPLIT_ADJUSTED FIX 2026-09-15: adj_close alone doesn't cover Alpaca-sourced
                # rows (adj_close == close there, no split adjustment applied at all) - now reads
                # price_daily_split_adjusted's adj_close_adjusted instead, which covers both
                # vendors correctly (see migration 1298 and _compute_momentum_row's matching fix
                # above for the full rationale).
                # close_adjusted/volume_adjusted (added alongside adj_close_adjusted for the
                # Amihud illiquidity computation below): their PRODUCT is dollar volume, and
                # both move oppositely for the same split (see migration 1298's own docstring:
                # volume divided by the same factor price is multiplied by), so the product is
                # split-invariant - dollar volume genuinely shouldn't jump around a split, and
                # this way it doesn't. Uses close_adjusted (raw close * split factor), not
                # adj_close_adjusted (also dividend-adjusted) - real daily dollar volume is
                # actual shares traded times the actual price that day, not a dividend-adjusted
                # synthetic price no trade ever executed at.
                cur.execute(
                    "SELECT date, adj_close_adjusted, close_adjusted, volume_adjusted "
                    "FROM price_daily_split_adjusted "
                    "WHERE symbol = %s ORDER BY date DESC LIMIT 252",
                    (symbol,),
                )
                rows = cur.fetchall()
                # Normalize dates to `date` objects immediately after fetching
                if rows:
                    rows = [
                        (
                            (
                                row[0].date()
                                if hasattr(row[0], "date")
                                else (
                                    date(row[0].year, row[0].month, row[0].day) if hasattr(row[0], "year") else row[0]
                                )
                            ),
                            row[1],
                            row[2],
                            row[3],
                        )
                        for row in rows
                    ]

                # STALE_PRICE FIX 2026-09-01 (/goal session - same root cause as
                # _compute_momentum_row's gate above, live-confirmed on WBS: Webster Financial,
                # a real actively-traded regional bank, ranked #4 in the Risk pillar with
                # risk_score=91.68 and #4 in Composite - off a price_daily feed frozen at
                # 2026-08-19, 13 trading days stale as of this fix (see
                # avb_eqr_wbs_yfinance_gap_reverified_still_open_20260901 in memory for the
                # known yfinance-outage root cause on this exact symbol). This method computes
                # volatility/beta from whatever the most recent 252 price_daily rows happen to
                # be with no check against the actual current date - same blind spot the
                # momentum gate above was built for, just unfixed on this sibling method in the
                # same loader. A stale-feed symbol's volatility/beta get silently reported as
                # current risk when they're actually a frozen historical window that may no
                # longer reflect the stock's real current risk profile.
                if rows:
                    latest_price_date = max(row[0] for row in rows)
                    now_et = datetime.now(EASTERN_TZ).date()
                    days_stale = MarketCalendar.trading_days_elapsed(latest_price_date, now_et)
                    if days_stale > STALE_PRICE_TRADING_DAYS_THRESHOLD:
                        reason = (
                            f"stale_price_data: last close {latest_price_date} is {days_stale} "
                            f"trading days old (threshold {STALE_PRICE_TRADING_DAYS_THRESHOLD}) - "
                            "symbol's price feed has stopped, not computing volatility/beta from "
                            "a frozen window"
                        )
                        logger.warning(f"[RISK_METRICS] {symbol}: stability unavailable - {reason}")
                        return {
                            "symbol": symbol,
                            "volatility_30d": None,
                            "volatility_60d": None,
                            "volatility_252d": None,
                            "downside_volatility_30d": None,
                            "downside_volatility_60d": None,
                            "downside_volatility_252d": None,
                            "max_drawdown_1y": None,
                            "beta": None,
                            "debt_to_assets": debt_to_assets,
                            "beta_unavailable_reason": "stale_price_data",
                            "volatility_30d_unavailable_reason": "stale_price_data",
                            "volatility_60d_unavailable_reason": "stale_price_data",
                            "volatility_252d_unavailable_reason": "stale_price_data",
                            "downside_volatility_30d_unavailable_reason": "stale_price_data",
                            "downside_volatility_60d_unavailable_reason": "stale_price_data",
                            "downside_volatility_252d_unavailable_reason": "stale_price_data",
                            "max_drawdown_1y_unavailable_reason": "stale_price_data",
                            "amihud_illiquidity_60d": None,
                            "amihud_illiquidity_60d_unavailable_reason": "stale_price_data",
                            "cmra_12m": None,
                            "cmra_12m_unavailable_reason": "stale_price_data",
                            "beta_bab": None,
                            "beta_bab_ts": None,
                            "beta_bab_rho": None,
                            "beta_bab_sigma_ratio": None,
                            "beta_bab_unavailable_reason": "stale_price_data",
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "data_unavailable": debt_to_assets is None,
                            "reason": reason if debt_to_assets is None else None,
                        }

                spy_rows: list[Any] = []
                if rows:
                    stock_dates = [row[0] for row in rows]
                    min_date = min(stock_dates)
                    max_date = max(stock_dates)
                    # SPLIT_ADJUSTED FIX 2026-09-15: same rationale as the two queries above -
                    # price_daily_split_adjusted covers Alpaca-sourced rows correctly too.
                    cur.execute(
                        "SELECT date, adj_close_adjusted FROM price_daily_split_adjusted "
                        "WHERE symbol = 'SPY' AND date >= %s AND date <= %s ORDER BY date ASC",
                        (min_date, max_date),
                    )
                    spy_rows_raw = cur.fetchall()
                    # Normalize SPY dates to `date` objects for consistency
                    spy_rows = (
                        [
                            (
                                (
                                    row[0].date()
                                    if hasattr(row[0], "date")
                                    else (
                                        date(row[0].year, row[0].month, row[0].day)
                                        if hasattr(row[0], "year")
                                        else row[0]
                                    )
                                ),
                                row[1],
                            )
                            for row in spy_rows_raw
                        ]
                        if spy_rows_raw
                        else []
                    )

                # CMRA raw inputs fetched here (still inside this `with` block - the cursor is
                # closed once it exits) - only `_calculate_cmra` itself (a pure function, no DB
                # access) runs later outside it. See `_get_cmra_monthly_inputs`'s own docstring.
                cmra_inputs = self._get_cmra_monthly_inputs(symbol, cur) if rows else None

                # BAB (Betting-Against-Beta, Frazzini & Pedersen 2014) fetch - still inside this
                # `with` block for the same reason cmra_inputs is (cursor closes once it exits;
                # `_calculate_beta_bab` itself is a pure function, no DB access). Separate, wider
                # (5yr) query from the 252-day window above - existing volatility/beta/CMRA
                # computations must not regress, so this does not reuse or resize `rows`.
                bab_series = self._fetch_bab_price_series(symbol, cur) if rows else None

            if not rows or len(rows) < 5:
                actual_rows = len(rows) if rows else 0
                reason = f"insufficient_price_history: {actual_rows}/5 days available"
                logger.warning(f"[RISK_METRICS] {symbol}: stability unavailable - {reason}")
                return {
                    "symbol": symbol,
                    "volatility_30d": None,
                    "volatility_60d": None,
                    "volatility_252d": None,
                    "downside_volatility_30d": None,
                    "downside_volatility_60d": None,
                    "downside_volatility_252d": None,
                    "max_drawdown_1y": None,
                    "beta": None,
                    "debt_to_assets": debt_to_assets,
                    "beta_unavailable_reason": "insufficient_price_history",
                    "volatility_30d_unavailable_reason": "insufficient_history",
                    "volatility_60d_unavailable_reason": "insufficient_history",
                    "volatility_252d_unavailable_reason": "insufficient_history",
                    "downside_volatility_30d_unavailable_reason": "insufficient_history",
                    "downside_volatility_60d_unavailable_reason": "insufficient_history",
                    "downside_volatility_252d_unavailable_reason": "insufficient_history",
                    "max_drawdown_1y_unavailable_reason": "insufficient_history",
                    "amihud_illiquidity_60d": None,
                    "amihud_illiquidity_60d_unavailable_reason": "insufficient_history",
                    "cmra_12m": None,
                    "cmra_12m_unavailable_reason": "insufficient_history",
                    "beta_bab": None,
                    "beta_bab_ts": None,
                    "beta_bab_rho": None,
                    "beta_bab_sigma_ratio": None,
                    "beta_bab_unavailable_reason": "insufficient_history",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "data_unavailable": debt_to_assets is None,  # All metrics failed; only debt_to_assets attempted
                    "reason": reason if debt_to_assets is None else None,
                }

            sorted_rows = sorted(rows, key=lambda r: r[0])
            prices = [(r[0], float(r[1])) for r in sorted_rows]

            returns = []
            # dollar_volumes[k] is index-aligned with returns[k] (both computed on the same
            # iteration, for the same day prices[i]) - required by
            # _calculate_amihud_illiquidity's own same-length-alignment contract.
            dollar_volumes: list[float | None] = []
            for i in range(1, len(prices)):
                if prices[i - 1][1] > 0:
                    ret = math.log(prices[i][1] / prices[i - 1][1])
                    returns.append(ret)
                    close_i, volume_i = sorted_rows[i][2], sorted_rows[i][3]
                    dollar_volumes.append(
                        float(close_i) * float(volume_i) if close_i is not None and volume_i is not None else None
                    )

            if not returns:
                reason = "invalid_price_data: no valid price transitions"
                logger.warning(f"[RISK_METRICS] {symbol}: stability unavailable - {reason}")
                return {
                    "symbol": symbol,
                    "volatility_30d": None,
                    "volatility_60d": None,
                    "volatility_252d": None,
                    "downside_volatility_30d": None,
                    "downside_volatility_60d": None,
                    "downside_volatility_252d": None,
                    "max_drawdown_1y": None,
                    "beta": None,
                    "debt_to_assets": debt_to_assets,
                    "beta_unavailable_reason": "insufficient_price_history",
                    "volatility_30d_unavailable_reason": "insufficient_history",
                    "volatility_60d_unavailable_reason": "insufficient_history",
                    "volatility_252d_unavailable_reason": "insufficient_history",
                    "downside_volatility_30d_unavailable_reason": "insufficient_history",
                    "downside_volatility_60d_unavailable_reason": "insufficient_history",
                    "downside_volatility_252d_unavailable_reason": "insufficient_history",
                    "max_drawdown_1y_unavailable_reason": "insufficient_history",
                    "amihud_illiquidity_60d": None,
                    "amihud_illiquidity_60d_unavailable_reason": "insufficient_history",
                    "cmra_12m": None,
                    "cmra_12m_unavailable_reason": "insufficient_history",
                    "beta_bab": None,
                    "beta_bab_ts": None,
                    "beta_bab_rho": None,
                    "beta_bab_sigma_ratio": None,
                    "beta_bab_unavailable_reason": "insufficient_history",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "data_unavailable": debt_to_assets is None,  # All metrics failed; only debt_to_assets attempted
                    "reason": reason if debt_to_assets is None else None,
                }

            # Calculate Amihud (2002) illiquidity - same 60-trading-day floor as vol_60d (its
            # own minimum meaningful-sample threshold, see _calculate_amihud_illiquidity's
            # docstring for the full rationale/citation).
            amihud_illiquidity_60d = (
                self._calculate_amihud_illiquidity(returns[-60:], dollar_volumes[-60:]) if len(returns) >= 60 else None
            )

            # Calculate CMRA (Barra US-E3's real Cumulative Range Volatility descriptor - see
            # `_calculate_cmra`'s own docstring for the primary-source citation). Genuinely
            # separate query/window from the 252-daily-return `returns` list above - CMRA needs
            # 13 real MONTH-END closes, not a slice of the daily series (fetched above, still
            # inside the `with DatabaseContext` block - `_calculate_cmra` itself is a pure
            # function and needs no DB access here).
            cmra_12m = self._calculate_cmra(*cmra_inputs) if cmra_inputs is not None else None

            # Calculate volatilities
            vol_30d = self._calculate_volatility(returns[-30:]) if len(returns) >= 30 else None
            vol_60d = self._calculate_volatility(returns[-60:]) if len(returns) >= 60 else None
            # BUG FIX (2026-07-27): vol_252d previously required only len(returns) >= 2 -
            # that floor came from _calculate_volatility's own divide-by-zero guard
            # (Bessel's correction needs len-1 >= 1), not a real "is this a meaningful
            # 252-day estimate" check. load_stock_scores.py._score_stability treats
            # volatility_252d as "12-month annualized volatility" and gives it 0.40 weight -
            # the single highest weight of any stability sub-component (more than
            # volatility_60d's 0.20 or volatility_30d's 0.15) - so a stock with e.g. 3-10
            # days of price history got a "252-day" figure computed from 2-9 daily returns,
            # confidently reported (data_unavailable=False) and given the most influence
            # over its stability score. Require the same floor volatility_60d already
            # enforces: vol_252d should never rest on a thinner sample than the mid-window
            # measure it's supposed to be a more-robust superset of.
            vol_252d = self._calculate_volatility(returns) if len(returns) >= 60 else None

            # Calculate downside volatilities (only negative returns - risk metric)
            downside_vol_30d = self._calculate_downside_volatility(returns[-30:]) if len(returns) >= 30 else None
            downside_vol_60d = self._calculate_downside_volatility(returns[-60:]) if len(returns) >= 60 else None
            downside_vol_252d = self._calculate_downside_volatility(returns) if len(returns) >= 60 else None

            # Calculate max drawdown over 252 days (peak-to-trough decline)
            max_drawdown_252d = self._calculate_max_drawdown([p[1] for p in prices]) if len(prices) >= 5 else None

            beta: float | dict[str, Any] | None = self._get_beta_from_db(symbol, prices, spy_rows)

            bab_result = self._calculate_beta_bab(*bab_series) if bab_series is not None else None
            beta_bab_reason: str | None = None if bab_result is not None else "insufficient_history"

            # Build unavailability reasons for any missing components
            unavailability_reasons = []
            if vol_30d is None and len(returns) < 30:
                unavailability_reasons.append(f"vol_30d: insufficient_returns ({len(returns)}/30 required)")
            if vol_60d is None and len(returns) < 60:
                unavailability_reasons.append(f"vol_60d: insufficient_returns ({len(returns)}/60 required)")
            if vol_252d is None and len(returns) < 60:
                unavailability_reasons.append(f"vol_252d: insufficient_returns ({len(returns)}/60 required)")
            # FIXED 2026-08-21 (goal session: missing-data root-cause audit): _get_beta_from_db
            # returns a specific, real reason (spy_price_data_insufficient/
            # insufficient_common_dates/insufficient_returns/spy_variance_zero/extreme_beta/
            # db_beta_error) for every failure mode - but until now that reason was only ever
            # folded into this function's own aggregate `unavailability_reason` log string;
            # beta_unavailable_reason (the column the coverage report and dashboard actually
            # read) was hardcoded to the single generic "missing_price_data" below regardless
            # of which of those six real causes applied. Live-confirmed: 100% of 217
            # null-beta stability_metrics rows carried that one generic string, most of them
            # for the identical "not enough history yet" cause volatility's sibling fields
            # correctly label "insufficient_history" right next to it - falling through to
            # "Other (errors / excluded)" in the coverage report instead of "Insufficient
            # history" (or "Implausible / rejected value" for extreme_beta).
            beta_reason: str | None = None
            if isinstance(beta, dict) and beta.get("data_unavailable"):
                beta_reason = str(beta.get("reason", "unknown"))
                unavailability_reasons.append(f"beta: {beta_reason}")
                beta = None

            # FIX 2026-07-20: Previously required ALL of vol_30d/vol_60d/vol_252d/beta
            # to mark the row available, discarding real computed values whenever any
            # one component was missing (e.g. a stock with 100 days of history gets a
            # real vol_252d-via-shorter-window... no, gets a real vol_30d/vol_60d but
            # no vol_252d, and the whole row was thrown away). Downstream consumer
            # load_stock_scores.py._score_stability() is explicitly documented to only
            # need ONE non-null field ("MINIMUM DATA REQUIREMENT: At least one of
            # volatility_252d/volatility_60d/beta/debt_to_assets must be non-NULL"), so
            # requiring all four upstream silently dropped real data the scorer was
            # designed to consume. Mark unavailable only if every component failed.
            has_any_metric = any(
                v is not None
                for v in [
                    vol_30d,
                    vol_60d,
                    vol_252d,
                    beta,
                    debt_to_assets,
                    downside_vol_30d,
                    downside_vol_60d,
                    downside_vol_252d,
                    max_drawdown_252d,
                    amihud_illiquidity_60d,
                    cmra_12m,
                ]
            )
            data_unavailable = not has_any_metric
            unavailability_reason: str | None = "; ".join(unavailability_reasons) if unavailability_reasons else None

            if data_unavailable and unavailability_reasons:
                logger.warning(f"[RISK_METRICS] {symbol}: incomplete stability metrics - {unavailability_reason}")

            return {
                "symbol": symbol,
                # `is not None` (not truthy) - a stock with an unchanged closing price for
                # its entire lookback window (illiquid/thinly-traded tickers, or a halted
                # symbol carrying a stale last price) genuinely computes to exactly 0.0, and
                # `if vol_Nd` would silently discard that real reading as unavailable.
                # load_stock_scores.py._score_stability checks `is not None` to decide
                # whether to include each component, so a falsely-NULLed 0.0 drops out of
                # the stability score entirely instead of correctly counting as "very low
                # volatility."
                "volatility_30d": round(vol_30d, 4) if vol_30d is not None else None,
                "volatility_60d": round(vol_60d, 4) if vol_60d is not None else None,
                "volatility_252d": round(vol_252d, 4) if vol_252d is not None else None,
                "downside_volatility_30d": round(downside_vol_30d, 4) if downside_vol_30d is not None else None,
                "downside_volatility_60d": round(downside_vol_60d, 4) if downside_vol_60d is not None else None,
                "downside_volatility_252d": round(downside_vol_252d, 4) if downside_vol_252d is not None else None,
                "max_drawdown_1y": round(max_drawdown_252d, 2) if max_drawdown_252d is not None else None,
                "amihud_illiquidity_60d": (
                    round(amihud_illiquidity_60d, 10) if amihud_illiquidity_60d is not None else None
                ),
                "cmra_12m": round(cmra_12m, 8) if cmra_12m is not None else None,
                "beta": round(beta, 4) if isinstance(beta, float) else None,
                "beta_bab": bab_result["beta_bab"] if bab_result else None,
                "beta_bab_ts": bab_result["beta_bab_ts"] if bab_result else None,
                "beta_bab_rho": bab_result["beta_bab_rho"] if bab_result else None,
                "beta_bab_sigma_ratio": bab_result["beta_bab_sigma_ratio"] if bab_result else None,
                "beta_bab_unavailable_reason": beta_bab_reason,
                "debt_to_assets": debt_to_assets,
                # Session 395+: Add unavailable_reason for each metric
                "beta_unavailable_reason": beta_reason if beta is None else None,
                "volatility_30d_unavailable_reason": "insufficient_history" if vol_30d is None else None,
                "volatility_60d_unavailable_reason": "insufficient_history" if vol_60d is None else None,
                "volatility_252d_unavailable_reason": "insufficient_history" if vol_252d is None else None,
                "downside_volatility_30d_unavailable_reason": "insufficient_history"
                if downside_vol_30d is None
                else None,
                "downside_volatility_60d_unavailable_reason": "insufficient_history"
                if downside_vol_60d is None
                else None,
                "downside_volatility_252d_unavailable_reason": "insufficient_history"
                if downside_vol_252d is None
                else None,
                "max_drawdown_1y_unavailable_reason": "insufficient_history" if max_drawdown_252d is None else None,
                "amihud_illiquidity_60d_unavailable_reason": (
                    "insufficient_history" if amihud_illiquidity_60d is None else None
                ),
                "cmra_12m_unavailable_reason": "insufficient_history" if cmra_12m is None else None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "data_unavailable": data_unavailable,
                "reason": unavailability_reason,
            }

        except RuntimeError as e:
            reason = str(e)[:150]
            logger.debug(f"[RISK_METRICS] {symbol}: stability unavailable - {reason}")
            return {
                "symbol": symbol,
                "volatility_30d": None,
                "volatility_60d": None,
                "volatility_252d": None,
                "downside_volatility_30d": None,
                "downside_volatility_60d": None,
                "downside_volatility_252d": None,
                "max_drawdown_1y": None,
                "beta": None,
                "debt_to_assets": debt_to_assets,
                "beta_unavailable_reason": "missing_price_data",
                "volatility_30d_unavailable_reason": "insufficient_history",
                "volatility_60d_unavailable_reason": "insufficient_history",
                "volatility_252d_unavailable_reason": "insufficient_history",
                "downside_volatility_30d_unavailable_reason": "insufficient_history",
                "downside_volatility_60d_unavailable_reason": "insufficient_history",
                "downside_volatility_252d_unavailable_reason": "insufficient_history",
                "max_drawdown_1y_unavailable_reason": "insufficient_history",
                "amihud_illiquidity_60d": None,
                "amihud_illiquidity_60d_unavailable_reason": "insufficient_history",
                "cmra_12m": None,
                "cmra_12m_unavailable_reason": "insufficient_history",
                "beta_bab": None,
                "beta_bab_ts": None,
                "beta_bab_rho": None,
                "beta_bab_sigma_ratio": None,
                "beta_bab_unavailable_reason": "insufficient_history",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "data_unavailable": debt_to_assets is None,  # All metrics failed; only debt_to_assets attempted
                "reason": reason if debt_to_assets is None else None,
            }
        except Exception as e:
            logger.warning(f"[RISK_METRICS] Stability error for {symbol}: {type(e).__name__}: {e}")
            return {
                "symbol": symbol,
                "volatility_30d": None,
                "volatility_60d": None,
                "volatility_252d": None,
                "downside_volatility_30d": None,
                "downside_volatility_60d": None,
                "downside_volatility_252d": None,
                "max_drawdown_1y": None,
                "beta": None,
                "debt_to_assets": debt_to_assets,
                "beta_unavailable_reason": "missing_price_data",
                "volatility_30d_unavailable_reason": "insufficient_history",
                "volatility_60d_unavailable_reason": "insufficient_history",
                "volatility_252d_unavailable_reason": "insufficient_history",
                "downside_volatility_30d_unavailable_reason": "insufficient_history",
                "downside_volatility_60d_unavailable_reason": "insufficient_history",
                "downside_volatility_252d_unavailable_reason": "insufficient_history",
                "max_drawdown_1y_unavailable_reason": "insufficient_history",
                "amihud_illiquidity_60d": None,
                "amihud_illiquidity_60d_unavailable_reason": "insufficient_history",
                "cmra_12m": None,
                "cmra_12m_unavailable_reason": "insufficient_history",
                "beta_bab": None,
                "beta_bab_ts": None,
                "beta_bab_rho": None,
                "beta_bab_sigma_ratio": None,
                "beta_bab_unavailable_reason": "insufficient_history",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "data_unavailable": debt_to_assets is None,
                "reason": f"unexpected_error: {type(e).__name__}" if debt_to_assets is None else None,
            }

    def _persist_stability_metrics(self, row: dict[str, Any]) -> None:
        """Write stability metrics row to stability_metrics table."""
        if "data_unavailable" not in row:
            logger.critical(
                f"CRITICAL: data_unavailable key missing from risk metrics row for {row.get('symbol')}. "
                "Failing fast - refusing to write corrupted data."
            )
            raise KeyError("data_unavailable key required in stability metrics row")

        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO stability_metrics
                    (symbol, volatility_30d, volatility_60d, volatility_252d,
                     downside_volatility_30d, downside_volatility_60d, downside_volatility_252d,
                     max_drawdown_1y, amihud_illiquidity_60d, cmra_12m, beta,
                     beta_bab, beta_bab_ts, beta_bab_rho, beta_bab_sigma_ratio, debt_to_assets,
                     created_at, data_unavailable, reason, reason_type, data_source,
                     beta_unavailable_reason, volatility_30d_unavailable_reason,
                     volatility_60d_unavailable_reason, volatility_252d_unavailable_reason,
                     downside_volatility_30d_unavailable_reason,
                     downside_volatility_60d_unavailable_reason,
                     downside_volatility_252d_unavailable_reason,
                     max_drawdown_1y_unavailable_reason,
                     amihud_illiquidity_60d_unavailable_reason,
                     cmra_12m_unavailable_reason, beta_bab_unavailable_reason)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol) DO UPDATE SET
                      volatility_30d = EXCLUDED.volatility_30d,
                      volatility_60d = EXCLUDED.volatility_60d,
                      volatility_252d = EXCLUDED.volatility_252d,
                      downside_volatility_30d = EXCLUDED.downside_volatility_30d,
                      downside_volatility_60d = EXCLUDED.downside_volatility_60d,
                      downside_volatility_252d = EXCLUDED.downside_volatility_252d,
                      max_drawdown_1y = EXCLUDED.max_drawdown_1y,
                      amihud_illiquidity_60d = EXCLUDED.amihud_illiquidity_60d,
                      cmra_12m = EXCLUDED.cmra_12m,
                      beta = EXCLUDED.beta,
                      beta_bab = EXCLUDED.beta_bab,
                      beta_bab_ts = EXCLUDED.beta_bab_ts,
                      beta_bab_rho = EXCLUDED.beta_bab_rho,
                      beta_bab_sigma_ratio = EXCLUDED.beta_bab_sigma_ratio,
                      debt_to_assets = EXCLUDED.debt_to_assets,
                      created_at = EXCLUDED.created_at,
                      data_unavailable = EXCLUDED.data_unavailable,
                      reason = EXCLUDED.reason,
                      reason_type = EXCLUDED.reason_type,
                      data_source = EXCLUDED.data_source,
                      beta_unavailable_reason = EXCLUDED.beta_unavailable_reason,
                      volatility_30d_unavailable_reason = EXCLUDED.volatility_30d_unavailable_reason,
                      volatility_60d_unavailable_reason = EXCLUDED.volatility_60d_unavailable_reason,
                      volatility_252d_unavailable_reason = EXCLUDED.volatility_252d_unavailable_reason,
                      downside_volatility_30d_unavailable_reason = EXCLUDED.downside_volatility_30d_unavailable_reason,
                      downside_volatility_60d_unavailable_reason = EXCLUDED.downside_volatility_60d_unavailable_reason,
                      downside_volatility_252d_unavailable_reason = EXCLUDED.downside_volatility_252d_unavailable_reason,
                      max_drawdown_1y_unavailable_reason = EXCLUDED.max_drawdown_1y_unavailable_reason,
                      amihud_illiquidity_60d_unavailable_reason = EXCLUDED.amihud_illiquidity_60d_unavailable_reason,
                      cmra_12m_unavailable_reason = EXCLUDED.cmra_12m_unavailable_reason,
                      beta_bab_unavailable_reason = EXCLUDED.beta_bab_unavailable_reason,
                      updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        row.get("symbol"),
                        row.get("volatility_30d"),
                        row.get("volatility_60d"),
                        row.get("volatility_252d"),
                        row.get("downside_volatility_30d"),
                        row.get("downside_volatility_60d"),
                        row.get("downside_volatility_252d"),
                        row.get("max_drawdown_1y"),
                        row.get("amihud_illiquidity_60d"),
                        row.get("cmra_12m"),
                        row.get("beta"),
                        row.get("beta_bab"),
                        row.get("beta_bab_ts"),
                        row.get("beta_bab_rho"),
                        row.get("beta_bab_sigma_ratio"),
                        row.get("debt_to_assets"),
                        row.get("created_at"),
                        row["data_unavailable"],
                        row.get("reason"),
                        row.get("reason_type"),
                        # Migration 1022 documents this column's intended value as
                        # "computed_from_price_daily" (volatility/beta are computed from
                        # price_daily here, not fetched from any external vendor) - never
                        # actually written until this fix, leaving all rows NULL.
                        "computed_from_price_daily",
                        row.get("beta_unavailable_reason"),
                        row.get("volatility_30d_unavailable_reason"),
                        row.get("volatility_60d_unavailable_reason"),
                        row.get("volatility_252d_unavailable_reason"),
                        row.get("downside_volatility_30d_unavailable_reason"),
                        row.get("downside_volatility_60d_unavailable_reason"),
                        row.get("downside_volatility_252d_unavailable_reason"),
                        row.get("max_drawdown_1y_unavailable_reason"),
                        row.get("amihud_illiquidity_60d_unavailable_reason"),
                        row.get("cmra_12m_unavailable_reason"),
                        row.get("beta_bab_unavailable_reason"),
                    ),
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[RISK_METRICS] Failed to persist stability metrics for {row.get('symbol')}: {e}")

    @staticmethod
    def _calculate_volatility(returns: list[float]) -> float | None:
        """EWMA-weighted annualized volatility, applying Barra USE4's real DASTD (Daily
        Standard Deviation) half-life - 42 trading days, per the Barra US Equity Model USE4
        Methodology Notes' Volatility descriptor ("the exponentially weighted standard
        deviation of daily excess returns") - to REPLACE the equal-weighted sample stdev this
        previously computed (factor-purity sweep follow-up, 2026-09-17: flagged as
        NOT-YET-ADDRESSED in risk_scoring.py's own module docstring, "none of which
        volatility_60d/252d actually compute"). An equal-weighted window treats a return from
        41 trading days ago identically to yesterday's; Barra's construction (and every other
        major vendor's realized-vol estimate - RiskMetrics/J.P. Morgan's original EWMA
        methodology uses the same exponential-decay principle) deliberately weights recent
        observations more heavily, since volatility clusters and decays.

        TWO HONEST DEVIATIONS FROM A LITERAL BARRA DASTD, disclosed rather than glossed over:
        (1) Computed on raw daily returns, not "excess returns" (return minus that day's
        risk-free rate) - this repo has no risk-free-rate time series wired into this loader,
        and at daily frequency (risk-free rate / 252) the subtraction is immaterial to several
        decimal places; genuinely different from Barra's literal formula, not claimed to be
        identical. (2) Barra's own 42-day half-life is published specifically for a 252-DAY
        window; applying that same half-life to the 30d/60d windows here is this codebase's
        own consistent extension of the recency-weighting PRINCIPLE (recent observations
        should count more, at every window length this pillar scores), not a literal Barra
        spec for those shorter windows - Barra itself does not define a 30d/60d DASTD variant.

        `returns` must be chronological ascending (oldest first) - callers already rely on
        this ordering via `returns[-N:]` slicing to take the most recent N returns.

        Weights are normalized to sum to 1 (a proper weighted average/variance), so no
        separate Bessel's-correction (N-1) term applies here - that correction exists to
        de-bias an EQUAL-weighted sample estimator; an exponentially-weighted estimator's
        "effective sample size" is already baked into the decay parameter itself, and Barra's
        own published formula does not apply a separate small-sample correction on top of it.
        """
        if not returns or len(returns) < 2:
            return None

        n = len(returns)
        decay = DASTD_DECAY_FACTOR
        # returns[-1] is the most recent observation (see docstring) -> weight decay**0;
        # returns[0] is the oldest -> weight decay**(n-1).
        raw_weights = [decay ** (n - 1 - i) for i in range(n)]
        total_weight = sum(raw_weights)
        weights = [w / total_weight for w in raw_weights]

        weighted_mean = sum(w * r for w, r in zip(weights, returns, strict=True))
        weighted_variance = sum(w * (r - weighted_mean) ** 2 for w, r in zip(weights, returns, strict=True))
        daily_std = math.sqrt(weighted_variance)
        return daily_std * math.sqrt(252)

    @staticmethod
    def _calculate_downside_volatility(returns: list[float]) -> float | None:
        """Calculate annualized downside volatility (std dev of negative returns only).

        Downside volatility is a risk metric that measures the standard deviation of only
        negative returns, providing a better reflection of downside risk than traditional
        volatility which treats gains and losses symmetrically. Used in Sortino ratio.

        Args:
            returns: List of daily log returns

        Returns:
            Annualized downside volatility (annualized by sqrt(252)), or None if insufficient data
        """
        if not returns or len(returns) < 2:
            return None

        downside_returns = [r for r in returns if r < 0]
        if not downside_returns or len(downside_returns) < 1:
            return None

        if len(downside_returns) < 2:
            return None

        mean_downside = sum(downside_returns) / len(downside_returns)
        variance = sum((r - mean_downside) ** 2 for r in downside_returns) / (len(downside_returns) - 1)
        daily_std = math.sqrt(variance)
        return daily_std * math.sqrt(252)

    @staticmethod
    def _calculate_max_drawdown(prices: list[float]) -> float | None:
        """Calculate maximum drawdown: largest peak-to-trough decline in percentage terms.

        Max drawdown measures the largest decline from a peak to a subsequent trough,
        expressed as a percentage. It represents the worst-case loss over the period.

        Args:
            prices: List of closing prices in chronological order

        Returns:
            Maximum drawdown as percentage (e.g., -25.5 for 25.5% decline), or None if insufficient data
        """
        if not prices or len(prices) < 2:
            return None

        max_drawdown = 0.0
        peak = prices[0]

        for price in prices[1:]:
            if price > 0 and peak > 0:
                drawdown = ((price - peak) / peak) * 100
                if drawdown < max_drawdown:
                    max_drawdown = drawdown
                if price > peak:
                    peak = price

        return max_drawdown if max_drawdown < 0 else None

    @staticmethod
    def _calculate_amihud_illiquidity(returns: list[float], dollar_volumes: list[float | None]) -> float | None:
        """Amihud (2002) illiquidity: mean(|daily return| / daily dollar volume) over the
        trailing window - one of the most replicated liquidity-premium measures in empirical
        finance (Amihud, Y., "Illiquidity and stock returns: cross-section and time-series
        effects", Journal of Financial Markets, 2002). Live-tested against this repo's own
        price_daily data before implementation (126 months, 2016-2026, median ~3,866
        symbols/month): t=3.34, positive - more illiquid genuinely predicts higher forward
        return here, matching the literature's direction. Flagged as an OPEN QUESTION in
        risk_scoring.py's own module docstring (2026-08-25) and left unimplemented pending
        this genuine new computation - unlike Size, which only needed reading an already-
        stored field.

        `returns` and `dollar_volumes` must be the SAME length and index-aligned (returns[i]
        is the return realized on the same trading day dollar_volumes[i] is the dollar volume
        for) - callers are responsible for that alignment; this function does not re-derive it.

        A day with zero or unknown dollar volume is skipped entirely (not treated as
        infinitely illiquid) - a real Amihud reading needs both a real return AND a real
        volume figure for that day, and this repo already treats "unknown" as "skip its
        contribution," never as a fabricated extreme (same governance principle
        RISK_MIN_WEIGHT_AVAILABLE/GROWTH_MIN_FIELDS_AVAILABLE apply elsewhere in this pillar's
        own scoring layer).

        Returns None if fewer than 2 valid (return, dollar_volume) pairs remain - the same
        minimum-sample floor _calculate_volatility applies.
        """
        if not returns or not dollar_volumes or len(returns) != len(dollar_volumes):
            return None

        daily_illiquidity = [
            abs(r) / dv for r, dv in zip(returns, dollar_volumes, strict=True) if dv is not None and dv > 0
        ]
        if len(daily_illiquidity) < 2:
            return None

        return sum(daily_illiquidity) / len(daily_illiquidity)

    @staticmethod
    def _calculate_cmra(monthly_returns: list[float], monthly_rf_rates: list[float]) -> float | None:
        """Barra US-E3's real Cumulative Range descriptor (Appendix A, "US-E3 Descriptor
        Definitions", Section 1 "Volatility", item v "CMRA") - fetched and read directly from
        the primary source this session (United States Equity Version 3 (E3) Risk Model
        Handbook, p.94), not recalled/paraphrased from a secondary description. Verbatim
        formula: let Z_t = sum_{s=1}^{t} [log(1+r_i,s) - log(1+r_f,s)] for t=1,...,12 (the
        cumulative return of the stock over the risk-free rate through month t); CMRA =
        log((1+Zmax)/(1+Zmin)) where Zmax/Zmin are the maximum/minimum values of Z_t over the
        last 12 months. Unlike DASTD (see `_calculate_volatility`'s own docstring for its
        undisclosed half-life), this formula has no undisclosed parameters - a genuine,
        fully-specified real-methodology descriptor, not an approximation of one.

        `monthly_returns`/`monthly_rf_rates` must both be exactly 12 elements, chronological
        ascending (index 0 = 12 months ago, index 11 = the most recently completed month) -
        `monthly_returns[s]` is the stock's arithmetic return for month s+1, `monthly_rf_rates[s]`
        the risk-free rate for that same month, matching the primary source's r_i,s/r_f,s
        pairing exactly.

        Returns None if either list isn't exactly 12 elements (this repo's own
        insufficient-history convention, same floor every other stability metric uses) or if
        any monthly return/rate is so extreme (<=-100%) that log(1+x) is undefined - a
        genuinely corrupt or delisted-mid-month price series, not a real CMRA reading.
        """
        if len(monthly_returns) != 12 or len(monthly_rf_rates) != 12:
            return None

        z_values = []
        z = 0.0
        try:
            for r, rf in zip(monthly_returns, monthly_rf_rates, strict=True):
                z += math.log(1.0 + r) - math.log(1.0 + rf)
                z_values.append(z)
            z_max = max(z_values)
            z_min = min(z_values)
            # PRE-SHIP VERIFICATION GUARD (found while live-checking this formula against the
            # real universe before wiring it into scoring, not assumed safe from the design
            # alone - same discipline this codebase applies elsewhere, e.g.
            # MIN_TRADING_DAYS_FOR_DRAWDOWN in risk_scoring.py). Zmax >= Zmin always (same set),
            # so (1+Zmax)/(1+Zmin) is a well-defined ratio >= 1 (CMRA >= 0) ONLY when 1+Zmin is
            # positive. When a symbol's cumulative log-excess return has fallen below -100% at
            # its worst point in the trailing 12 months (1+Zmin <= 0) - live-confirmed on real
            # distressed/delisting-adjacent penny stocks (DCX, LXEH, QTI: single months of
            # -70% to -96%) - the ratio can flip to a small POSITIVE number even though both
            # terms are negative, producing a spuriously NEGATIVE "CMRA" (as low as -3.3,
            # live-observed) that would make the most distressed stock in the universe look
            # like the single safest one under this pillar's "lower is better" scoring
            # convention - the exact "artifact tops the safest list" failure mode this file's
            # own NEAR_ZERO_LIQUIDITY_THRESHOLD/RISK_MIN_WEIGHT_AVAILABLE gates already exist to
            # catch elsewhere. Not a real CMRA reading - the range measurement itself is
            # undefined once cumulative excess return breaches -100%, so this returns None
            # (insufficient/invalid) rather than fabricate a number.
            if 1.0 + z_min <= 0:
                return None
            return math.log((1.0 + z_max) / (1.0 + z_min))
        except (ValueError, ZeroDivisionError):
            return None

    def _get_dgs3mo_series(self, cur: Any) -> list[tuple[Any, float]]:
        """Lazily fetches and caches the FULL historical DGS3MO (3-month Treasury) series once
        per loader run - CMRA needs the risk-free rate AS OF each of the trailing 12 month-end
        dates (not just today's latest value, unlike momentum_scoring.py's
        `_get_risk_free_rate_annual`, which only ever needs "now"). Same real series
        algo/reporting/performance.py and momentum_scoring.py's own risk-free netting already
        use, not a new data source. Cached on the instance so a full-universe run queries this
        once, not once per symbol."""
        cached: list[tuple[Any, float]] | None = getattr(self, "_dgs3mo_series_cache", None)
        if cached is not None:
            return cached
        cur.execute(
            "SELECT date, value::float FROM economic_data WHERE series_id = 'DGS3MO' "
            "AND value IS NOT NULL ORDER BY date ASC"
        )
        series = [(row[0].date() if hasattr(row[0], "date") else row[0], float(row[1])) for row in cur.fetchall()]
        self._dgs3mo_series_cache = series
        return series

    @staticmethod
    def _dgs3mo_rate_at(series: list[tuple[Any, float]], target_date: Any) -> float | None:
        """Most recent DGS3MO annual rate (raw percentage point, e.g. 4.07) on or before
        `target_date`, via binary search over the chronologically-sorted series from
        `_get_dgs3mo_series`. Returns None if `target_date` predates every DGS3MO observation
        on file - same graceful "no rate available" fallback every other DGS3MO consumer in
        this codebase uses (see momentum_scoring.py's own `_get_risk_free_rate_annual`)."""
        import bisect

        dates = [d for d, _ in series]
        idx = bisect.bisect_right(dates, target_date) - 1
        if idx < 0:
            return None
        return series[idx][1]

    def _get_cmra_monthly_inputs(self, symbol: str, cur: Any) -> tuple[list[float], list[float]] | None:
        """Fetches the trailing 13 real month-end adjusted closes (giving 12 monthly returns)
        and each month's DGS3MO-derived monthly risk-free rate, for `_calculate_cmra`. Returns
        None if fewer than 13 distinct months of price history exist yet (same "insufficient
        history" treatment as every other stability metric in this file - a young IPO simply
        doesn't have a CMRA reading yet, not a fabricated one from a partial window).

        Uses price_daily_split_adjusted's adj_close_adjusted (same split+dividend-adjusted,
        cross-vendor-consistent series `_compute_stability_row`'s own daily-return computation
        already uses, and for the identical reason - see that method's own ADJ_CLOSE FIX
        docstring).
        """
        cur.execute(
            """
            SELECT date, adj_close_adjusted FROM (
                SELECT date, adj_close_adjusted,
                       ROW_NUMBER() OVER (PARTITION BY date_trunc('month', date) ORDER BY date DESC) AS rn
                FROM price_daily_split_adjusted
                WHERE symbol = %s AND date >= CURRENT_DATE - INTERVAL '400 days'
                  AND adj_close_adjusted IS NOT NULL AND adj_close_adjusted > 0
            ) sub
            WHERE rn = 1
            ORDER BY date DESC
            LIMIT 13
            """,
            (symbol,),
        )
        rows = cur.fetchall()
        if len(rows) < 13:
            return None
        rows = sorted(rows, key=lambda r: r[0])
        dates = [r[0].date() if hasattr(r[0], "date") else r[0] for r in rows]
        closes = [float(r[1]) for r in rows]

        monthly_returns = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]

        dgs3mo_series = self._get_dgs3mo_series(cur)
        monthly_rf_rates = []
        for d in dates[1:]:
            rate_annual_pct = self._dgs3mo_rate_at(dgs3mo_series, d)
            monthly_rf_rates.append((rate_annual_pct / 100.0) / 12.0 if rate_annual_pct is not None else 0.0)

        return monthly_returns, monthly_rf_rates

    @staticmethod
    def _fetch_bab_price_series(symbol: str, cur: Any) -> tuple[list[Any], list[float], list[float]] | None:
        """5-year, common-date-aligned adjusted-close series for `symbol` and SPY, for BAB beta
        (Frazzini & Pedersen 2014, "Betting Against Beta") - a separate, wider fetch from
        `_compute_stability_row`'s own 252-day window used by volatility/CMRA/the existing naive
        `beta` column (those are unchanged by this addition - see migration 1307's docstring for
        why `beta` is not overwritten). 5 years is needed for the paper's own correlation-window
        spec (750+ overlapping 3-day return observations); the 1-year volatility leg is sliced
        from the same series in `_calculate_beta_bab` rather than fetched separately.

        Returns None if fewer than 121 common trading dates exist (matches
        `_calculate_beta_bab`'s own minimum-history floor) - a young IPO or thin/gapped SPY
        overlap simply doesn't have a BAB reading yet, not a fabricated one from a partial window.
        """
        cur.execute(
            "SELECT date, adj_close_adjusted FROM price_daily_split_adjusted "
            "WHERE symbol = %s AND date >= CURRENT_DATE - INTERVAL '1830 days' "
            "AND adj_close_adjusted IS NOT NULL AND adj_close_adjusted > 0 ORDER BY date ASC",
            (symbol,),
        )
        stock_rows = cur.fetchall()
        if not stock_rows:
            return None

        cur.execute(
            "SELECT date, adj_close_adjusted FROM price_daily_split_adjusted "
            "WHERE symbol = 'SPY' AND date >= %s AND date <= %s "
            "AND adj_close_adjusted IS NOT NULL AND adj_close_adjusted > 0 ORDER BY date ASC",
            (stock_rows[0][0], stock_rows[-1][0]),
        )
        spy_rows = cur.fetchall()
        if not spy_rows:
            return None

        stock_by_date = {r[0]: float(r[1]) for r in stock_rows}
        spy_by_date = {r[0]: float(r[1]) for r in spy_rows}
        common_dates = sorted(set(stock_by_date) & set(spy_by_date))
        if len(common_dates) < 121:
            return None

        return common_dates, [stock_by_date[d] for d in common_dates], [spy_by_date[d] for d in common_dates]

    @staticmethod
    def _calculate_beta_bab(
        common_dates: list[Any],
        stock_prices: list[float],
        spy_prices: list[float],
    ) -> dict[str, float] | None:
        """Frazzini & Pedersen (2014, "Betting Against Beta", Journal of Financial Economics
        111(1)) shrinkage beta estimator, verified against the actual published paper (section
        3.1-3.2) rather than a secondary description:

            beta_ts = rho * (sigma_i / sigma_m)
            beta_bab = w * beta_ts + (1 - w) * beta_XS,  w = 0.6, beta_XS = 1.0 (fixed constants
            the paper applies to every asset/period - not fitted to this repo's own data)

        sigma_i/sigma_m are each series' own std dev of daily log returns over the trailing
        ~1 year (>=120 obs required, the paper's own stated minimum). rho is the correlation of
        OVERLAPPING 3-day log returns (r_3d_t = ln(P_t/P_(t-3))) over the full 5-year window
        (>=750 obs required, the paper's own stated minimum) - 3-day, not 1-day, returns
        specifically because the paper uses them to reduce the effect of nonsynchronous/thin
        trading on the correlation estimate; this is the estimator's own design, not this repo's
        approximation of it.

        `common_dates`/`stock_prices`/`spy_prices` must be the same length, index-aligned,
        chronological ascending, and come from `_fetch_bab_price_series` (or an equivalent
        common-trading-date join) - contiguous-index 3-day steps assume a shared trading
        calendar between the two series, the same practical simplification most real-world BAB
        implementations use (trading-day index, not calendar date).

        Returns None if either volatility leg has fewer than 120 observations, the correlation
        leg has fewer than 750, sigma_m is exactly 0, or rho is undefined (e.g. a
        constant-price series) - an honest "not enough real history yet", not a fabricated beta.
        """
        import numpy as np

        if len(common_dates) < 121 or len(stock_prices) != len(common_dates) or len(spy_prices) != len(common_dates):
            return None

        stock_arr = np.array(stock_prices, dtype=float)
        spy_arr = np.array(spy_prices, dtype=float)

        daily_stock_ret = np.diff(np.log(stock_arr))
        daily_spy_ret = np.diff(np.log(spy_arr))
        if len(daily_stock_ret) < 120 or len(daily_spy_ret) < 120:
            return None

        sigma_i = float(np.std(daily_stock_ret[-252:], ddof=1))
        sigma_m = float(np.std(daily_spy_ret[-252:], ddof=1))
        if sigma_m == 0:
            return None

        r3_stock = np.log(stock_arr[3:]) - np.log(stock_arr[:-3])
        r3_spy = np.log(spy_arr[3:]) - np.log(spy_arr[:-3])
        if len(r3_stock) < 750:
            return None

        with np.errstate(invalid="ignore"):
            rho = float(np.corrcoef(r3_stock, r3_spy)[0, 1])
        if np.isnan(rho):
            return None

        sigma_ratio = sigma_i / sigma_m
        beta_ts = rho * sigma_ratio
        beta_bab = 0.6 * beta_ts + 0.4 * 1.0

        return {
            "beta_bab": round(beta_bab, 4),
            "beta_bab_ts": round(beta_ts, 4),
            "beta_bab_rho": round(rho, 6),
            "beta_bab_sigma_ratio": round(sigma_ratio, 6),
        }

    @staticmethod
    def _get_beta_from_db(
        symbol: str,
        stock_prices: list[tuple[Any, float]],
        spy_rows: list[Any],
    ) -> float | dict[str, Any]:
        import numpy as np

        # FIXED 2026-08-22 (goal session - coverage-bucket root-cause audit): these floors
        # (5 common dates, 4 return observations) came from np.cov()/np.var(ddof=1)'s own
        # divide-by-zero guards, not a real "is this a statistically meaningful beta"
        # check - the exact same bug class already fixed 2026-07-27 for vol_252d a few
        # lines below in this same file (see that fix's comment: "should never rest on a
        # thinner sample than the mid-window measure it's supposed to be a more-robust
        # superset of"). A covariance-based beta from 4-5 daily return observations (2-3
        # degrees of freedom) is dominated by sampling noise, not signal - live-confirmed:
        # a DB-wide sweep of the current "extreme_beta" rejections found ~190 distinct
        # symbols with |beta| > 10 (up to 59.46), values only an estimate built from a
        # handful of days could plausibly produce. The `abs(beta) > 10` sanity check below
        # only catches the most extreme of these - equally unreliable but merely
        # "plausible-looking" betas (e.g. 3.2 or -2.1 from 5 days of data) were silently
        # ACCEPTED and fed into load_stock_scores.py's stability score at 0.15 weight as if
        # they were real 1-year risk estimates. Raised to the same 60-return floor
        # volatility_252d already enforces, for consistency within this same loader.
        min_spy_days = 61
        if not spy_rows or len(spy_rows) < min_spy_days:
            actual = len(spy_rows) if spy_rows else 0
            return {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": f"spy_price_data_insufficient: {actual}/{min_spy_days} days",
            }

        try:
            stock_by_date = {p[0]: p[1] for p in stock_prices}
            spy_by_date: dict[Any, float] = {row[0]: float(row[1]) for row in spy_rows}

            common_dates = sorted(set(stock_by_date.keys()) & set(spy_by_date.keys()))
            if len(common_dates) < 61:
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"insufficient_common_dates: {len(common_dates)}/61",
                }

            stock_aligned = [stock_by_date[d] for d in common_dates]
            spy_aligned = [spy_by_date[d] for d in common_dates]

            stock_returns = np.diff(np.log(np.array(stock_aligned, dtype=float)))
            spy_returns = np.diff(np.log(np.array(spy_aligned, dtype=float)))

            if len(stock_returns) < 60:
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"insufficient_returns: {len(stock_returns)}/60",
                }

            spy_var = float(np.var(spy_returns, ddof=1))
            if spy_var == 0:
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": "spy_variance_zero",
                    "reason_type": "loader_failed",
                }

            cov_matrix = np.cov(stock_returns, spy_returns)
            beta = float(cov_matrix[0, 1]) / spy_var

            if abs(beta) > 10:
                logger.warning(f"[RISK_METRICS] {symbol}: extreme DB beta {beta:.2f} - marking unavailable.")
                return {
                    "symbol": symbol,
                    "data_unavailable": True,
                    "reason": f"extreme_beta: {beta:.2f}",
                }

            return round(beta, 4)

        except Exception as e:
            logger.warning(f"[RISK_METRICS] {symbol}: DB beta computation failed: {type(e).__name__}: {e}")
            return {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": f"db_beta_error: {type(e).__name__}",
            }


if __name__ == "__main__":
    sys.exit(run_loader(RiskMetricsLoader))
