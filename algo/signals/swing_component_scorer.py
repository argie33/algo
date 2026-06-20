#!/usr/bin/env python3
"""
Swing Component Scorer - Calculate individual scoring components

Responsibilities:
- Compute 7 weighted scoring components (setup, trend, momentum, volume, fundamentals, sector, multi-timeframe)
- Support configuration loading
- Provide detailed scoring breakdowns
"""

import logging
from typing import Any

import psycopg2

from utils.db import DatabaseContext


logger = logging.getLogger(__name__)


class SwingComponentScorer:
    """Calculate individual swing score components."""

    W_SETUP = 25
    W_TREND = 20
    W_MOMENTUM = 20
    W_VOLUME = 12
    W_FUNDAMENTALS = 10
    W_SECTOR = 8
    W_MULTI_TF = 5

    def __init__(self, config, signals_computer):
        self.config = config
        self._signals = signals_computer

    def _load_config_weights(self, cur) -> dict[str, int]:
        """Load swing score component weights from config table if available."""
        weights = {}
        try:
            cur.execute("SELECT key, value FROM algo_config WHERE key LIKE 'swing_weight_%'")
            weights = {k: int(v) for k, v in cur.fetchall()}
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"Could not load swing weights from config: {e} — using defaults")
        return weights

    def _load_config_val(self, key: str, default, cur=None):
        """Load a single config value from database or return default.

        Args:
            key: Config key to load
            default: Default value if key not found or error occurs
            cur: Optional database cursor. If provided, uses existing transaction.
                 If None, opens new transaction (nested transaction risk if called within existing context).
        """
        if cur is not None:
            # Use provided cursor (avoid nested transaction)
            try:
                cur.execute(
                    "SELECT value FROM algo_config WHERE key = %s",
                    (key,),
                )
                row = cur.fetchone()
                if row:
                    return type(default)(row[0])
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.debug(f"Could not load config key {key}: {e}")
            return default

        # Fallback: open new transaction (only for standalone calls)
        try:
            with DatabaseContext("read") as new_cur:
                new_cur.execute(
                    "SELECT value FROM algo_config WHERE key = %s",
                    (key,),
                )
                row = new_cur.fetchone()
                if row:
                    return type(default)(row[0])
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"Could not load config key {key}: {e}")
        return default

    def compute_setup_component(self, symbol: str, eval_date) -> tuple[float, dict[str, Any]]:
        """Compute setup quality component (25 pts max)."""
        setup_pts, setup_detail = self._setup_component(symbol, eval_date)
        return setup_pts, setup_detail

    def compute_trend_component(self, symbol: str, eval_date, cur) -> tuple[float, dict[str, Any]]:
        """Compute trend quality component (20 pts max)."""
        trend_pts, trend_detail = self._trend_component(symbol, eval_date, cur)
        return trend_pts, trend_detail

    def compute_momentum_component(self, symbol: str, eval_date, cur) -> tuple[float, dict[str, Any]]:
        """Compute momentum/RS component (20 pts max)."""
        mom_pts, mom_detail = self._momentum_component(symbol, eval_date, cur)
        return mom_pts, mom_detail

    def compute_volume_component(self, symbol: str, eval_date, cur) -> tuple[float, dict[str, Any]]:
        """Compute volume component (12 pts max)."""
        vol_pts, vol_detail = self._volume_component(symbol, eval_date, cur)
        return vol_pts, vol_detail

    def compute_fundamentals_component(self, symbol: str, cur) -> tuple[float, dict[str, Any]]:
        """Compute fundamentals component (10 pts max)."""
        fund_pts, fund_detail = self._fundamentals_component(symbol, cur)
        return fund_pts, fund_detail

    def compute_sector_component(self, symbol: str, eval_date, sector, industry, cur) -> tuple[float, dict[str, Any]]:
        """Compute sector/industry component (8 pts max)."""
        sec_pts, sec_detail = self._sector_component(symbol, eval_date, sector, industry, cur)
        return sec_pts, sec_detail

    def compute_multi_timeframe_component(self, symbol: str, eval_date, cur) -> tuple[float, dict[str, Any]]:
        """Compute multi-timeframe component (5 pts max)."""
        mtf_pts, mtf_detail = self._multi_timeframe_component(symbol, eval_date, cur)
        return mtf_pts, mtf_detail

    # ============= Component Implementations =============

    def _setup_component(self, symbol: str, eval_date) -> tuple[float, dict[str, Any]]:
        """Setup quality component: base type, breakout proximity, consolidation quality."""
        try:
            setup = self._signals.classify_base_type(symbol, eval_date)
            if not setup or not setup.get("base_type"):
                return 0, {"error": "No setup found"}

            base_type = setup["base_type"]
            base_quality = setup.get("quality", "D")

            base_type_pts = {
                "high_tight": 25,
                "tight_consolidation": 23,
                "low_and_tight": 21,
                "vcp": 20,
                "descending_channel": 18,
                "ascending_channel": 15,
                "wide_and_loose": 5,
            }.get(base_type, 10)

            quality_multiplier = {
                "A": 1.0,
                "B": 0.9,
                "C": 0.75,
                "D": 0.5,
            }.get(base_quality, 0.5)

            breakout_proximity = setup.get("breakout_proximity_pct", 0)
            breakout_pts = max(0, 5 * (1 - breakout_proximity / 10))

            pivot_count = setup.get("pivot_count", 0)
            pivot_pts = min(5, pivot_count * 1.5)

            pts = (base_type_pts * quality_multiplier + breakout_pts + pivot_pts) * 0.5
            return min(pts, self.W_SETUP), {
                "base_type": base_type,
                "quality": base_quality,
                "breakout_proximity_pct": round(breakout_proximity, 1),
                "pivot_count": pivot_count,
            }
        except Exception as e:
            logger.debug(f"Setup component failed for {symbol}: {e}")
            return 0, {"error": str(e)[:50]}

    def _trend_component(self, symbol: str, eval_date, cur) -> tuple[float, dict[str, Any]]:
        """Trend quality: Minervini score, Weinstein stage, 30wk MA slope."""
        try:
            cur.execute(
                "SELECT minervini_score, weinstein_stage, ma_30wk_slope FROM technical_signals WHERE symbol = %s AND date = %s",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return 0, {"error": "No trend data"}

            minervini_score = float(row[0]) if row[0] else 0
            weinstein_stage = int(row[1]) if row[1] else 0
            ma_slope = float(row[2]) if row[2] else 0

            minervini_pts = min(10, minervini_score * 1.25)
            stage_pts = 7 if weinstein_stage == 2 else (5 if weinstein_stage == 1 else 0)
            slope_pts = min(3, max(0, ma_slope / 100))

            pts = minervini_pts + stage_pts + slope_pts
            return min(pts, self.W_TREND), {
                "minervini_score": round(minervini_score, 1),
                "weinstein_stage": weinstein_stage,
                "ma_30wk_slope": round(ma_slope, 2),
            }
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.debug(f"Trend component failed for {symbol}: {e}")
            return 0, {"error": str(e)[:50]}

    def _momentum_component(self, symbol: str, eval_date, cur) -> tuple[float, dict[str, Any]]:
        """Momentum: RS percentile, 1m/3m/6m returns."""
        try:
            cur.execute(
                "SELECT rs_percentile, return_1m, return_3m, return_6m FROM momentum WHERE symbol = %s AND date = %s",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return 0, {"error": "No momentum data"}

            rs_pct = float(row[0]) if row[0] else 0
            r1m = float(row[1]) if row[1] else 0
            r3m = float(row[2]) if row[2] else 0
            r6m = float(row[3]) if row[3] else 0

            rs_pts = min(10, rs_pct / 10)
            return_blend = (r1m * 0.5 + r3m * 0.3 + r6m * 0.2) / 100
            return_pts = min(10, max(0, return_blend * 10))

            pts = rs_pts + return_pts
            return min(pts, self.W_MOMENTUM), {
                "rs_percentile": round(rs_pct, 1),
                "return_1m": round(r1m, 2),
                "return_3m": round(r3m, 2),
                "return_6m": round(r6m, 2),
            }
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.debug(f"Momentum component failed for {symbol}: {e}")
            return 0, {"error": str(e)[:50]}

    def _volume_component(self, symbol: str, eval_date, cur) -> tuple[float, dict[str, Any]]:
        """Volume: breakout confirmation, accumulation days."""
        try:
            cur.execute(
                "SELECT breakout_vol_ratio, accumulation_days FROM volume_analysis WHERE symbol = %s AND date = %s",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if not row:
                return 0, {"error": "No volume data"}

            vol_ratio = float(row[0]) if row[0] else 1.0
            accum_days = int(row[1]) if row[1] else 0

            vol_pts = min(8, (vol_ratio - 1) * 4) if vol_ratio > 1 else 0
            accum_pts = min(4, accum_days / 10)

            pts = vol_pts + accum_pts
            return min(pts, self.W_VOLUME), {
                "breakout_vol_ratio": round(vol_ratio, 2),
                "accumulation_days": accum_days,
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"Volume component failed for {symbol}: {e}")
            return 0, {"error": str(e)[:50]}

    def _fundamentals_component(self, symbol: str, cur) -> tuple[float, dict[str, Any]]:
        """Fundamentals: EPS growth, revenue growth, ROE."""
        try:
            cur.execute(
                "SELECT eps_growth, revenue_growth, roe FROM fundamentals WHERE symbol = %s ORDER BY date DESC LIMIT 1",
                (symbol,),
            )
            row = cur.fetchone()
            if not row:
                return 0, {"error": "No fundamentals data"}

            eps_growth = float(row[0]) if row[0] else 0
            rev_growth = float(row[1]) if row[1] else 0
            roe = float(row[2]) if row[2] else 0

            eps_pts = min(4, eps_growth / 50) if eps_growth > 0 else 0
            rev_pts = min(3, rev_growth / 20) if rev_growth > 0 else 0
            roe_pts = min(3, roe / 15) if roe > 0 else 0

            pts = eps_pts + rev_pts + roe_pts
            return min(pts, self.W_FUNDAMENTALS), {
                "eps_growth": round(eps_growth, 2),
                "revenue_growth": round(rev_growth, 2),
                "roe": round(roe, 2),
            }
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.debug(f"Fundamentals component failed for {symbol}: {e}")
            return 0, {"error": str(e)[:50]}

    def _sector_component(
        self, symbol: str, eval_date, sector: str | None, industry: str | None, cur
    ) -> tuple[float, dict[str, Any]]:
        """Sector/Industry: industry rank vs sector rank."""
        try:
            if not industry:
                return 0, {"reason": "No industry data"}

            cur.execute(
                "SELECT industry_rank, sector_rank FROM rankings WHERE symbol = %s AND date = %s",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if not row:
                return 0, {"reason": "No ranking data"}

            industry_rank = float(row[0]) if row[0] else None
            sector_rank = float(row[1]) if row[1] else None

            if not industry_rank:
                return 0, {"reason": "No industry rank"}

            pts = 0.0
            if sector_rank and industry_rank < sector_rank:
                pts = min(8.0, (sector_rank - industry_rank) / 50)

            return pts, {
                "industry_rank": round(industry_rank, 1) if industry_rank else None,
                "sector_rank": round(sector_rank, 1) if sector_rank else None,
            }
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.debug(f"Sector component failed for {symbol}: {e}")
            return 0, {"error": str(e)[:50]}

    def _multi_timeframe_component(self, symbol: str, eval_date, cur) -> tuple[float, dict[str, Any]]:
        """Multi-timeframe: weekly + monthly alignment."""
        try:
            cur.execute(
                "SELECT weekly_signal, monthly_signal, weekly_ma_50, monthly_ma_50 FROM multi_timeframe WHERE symbol = %s AND date = %s",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if not row:
                return 0, {"error": "No MTF data"}

            weekly_signal = row[0]
            monthly_signal = row[1]
            weekly_above = bool(row[2])
            monthly_above = bool(row[3])

            weekly_buy = weekly_signal and weekly_signal.lower() in ("buy", "strong_buy")
            monthly_up = monthly_signal and monthly_signal.lower() in ("buy", "strong_buy")

            pts = 0.0
            if weekly_buy:
                pts += 2.5
            if weekly_above:
                pts += 1.0
            if monthly_up:
                pts += 1.5

            return min(pts, self.W_MULTI_TF), {
                "weekly_buy_recent": weekly_buy,
                "weekly_above_ma": weekly_above,
                "monthly_buy_recent": monthly_up,
                "monthly_above_ma": monthly_above,
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"Multi-timeframe component failed for {symbol}: {e}")
            return 0, {"error": str(e)[:50]}
