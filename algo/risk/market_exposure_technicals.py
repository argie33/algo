#!/usr/bin/env python3

"""Technical/price-derived factor mixin for MarketExposure (algo/risk/market_exposure.py).

Split out of market_exposure.py's monolithic MarketExposure class as part of the
2026-09-05 bloater-decomposition pass (same mixin pattern established by
algo/monitoring/position_monitor.py's split, commit 1d8a64f73). Mechanical split only -
no behavior change; every method body here is byte-identical to what was previously
directly on MarketExposure.

Holds the price/volume-derived factor calculations not yet migrated to
MarketFactorCalculator: Pillar 1's market-technicals sub-signal, the veto-4 market-
confirmation check, the A/D line, the HY credit-spread factor, and Layer 2's
volatility-managed scaling multiplier.

Qualified module-attribute access (`import algo.risk.market_exposure as _me`, then
`_me._annualized_std(...)`) is used for the one cross-module helper this mixin needs,
so the reference resolves through the base module regardless of import ordering - same
technique, same reasoning, as market_exposure_cache.py's `_me.DatabaseContext` (see that
module's docstring) and algo/monitoring/position_order_management.py's
`import algo.monitoring.position_monitor as _pm`.
"""

from __future__ import annotations

import logging
import math
from datetime import date as _date
from datetime import timedelta
from itertools import pairwise
from typing import Any

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

import algo.risk.market_exposure as _me
from algo.infrastructure.config.sql_intervals import get_interval_sql

logger = logging.getLogger(__name__)


class MarketExposureTechnicalsMixin:
    """Technical/price-derived factors: market technicals, A/D line, credit spread,
    market-confirmation veto check, and the vol-managed scaling multiplier.

    Not usable standalone - relies on the `calculator` instance attribute defined on
    MarketExposure itself (same declare-for-mypy pattern as
    algo/monitoring/position_health_checks.py's `config: Any`).
    """

    calculator: Any

    _VOL_MANAGED_MIN_HISTORY_DAYS = 252  # need >=1yr for a stable full-sample target_vol
    _VOL_MANAGED_REALIZED_WINDOW_DAYS = 21  # 1 trading month, matches Moreira & Muir's own window
    _VOL_MANAGED_CAP_LO = 0.25
    _VOL_MANAGED_CAP_HI = 2.0
    _VOL_MANAGED_ACTIVATION_DATE = _date(2026, 8, 24)  # Phase B backtest date; pinned to 1.0 (inert) before this

    def _vol_managed_multiplier(self, eval_date: _date, cur: PsycopgCursor[Any]) -> float:
        """Layer 2: volatility-managed scaling multiplier (Moreira & Muir, 2017, JoF -
        scale exposure inversely to realized volatility): weight_t = target_vol /
        realized_vol_t, where realized_vol_t is a trailing 21-trading-day annualized
        stdev of daily returns and target_vol is the full-sample annualized stdev (so the
        managed series has ~ the same unconditional vol as buy-and-hold - the paper's own
        normalization). Capped to [0.25, 2.0]: the original paper is an academic
        long/short-cash construct with no such bound, but this multiplier is applied to a
        bounded 0-100 exposure_pct, so an implementation cap is necessary and disclosed.

        ACTIVATED 2026-08-24 (Phase B backtest run, see below) - was PINNED TO 1.0
        (inert) from the 2026-08-23 redesign until proven against this system's own
        data. The underlying research is genuinely contested in the general literature
        (Cederburg et al. found volatility-managed portfolios fail out-of-sample;
        Barroso & Detzel found they don't survive transaction costs) - this system does
        not resolve that general debate, it only tests whether this exact pre-specified
        formula helps on the two assets this multiplier would actually apply to.

        PHASE B BACKTEST (2026-08-24, pre-specified formula above, no parameter fitting -
        same rigor as the PILLAR 1 SUB-WEIGHT EVIDENCE backtest earlier in this file):
        this exact weight formula (21-day realized vol, full-sample target vol, [0.25,2.0]
        cap, weekly rebalance, no lookahead - weight known at close(t) applied to return
        t->t+1) applied to SPY's real price history (1993-2026, 32 years, 8427 usable
        daily observations) and independently to QQQ (1999-2026, 26 years, 6885
        observations): weekly Sharpe improved on BOTH (SPY 0.581->0.657, QQQ
        0.502->0.741) and weekly CAGR improved on both (SPY 8.79%->10.91%, QQQ
        9.68%->17.17%) versus unmanaged buy-and-hold over the same window. Consistent
        sign and magnitude across two different assets, matching this file's existing
        bar for treating a result as real signal rather than a single-path fluke.
        Caveats (same class as Pillar 1's): weekly not daily rebalance, no transaction
        costs modeled, cap bounds ([0.25, 2.0]) are an implementation choice not fitted
        to the data. Revisit if a walk-forward/out-of-sample harness on this system's own
        trade history (not yet available - see PILLAR 3 VETO SCOPE above) contradicts
        this.

        Degrades gracefully to neutral (1.0, no scaling) rather than raising on any
        missing/insufficient/non-finite data or DB error - this is an optional scaling
        layer on top of the composite, not a required factor; the composite score itself
        must not become unavailable because this layer can't compute.

        Gated on eval_date < _VOL_MANAGED_ACTIVATION_DATE returning inert 1.0: this
        multiplier was not live in production before that date, so a backfill/recompute
        for an earlier eval_date must reproduce what was actually decided then, not
        silently apply today's code to history (that would corrupt the historical record
        this system's own future regime backtests read as ground truth).
        """
        if eval_date < self._VOL_MANAGED_ACTIVATION_DATE:
            return 1.0

        try:
            cur.execute(
                "SELECT close FROM price_daily WHERE symbol = 'SPY' AND date <= %s "
                "AND close IS NOT NULL ORDER BY date DESC LIMIT 3000",
                (eval_date,),
            )
            rows = cur.fetchall()
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"[VOL_MANAGED] SPY price query failed, degrading to neutral 1.0: {e}")
            return 1.0

        closes_desc = [float(r[0]) for r in rows if r[0] is not None]
        if len(closes_desc) < self._VOL_MANAGED_MIN_HISTORY_DAYS:
            return 1.0

        closes = list(reversed(closes_desc))  # oldest first
        returns: list[float] = []
        for prev, curr in pairwise(closes):
            if prev <= 0 or curr <= 0:
                continue
            r = (curr - prev) / prev
            if math.isnan(r) or math.isinf(r):
                continue
            returns.append(r)

        if len(returns) < self._VOL_MANAGED_MIN_HISTORY_DAYS:
            return 1.0

        target_vol = _me._annualized_std(returns)
        realized_vol = _me._annualized_std(returns[-self._VOL_MANAGED_REALIZED_WINDOW_DAYS :])
        if target_vol is None or realized_vol is None or realized_vol <= 0:
            return 1.0

        weight = target_vol / realized_vol
        if math.isnan(weight) or math.isinf(weight):
            return 1.0

        return max(self._VOL_MANAGED_CAP_LO, min(self._VOL_MANAGED_CAP_HI, weight))

    def _market_technicals_factor(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Market Technicals: SPY RSI(14) + MACD(12,26,9) histogram, blended - a minor
        (10% weight) sub-signal inside Pillar 1 (Trend & Momentum), not a standalone
        pillar - it's price-derived, same information family as trend_30wk/spy_momentum.

        Deliberately does NOT re-derive SPY price vs its 30-week MA (already trend_30wk)
        or vs the 50/200-DMA breadth reads (already Pillar 3's participation sub-score) -
        those are this file's existing long-term-trend/participation reads and adding
        another SPY-vs-MA sub-metric here would be exactly the double-counting bug class
        real multi-factor models are built to avoid. RSI and MACD are genuinely distinct
        constructs - not represented anywhere else in this model:

          - RSI(14): a bounded (0-100), universally-thresholded oscillator (70/30
            overbought/oversold is the standard convention). Scored contrarian-at-
            extremes with a neutral dead-zone (same convention as AAII/Put-Call): 40-60
            is neutral (50pts), ramping to 100 by RSI<=20 (oversold -> bullish
            contrarian) and down to 0 by RSI>=80 (overbought -> bearish contrarian).
          - MACD histogram, normalized by price (histogram/close, not raw points) and
            z-scored against its own trailing history (same Barra/Axioma-style
            normalization used elsewhere) - scored DIRECTLY (higher_is_worse=False):
            strengthening positive histogram is real trend-confirming bullish momentum,
            not an investor-psychology extreme to fade.

        Blended 50/50 - a short-term mean-reversion oscillator and a medium-term trend-
        confirmation signal, neither dominates the other's information content.
        """
        cur.execute(
            "SELECT close, date FROM price_daily WHERE symbol = 'SPY' AND date <= %s "
            "AND close IS NOT NULL ORDER BY date DESC LIMIT 400",
            (eval_date,),
        )
        rows = cur.fetchall()
        if len(rows) < 220:
            return {
                "data_unavailable": True,
                "reason": f"Insufficient SPY price history for technicals (have {len(rows)}, need 220+)",
            }

        from algo.infrastructure import MarketCalendar

        most_recent_date = rows[0][1]
        expected_date = eval_date - timedelta(days=1)
        for _ in range(10):
            if MarketCalendar.is_trading_day(expected_date):
                break
            expected_date -= timedelta(days=1)
        if most_recent_date < expected_date:
            return {
                "data_unavailable": True,
                "reason": (
                    f"SPY price data is stale: most recent close from {most_recent_date}, "
                    f"but eval_date is {eval_date} (expected data from {expected_date})."
                ),
            }

        closes = [float(r[0]) for r in reversed(rows)]
        if any(math.isnan(c) or math.isinf(c) or c <= 0 for c in closes):
            return {"data_unavailable": True, "reason": "Non-finite or non-positive SPY close in technicals window"}

        rsi = self.calculator._compute_rsi(closes, period=14)
        if rsi is None:
            return {"data_unavailable": True, "reason": "RSI computation failed (insufficient data)"}

        hist_pct_series = self.calculator._macd_histogram_pct_series(closes)
        warm_up = 200
        zscore_window = hist_pct_series[warm_up:]
        if len(zscore_window) < 15:
            return {
                "data_unavailable": True,
                "reason": f"Insufficient MACD history after warm-up to z-score (have {len(zscore_window)}, need 15+)",
            }
        current_hist_pct = zscore_window[-1]
        macd_z = self.calculator._sample_zscore(current_hist_pct, zscore_window)
        if macd_z is None:
            return {"data_unavailable": True, "reason": "Cannot z-score MACD histogram (zero variance in history)"}

        if rsi >= 80:
            rsi_score = 0.0
        elif rsi <= 20:
            rsi_score = 100.0
        elif rsi >= 60:
            rsi_score = 50.0 - (rsi - 60) / 20.0 * 50.0
        elif rsi <= 40:
            rsi_score = 50.0 + (40 - rsi) / 20.0 * 50.0
        else:
            rsi_score = 50.0

        macd_score = self.calculator._zscore_to_score(-macd_z)
        composite = round(0.5 * rsi_score + 0.5 * macd_score, 1)
        return {
            "score": composite,
            "rsi_14": round(rsi, 1),
            "rsi_score": round(rsi_score, 1),
            "macd_histogram_pct": round(current_hist_pct, 4),
            "macd_z": round(macd_z, 2),
            "macd_score": round(macd_score, 1),
        }

    def _has_market_confirmation(self, eval_date: _date, cur: PsycopgCursor[Any]) -> bool:
        """Detect a volume-backed rally day in last 30 days.

        A qualifying day: index closes ≥1.7% on volume above prior day.
        Used only as a hard veto condition (not a scoring factor): when SPY
        is below its 30-week MA and no such day has occurred, the market has
        not confirmed an attempted recovery, so exposure is capped at 40%.
        """
        interval_30d = get_interval_sql("30d")
        cur.execute(
            f"""
            WITH d AS (
                SELECT date, close, volume,
                       LAG(close) OVER (ORDER BY date) AS prev_close,
                       LAG(volume) OVER (ORDER BY date) AS prev_vol
                FROM price_daily
                WHERE symbol = 'SPY' AND date <= %s
                  AND date >= %s::date - {interval_30d}
            )
            SELECT 1 FROM d
            WHERE prev_close IS NOT NULL
              AND close >= prev_close * 1.017
              AND volume > prev_vol
            ORDER BY date DESC
            LIMIT 1
            """,
            (eval_date, eval_date),
        )
        return cur.fetchone() is not None

    def _ad_line(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """A/D line: cumulative advancers - decliners vs SPY direction.

        Uses pre-computed advance_decline_ratio from market_health_daily and
        SPY close from price_daily (fast, <1s indexed lookups) instead of
        computing LAG() window functions across 5000 stocks x 35 days (~175,000 rows).
        """
        cur.execute(
            """
            WITH mh AS (
                SELECT date, advance_decline_ratio
                FROM market_health_daily
                WHERE date <= %s AND advance_decline_ratio IS NOT NULL
                ORDER BY date DESC LIMIT 22
            ),
            spy AS (
                SELECT date, close FROM price_daily
                WHERE symbol = 'SPY' AND date <= %s
                ORDER BY date DESC LIMIT 22
            )
            SELECT mh.date, mh.advance_decline_ratio AS ratio, spy.close AS spy_close
            FROM mh
            JOIN spy ON mh.date = spy.date
            ORDER BY mh.date ASC
            """,
            (eval_date, eval_date),
        )
        rows = cur.fetchall()
        if len(rows) < 5:
            msg = (
                f"[MARKET_EXPOSURE CRITICAL] Insufficient A/D line data for {eval_date}: "
                f"{len(rows)} rows, need 5+. "
                f"A/D line is required for accurate market breadth assessment. "
                f"Cannot compute exposure score with missing historical data. "
                f"Check market_health_daily table for advance_decline_ratio data gaps."
            )
            logger.error(msg)
            raise RuntimeError(msg)

        nets = []
        ad_dates = []
        for r in rows:
            if len(r) < 3:
                msg = (
                    f"[MARKET_EXPOSURE CRITICAL] A/D line query returned corrupted row with {len(r)} fields. "
                    f"Expected (date, ratio, spy_close). "
                    f"Cannot compute A/D line with malformed data. "
                    f"Check market_health_daily and price_daily tables."
                )
                logger.error(msg)
                raise RuntimeError(msg)
            row_date, ratio = r[0], r[1]
            if ratio is None:
                msg = (
                    f"[MARKET_EXPOSURE CRITICAL] A/D ratio corrupted/missing for {row_date}. "
                    f"Cannot compute A/D line with data gaps - requires complete daily sequence. "
                    f"Check market_health_daily table for data quality."
                )
                logger.error(msg)
                raise RuntimeError(msg)
            nets.append((float(ratio) - 1) / (float(ratio) + 1))
            ad_dates.append(row_date)

        if len(nets) < 2:
            msg = (
                f"[MARKET_EXPOSURE CRITICAL] Insufficient valid A/D ratios for {eval_date}. "
                f"A/D line calculation requires minimum 2 valid data points. "
                f"Check market_health_daily table for data completeness."
            )
            logger.error(msg)
            raise RuntimeError(msg)

        first_net = nets[0]
        last_net = nets[-1]
        ad_change = last_net - first_net

        # Extract first and last SPY closes from the rows tuple data
        if len(rows[0]) < 3 or rows[0][2] is None:
            raise RuntimeError(
                f"[MARKET_EXPOSURE CRITICAL] First SPY close missing for A/D line on {eval_date}. "
                f"Cannot compute trend direction without benchmark data. "
                f"Check price_daily table for SPY data."
            )
        if len(rows[-1]) < 3 or rows[-1][2] is None:
            raise RuntimeError(
                f"[MARKET_EXPOSURE CRITICAL] Last SPY close missing for A/D line on {eval_date}. "
                f"Cannot compute trend direction without benchmark data. "
                f"Check price_daily table for SPY data."
            )

        first_spy = float(rows[0][2])
        last_spy = float(rows[-1][2])

        if math.isnan(first_spy) or math.isinf(first_spy) or math.isnan(last_spy) or math.isinf(last_spy):
            raise RuntimeError(
                f"[MARKET_EXPOSURE CRITICAL] Non-finite SPY price (first={first_spy}, last={last_spy}) on {eval_date}. "
                f"Cannot compute A/D line direction without valid benchmark price. "
                f"Check price_daily table for SPY data integrity."
            )

        if first_spy <= 0:
            raise RuntimeError(
                f"[MARKET_EXPOSURE CRITICAL] Invalid first SPY price {first_spy} on {eval_date}. "
                f"Cannot compute A/D line direction without valid benchmark price. "
                f"Check price_daily table for SPY data integrity."
            )

        spy_change_pct = (last_spy - first_spy) / first_spy * 100.0
        # Ordered worst to best: bearish_confirming (0, real broad decline) <
        # bearish_divergence (30, rally not broadly supported) < bullish_divergence (60,
        # breadth improving despite price dip - "hidden bullish") < bullish_confirming (100).
        if ad_change > 0 and spy_change_pct > 0:
            score = 100.0
            relation = "bullish_confirming"
        elif ad_change > 0 and spy_change_pct < 0:
            score = 60.0  # hidden bullish
            relation = "bullish_divergence"
        elif ad_change < 0 and spy_change_pct < 0:
            score = 0.0  # confirmed broad-based decline - worse than a mere divergence
            relation = "bearish_confirming"
        else:
            score = 30.0  # bearish divergence
            relation = "bearish_divergence"
        return {
            "score": score,
            "ad_change_20d": round(ad_change, 4),
            "spy_change_pct_20d": round(spy_change_pct, 2),
            "relation": relation,
            "direction": "up" if ad_change > 0 else "down",
        }

    def _credit_spread(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """HY OAS credit spread (BAMLH0A0HYM2) - credit leads equity.

        Based on Apollo/Torsten Slok research: HY spreads widen 4-6 weeks
        before equity markets price in credit risk. Rapidly widening spreads
        (>+1pp in 20 trading days) get an additional 20% score haircut.

        CRITICAL: Credit spread mean-reversion signal requires 20+ days of history.
        Without trend, we cannot reliably assess credit cycle direction.
        No fallback to partial history - require minimum 20 days or raise error.

        Scale: <3.5% = tight/healthy, 4-5% = mild stress, >7% = severe stress.

        FRED changed its distribution policy for ICE BofA index series (including this
        factor's own BAMLH0A0HYM2) in April 2026 - only a rolling ~3-year window is
        served via the API now regardless of request range. This is a permanent
        external ceiling on how much HY OAS history this factor can ever pull from FRED
        directly - not fixable without sourcing raw ICE data directly.
        """
        cur.execute(
            """
            SELECT value::float, date
            FROM economic_data
            WHERE series_id = 'BAMLH0A0HYM2' AND date <= %s
            ORDER BY date DESC LIMIT 25
            """,
            (eval_date,),
        )
        rows = cur.fetchall()
        if not rows or len(rows) < 1:
            raise RuntimeError(
                f"[CREDIT SPREAD CRITICAL] No HY OAS data (BAMLH0A0HYM2) for {eval_date}. "
                f"Credit spreads are a required factor for exposure calculation. "
                f"Cannot assess credit market stress without HY spread data. "
                f"Check economic_data table for BAMLH0A0HYM2 series."
            )

        # Validate current HY value
        if len(rows[0]) < 1 or rows[0][0] is None:
            raise RuntimeError(
                f"[CREDIT SPREAD CRITICAL] Current HY OAS value is NULL for {eval_date}. "
                f"Cannot calculate credit spread score without current reading. "
                f"Check economic_data table - latest BAMLH0A0HYM2 entry may be corrupted."
            )

        hy = float(rows[0][0])

        if math.isnan(hy) or math.isinf(hy):
            raise RuntimeError(
                f"[CREDIT SPREAD CRITICAL] Non-finite HY OAS value ({hy}) for {eval_date}. "
                f"Cannot calculate credit spread score without a valid current reading. "
                f"Check economic_data table for BAMLH0A0HYM2 data integrity."
            )

        # CRITICAL: 20-day trend is required for credit spread signal (mean-reversion indicator)
        if len(rows) < 20:
            raise RuntimeError(
                f"[CREDIT SPREAD CRITICAL] Insufficient HY OAS history for {eval_date}: "
                f"have {len(rows)} days, but require 20+ days for mean-reversion trend analysis. "
                f"Credit spread signals (leading economic indicator) require full 20-day window. "
                f"Cannot assess credit cycle direction with incomplete history - risk assessment incomplete. "
                f"Check: (1) economic_data table completeness, (2) BAMLH0A0HYM2 loader freshness"
            )

        # Validate 20d-ago value (last row in reverse-chronological order)
        if len(rows[-1]) < 1 or rows[-1][0] is None:
            raise RuntimeError(
                f"[CREDIT SPREAD CRITICAL] 20-day historical HY OAS value is NULL for {eval_date}. "
                f"Cannot calculate credit spread trend without historical anchor. "
                f"Check economic_data table - older BAMLH0A0HYM2 entries may have gaps."
            )

        hy_20d_ago = float(rows[-1][0])
        if math.isnan(hy_20d_ago) or math.isinf(hy_20d_ago):
            raise RuntimeError(
                f"[CREDIT SPREAD CRITICAL] Non-finite 20-day-ago HY OAS value ({hy_20d_ago}) for {eval_date}. "
                f"Cannot calculate credit spread trend without a valid historical anchor. "
                f"Check economic_data table for BAMLH0A0HYM2 data integrity."
            )
        widening_1pp = (hy - hy_20d_ago) > 1.0

        if hy < 3.5:
            score = 100.0
        elif hy < 4.5:
            score = 85.0
        elif hy < 5.5:
            score = 65.0
        elif hy < 7.0:
            score = 35.0
        else:
            score = 10.0

        # Rapid widening haircut: stress is accelerating
        if widening_1pp and hy > 4.0:
            score *= 0.80

        result = {
            "score": round(score, 1),
            "value": round(hy, 3),
            "widening_rapidly": widening_1pp,
            "hy_20d_ago": round(hy_20d_ago, 3),
        }
        return result
