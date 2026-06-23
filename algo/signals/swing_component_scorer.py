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

    def __init__(self, config: Any, signals_computer: Any) -> None:
        self.config = config
        self._signals = signals_computer

    def _load_config_weights(self, cur: Any) -> dict[str, int]:
        """Load swing score component weights from config table.

        Raises on database errors—configuration must be loaded fresh.
        Returns empty dict if no custom weights are configured.
        """
        try:
            cur.execute("SELECT key, value FROM algo_config WHERE key LIKE 'swing_weight_%'")
            return {k: int(v) for k, v in cur.fetchall()}
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Failed to load swing weights from config: {e}") from e

    def _load_config_val(self, key: str, default: Any, cur: Any | None = None) -> Any:
        """Load a single config value from database or return default.

        Raises on database errors—configuration must be loaded fresh.
        Returns default only if the config key is not found in the database.

        Args:
            key: Config key to load
            default: Default value if key not found (but not on database errors)
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
                return default
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise RuntimeError(f"Failed to load config key {key}: {e}") from e

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
                return default
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Failed to load config key {key}: {e}") from e

    def compute_setup_component(self, symbol: str, eval_date: Any) -> tuple[float, dict[str, Any]]:
        """Compute setup quality component (25 pts max)."""
        setup_pts, setup_detail = self._setup_component(symbol, eval_date)
        return setup_pts, setup_detail

    def compute_trend_component(self, symbol: str, eval_date: Any, cur: Any) -> tuple[float, dict[str, Any]]:
        """Compute trend quality component (20 pts max)."""
        trend_pts, trend_detail = self._trend_component(symbol, eval_date, cur)
        return trend_pts, trend_detail

    def compute_momentum_component(self, symbol: str, eval_date: Any, cur: Any) -> tuple[float, dict[str, Any]]:
        """Compute momentum/RS component (20 pts max)."""
        mom_pts, mom_detail = self._momentum_component(symbol, eval_date, cur)
        return mom_pts, mom_detail

    def compute_volume_component(self, symbol: str, eval_date: Any, cur: Any) -> tuple[float, dict[str, Any]]:
        """Compute volume component (12 pts max)."""
        vol_pts, vol_detail = self._volume_component(symbol, eval_date, cur)
        return vol_pts, vol_detail

    def compute_fundamentals_component(self, symbol: str, cur: Any) -> tuple[float, dict[str, Any]]:
        """Compute fundamentals component (10 pts max)."""
        fund_pts, fund_detail = self._fundamentals_component(symbol, cur)
        return fund_pts, fund_detail

    def compute_sector_component(
        self, symbol: str, eval_date: Any, sector: Any, industry: Any, cur: Any
    ) -> tuple[float, dict[str, Any]]:
        """Compute sector/industry component (8 pts max)."""
        sec_pts, sec_detail = self._sector_component(symbol, eval_date, sector, industry, cur)
        return sec_pts, sec_detail

    def compute_multi_timeframe_component(self, symbol: str, eval_date: Any, cur: Any) -> tuple[float, dict[str, Any]]:
        """Compute multi-timeframe component (5 pts max)."""
        mtf_pts, mtf_detail = self._multi_timeframe_component(symbol, eval_date, cur)
        return mtf_pts, mtf_detail

    # ============= Component Implementations =============

    def _setup_component(self, symbol: str, eval_date: Any) -> tuple[float, dict[str, Any]]:
        """Setup quality component: base type, breakout proximity, consolidation quality."""
        try:
            setup = self._signals.classify_base_type(symbol, eval_date)
            if not setup:
                logger.critical(
                    f"CRITICAL: Base type classification returned None for {symbol}. "
                    f"Cannot evaluate setup quality component. Signal validation incomplete."
                )
                raise ValueError(f"{symbol}: Base type classification failed. Setup component unavailable.")
            if not setup.get("base_type"):
                logger.critical(
                    f"CRITICAL: Base type missing from classification result for {symbol}. "
                    f"Classification returned data but without base_type field. Data corruption or schema mismatch."
                )
                raise ValueError(f"{symbol}: base_type field missing from classification. Setup validation failed.")

            base_type = setup["base_type"]
            if "quality" not in setup or setup["quality"] is None:
                raise ValueError(f"Base setup for {symbol} missing required 'quality' field")
            base_quality = setup["quality"]

            base_type_mapping = {
                "high_tight": 25,
                "tight_consolidation": 23,
                "low_and_tight": 21,
                "vcp": 20,
                "descending_channel": 18,
                "ascending_channel": 15,
                "wide_and_loose": 5,
            }
            if base_type not in base_type_mapping:
                raise ValueError(
                    f"{symbol}: Unknown base_type '{base_type}'. "
                    f"Must be one of {list(base_type_mapping.keys())}. "
                    f"Setup component scoring cannot proceed with unknown base type."
                )
            base_type_pts = base_type_mapping[base_type]

            quality_multipliers = {
                "A": 1.0,
                "B": 0.9,
                "C": 0.75,
                "D": 0.5,
            }
            if base_quality not in quality_multipliers:
                raise ValueError(
                    f"{symbol}: Unknown quality grade '{base_quality}'. "
                    f"Must be one of {list(quality_multipliers.keys())}. "
                    f"Cannot compute setup quality without valid grade."
                )
            quality_multiplier = quality_multipliers[base_quality]

            breakout_proximity = setup.get("breakout_proximity_pct")
            if breakout_proximity is None:
                raise ValueError(
                    f"{symbol}: breakout_proximity_pct missing from setup data. "
                    f"Cannot compute breakout quality without proximity metric. "
                    f"Setup component scoring incomplete."
                )
            breakout_pts = max(0, 5 * (1 - breakout_proximity / 10))

            pivot_count = setup.get("pivot_count")
            if pivot_count is None:
                raise ValueError(
                    f"{symbol}: pivot_count missing from setup data. "
                    f"Cannot compute pivot strength without pivot count. "
                    f"Setup component scoring incomplete."
                )
            pivot_pts = min(5, pivot_count * 1.5)

            pts = (base_type_pts * quality_multiplier + breakout_pts + pivot_pts) * 0.5
            return min(pts, self.W_SETUP), {
                "base_type": base_type,
                "quality": base_quality,
                "breakout_proximity_pct": round(breakout_proximity, 1),
                "pivot_count": pivot_count,
            }
        except ValueError:
            # ValueError = validation error (missing data, bad quality, etc.)
            # Propagate to caller for proper handling, don't silently degrade to 0 pts
            raise
        except (TypeError, AttributeError, KeyError) as e:
            # Unexpected data structure error — convert to ValueError for consistency
            raise ValueError(f"{symbol}: Setup component data structure error: {e}") from e

    def _trend_component(self, symbol: str, eval_date: Any, cur: Any) -> tuple[float, dict[str, Any]]:
        """Trend quality: Minervini score, Weinstein stage, 30wk MA slope.

        CRITICAL: Raises on missing trend data instead of defaulting to 0.
        Signal scoring requires complete technical data; missing trend data
        means signal evaluation is incomplete.
        """
        try:
            cur.execute(
                "SELECT minervini_score, weinstein_stage, ma_30wk_slope FROM technical_signals WHERE symbol = %s AND date = %s",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                raise ValueError(
                    f"{symbol}: Technical signals missing for {eval_date}. "
                    f"Trend component requires minervini_score, weinstein_stage, and ma_30wk_slope. "
                    f"Cannot score trend without technical indicators."
                )

            if row[0] is None:
                raise ValueError(f"{symbol}: minervini_score is NULL")
            if row[1] is None:
                raise ValueError(f"{symbol}: weinstein_stage is NULL")
            if row[2] is None:
                raise ValueError(f"{symbol}: ma_30wk_slope is NULL")

            minervini_score = float(row[0])
            weinstein_stage = int(row[1])
            ma_slope = float(row[2])

            minervini_pts = min(10, minervini_score * 1.25)
            stage_pts = 7 if weinstein_stage == 2 else (5 if weinstein_stage == 1 else 0)
            slope_pts = min(3, max(0, ma_slope / 100))

            pts = minervini_pts + stage_pts + slope_pts
            return min(pts, self.W_TREND), {
                "minervini_score": round(minervini_score, 1),
                "weinstein_stage": weinstein_stage,
                "ma_30wk_slope": round(ma_slope, 2),
            }
        except ValueError:
            # ValueError = missing/invalid critical data. Propagate instead of degrading.
            raise
        except (ZeroDivisionError, TypeError) as e:
            logger.error(f"Trend component calculation error for {symbol}: {e}")
            raise ValueError(f"{symbol}: Trend component failed unexpectedly: {e}") from e

    def _momentum_component(self, symbol: str, eval_date: Any, cur: Any) -> tuple[float, dict[str, Any]]:
        """Momentum: RS percentile, 1m/3m/6m returns.

        CRITICAL: Raises on missing momentum data instead of defaulting to 0.
        Signal scoring requires complete price history; missing momentum data
        means signal evaluation is incomplete.
        """
        try:
            cur.execute(
                "SELECT rs_percentile, return_1m, return_3m, return_6m FROM momentum WHERE symbol = %s AND date = %s",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                raise ValueError(
                    f"{symbol}: Momentum data missing for {eval_date}. "
                    f"Momentum component requires rs_percentile, return_1m, return_3m, return_6m. "
                    f"Cannot score momentum without price return history."
                )

            if row[0] is None:
                raise ValueError(f"{symbol}: rs_percentile is NULL")
            if row[1] is None:
                raise ValueError(f"{symbol}: return_1m is NULL")
            if row[2] is None:
                raise ValueError(f"{symbol}: return_3m is NULL")
            if row[3] is None:
                raise ValueError(f"{symbol}: return_6m is NULL")

            rs_pct = float(row[0])
            r1m = float(row[1])
            r3m = float(row[2])
            r6m = float(row[3])

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
        except ValueError:
            # ValueError = missing/invalid critical data. Propagate instead of degrading.
            raise
        except (ZeroDivisionError, TypeError) as e:
            logger.error(f"Momentum component calculation error for {symbol}: {e}")
            raise ValueError(f"{symbol}: Momentum component failed unexpectedly: {e}") from e

    def _volume_component(self, symbol: str, eval_date: Any, cur: Any) -> tuple[float, dict[str, Any]]:
        """Volume: breakout confirmation, accumulation days.

        CRITICAL: Raises on missing volume data instead of defaulting to 0.
        Signal scoring requires complete volume analysis; missing volume data
        means signal evaluation is incomplete.
        """
        try:
            cur.execute(
                "SELECT breakout_vol_ratio, accumulation_days FROM volume_analysis WHERE symbol = %s AND date = %s",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(
                    f"{symbol}: Volume analysis missing for {eval_date}. "
                    f"Volume component requires breakout_vol_ratio and accumulation_days. "
                    f"Cannot score volume without volume analysis."
                )

            if row[0] is None:
                raise ValueError(f"{symbol}: breakout_vol_ratio is NULL")
            if row[1] is None:
                raise ValueError(f"{symbol}: accumulation_days is NULL")

            vol_ratio = float(row[0])
            accum_days = int(row[1])

            vol_pts = min(8, (vol_ratio - 1) * 4) if vol_ratio > 1 else 0
            accum_pts = min(4, accum_days / 10)

            pts = vol_pts + accum_pts
            return min(pts, self.W_VOLUME), {
                "breakout_vol_ratio": round(vol_ratio, 2),
                "accumulation_days": accum_days,
            }
        except ValueError:
            # ValueError = missing/invalid critical data. Propagate instead of degrading.
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"Volume component database error for {symbol}: {e}")
            raise ValueError(f"{symbol}: Volume component database error: {e}") from e

    def _fundamentals_component(self, symbol: str, cur: Any) -> tuple[float, dict[str, Any]]:
        """Fundamentals: EPS growth, revenue growth, ROE.

        CRITICAL: Raises on missing fundamentals data instead of defaulting to 0.
        Signal scoring requires complete fundamental analysis; missing fundamentals
        means signal evaluation is incomplete.
        """
        try:
            cur.execute(
                "SELECT eps_growth, revenue_growth, roe FROM fundamentals WHERE symbol = %s ORDER BY date DESC LIMIT 1",
                (symbol,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(
                    f"{symbol}: Fundamentals data missing. "
                    f"Fundamentals component requires eps_growth, revenue_growth, and roe. "
                    f"Cannot score fundamentals without growth metrics."
                )

            if row[0] is None:
                raise ValueError(f"{symbol}: eps_growth is NULL")
            if row[1] is None:
                raise ValueError(f"{symbol}: revenue_growth is NULL")
            if row[2] is None:
                raise ValueError(f"{symbol}: roe is NULL")

            eps_growth = float(row[0])
            rev_growth = float(row[1])
            roe = float(row[2])

            eps_pts = min(4, eps_growth / 50) if eps_growth > 0 else 0
            rev_pts = min(3, rev_growth / 20) if rev_growth > 0 else 0
            roe_pts = min(3, roe / 15) if roe > 0 else 0

            pts = eps_pts + rev_pts + roe_pts
            return min(pts, self.W_FUNDAMENTALS), {
                "eps_growth": round(eps_growth, 2),
                "revenue_growth": round(rev_growth, 2),
                "roe": round(roe, 2),
            }
        except ValueError:
            raise
        except (ZeroDivisionError, TypeError) as e:
            logger.error(f"Fundamentals component calculation error for {symbol}: {e}")
            raise ValueError(f"{symbol}: Fundamentals component failed unexpectedly: {e}") from e

    def _sector_component(
        self, symbol: str, eval_date: Any, sector: str | None, industry: str | None, cur: Any
    ) -> tuple[float, dict[str, Any]]:
        """Sector/Industry: industry rank vs sector rank.

        CRITICAL: Raises on missing sector/industry data instead of defaulting to 0.
        Signal scoring requires sector context; missing sector ranking
        means signal evaluation is incomplete.
        """
        try:
            if not industry:
                raise ValueError(
                    f"{symbol}: Industry classification missing. "
                    f"Sector component requires industry classification and rankings. "
                    f"Cannot score sector without industry context."
                )

            cur.execute(
                "SELECT industry_rank, sector_rank FROM rankings WHERE symbol = %s AND date = %s",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(
                    f"{symbol}: Sector rankings missing for {eval_date}. "
                    f"Sector component requires industry_rank and sector_rank. "
                    f"Cannot score sector ranking without ranking data."
                )

            if row[0] is None:
                raise ValueError(f"{symbol}: industry_rank is NULL")
            if row[1] is None:
                raise ValueError(f"{symbol}: sector_rank is NULL")

            industry_rank = float(row[0])
            sector_rank = float(row[1])

            pts = 0.0
            if sector_rank and industry_rank < sector_rank:
                pts = min(8.0, (sector_rank - industry_rank) / 50)

            return pts, {
                "industry_rank": round(industry_rank, 1),
                "sector_rank": round(sector_rank, 1),
            }
        except ValueError:
            raise
        except (ZeroDivisionError, TypeError) as e:
            logger.error(f"Sector component calculation error for {symbol}: {e}")
            raise ValueError(f"{symbol}: Sector component failed unexpectedly: {e}") from e

    def _multi_timeframe_component(self, symbol: str, eval_date: Any, cur: Any) -> tuple[float, dict[str, Any]]:
        """Multi-timeframe: weekly + monthly alignment.

        CRITICAL: Raises on missing multi-timeframe data instead of defaulting to 0.
        Signal scoring requires multi-timeframe confirmation; missing timeframe data
        means signal evaluation is incomplete.
        """
        try:
            cur.execute(
                "SELECT weekly_signal, monthly_signal, weekly_ma_50, monthly_ma_50 FROM multi_timeframe WHERE symbol = %s AND date = %s",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(
                    f"{symbol}: Multi-timeframe data missing for {eval_date}. "
                    f"Multi-timeframe component requires weekly_signal, monthly_signal, "
                    f"weekly_ma_50, and monthly_ma_50. "
                    f"Cannot score multi-timeframe alignment without weekly/monthly signals."
                )

            if row[0] is None:
                raise ValueError(f"{symbol}: weekly_signal is NULL")
            if row[1] is None:
                raise ValueError(f"{symbol}: monthly_signal is NULL")
            if row[2] is None:
                raise ValueError(f"{symbol}: weekly_ma_50 is NULL")
            if row[3] is None:
                raise ValueError(f"{symbol}: monthly_ma_50 is NULL")

            weekly_signal = row[0]
            monthly_signal = row[1]
            weekly_above = bool(row[2])
            monthly_above = bool(row[3])

            weekly_buy = weekly_signal and weekly_signal.lower() in (
                "buy",
                "strong_buy",
            )
            monthly_up = monthly_signal and monthly_signal.lower() in (
                "buy",
                "strong_buy",
            )

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
        except ValueError:
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"Multi-timeframe component database error for {symbol}: {e}")
            raise ValueError(f"{symbol}: Multi-timeframe component failed: {e}") from e
