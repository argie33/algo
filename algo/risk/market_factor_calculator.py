#!/usr/bin/env python3
"""
Market Factor Calculator - Compute individual market factors

Responsibilities:
- Calculate 12 market factors (trend, momentum, breadth, VIX, credit, etc.)
- Provide utility methods for common calculations (_pct_above_ma, _vix_score, etc.)
- Return structured factor data for scoring
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

    def _vix_score(self, vix: float, rising: bool, term_structure: float | None = None) -> tuple[float, dict[str, Any]]:
        """Score VIX level and term structure.

        Level tiers: <15=100, 15-25=80, 25-35=40, 35+=0
        Term structure penalty if inverted (backwardation).
        """
        if vix < 15:
            level_score = 100.0
        elif vix < 25:
            level_score = 80.0
        elif vix < 35:
            level_score = 40.0
        else:
            level_score = 0.0

        # Trend penalty
        trend_mult = 1.0 if not rising else 0.8

        # Term structure penalty if inverted
        ts_mult = 1.0
        if term_structure and term_structure < 1.0:
            ts_mult = 0.6  # backwardation penalty

        final_score = level_score * trend_mult * ts_mult
        return final_score, {
            "level": round(vix, 1),
            "level_score": round(level_score, 1),
            "rising": rising,
            "term_structure": round(term_structure, 2) if term_structure else None,
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
        """VIX level + term structure (critical).

        Raises RuntimeError if data unavailable - VIX is foundational to risk assessment.
        VIX is a 10pt factor. Missing volatility data is a data error, not a skip condition.
        """
        try:
            # Get latest VIX data on or before eval_date
            cur.execute(
                "SELECT date, vix_level FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 1",
                (eval_date,),
            )
            row = cur.fetchone()

            # No data available: fail-fast with diagnostic info
            if not row:
                cur.execute("SELECT MAX(date) FROM market_health_daily")
                latest_row = cur.fetchone()
                latest_date = latest_row[0] if latest_row and latest_row[0] is not None else "EMPTY"
                raise RuntimeError(
                    f"[VIX CRITICAL] No market_health_daily data found on or before {eval_date}. "
                    f"Latest available date: {latest_date}. "
                    f"Check: (1) market_health_daily freshness, (2) eval_date not in future"
                )

            # Data exists but VIX level is NULL: data quality issue
            data_date = row[0]
            vix = row[1]
            if vix is None:
                raise RuntimeError(
                    f"[VIX CRITICAL] VIX level is NULL for {data_date}. "
                    f"Data quality issue in market_health_daily - vix_level column not populated. "
                    f"Check market health loader."
                )

            # VIX level available: compute score
            vix = float(vix)
            if math.isnan(vix) or math.isinf(vix):
                raise RuntimeError(
                    f"[VIX CRITICAL] Non-finite VIX level for {data_date}: {vix!r}. "
                    f"Data quality issue in market_health_daily."
                )
            score, detail = self._vix_score(vix, vix > 20)
            return {"value": round(vix, 1), "score": score, **detail}

        except RuntimeError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[VIX CRITICAL] VIX regime query failed: {e}. "
                f"Cannot proceed with position sizing without volatility regime data."
            ) from e

    def put_call_ratio(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Put/call ratio (contrarian indicator, 8pt factor - OPTIONAL enrichment).

        Returns explicit data_unavailable marker if data unavailable. Put/call ratio is
        optional sentiment enrichment (Session 291+: yfinance removed, no official source).
        Gracefully degrades with explicit marker, not RuntimeError.
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
            if not row:
                # Put/call ratio data unavailable - return explicit marker
                # This is an expected, graceful degradation (optional enrichment)
                return {
                    "data_unavailable": True,
                    "reason": f"Put/call ratio data unavailable on or before {eval_date} (optional sentiment enrichment)",
                }

            # Support both DictCursor (row is dict) and tuple cursor (row is tuple)
            if isinstance(row, dict):
                pcr_val = row.get("put_call_ratio")
            else:
                # Tuple result - validate structure before indexing
                if not row or len(row) < 1:
                    return {"data_unavailable": True, "reason": "Query returned empty or invalid result structure"}
                pcr_val = row[0]
            if pcr_val is None:
                return {"data_unavailable": True, "reason": "put_call_ratio value is NULL (data quality issue)"}

            pcr = float(pcr_val)
            if not (0.2 <= pcr <= 3.0):
                reason = f"Put/call ratio {pcr} outside realistic 0.2-3.0 range (data quality issue)"
                logger.warning(f"[PUT_CALL_RATIO] {reason} - treating as unavailable")
                return {"data_unavailable": True, "reason": reason}
            score = max(0, min(100, (pcr - 0.7) * 100))
            return {"value": round(pcr, 2), "score": score}
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
                bull = float(row[0])
                bear = float(row[1])
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

    def positioning(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any]:
        """Positioning & flows (5pt factor - OPTIONAL enrichment, replaces NAAIM 2026-08-20).

        NAAIM's public page transitioned to a subscription-based access model 2026-08-01, with
        no free source left. Rather than replace it with another scraped survey, this factor
        aggregates two datasets already ingested for other purposes into a universe-wide
        "smart money positioning" read - immune to paywalling since both are official-source
        filings (SEC Form 4, FINRA), not a voluntary self-reported poll:

        - Insider buying breadth (60% weight): % of the actively-reporting universe with net
          insider buying over the trailing 90 days (insider_transaction_velocity, Form 4).
          Scored as a DIRECT signal, not contrarian - academic research on aggregate insider
          trading (Seyhun 1998, Lakonishok & Lee 2001) finds insider buying breadth positively
          predicts forward market returns, most strongly at extremes (insiders collectively
          "buying the dip" near lows).
        - Short interest trend (40% weight): change in market-wide average short interest %
          over the last ~4 FINRA settlement cycles (short_interest_finra, bi-weekly). Scored as
          a direct bearish-conviction signal (rising aggregate short interest = more informed
          bearish positioning building), not the contrarian squeeze-risk reading - that's a
          tactical trade-level signal, not a risk-model input.

        Score thresholds below are a first pass, not backtested (see the exposure-model design
        memo's validation section) - reasonable starting points pending real calibration once
        enough history accumulates.

        Returns explicit data_unavailable marker if either input can't be computed, mirroring
        put_call_ratio's graceful-degradation pattern - this is new, unvalidated signal and
        must not take the whole 12-factor composite down if it's temporarily unavailable.
        """
        try:
            insider = self._insider_buying_breadth(eval_date, cur)
            short_int = self._short_interest_trend(eval_date, cur)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            return {"data_unavailable": True, "reason": f"Positioning query failed: {type(e).__name__}: {e}"}

        if insider is None and short_int is None:
            return {
                "data_unavailable": True,
                "reason": (
                    f"Positioning data unavailable on or before {eval_date}: neither insider "
                    f"buying breadth nor short interest trend could be computed (insufficient "
                    f"sample size or no data)."
                ),
            }

        parts: list[tuple[float, float]] = []  # (score, weight)
        detail: dict[str, Any] = {}
        if insider is not None:
            parts.append((insider["score"], 0.60))
            detail["insider_buying_breadth_pct"] = insider["breadth_pct"]
            detail["insider_active_count"] = insider["active_count"]
        else:
            detail["insider_buying_breadth_pct"] = None
        if short_int is not None:
            parts.append((short_int["score"], 0.40))
            detail["short_interest_chg_pct"] = short_int["chg_pct"]
        else:
            detail["short_interest_chg_pct"] = None

        total_weight = sum(w for _, w in parts)
        blended = sum(s * w for s, w in parts) / total_weight
        return {"value": round(blended, 1), "score": round(blended, 1), **detail}

    def _insider_buying_breadth(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any] | None:
        """% of actively-reporting universe with net insider buying over trailing 30d.

        Uses the latest measurement per symbol on or before eval_date (this table is a
        rolling per-symbol watermark panel, not a fixed daily snapshot - MAX(measurement_date)
        across the whole table does not mean every symbol was refreshed that day). A 120-day
        staleness bound per symbol excludes rows too old to reflect a genuine "trailing 90d"
        window; a minimum 50-symbol active sample guards against noise when coverage is thin.

        Uses the 90-day columns, not 30-day: live-verified 2026-08-20 that
        buy_transactions_30d/sell_transactions_30d are 0 for effectively the entire universe
        (0/4878 active even in a full-universe loader pass dated 2026-08-13) while the 90-day
        columns show healthy activity (1998/5604 active as of the same check) - looks like a
        real bug in the loader's 30-day window computation, not a quiet market. Not
        investigated/fixed here (out of scope for the exposure-model work this factor is part
        of); using the 90-day columns sidesteps it and is arguably the better choice anyway
        for a slower-moving positioning signal less prone to zero-activity gaps.
        """
        cur.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (symbol)
                    symbol, buy_transactions_90d, sell_transactions_90d, net_buy_transactions_90d
                FROM insider_transaction_velocity
                WHERE measurement_date <= %s AND measurement_date >= %s::date - INTERVAL '120 days'
                ORDER BY symbol, measurement_date DESC
            )
            SELECT
                COUNT(*) FILTER (WHERE COALESCE(buy_transactions_90d, 0) + COALESCE(sell_transactions_90d, 0) > 0)
                    AS active_count,
                COUNT(*) FILTER (
                    WHERE COALESCE(buy_transactions_90d, 0) + COALESCE(sell_transactions_90d, 0) > 0
                    AND COALESCE(net_buy_transactions_90d, 0) > 0
                ) AS net_buyers
            FROM latest
            """,
            (eval_date, eval_date),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            return None
        active_count, net_buyers = int(row[0]), int(row[1] or 0)
        if active_count < 50:
            logger.info(
                f"[POSITIONING] Insider breadth sample too small ({active_count} active symbols) for {eval_date}, skipping."
            )
            return None
        breadth_pct = net_buyers * 100.0 / active_count
        # Linear: 30% net-buyer breadth -> 0, 50% -> 50, 70% -> 100. Illustrative bounds
        # (most companies show some routine insider selling for tax/diversification reasons,
        # so 50%+ net-buyer breadth is already an elevated reading) - see docstring on
        # positioning() re: calibration.
        score = min(100.0, max(0.0, (breadth_pct - 30) / 0.4))
        return {"score": score, "breadth_pct": round(breadth_pct, 1), "active_count": active_count}

    def _short_interest_trend(self, eval_date: _date, cur: PsycopgCursor[Any]) -> dict[str, Any] | None:
        """Change in market-wide average short interest % over the available FINRA settlement cycles.

        FINRA settlement cycles are bi-weekly (15th/EOM); up to 4 cycles back (~8 weeks) is
        used when available. Requires at least 2 cycles (current + one baseline) rather than
        a hard 4 - live-verified 2026-08-20 this local DB only has 3 cycles of history yet
        (a real backfill-depth limitation, not a bug), and a 4-cycle floor made this signal
        permanently unavailable rather than using a shorter, still-meaningful lookback. Rising
        aggregate short interest is scored as a direct bearish-conviction signal (see
        positioning() docstring), not contrarian squeeze risk.

        Uses the MEDIAN of short_pct, not AVG, and excludes values outside a sane 0-100%
        range - live-verified 2026-08-20 that short_pct carries real outlier corruption
        (max observed 1,035,388.96% and 3,486.01% in different cycles, presumably a
        shares_outstanding computation issue upstream - see short_interest_finra's own
        short_pct = short_shares / company_info_sec.shares_outstanding derivation per
        steering/DATA_LOADERS.md). A plain AVG() over ~4,400-4,900 rows swung from 9.5% to
        220% between adjacent cycles purely from a handful of these corrupted rows - not
        investigated/fixed at the source here (out of scope for this factor), but a
        market-wide positioning signal cannot be built on an aggregate that a few corrupted
        rows can dominate.
        """
        cur.execute(
            "SELECT DISTINCT settlement_date FROM short_interest_finra WHERE settlement_date <= %s "
            "ORDER BY settlement_date DESC LIMIT 4",
            (eval_date,),
        )
        cycles = [r[0] for r in cur.fetchall()]
        if len(cycles) < 2:
            return None
        current_cycle, baseline_cycle = cycles[0], cycles[-1]

        median_sql = (
            "SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY short_pct) FROM short_interest_finra "
            "WHERE settlement_date = %s AND data_unavailable IS NOT TRUE AND short_pct IS NOT NULL "
            "AND short_pct BETWEEN 0 AND 100"
        )
        cur.execute(median_sql, (current_cycle,))
        current_row = cur.fetchone()
        cur.execute(median_sql, (baseline_cycle,))
        baseline_row = cur.fetchone()
        if not current_row or current_row[0] is None or not baseline_row or baseline_row[0] is None:
            return None
        current_avg, baseline_avg = float(current_row[0]), float(baseline_row[0])
        if math.isnan(current_avg) or math.isinf(current_avg) or math.isnan(baseline_avg) or math.isinf(baseline_avg):
            return None
        if baseline_avg <= 0:
            return None
        chg_pct = (current_avg - baseline_avg) / baseline_avg * 100.0
        # Linear: -15% (short interest falling, covering) -> 80, 0% (flat) -> 50,
        # +15% (short interest rising, bearish conviction building) -> 20. Illustrative bounds.
        score = min(100.0, max(0.0, 50.0 - chg_pct * 2.0))
        return {"score": score, "chg_pct": round(chg_pct, 1)}
