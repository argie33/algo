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

        Raises: RuntimeError if score is missing or invalid (fail-closed)
        """
        score = factor.get("score")
        if score is None:
            raise ValueError("Market factor score missing - all factors required for exposure calculation")

        try:
            score = float(score)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Market factor score is not numeric: {score}") from e

        return score * weight / 100.0, weight

    def _pct_above_ma(self, eval_date: Any, ma_days: int, cur: Any) -> dict[str, Any]:
        """Calculate % of stocks trading above N-day MA (optional).

        Linear scale: 20% = 0 pts, 50% = 50 pts, 80% = 100 pts
        Uses most recent available date on or before eval_date (technical_data_daily may lag prices).
        Returns neutral score if breadth data unavailable.
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
                score = (pct - 20) / 0.6 if pct >= 20 else 0
                score = min(100, max(0, score))
                return {"value": pct, "score": score}
            logger.debug(f"Breadth {ma_days}-day unavailable for {eval_date} (optional, using neutral score)")
            return {"value": None, "score_factor": 0.5, "score": 50}
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"Breadth {ma_days}-day MA query failed (optional): {e}, using neutral score")
            return {"value": None, "score_factor": 0.5, "score": 50}

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
        """Trend factor: SPY vs 30-week MA (optional).

        Returns neutral score if data unavailable. Trend is a 15pt factor
        but missing weekly price data is acceptable — falls back to neutral.
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
            logger.debug(f"Trend data unavailable for {eval_date} (optional, using neutral score)")
            return {"above_30wma": None, "score": 50, "value": None}
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ValueError) as e:
            logger.debug(f"Trend calculation failed (optional): {e}, using neutral score")
            return {"above_30wma": None, "score": 50, "value": None}

    def spy_momentum(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """SPY 12-month momentum (TSMOM, optional).

        Returns neutral score if data unavailable. Momentum is a 10pt factor
        but missing historical data is acceptable — falls back to neutral.
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
            logger.debug(f"Momentum data unavailable for {eval_date} (optional, using neutral score)")
            return {"return_12m": None, "score": 50, "value": None}
        except (ValueError, ZeroDivisionError, TypeError, psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"Momentum calculation failed (optional): {e}, using neutral score")
            return {"return_12m": None, "score": 50, "value": None}

    def selling_pressure(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Heavy-volume down days in last 25 sessions (optional).

        Returns neutral score if data unavailable. Selling pressure is a 10pt
        factor but missing volume/price data is acceptable — falls back to neutral.
        """
        try:
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
            if row:
                # Use 0 if data missing rather than failing
                dist = int(row[0]) if row[0] is not None else 0
                # 0-2 = 100, 3-4 = 60, 5+ = 20
                score = 100.0 if dist <= 2 else (60.0 if dist <= 4 else 20.0)
                return {"heavy_down_days": dist, "count": dist, "score": score}
            logger.debug(f"Selling pressure unavailable for {eval_date} (optional, using neutral score)")
            return {"heavy_down_days": None, "count": None, "score": 50}
        except (ValueError, ZeroDivisionError, TypeError, psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"Selling pressure calculation failed (optional): {e}, using neutral score")
            return {"heavy_down_days": None, "count": None, "score": 50}

    def vix_regime(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """VIX level + term structure."""
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
                return {"vix": round(vix, 1), "score": score, **detail}
            raise RuntimeError("No VIX data available for volatility regime calculation")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"VIX regime calculation failed: {e}") from e

    def put_call_ratio(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Put/call ratio (contrarian indicator, optional).

        Returns neutral score (50) if data unavailable, allowing market exposure
        computation to continue without put/call data. Put/call is an 8pt factor
        (non-critical) vs VIX (10pt critical) — missing data degrades signal but
        doesn't halt calculation.
        """
        try:
            cur.execute("SAVEPOINT sp_put_call")
            cur.execute(
                "SELECT put_call_ratio FROM market_health_daily WHERE date = %s ORDER BY date DESC LIMIT 1",
                (eval_date,),
            )
            row = cur.fetchone()
            cur.execute("RELEASE SAVEPOINT sp_put_call")
            if not row or row[0] is None:
                logger.debug(f"Put/call ratio unavailable for {eval_date} (optional, using neutral score)")
                return {"put_call_ratio": None, "score": 50}
            pcr = float(row[0])
            score = max(0, min(100, (pcr - 0.7) * 100))
            return {"put_call_ratio": round(pcr, 2), "score": score}
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sp_put_call")
                cur.execute("RELEASE SAVEPOINT sp_put_call")
            except Exception:
                pass
            logger.debug(f"Put/call ratio query failed (optional): {e}, using neutral score")
            return {"put_call_ratio": None, "score": 50}

    def new_highs_lows(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """52-week new highs vs new lows (optional).

        Returns neutral score (50) if data unavailable. New highs/lows is a 7pt
        factor (non-critical) — missing data degrades signal but doesn't halt
        calculation.
        """
        try:
            cur.execute("SAVEPOINT sp_nhnl")
            cur.execute(
                """
                SELECT new_highs_count, new_lows_count FROM market_health_daily
                WHERE date = %s ORDER BY date DESC LIMIT 1
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
            logger.debug(f"New highs/lows unavailable for {eval_date} (optional, using neutral score)")
            return {"new_highs": None, "new_lows": None, "nh_pct": None, "score": 50}
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sp_nhnl")
                cur.execute("RELEASE SAVEPOINT sp_nhnl")
            except Exception:
                pass
            logger.debug(f"New highs/lows query failed (optional): {e}, using neutral score")
            return {"new_highs": None, "new_lows": None, "nh_pct": None, "score": 50}

    def ad_line(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Advance/decline line vs SPY (optional).

        Returns neutral score (50) if data unavailable. A/D line is a 6pt factor
        (non-critical) — missing data degrades signal but doesn't halt calculation.
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
                return {"direction": direction, "score": score}
            logger.debug(f"A/D line unavailable for {eval_date} (optional, using neutral score)")
            return {"direction": None, "score": 50}
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sp_ad_line")
                cur.execute("RELEASE SAVEPOINT sp_ad_line")
            except Exception:
                pass
            logger.debug(f"A/D line query failed (optional): {e}, using neutral score")
            return {"direction": None, "score": 50}

    def credit_spread(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """High-yield credit spread (HY OAS, optional).

        Returns neutral score (50) if data unavailable. Credit spreads is a 10pt
        factor — missing data degrades signal but doesn't halt calculation.
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
                return {"hy_oas": round(oas, 0), "score": score}
            logger.debug(f"Credit spreads unavailable for {eval_date} (optional, using neutral score)")
            return {"hy_oas": None, "score": 50}
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sp_credit")
                cur.execute("RELEASE SAVEPOINT sp_credit")
            except Exception:
                pass
            logger.debug(f"Credit spread query failed (optional): {e}, using neutral score")
            return {"hy_oas": None, "score": 50}

    def aaii(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """AAII sentiment (contrarian at extremes only, optional).

        Returns neutral score (50) if data unavailable. AAII is a 3pt factor
        (non-critical) — missing data degrades signal but doesn't halt calculation.
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
                    "spread": round(spread, 1),
                    "score": score,
                }
            logger.debug(f"AAII sentiment unavailable for {eval_date} (optional, using neutral score)")
            return {"bullish": None, "bearish": None, "spread": None, "score": 50}
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sp_aaii")
                cur.execute("RELEASE SAVEPOINT sp_aaii")
            except Exception:
                pass
            logger.debug(f"AAII sentiment query failed (optional): {e}, using neutral score")
            return {"bullish": None, "bearish": None, "spread": None, "score": 50}

    def naaim(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """NAAIM exposure (contrarian positioning, optional). Uses most recent weekly reading."""
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
                return {"exposure": round(exp, 1), "score": score}
            logger.debug(f"NAAIM unavailable for {eval_date} (optional, using neutral score)")
            return {"exposure": None, "score": 50}
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT sp_naaim")
                cur.execute("RELEASE SAVEPOINT sp_naaim")
            except Exception:
                pass
            logger.debug(f"NAAIM query failed (optional): {e}, using neutral score")
            return {"exposure": None, "score": 50}
