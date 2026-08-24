#!/usr/bin/env python3
"""
Market Factor Calculator - Compute individual market factors

Responsibilities:
- Calculate market factors (trend, momentum, breadth, VIX, sentiment, etc.) consumed by
  algo/risk/market_exposure.py's 3-pillar composite (see that module's docstring for the
  pillar architecture and the evidence framework behind it)
- Provide utility methods for common calculations (_pct_above_ma, _vix_score, etc.)
- Return structured factor data for scoring

REMOVED 2026-08-23 (pillar redesign, goal: evidence-based exposure model): positioning()
and its two helpers (_insider_buying_breadth, _short_interest_trend) - insider buying
breadth + short interest trend was a real signal in principle, but not covered by the
redesign's evidence framework and its short-interest leg had only 3 FINRA settlement
cycles of local history, too thin to trust regardless. Confirmed zero other callers
before removal (grep across the repo). See market_exposure.py's module docstring,
"Dropped entirely" section, for the full reasoning.
"""

from __future__ import annotations

import logging
import math
from datetime import date as _date
from typing import Any

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor

from algo.infrastructure.config.sql_intervals import get_interval_sql

logger = logging.getLogger(__name__)


class MarketFactorCalculator:
    def __init__(self) -> None:
        pass

    @staticmethod
    def _wt_pts(factor: dict[str, Any], weight: float) -> tuple[float, float]:
        """Scale factor score to weight. Returns (pts, avail_weight).

        Raises exception if score is missing - market factors are critical
        for position sizing and must not silently degrade.
        """
        score = factor.get("score")
        if score is None:
            factor_name = factor["name"]
            raise ValueError(
                f"[MARKET_FACTOR] Missing score for factor '{factor_name}'. "
                f"Market factors are critical for exposure calculation - missing data must be explicit."
            )

        try:
            score = float(score)
        except (ValueError, TypeError) as e:
            factor_name = factor["name"]
            raise ValueError(
                f"[MARKET_FACTOR] Invalid score for factor '{factor_name}': {score!r}. "
                f"Cannot compute exposure with non-numeric factor scores."
            ) from e

        # BUG CLASS FOUND 2026-08-10 (same as phase7/phase8/exit_engine/order_manager/
        # position_sizer fixes this session): a NaN or Infinity score here would silently
        # wash through the caller's max(0.0, min(100.0, score)) clamp into a confident but
        # fabricated 0.0 or 100.0 - the single choke point every market exposure factor
        # funnels through, so this one check protects all of them from a laundered score
        # that already made it this far as a "valid" float.
        if math.isnan(score) or math.isinf(score):
            factor_name = factor["name"]
            raise ValueError(
                f"[MARKET_FACTOR] Non-finite score for factor '{factor_name}': {score!r}. "
                f"Cannot compute exposure with NaN/Infinity factor scores."
            )

        return score * weight / 100.0, weight

    @staticmethod
    def _sample_zscore(current: float, history: list[float]) -> float | None:
        """Sample z-score of `current` against its own real historical distribution.

        Standard Barra/Axioma-style factor normalization: standardize a raw reading
        against its own history rather than score it off a fixed, eyeballed threshold
        that goes stale as the regime shifts. `history` should be the series' own past
        readings (current value may or may not be included - negligible effect on a
        reasonably-sized sample). Requires >=15 points and non-zero variance; returns
        None otherwise rather than a misleadingly precise number off too little data.
        """
        n = len(history)
        if n < 15:
            return None
        mean = sum(history) / n
        variance = sum((x - mean) ** 2 for x in history) / (n - 1)
        stdev = math.sqrt(variance)
        if stdev < 1e-9:
            return None
        z = (current - mean) / stdev
        if math.isnan(z) or math.isinf(z):
            return None
        return z

    @staticmethod
    def _zscore_to_score(z: float, cap: float = 2.5) -> float:
        """Map a z-score (positive = worse/more-bearish, by the caller's convention) to a
        0-100 factor score: z=0 (average reading) -> 50, z=+cap -> 0, z=-cap -> 100.

        cap=2.5 std devs covers ~98.8% of a normal distribution - wide enough that routine
        variation doesn't pin the score at the boundary, tight enough that a genuine tail
        reading actually reaches it. The caller is responsible for sign convention (flip the
        raw z before calling if a lower raw reading is the bearish direction, e.g. an
        inverted yield curve) so this mapping stays uniform across every factor that uses it.
        """
        if math.isnan(z) or math.isinf(z):
            return 50.0
        score = 50.0 - (z / cap) * 50.0
        return max(0.0, min(100.0, score))

    @staticmethod
    def _compute_rsi(closes: list[float], period: int = 14) -> float | None:
        """Wilder's RSI (the original, standard smoothing - not a naive rolling average),
        computed over the full `closes` series (oldest first) and returned as the final
        (most recent) value only. Returns None if there aren't enough points to seed the
        smoothing window.
        """
        if len(closes) < period + 1:
            return None
        gains = []
        losses = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0.0))
            losses.append(max(-diff, 0.0))
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_gain < 1e-9 and avg_loss < 1e-9:
            # Genuinely zero movement over the whole window (stale/frozen feed, duplicate
            # placeholder rows - same failure mode as the flat-OHLC/near-zero-ATR bugs
            # found elsewhere in this codebase) is NOT the same thing as a real all-up-days
            # rally: both hit the avg_loss<1e-9 branch below, but only the rally case is a
            # genuine RSI=100 extreme. Report neutral rather than fabricating an extreme
            # reading off data with no actual price action in it.
            return 50.0
        if avg_loss < 1e-9:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def _ema_series(values: list[float], period: int) -> list[float]:
        """Exponential moving average, seeded with the first value (pandas' `ewm(adjust=
        False)` convention) rather than an SMA warm-up - simplest correct implementation,
        and any early-window transient bias washes out given the long buffer callers keep
        before their actual analysis window (see _macd_histogram_pct_series).
        """
        alpha = 2.0 / (period + 1)
        ema = [values[0]]
        for v in values[1:]:
            ema.append(alpha * v + (1 - alpha) * ema[-1])
        return ema

    @classmethod
    def _macd_histogram_pct_series(
        cls, closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
    ) -> list[float]:
        """Standard MACD(12,26,9) histogram (macd_line - signal_line), normalized by price
        (histogram / close * 100) so the series is comparable across price regimes/levels
        rather than raw dollar magnitude (which trends up with SPY's price over decades).
        Returns one value per input close (oldest first) - callers should discard an early
        warm-up slice before treating the series as stationary enough to z-score.
        """
        ema_fast = cls._ema_series(closes, fast)
        ema_slow = cls._ema_series(closes, slow)
        macd_line = [f - s for f, s in zip(ema_fast, ema_slow, strict=True)]
        signal_line = cls._ema_series(macd_line, signal)
        return [(m - s) / c * 100.0 for m, s, c in zip(macd_line, signal_line, closes, strict=True)]

    def _pct_above_ma(self, eval_date: _date, ma_days: int, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Calculate % of stocks trading above N-day MA (critical).

        Linear scale: 20% = 0 pts, 50% = 50 pts, 80% = 100 pts
        Uses most recent available date on or before eval_date (technical_data_daily may lag prices).
        Raises RuntimeError if data unavailable - market breadth is required for position sizing.
        """
        try:
            cur.execute(
                f"""
                SELECT
                    SUM(CASE WHEN close > sma_{ma_days} THEN 1 ELSE 0 END) * 100.0 / COUNT(*)
                    as pct_above
                FROM technical_data_daily
                WHERE date = (
                    SELECT MAX(date) FROM technical_data_daily
                    WHERE date <= %s AND sma_{ma_days} IS NOT NULL
                )
                AND sma_{ma_days} IS NOT NULL
                """,
                (eval_date,),
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                pct = float(row[0])
                # Linear: 20% -> 0, 50% -> 50, 80% -> 100
                score = (pct - 20) / 0.6
                score = min(100, max(0, score))
                return {"value": pct, "score": score}
            raise RuntimeError(
                f"[BREADTH CRITICAL] Cannot compute market exposure without {ma_days}-day breadth data. "
                f"Check: (1) technical_data_daily freshness, (2) SMA calculation in loader"
            )
        except RuntimeError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[BREADTH CRITICAL] Breadth {ma_days}-day MA query failed: {e}. "
                f"Cannot proceed with position sizing without technical breadth data."
            ) from e

    def _vix_score(self, vix: float, rising: bool) -> tuple[float, dict[str, Any]]:
        """Score VIX level, with an additive penalty for a genuine rising trend.

        Level tiers: <15=100, 15-25=80, 25-35=40, 35+=0.

        FIXED 2026-08-22 (goal: exposure-model integrity review): this used to combine
        level_score * trend_mult * ts_mult - the only multiplicative combination in this
        file; every other factor and modifier combines additively, with no comment
        anywhere explaining why VIX was different. `rising` now gets a flat 10pt additive
        penalty like everything else. `term_structure` (VIX3M) is removed entirely - see
        vix_regime()'s docstring for why.
        """
        if vix < 15:
            level_score = 100.0
        elif vix < 25:
            level_score = 80.0
        elif vix < 35:
            level_score = 40.0
        else:
            level_score = 0.0

        trend_penalty = 10.0 if rising else 0.0
        final_score = max(0.0, level_score - trend_penalty)
        return final_score, {
            "level": round(vix, 1),
            "level_score": round(level_score, 1),
            "rising": rising,
        }

    # REMOVED 2026-08-20 (goal: finance-accuracy audit): _has_market_confirmation was dead
    # code - confirmed zero callers anywhere in production (MarketExposure has its own,
    # differently-defined _has_market_confirmation, which is the actual "canonical
    # implementation... called directly from compute()" per that method's own comment in
    # market_exposure.py). See ad_line/credit_spread's removal comment just below for the
    # full pattern this belongs to.

    # ============= Factor Implementations =============

    def trend_30wk(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Trend factor: SPY vs 30-week MA (critical).

        Raises RuntimeError if data unavailable - SPY trend is foundational to veto logic.
        Trend is a 15pt factor. Missing weekly price data is a data error, not a skip condition.
        """
        try:
            cur.execute(
                """
                WITH w AS (
                    SELECT close,
                           AVG(close) OVER (ORDER BY date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) as sma30,
                           ROW_NUMBER() OVER (ORDER BY date DESC) as rn
                    FROM price_weekly WHERE symbol = 'SPY' AND date <= %s
                )
                SELECT close, sma30 FROM w WHERE rn = 1
                """,
                (eval_date,),
            )
            row = cur.fetchone()
            if row and row[0] is not None and row[1] is not None:
                spy = float(row[0])
                sma = float(row[1])
                if math.isnan(spy) or math.isinf(spy) or math.isnan(sma) or math.isinf(sma):
                    raise RuntimeError(
                        f"[TREND CRITICAL] Non-finite SPY trend data: close={spy!r}, sma30={sma!r}. "
                        f"Cannot compute trend score from NaN/Infinity prices."
                    )
                # Calculate price vs MA percentage for dashboard display
                price_vs_ma_pct = ((spy - sma) / sma) * 100 if sma > 0 else 0
                # Score: 100 if above MA (bullish), 0 if below (bearish)
                score = 100.0 if spy > sma else 0.0
                return {
                    "above_30wma": spy > sma,
                    "score": score,
                    "price_vs_ma_pct": price_vs_ma_pct,
                    "value": "bullish" if spy > sma else "bearish",
                }
            raise RuntimeError(
                "[TREND CRITICAL] SPY 30-week trend data unavailable. "
                "Check: (1) price_weekly table has recent SPY prices, (2) eval_date is not in future"
            )
        except RuntimeError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError) as e:
            raise RuntimeError(
                f"[TREND CRITICAL] SPY trend calculation failed: {e}. "
                f"Cannot proceed with position sizing without SPY 30-week trend."
            ) from e

    def spy_momentum(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """SPY 12-month momentum (TSMOM, critical).

        Raises RuntimeError if data unavailable - momentum is key to trend confirmation.
        Momentum is a 10pt factor. Missing historical data is a data error, not a skip condition.
        """
        try:
            interval_365d = get_interval_sql("365d")
            cur.execute(
                f"""
                WITH d AS (
                    SELECT close, date FROM price_daily WHERE symbol = 'SPY' AND date <= %s
                    ORDER BY date DESC LIMIT 1
                ),
                y_ago AS (
                    SELECT close FROM price_daily WHERE symbol = 'SPY' AND date <= %s::date - {interval_365d}
                    ORDER BY date DESC LIMIT 1
                )
                SELECT d.close, y_ago.close FROM d, y_ago
                """,
                (eval_date, eval_date),
            )
            row = cur.fetchone()
            if row and row[0] is not None and row[1] is not None:
                current = float(row[0])
                year_ago = float(row[1])
                # NaN fails every ordinary comparison (including `<= 0` below), so a NaN
                # year_ago would otherwise skip that guard entirely and silently launder
                # through score = min(100, max(0, ret * 200)) into a fabricated value.
                if math.isnan(current) or math.isinf(current) or math.isnan(year_ago) or math.isinf(year_ago):
                    raise ValueError(f"Non-finite SPY momentum prices: current={current!r}, year_ago={year_ago!r}")
                if year_ago <= 0:
                    raise ValueError(f"Year-ago price must be positive for momentum calculation: {year_ago}")
                ret = (current - year_ago) / year_ago
                score = min(100, max(0, ret * 200))
                return {"return_12m": round(ret * 100, 1), "score": score, "value": round(ret * 100, 1)}
            raise RuntimeError(
                "[MOMENTUM CRITICAL] SPY 12-month momentum data unavailable. "
                "Check: (1) price_daily has 365 days of SPY history, (2) eval_date is not in future"
            )
        except RuntimeError:
            raise
        except (ValueError, ZeroDivisionError, TypeError, psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[MOMENTUM CRITICAL] SPY momentum calculation failed: {e}. "
                f"Cannot proceed with position sizing without momentum confirmation."
            ) from e

    def selling_pressure(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Heavy-volume down days in last 25 sessions (critical).

        Raises RuntimeError if data unavailable - selling pressure is required for veto 3.
        Selling pressure is a 10pt factor and missing volume/price data is a data error, not a skip.
        Must be TODAY's data for current market assessment.
        """
        try:
            # First verify we have TODAY's SPY price data
            cur.execute(
                "SELECT date, close FROM price_daily WHERE symbol = 'SPY' AND date <= %s ORDER BY date DESC LIMIT 1",
                (eval_date,),
            )
            price_row = cur.fetchone()
            if not price_row:
                raise RuntimeError(
                    "[SELLING_PRESSURE CRITICAL] SPY price data not available. "
                    "Check: (1) price_daily has SPY records, (2) loader has run today"
                )

            most_recent_date = price_row[0]

            # Use trading-day logic instead of calendar days, and accept the most
            # recently COMPLETED trading day's data rather than demanding eval_date's
            # own close - the orchestrator runs this pre-market (2 AM ET), hours before
            # today's close exists. Walk back from the trading day before eval_date to
            # find the latest close we can reasonably expect to already be loaded.
            from datetime import timedelta

            from algo.infrastructure import MarketCalendar

            expected_date = eval_date - timedelta(days=1)
            for _ in range(10):
                if MarketCalendar.is_trading_day(expected_date):
                    break
                expected_date -= timedelta(days=1)

            if most_recent_date < expected_date:
                raise RuntimeError(
                    f"[SELLING_PRESSURE CRITICAL] SPY price data is stale: from {most_recent_date}, "
                    f"but eval_date is {eval_date} (expected data from {expected_date}). "
                    f"Distribution day detection requires most recent trading day's market data. "
                    f"Cannot use older selling pressure for risk assessment."
                )

            # Now calculate distribution days from last 25 sessions
            cur.execute(
                """
                WITH d AS (
                    SELECT close, volume,
                           LAG(close) OVER (ORDER BY date) as prev_close,
                           AVG(volume) OVER (ORDER BY date ROWS BETWEEN 49 PRECEDING AND 1 PRECEDING) as avg50
                    FROM price_daily WHERE symbol = 'SPY' AND date <= %s
                    ORDER BY date DESC LIMIT 25
                )
                SELECT COUNT(*) FILTER (WHERE close < prev_close AND volume > avg50) FROM d
                """,
                (eval_date,),
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                dist = int(row[0])
                # 0-2 = 100 (clean), 3-4 = 60 (caution), 5+ = 20 (pressure)
                if dist <= 2:
                    score, regime = 100.0, "clean"
                elif dist <= 4:
                    score, regime = 60.0, "caution"
                else:
                    score, regime = 20.0, "pressure"
                return {
                    "heavy_down_days": dist,
                    "count": dist,
                    "value": dist,
                    "score": score,
                    "regime": regime,
                }
            raise RuntimeError(
                "[SELLING_PRESSURE CRITICAL] SPY price/volume data unavailable for distribution detection. "
                "Check: (1) price_daily has at least 25 recent SPY records, (2) volume column is populated"
            )
        except RuntimeError:
            raise
        except (ValueError, ZeroDivisionError, TypeError, psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[SELLING_PRESSURE CRITICAL] Selling pressure calculation failed: {e}. "
                f"Cannot proceed with position sizing without distribution detection."
            ) from e

    def vix_regime(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """VIX level + genuine day-over-day trend (critical).

        Raises RuntimeError if data unavailable - VIX is foundational to risk assessment.
        VIX is a factor weighted per MarketExposure.W_VIX. Missing volatility data is a
        data error, not a skip condition.

        FIXED 2026-08-22 (goal: exposure-model integrity review): "rising" previously meant
        `vix > 20` - a re-test of the level tier, not a trend read. Two consequences: the
        in-score "rising" penalty was really a second, hidden level penalty, and hard Veto 2
        ("VIX>40 rising") was mathematically just "VIX>40", since 40>20 always implies
        vix>20. Live-verified against 20 days of real market_exposure_daily rows: "rising"
        read false on every single day in that window even while VIX genuinely climbed
        14.6->19.6, because it never crossed 20. Now compares today's VIX to 5 sessions ago
        (VIX moves faster than the 20d windows used elsewhere in this file for slower series
        like credit spreads) - a real trend read.

        REMOVED (2026-08-22): term structure (VIX3M). Advertised in this file's docstrings
        since the 2026-08-20 redesign but never wired to any real data source -
        market_health_daily has no vix3m column and nothing in this codebase loads one.
        Rather than fabricate an input, the claim is removed; add it back only when a real
        VIX3M source exists.
        """
        try:
            # Pull 6 sessions: today's reading plus a real 5-session-ago comparison point.
            cur.execute(
                "SELECT date, vix_level FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 6",
                (eval_date,),
            )
            rows = cur.fetchall()

            # No data available: fail-fast with diagnostic info
            if not rows:
                cur.execute("SELECT MAX(date) FROM market_health_daily")
                latest_row = cur.fetchone()
                latest_date = latest_row[0] if latest_row and latest_row[0] is not None else "EMPTY"
                raise RuntimeError(
                    f"[VIX CRITICAL] No market_health_daily data found on or before {eval_date}. "
                    f"Latest available date: {latest_date}. "
                    f"Check: (1) market_health_daily freshness, (2) eval_date not in future"
                )

            # Data exists but VIX level is NULL: data quality issue
            data_date, vix_raw = rows[0]
            if vix_raw is None:
                raise RuntimeError(
                    f"[VIX CRITICAL] VIX level is NULL for {data_date}. "
                    f"Data quality issue in market_health_daily - vix_level column not populated. "
                    f"Check market health loader."
                )

            # VIX level available: compute score
            vix = float(vix_raw)
            if math.isnan(vix) or math.isinf(vix):
                raise RuntimeError(
                    f"[VIX CRITICAL] Non-finite VIX level for {data_date}: {vix!r}. "
                    f"Data quality issue in market_health_daily."
                )

            # Real trend: today vs ~5 sessions ago. Missing depth degrades to "not rising"
            # rather than failing - trend is an enrichment on the level score, not foundational.
            rising = False
            if len(rows) >= 6 and rows[5][1] is not None:
                vix_5d_ago = float(rows[5][1])
                if not (math.isnan(vix_5d_ago) or math.isinf(vix_5d_ago)):
                    rising = vix > vix_5d_ago

            score, detail = self._vix_score(vix, rising)
            return {"value": round(vix, 1), "score": score, **detail}

        except RuntimeError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[VIX CRITICAL] VIX regime query failed: {e}. "
                f"Cannot proceed with position sizing without volatility regime data."
            ) from e

    def put_call_ratio(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Put/call ratio (contrarian indicator - OPTIONAL enrichment), z-scored against
        its own real history.

        FIXED 2026-08-22 (goal: exposure-model integrity review): the old scoring formula
        (score = (pcr - 0.7) * 100) was calibrated for the classic CBOE broad-market
        VOLUME put/call ratio (~0.5-1.2 typical range) - but the value actually fed in here
        is a single-expiration SPY options OPEN-INTEREST ratio (see
        loaders/market_health_fetchers.py's PutCallRatioFetcher), a structurally different,
        noisier metric that runs higher (live-verified: real readings in this DB span
        0.87-2.84 across three weeks with nothing unusual happening on any of those days -
        crossing 2.0, near this factor's old max-score ceiling, three separate times in an
        ordinary market). Scoring a metric against thresholds built for a DIFFERENT metric's
        distribution isn't a real signal, just a coincidence of similar-looking numbers.
        Now z-scored against its own real historical distribution instead, the same
        convention every other factor in this file uses. That history is thin (this source
        only started 2026-07) so this degrades gracefully to unavailable rather than a fixed
        threshold when there isn't enough of it yet - an honest "don't know" beats a
        confident wrong number.
        """
        try:
            # put_call_ratio_data_unavailable must be excluded explicitly, not inferred from
            # NULL-ness alone: 8 historical rows (2026-07-02 to 2026-07-14) have a real-looking
            # non-NULL put_call_ratio (a stale 2.0531 repeated across every one of them) even
            # though the fetch failed and data_unavailable=True - a failed-fetch value that was
            # never cleared from the column. Without this filter, any eval_date landing on one
            # of those dates (e.g. a backtest) would silently score real position-sizing input
            # off fabricated sentiment data instead of raising the fail-fast error below.
            cur.execute(
                "SELECT put_call_ratio FROM market_health_daily "
                "WHERE date <= %s AND put_call_ratio IS NOT NULL "
                "AND put_call_ratio_data_unavailable IS NOT TRUE "
                "ORDER BY date DESC LIMIT 1",
                (eval_date,),
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                return {
                    "data_unavailable": True,
                    "reason": f"Put/call ratio data unavailable on or before {eval_date} (optional sentiment enrichment)",
                }

            pcr = float(row[0])
            if math.isnan(pcr) or math.isinf(pcr) or not (0.2 <= pcr <= 3.0):
                reason = f"Put/call ratio {pcr} non-finite or outside realistic 0.2-3.0 range (data quality issue)"
                logger.warning(f"[PUT_CALL_RATIO] {reason} - treating as unavailable")
                return {"data_unavailable": True, "reason": reason}

            cur.execute(
                "SELECT put_call_ratio FROM market_health_daily "
                "WHERE date <= %s AND put_call_ratio IS NOT NULL "
                "AND put_call_ratio_data_unavailable IS NOT TRUE "
                "AND put_call_ratio BETWEEN 0.2 AND 3.0 "
                "ORDER BY date DESC LIMIT 500",
                (eval_date,),
            )
            history = [float(r[0]) for r in cur.fetchall()]
            z = self._sample_zscore(pcr, history)
            if z is None:
                return {
                    "data_unavailable": True,
                    "reason": f"Insufficient put/call ratio history to z-score (have {len(history)}, need 15+)",
                    "value": round(pcr, 2),
                }
            # Higher put/call ratio = more fear priced into options = contrarian bullish, so
            # a high raw reading should score HIGH - flip the sign before mapping (the shared
            # _zscore_to_score convention treats positive input as the bearish/low-score
            # direction).
            score = self._zscore_to_score(-z)
            return {"value": round(pcr, 2), "score": score, "z": round(z, 2)}
        except (psycopg2.DatabaseError, psycopg2.OperationalError, psycopg2.ProgrammingError) as e:
            return {"data_unavailable": True, "reason": f"Query failed: {type(e).__name__}"}

    def new_highs_lows(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """52-week new highs vs new lows (critical).

        Raises RuntimeError if data unavailable - market leadership is key to confirm trends.
        New highs/lows is a 7pt factor (MarketExposure.W_NEW_HIGHS_LOWS). Missing leadership
        data is a data error, not a skip.
        """
        try:
            cur.execute(
                """
                SELECT new_highs_count, new_lows_count FROM market_health_daily
                WHERE date <= %s ORDER BY date DESC LIMIT 1
                """,
                (eval_date,),
            )
            row = cur.fetchone()
            if row and row[0] is not None and row[1] is not None:
                nh = int(row[0])
                nl = int(row[1])
                total = nh + nl
                if total > 0:
                    nh_pct = nh * 100 / total
                    score = 100.0 if nh_pct > 80 else (70.0 if nh_pct > 50 else (30.0 if nh_pct > 20 else 0.0))
                    return {
                        "new_highs": nh,
                        "new_lows": nl,
                        "nh_pct": round(nh_pct, 1),
                        "score": score,
                    }
            raise RuntimeError(
                "[NEW_HIGHS_LOWS CRITICAL] Market leadership data unavailable. "
                "Check: (1) market_health_daily table has recent readings, (2) new_highs_count and new_lows_count columns populated"
            )
        except RuntimeError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[NEW_HIGHS_LOWS CRITICAL] New highs/lows query failed: {e}. "
                f"Cannot proceed without leadership confirmation."
            ) from e

    # REMOVED 2026-08-20 (goal: finance-accuracy audit): ad_line() and credit_spread() were
    # dead code, confirmed via a repo-wide grep for any caller (zero found, including in
    # MarketExposure.compute() itself) - a real, currently-unnoticed bug class, not a
    # harmless duplicate:
    #
    # - ad_line() read `ad_line_daily.direction` - a table with NO loader anywhere in this
    #   codebase (confirmed: no migration wires it into loader_registry.py, no Step
    #   Functions state, no local_loader_scheduler.py entry) and only 20 rows total, frozen
    #   at 2026-06-26 (~2 months stale as of this fix). Because this method was never
    #   called, that staleness never actually corrupted a real exposure score - but it's
    #   exactly the kind of frozen, unmonitored data source that WOULD have, had anything
    #   ever wired it in without noticing the missing loader.
    # - credit_spread() read `credit_spreads.hy_oas` - a different table entirely from the
    #   live credit-spread signal (MarketExposure._credit_spread(), which correctly reads
    #   the real, actively-loaded FRED series economic_data.BAMLH0A0HYM2).
    #
    # The REAL, live implementations MarketExposure.compute() actually calls are its own
    # local _ad_line()/_credit_spread() methods (see the "canonical implementations... not
    # yet migrated to MarketFactorCalculator" comment in market_exposure.py) - this class's
    # own module docstring claiming "Calculate 12 market factors" was accurate in aggregate
    # (10 methods here + these 2 MarketExposure-local ones = 12) but these 2 dead methods
    # were never part of that count; they were leftover from an incomplete migration in the
    # OPPOSITE direction (consolidating everything into this calculator class) that was
    # abandoned after ad_line/credit_spread, leaving unreachable duplicates with their own
    # (untested) logic and data sources that had silently drifted from the real ones.

    def aaii(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """AAII sentiment factor - contrarian at extremes (Session 361 fix).

        Proper contrarian scoring:
        - Extreme bearish (spread < -15) = many bears scared = bullish signal = HIGH score
        - Extreme bullish (spread > 15) = many bulls greedy = bearish signal = LOW score
        - Neutral (-15 to +15) = indecision = middle score

        Raises RuntimeError if data unavailable - sentiment extremes are key contrarian signals.
        AAII is a 3pt factor. Missing sentiment data is a data error, not a skip condition.
        """
        try:
            cur.execute(
                "SELECT bullish, bearish, date FROM aaii_sentiment WHERE date <= %s ORDER BY date DESC LIMIT 1",
                (eval_date,),
            )
            row = cur.fetchone()
            if row and row[0] is not None and row[1] is not None:
                # BUG FOUND 2026-08-11: unlike every daily factor in this file (e.g. the SPY
                # selling-pressure check above), this query had no staleness bound at all -
                # "most recent reading, however old" would be used silently forever if the
                # weekly AAII loader ever stopped running (site/scraper change, Incapsula
                # bypass breaking - see loader history). AAII publishes weekly; 21 days gives
                # generous room for a holiday-delayed publication (never false-positives on
                # normal operation) while still catching a genuinely dead loader well before
                # it silently feeds a stale contrarian signal into risk scoring for months.
                reading_date = row[2]
                staleness_days = (eval_date - reading_date).days
                if staleness_days > 21:
                    raise RuntimeError(
                        f"[AAII CRITICAL] AAII sentiment data is stale: most recent reading from "
                        f"{reading_date} ({staleness_days} days before eval_date {eval_date}), "
                        f"exceeds 21-day tolerance for a weekly survey. Check the aaii_sentiment "
                        f"loader - it may have stopped running."
                    )
                # aaii_sentiment.bullish/bearish are stored as fractions of 1 (e.g. 0.3470 =
                # 34.7%), not percentage-points - confirmed live 2026-08-20 across 2036/2041
                # rows back to 1987. The spread/±15 contrarian thresholds below are calibrated
                # for a percentage-point scale, so convert here rather than at every call site.
                bull = float(row[0]) * 100
                bear = float(row[1]) * 100
                if math.isnan(bull) or math.isinf(bull) or math.isnan(bear) or math.isinf(bear):
                    raise RuntimeError(
                        f"[AAII CRITICAL] Non-finite AAII sentiment data: bullish={bull!r}, bearish={bear!r}. "
                        f"Data quality issue in aaii_sentiment."
                    )
                spread = bull - bear

                # Contrarian scoring: opposite of consensus
                if spread < -15:
                    # Extreme bearish: many bears = contrarian bullish signal
                    # Scale: spread -15 → score 75, spread -30 → score 85, spread -50+ → score 95
                    score = 75 + min(20, abs(spread + 15) / 2)
                elif spread > 15:
                    # Extreme bullish: many bulls = contrarian bearish signal
                    # Scale: spread +15 → score 25, spread +30 → score 15, spread +50+ → score 5
                    score = 25 - min(20, (spread - 15) / 2)
                else:
                    # Neutral range: -15 to +15 = indecision, neither bullish nor bearish
                    score = 50

                # Clamp to 0-100 range
                score = min(100, max(0, score))

                return {
                    "bullish": round(bull, 1),
                    "bearish": round(bear, 1),
                    "bullish_pct": round(bull, 1),
                    "bearish_pct": round(bear, 1),
                    "spread": round(spread, 1),
                    "score": score,
                }
            raise RuntimeError(
                "[AAII CRITICAL] AAII sentiment data unavailable. "
                "Check: (1) aaii_sentiment table has recent readings, (2) bullish and bearish columns are populated"
            )
        except RuntimeError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[AAII CRITICAL] AAII sentiment query failed: {e}. Cannot proceed without contrarian sentiment data."
            ) from e

    # positioning() / _insider_buying_breadth() / _short_interest_trend() removed
    # 2026-08-23 - see module docstring.
