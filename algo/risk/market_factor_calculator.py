#!/usr/bin/env python3
"""
Market Factor Calculator - Compute individual market factors

Responsibilities:
- Calculate 12 market factors (trend, momentum, breadth, VIX, credit, etc.)
- Provide utility methods for common calculations (_pct_above_ma, _vix_score, etc.)
- Return structured factor data for scoring
"""

import logging
from typing import Any

import psycopg2

logger = logging.getLogger(__name__)


class MarketFactorCalculator:
    """Calculate individual market exposure factors."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def _wt_pts(factor: dict[str, Any], weight: float) -> tuple[float, float]:
        """Scale factor score to weight. Returns (pts, avail_weight).

        Raises exception if score is missing — market factors are critical
        for position sizing and must not silently degrade.
        """
        score = factor.get("score")
        if score is None:
            factor_name = factor.get("name", "unknown")
            raise ValueError(
                f"[MARKET_FACTOR] Missing score for factor '{factor_name}'. "
                f"Market factors are critical for exposure calculation — missing data must be explicit."
            )

        try:
            score = float(score)
        except (ValueError, TypeError) as e:
            factor_name = factor.get("name", "unknown")
            raise ValueError(
                f"[MARKET_FACTOR] Invalid score for factor '{factor_name}': {score!r}. "
                f"Cannot compute exposure with non-numeric factor scores."
            ) from e

        return score * weight / 100.0, weight

    def _pct_above_ma(self, eval_date: Any, ma_days: int, cur: Any) -> dict[str, Any]:
        """Calculate % of stocks trading above N-day MA (critical).

        Linear scale: 20% = 0 pts, 50% = 50 pts, 80% = 100 pts
        Uses most recent available date on or before eval_date (technical_data_daily may lag prices).
        Raises RuntimeError if data unavailable — market breadth is required for position sizing.
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
                # Linear: 20% → 0, 50% → 50, 80% → 100
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
        level_score = 100.0
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

    def _has_market_confirmation(self, eval_date: Any, cur: Any) -> bool:
        """Check for volume-backed rally confirmation (hard gate).

        True if: volume today > 20-day average AND price > previous close
        """
        try:
            cur.execute(
                """
                WITH d AS (
                    SELECT close, volume,
                           AVG(volume) OVER (ORDER BY date ROWS BETWEEN 19 PRECEDING AND 1 PRECEDING) as avg20,
                           LAG(close) OVER (ORDER BY date) as prev_close,
                           symbol
                    FROM price_daily
                    WHERE symbol = 'SPY' AND date <= %s
                    ORDER BY date DESC LIMIT 1
                )
                SELECT (volume > avg20 AND close > prev_close) FROM d
                """,
                (eval_date,),
            )
            row = cur.fetchone()
            return bool(row and row[0]) if row else False
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"Market confirmation check failed: {e}", exc_info=True)
            raise RuntimeError(
                f"Cannot determine market confirmation status: database query failed ({e}). "
                f"Cannot proceed with trading without valid market data."
            ) from e

    # ============= Factor Implementations =============

    def trend_30wk(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Trend factor: SPY vs 30-week MA (critical).

        Raises RuntimeError if data unavailable — SPY trend is foundational to veto logic.
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
                if spy is None or sma is None:
                    raise ValueError(f"SPY trend data not numeric: close={row[0]}, sma={row[1]}")
                score = 100.0 if spy > sma else 0.0
                return {"above_30wma": spy > sma, "score": score, "value": "bullish" if spy > sma else "bearish"}
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

    def spy_momentum(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """SPY 12-month momentum (TSMOM, critical).

        Raises RuntimeError if data unavailable — momentum is key to trend confirmation.
        Momentum is a 10pt factor. Missing historical data is a data error, not a skip condition.
        """
        try:
            cur.execute(
                """
                WITH d AS (
                    SELECT close, date FROM price_daily WHERE symbol = 'SPY' AND date <= %s
                    ORDER BY date DESC LIMIT 1
                ),
                y_ago AS (
                    SELECT close FROM price_daily WHERE symbol = 'SPY' AND date <= %s::date - INTERVAL '365 days'
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
                if current is None or year_ago is None:
                    raise ValueError(f"SPY momentum data not numeric: current={row[0]}, year_ago={row[1]}")
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

    def selling_pressure(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Heavy-volume down days in last 25 sessions (critical).

        Raises RuntimeError if data unavailable — selling pressure is required for veto 3.
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
            age = eval_date - most_recent_date if hasattr(eval_date, "__sub__") else 0
            if age and age.days > 0:
                raise RuntimeError(
                    f"[SELLING_PRESSURE CRITICAL] SPY price data is stale: from {most_recent_date}, "
                    f"but eval_date is {eval_date} ({age.days} days old). "
                    f"Distribution day detection requires TODAY's market data (prices, volumes). "
                    f"Cannot use yesterday's selling pressure for today's risk assessment."
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
                # 0-2 = 100, 3-4 = 60, 5+ = 20
                score = 100.0 if dist <= 2 else (60.0 if dist <= 4 else 20.0)
                return {"heavy_down_days": dist, "count": dist, "value": dist, "score": score}
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

    def vix_regime(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """VIX level + term structure (critical).

        Raises RuntimeError if data unavailable — VIX is foundational to risk assessment.
        VIX is a 10pt factor. Missing volatility data is a data error, not a skip condition.
        """
        try:
            cur.execute(
                "SELECT vix_level FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 1",
                (eval_date,),
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                vix = float(row[0])
                # Simplified: no term structure data
                score, detail = self._vix_score(vix, vix > 20)
                return {"value": round(vix, 1), "score": score, **detail}
            raise RuntimeError(
                "[VIX CRITICAL] VIX level unavailable. "
                "Check: (1) market_health_daily table has recent VIX readings, (2) vix_level column is populated"
            )
        except RuntimeError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[VIX CRITICAL] VIX regime query failed: {e}. "
                f"Cannot proceed with position sizing without volatility regime data."
            ) from e

    def put_call_ratio(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Put/call ratio (contrarian indicator, critical).

        Raises RuntimeError if data unavailable — sentiment extremes are key to risk management.
        Put/call is a 5pt factor. Missing options data is a data error, not a skip condition.
        """
        try:
            cur.execute("SAVEPOINT sp_put_call")
            cur.execute(
                "SELECT put_call_ratio FROM market_health_daily WHERE date <= %s ORDER BY date DESC LIMIT 1",
                (eval_date,),
            )
            row = cur.fetchone()
            cur.execute("RELEASE SAVEPOINT sp_put_call")
            if not row or row[0] is None:
                raise RuntimeError(
                    "[PUT_CALL CRITICAL] Put/call ratio unavailable. "
                    "Check: (1) market_health_daily table has recent readings, (2) put_call_ratio column is populated"
                )
            pcr = float(row[0])
            if pcr <= 0:
                raise RuntimeError(
                    f"[PUT_CALL CRITICAL] Put/call ratio invalid for {eval_date}: {pcr}. "
                    f"Put/call ratio must be > 0 (ratio of puts to calls). "
                    f"Value of {pcr} is corrupted data. Check market_health_daily data quality."
                )
            score = max(0, min(100, (pcr - 0.7) * 100))
            return {"value": round(pcr, 2), "score": score}
        except RuntimeError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sp_put_call")
                cur.execute("RELEASE SAVEPOINT sp_put_call")
            except Exception as cleanup_err:
                logger.error(f"Savepoint cleanup failed (put_call_ratio): {cleanup_err}", exc_info=True)
            raise RuntimeError(
                f"[PUT_CALL CRITICAL] Put/call ratio query failed: {e}. "
                f"Cannot proceed with position sizing without sentiment data."
            ) from e

    def new_highs_lows(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """52-week new highs vs new lows (critical).

        Raises RuntimeError if data unavailable — market leadership is key to confirm trends.
        New highs/lows is a 5pt factor. Missing leadership data is a data error, not a skip.
        """
        try:
            cur.execute("SAVEPOINT sp_nhnl")
            cur.execute(
                """
                SELECT new_highs_count, new_lows_count FROM market_health_daily
                WHERE date <= %s ORDER BY date DESC LIMIT 1
                """,
                (eval_date,),
            )
            row = cur.fetchone()
            cur.execute("RELEASE SAVEPOINT sp_nhnl")
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
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sp_nhnl")
                cur.execute("RELEASE SAVEPOINT sp_nhnl")
            except Exception as cleanup_err:
                logger.error(f"Savepoint cleanup failed (new_highs_lows): {cleanup_err}", exc_info=True)
            raise RuntimeError(
                f"[NEW_HIGHS_LOWS CRITICAL] New highs/lows query failed: {e}. "
                f"Cannot proceed without leadership confirmation."
            ) from e

    def ad_line(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Advance/decline line vs SPY (critical).

        Raises RuntimeError if data unavailable — A/D confirmation is key to market health check.
        A/D line is a 5pt factor. Missing breadth direction data is a data error, not a skip.
        """
        try:
            cur.execute("SAVEPOINT sp_ad_line")
            cur.execute(
                """
                WITH ad AS (
                    SELECT direction FROM ad_line_daily WHERE date <= %s ORDER BY date DESC LIMIT 1
                )
                SELECT direction FROM ad
                """,
                (eval_date,),
            )
            row = cur.fetchone()
            cur.execute("RELEASE SAVEPOINT sp_ad_line")
            if row is not None and row[0] is not None:
                direction = row[0]
                score = 100.0 if direction == "up" else 0.0
                return {"direction": direction, "relation": direction, "value": direction, "score": score}
            raise RuntimeError(
                "[AD_LINE CRITICAL] Advance/decline line data unavailable. "
                "Check: (1) ad_line_daily table has recent readings, (2) direction column is populated"
            )
        except RuntimeError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sp_ad_line")
                cur.execute("RELEASE SAVEPOINT sp_ad_line")
            except Exception as cleanup_err:
                logger.error(f"Savepoint cleanup failed (ad_line): {cleanup_err}", exc_info=True)
            raise RuntimeError(
                f"[AD_LINE CRITICAL] A/D line query failed: {e}. Cannot proceed without breadth confirmation."
            ) from e

    def credit_spread(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """High-yield credit spread (HY OAS, critical).

        Raises RuntimeError if data unavailable — credit stress is key systemic risk indicator.
        Credit spread is a 10pt factor. Missing credit data is a data error, not a skip.
        """
        try:
            cur.execute("SAVEPOINT sp_credit")
            cur.execute(
                "SELECT hy_oas FROM credit_spreads WHERE date <= %s ORDER BY date DESC LIMIT 1",
                (eval_date,),
            )
            row = cur.fetchone()
            cur.execute("RELEASE SAVEPOINT sp_credit")
            if row is not None and row[0] is not None:
                oas = float(row[0])
                score = max(0, min(100, 100 - (oas - 300) / 2))
                return {"value": round(oas, 0), "score": score}
            raise RuntimeError(
                "[CREDIT_SPREAD CRITICAL] High-yield credit spread data unavailable. "
                "Check: (1) credit_spreads table has recent readings, (2) hy_oas column is populated"
            )
        except RuntimeError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sp_credit")
                cur.execute("RELEASE SAVEPOINT sp_credit")
            except Exception as cleanup_err:
                logger.error(f"Savepoint cleanup failed (credit_spread): {cleanup_err}", exc_info=True)
            raise RuntimeError(
                f"[CREDIT_SPREAD CRITICAL] Credit spread query failed: {e}. "
                f"Cannot proceed without systemic stress assessment."
            ) from e

    def aaii(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """AAII sentiment (contrarian at extremes, critical).

        Raises RuntimeError if data unavailable — sentiment extremes are key contrarian signals.
        AAII is a 3pt factor. Missing sentiment data is a data error, not a skip condition.
        """
        try:
            cur.execute("SAVEPOINT sp_aaii")
            cur.execute(
                "SELECT bullish, bearish FROM aaii_sentiment WHERE date <= %s ORDER BY date DESC LIMIT 1",
                (eval_date,),
            )
            row = cur.fetchone()
            cur.execute("RELEASE SAVEPOINT sp_aaii")
            if row and row[0] is not None and row[1] is not None:
                bull = float(row[0])
                bear = float(row[1])
                spread = bull - bear
                score = min(100, max(0, (abs(spread) - 15) * 5))
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
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sp_aaii")
                cur.execute("RELEASE SAVEPOINT sp_aaii")
            except Exception as cleanup_err:
                logger.error(f"Savepoint cleanup failed (aaii): {cleanup_err}", exc_info=True)
            raise RuntimeError(
                f"[AAII CRITICAL] AAII sentiment query failed: {e}. Cannot proceed without contrarian sentiment data."
            ) from e

    def naaim(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """NAAIM exposure (contrarian positioning, critical). Uses most recent weekly reading.

        Raises RuntimeError if data unavailable — professional positioning is key contrarian signal.
        NAAIM is a 3pt factor. Missing positioning data is a data error, not a skip condition.
        """
        try:
            cur.execute("SAVEPOINT sp_naaim")
            cur.execute(
                "SELECT naaim_number_mean FROM naaim WHERE date <= %s ORDER BY date DESC LIMIT 1",
                (eval_date,),
            )
            row = cur.fetchone()
            cur.execute("RELEASE SAVEPOINT sp_naaim")
            if row is not None and row[0] is not None:
                exp = float(row[0])
                score = min(100, max(0, 100 - exp / 2))
                return {"value": round(exp, 1), "score": score}
            raise RuntimeError(
                "[NAAIM CRITICAL] NAAIM professional positioning data unavailable. "
                "Check: (1) naaim table has recent readings, (2) naaim_number_mean column is populated"
            )
        except RuntimeError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sp_naaim")
                cur.execute("RELEASE SAVEPOINT sp_naaim")
            except Exception as cleanup_err:
                logger.error(f"Savepoint cleanup failed (naaim): {cleanup_err}", exc_info=True)
            raise RuntimeError(
                f"[NAAIM CRITICAL] NAAIM query failed: {e}. Cannot proceed without professional positioning data."
            ) from e
