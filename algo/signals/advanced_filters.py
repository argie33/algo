#!/usr/bin/env python3

import logging
from datetime import date as _date
from typing import Any

import psycopg2

from algo.signals.filter_registry import FilterRegistry
from algo.signals.signal_api import SignalAPI
from utils.db import DatabaseContext
from utils.signals import GradeClassifier


logger = logging.getLogger(__name__)


class AdvancedFilters:
    """Quality boosters that turn 'qualifying' signals into 'best' signals.

    All filter weights and thresholds are centralized in FilterRegistry.
    This class focuses on the evaluation logic, not parameter definitions.
    """

    def __init__(self, config):
        self.config = config
        self._strong_sectors = None
        self._strong_industries = None
        self._market_breadth = None
        self._sector_full_ranking = None
        self._signal_api = None  # SignalAPI, lazy-init

        # Validate critical signal filter config at init time (fail-fast)
        critical_config_keys = [
            "strong_sector_top_n",
            "block_days_before_earnings",
            "max_extension_above_50ma_pct",
            "min_avg_daily_dollar_volume",
            "require_strong_sector",
        ]
        for key in critical_config_keys:
            if key not in config or config[key] is None:
                raise ValueError(
                    f"CRITICAL: {key} config missing or None. "
                    f"Required for signal filtering. "
                    f"Defaults: strong_sector_top_n=5, block_days_before_earnings=5, "
                    f"max_extension_above_50ma_pct=15.0, min_avg_daily_dollar_volume=500_000, "
                    f"require_strong_sector=False"
                )

        # Store validated config values as instance variables (fail-fast guaranteed them to exist)
        self.strong_sector_top_n = int(config["strong_sector_top_n"])
        self.block_days_before_earnings = int(config["block_days_before_earnings"])
        self.max_extension_above_50ma_pct = float(config["max_extension_above_50ma_pct"])
        self.min_avg_daily_dollar_volume = float(config["min_avg_daily_dollar_volume"])
        self.require_strong_sector = bool(config["require_strong_sector"])

        # Cache subscore caps from registry
        self._subscore_caps = {
            "momentum": FilterRegistry.get_subscore_cap("momentum"),
            "quality": FilterRegistry.get_subscore_cap("quality"),
            "catalyst": FilterRegistry.get_subscore_cap("catalyst"),
            "risk": FilterRegistry.get_subscore_cap("risk"),
        }

    def _load_config_val(self, key: str, default: Any) -> Any:
        """Load a config value from AlgoConfig, with fallback to default.

        Raises on database/connection errors — those indicate system failure.
        Returns default only if config value is missing.
        """
        try:
            val = self.config.get(key)
            return val if val is not None else default
        except (RuntimeError, OSError) as e:
            raise RuntimeError(f"CRITICAL: Database/connection error loading config[{key}]: {e}") from e
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"Config value {key} unavailable, using default: {e}")
            return default

    # ---------- Pre-load: market context ----------

    def load_market_context(self, eval_date: Any) -> dict[str, Any]:
        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT sector_name, current_rank, momentum_score
                FROM sector_ranking
                WHERE date = (
                    SELECT MAX(date) FROM sector_ranking
                    WHERE date <= %s
                )
                AND sector_name <> '' AND sector_name IS NOT NULL
                AND sector_name <> 'Benchmark'
                ORDER BY current_rank ASC
                """,
                (eval_date,),
            )
            sectors = cur.fetchall()
            self._sector_full_ranking = {row[0]: int(row[1]) for row in sectors}
            self._strong_sectors = {
                row[0]: float(row[2]) for row in sectors[: self.strong_sector_top_n] if row[2] is not None
            }

            if not self._strong_sectors:
                raise ValueError(
                    f"No sector ranking data available for {eval_date} — "
                    f"cannot proceed without sector ranking for signal evaluation"
                )

            cur.execute(
                """
                SELECT industry, momentum_score
                FROM industry_ranking
                WHERE date_recorded = (
                    SELECT MAX(date_recorded) FROM industry_ranking
                    WHERE date_recorded <= %s
                )
                AND industry <> '' AND industry IS NOT NULL
                AND momentum_score IS NOT NULL
                ORDER BY momentum_score DESC
                """,
                (eval_date,),
            )
            industries = cur.fetchall()
            if industries:
                cutoff_idx = max(1, len(industries) // 4)
                self._strong_industries = {row[0]: float(row[1]) for row in industries[:cutoff_idx]}
            else:
                self._strong_industries = {}

            cur.execute(
                "SELECT bullish, bearish, neutral FROM aaii_sentiment WHERE date <= %s ORDER BY date DESC LIMIT 1",
                (eval_date,),
            )
            sent = cur.fetchone()
            if sent and sent[0] is not None and sent[1] is not None:
                self._market_breadth = {
                    "bullish": float(sent[0]),
                    "bearish": float(sent[1]),
                    "bull_bear_spread": float(sent[0]) - float(sent[1]),
                }

            return {
                "strong_sectors": list(self._strong_sectors.keys()),
                "strong_industries_count": len(self._strong_industries),
                "market_breadth": self._market_breadth,
            }

    # ---------- Per-candidate evaluation ----------

    def evaluate_candidate(
        self, symbol: str, signal_date: Any, entry_price: float, sector: str | None, industry: str | None
    ) -> dict[str, Any]:
        """Run all advanced filters for one candidate.

        Returns dict with:
          'pass': bool (hard fails)
          'reason': string for failure
          'composite_score': 0-100
          'subscores': {momentum, quality, catalyst, risk}
          'components': dict
        """
        with DatabaseContext("read") as cur:
            components = {}
            subscores = {"momentum": 0.0, "quality": 0.0, "catalyst": 0.0, "risk": 0.0}
            hard_fail = None

            # ===== HARD-FAIL gates (independent) =====

            # H1. Earnings proximity (CRITICAL: must not skip on exception)
            days_to_earnings = None
            try:
                days_to_earnings = self._estimate_days_to_earnings(symbol, signal_date, cur)
            except ValueError as e:
                # Earnings data unavailability is INCOMPLETE VALIDATION — must HARD FAIL, not degrade.
                # Continuing without earnings check exposes position to surprise earnings gaps.
                hard_fail = f"Earnings data unavailable (cannot validate blackout): {str(e)[:40]}"
                logger.warning(f"  {symbol}: {hard_fail}")

            components["days_to_earnings"] = days_to_earnings
            if days_to_earnings is not None and 0 <= days_to_earnings <= self.block_days_before_earnings:
                hard_fail = (
                    hard_fail or f"Earnings in ~{days_to_earnings}d (block window {self.block_days_before_earnings}d)"
                )

            # H2. Over-extended (CRITICAL: must not skip on exception)
            ext_pct = None
            try:
                ext_pct = self._extension_pct(symbol, signal_date, entry_price, cur)
            except ValueError as e:
                # SMA_50 data unavailability is INCOMPLETE VALIDATION — must HARD FAIL, not degrade.
                # Cannot measure extension without SMA_50; trade validity is unmeasurable.
                hard_fail = f"Extension validation failed (SMA_50 missing): {str(e)[:40]}"
                logger.warning(f"  {symbol}: {hard_fail}")

            components["extension_pct"] = ext_pct
            if ext_pct is not None and ext_pct > self.max_extension_above_50ma_pct:
                hard_fail = hard_fail or f"{ext_pct:.1f}% above 50-DMA (max {self.max_extension_above_50ma_pct:.0f})"

            # H4. Liquidity (institutional must — CRITICAL: must not skip on exception)
            avg_dollar_vol = None
            try:
                avg_dollar_vol = self._avg_dollar_volume(symbol, signal_date, cur)
            except ValueError as e:
                # Liquidity data unavailability is INCOMPLETE VALIDATION — must HARD FAIL, not degrade.
                # Cannot validate minimum liquidity; trade size calculation is unreliable.
                hard_fail = f"Liquidity validation failed (price/volume missing): {str(e)[:40]}"
                logger.warning(f"  {symbol}: {hard_fail}")

            components["avg_dollar_volume"] = avg_dollar_vol
            if avg_dollar_vol is not None and avg_dollar_vol < self.min_avg_daily_dollar_volume:
                hard_fail = (
                    hard_fail
                    or f"Liquidity ${avg_dollar_vol / 1e6:.1f}M < ${self.min_avg_daily_dollar_volume / 1e6:.1f}M"
                )

            # H5. Strong-sector requirement
            if self.require_strong_sector:
                if sector and sector not in (self._strong_sectors or {}):
                    hard_fail = hard_fail or f'Sector "{sector}" not in top {len(self._strong_sectors or {})}'

            # ===== SOFT scoring (always computed, even when hard-failed) =====

            # MOMENTUM (40) — missing data in soft scoring is INCOMPLETE VALIDATION, hard-fail
            try:
                rs_pts, rs_value = self._mansfield_rs_score(symbol, signal_date, cur)
                components["relative_strength"] = {
                    "pts": round(rs_pts, 1),
                    "excess_vs_spy": rs_value,
                }
                subscores["momentum"] += rs_pts
            except ValueError as e:
                hard_fail = f"Mansfield RS score unavailable: {str(e)[:40]}"
                logger.warning(f"  {symbol}: {hard_fail}")

            try:
                sec_pts = self._sector_momentum_score(sector)
                components["sector_strength"] = round(sec_pts, 1)
                subscores["momentum"] += sec_pts
            except ValueError as e:
                hard_fail = f"Sector momentum score unavailable: {str(e)[:40]}"
                logger.warning(f"  {symbol}: {hard_fail}")

            try:
                ind_pts = self._industry_momentum_score(industry)
                components["industry_strength"] = round(ind_pts, 1)
                subscores["momentum"] += ind_pts
            except ValueError as e:
                hard_fail = f"Industry momentum score unavailable: {str(e)[:40]}"
                logger.warning(f"  {symbol}: {hard_fail}")

            try:
                vol_pts, vol_ratio = self._volume_confirmation_score(symbol, signal_date, cur)
                components["volume_ratio"] = vol_ratio
                subscores["momentum"] += vol_pts
            except ValueError as e:
                hard_fail = f"Volume confirmation score unavailable: {str(e)[:40]}"
                logger.warning(f"  {symbol}: {hard_fail}")

            try:
                trend_pts = self._price_trend_score(symbol, signal_date, cur)
                components["price_trend_pts"] = round(trend_pts, 1)
                subscores["momentum"] += trend_pts
            except ValueError as e:
                hard_fail = f"Price trend score unavailable: {str(e)[:40]}"
                logger.warning(f"  {symbol}: {hard_fail}")

            setup_pts, setup_breakdown = self._setup_quality_score(symbol, signal_date)
            components["setup_quality"] = setup_breakdown
            subscores["momentum"] += setup_pts

            # QUALITY (30)
            ibd_pts, ibd_breakdown = self._ibd_composite_score(symbol, cur)
            components["ibd_composite"] = ibd_breakdown
            subscores["quality"] += ibd_pts

            fin_pts, fin_val = self._financial_quality_score(symbol, cur)
            components["financial_quality"] = fin_val
            subscores["quality"] += fin_pts

            eq_pts, eq_val = self._earnings_quality_score(symbol, cur)
            components["earnings_quality_score"] = eq_val
            subscores["quality"] += eq_pts

            # CATALYST (15)
            grw_pts, grw_breakdown = self._growth_score(symbol, cur)
            components["growth"] = grw_breakdown
            subscores["catalyst"] += grw_pts

            an_pts, an_net = self._analyst_score(symbol, signal_date, cur)
            components["analyst_net_actions"] = an_net
            subscores["catalyst"] += an_pts

            in_pts, in_net = self._insider_score(symbol, signal_date, cur)
            components["insider_net_value"] = in_net
            subscores["catalyst"] += in_pts

            # RISK (15) — these are GOOD when low risk
            try:
                ext_pts = self._extension_risk_score(ext_pct)
                components["extension_pts"] = round(ext_pts, 1)
                subscores["risk"] += ext_pts
            except ValueError as e:
                hard_fail = hard_fail or f"Extension risk assessment failed: {str(e)[:40]}"

            try:
                ep_pts = self._earnings_proximity_score(days_to_earnings, self.block_days_before_earnings)
                components["earnings_proximity_pts"] = round(ep_pts, 1)
                subscores["risk"] += ep_pts
            except ValueError as e:
                hard_fail = hard_fail or f"Earnings proximity assessment failed: {str(e)[:40]}"

            composite_score = min(100.0, sum(subscores.values()))
            return {
                "pass": hard_fail is None,
                "reason": hard_fail or "all advanced gates passed",
                "composite_score": round(composite_score, 1),
                "subscores": {k: round(v, 1) for k, v in subscores.items()},
                "subscore_max": self._subscore_caps,
                "components": components,
            }

    # ============= MOMENTUM =============

    def _mansfield_rs_score(self, symbol, signal_date, cur):
        """Compute Mansfield-style RS percentile vs SPY.

        Raises:
            ValueError: If RS data unavailable (missing price history)
        """
        if self._signal_api is None:
            self._signal_api = SignalAPI()

        rs_percentile = self._signal_api.rank_rs_percentile(cur, symbol, signal_date, lookback=60)
        # ValueError (missing data) and other errors propagate to caller

        pts = (rs_percentile / 100.0) * FilterRegistry.get_weight("momentum_rs")
        return pts, round(rs_percentile, 1)

    def _sector_momentum_score(self, sector):
        if not self._strong_sectors:
            raise ValueError("Sector ranking data not loaded — call load_market_context() first")
        if not sector:
            raise ValueError("Sector name is missing or empty")
        rank = self._sector_full_ranking.get(sector, 99) if self._sector_full_ranking else 99
        # Top sector = 10pts, rank 5 = 5pts, rank 11 = 0pts
        return max(0.0, FilterRegistry.get_weight("momentum_sector") * (1.0 - (rank - 1) / 10.0))

    def _industry_momentum_score(self, industry):
        if self._strong_industries is None:
            raise ValueError("Industry ranking data not loaded — call load_market_context() first")
        if not industry:
            raise ValueError("Industry name is missing or empty")
        return FilterRegistry.get_weight("momentum_industry") if industry in self._strong_industries else 0.0

    def _volume_confirmation_score(self, symbol, signal_date, cur):
        cur.execute(
            """
            WITH d AS (
                SELECT date, volume,
                       AVG(volume) OVER (ORDER BY date ROWS BETWEEN 50 PRECEDING AND 1 PRECEDING) AS avg_vol
                FROM price_daily
                WHERE symbol = %s AND date <= %s
                ORDER BY date DESC LIMIT 1
            )
            SELECT volume, avg_vol FROM d
            """,
            (symbol, signal_date),
        )
        row = cur.fetchone()
        if not row or not row[0] or not row[1]:
            raise ValueError(f"Volume data missing for {symbol} on {signal_date} — cannot confirm volume strength")
        vol = float(row[0])
        avg = float(row[1])
        if avg <= 0:
            raise ValueError(f"Invalid volume average (≤0) for {symbol} on {signal_date} — data corruption")
        ratio = vol / avg
        momentum_vol_weight = FilterRegistry.get_weight("momentum_volume")
        vol_breakeven = FilterRegistry.get_threshold("volume_ratio_breakeven")
        vol_full_points = FilterRegistry.get_threshold("volume_ratio_full_points")
        vol_range = vol_full_points - vol_breakeven
        pts = max(
            0.0,
            min(momentum_vol_weight, (ratio - vol_breakeven) * momentum_vol_weight / vol_range),
        )
        return pts, round(ratio, 2)

    def _price_trend_score(self, symbol, signal_date, cur):
        """Multi-timeframe alignment (Elder Triple Screen):
        +2 pts each if 5d return positive, 20d return positive,
        +1 pt if also a BUY signal on weekly timeframe (very strong combo).

        Raises:
            ValueError: If price data unavailable (insufficient history)
        """
        r5 = self._period_return(symbol, signal_date, 5, cur)
        r20 = self._period_return(symbol, signal_date, 20, cur)
        score = 0.0
        if r5 > 0:
            score += 2.0
        if r20 > 0:
            score += 2.0

        # Weekly alignment: if buy_sell_weekly also says BUY in last 30 days, bonus
        try:
            cur.execute(
                """SELECT 1 FROM buy_sell_weekly
                   WHERE symbol = %s AND signal_type = 'BUY'
                     AND date >= %s::date - INTERVAL '30 days'
                     AND date <= %s
                   LIMIT 1""",
                (symbol, signal_date, signal_date),
            )
            if cur.fetchone():
                score += 1.0
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            # Weekly data missing or unavailable — continue without bonus
            logger.debug(f"Weekly alignment data unavailable for {symbol}: {e} (continuing without bonus)")

        return min(score, FilterRegistry.get_weight("momentum_price_trend"))

    def _setup_quality_score(self, symbol, signal_date):
        """Bonus pts for entering on a real base breakout / VCP (canonical swing setup).

        +3 pts: in identified base AND breakout imminent (within 2% of pivot)
        +2 pts: VCP confirmed (sequential range narrowing)
        +1 pt:  pivot breakout fired today on volume
        +1 pt:  Minervini power trend (20%+ in 21 days)
        Capped at 5.

        Returns 0 score if setup data unavailable (graceful degradation).
        Raises on data retrieval errors.
        """
        try:
            if self._signal_api is None:
                self._signal_api = SignalAPI()
            base = self._signal_api.detect_base(symbol, signal_date)
            vcp = self._signal_api.detect_vcp(symbol, signal_date)
            pivot = self._signal_api.detect_pivot(symbol, signal_date)
            power = self._signal_api.detect_power_trend(symbol, signal_date)
        except ValueError as e:
            # Missing setup detection data — cannot proceed safely
            logger.error(f"Setup quality data unavailable for {symbol}: {e}")
            raise
        # Other exceptions (RuntimeError, ConnectionError, etc.) propagate to caller

        pts = 0.0
        if base.get("in_base") and base.get("breakout_imminent"):
            pts += 3.0
        elif base.get("in_base"):
            pts += 1.5
        if vcp.get("is_vcp"):
            pts += 2.0
        if pivot.get("breakout"):
            pts += 1.0
        if power.get("power_trend"):
            pts += 1.0
        pts = min(5.0, pts)

        return pts, {
            "in_base": base.get("in_base"),
            "breakout_imminent": base.get("breakout_imminent"),
            "base_depth_pct": base.get("base_depth_pct"),
            "is_vcp": vcp.get("is_vcp"),
            "vcp_contractions": vcp.get("contractions"),
            "pivot_breakout": pivot.get("breakout"),
            "power_trend": power.get("power_trend"),
            "return_21d": power.get("return_21d"),
        }

    def _period_return(self, symbol, end_date, lookback_days, cur):
        """Compute simple return over a lookback period.

        Raises:
            ValueError: If price data is missing or invalid for the period
        """
        cur.execute(
            """
            WITH bracket AS (
                SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                FROM price_daily
                WHERE symbol = %s AND date <= %s
                  AND date >= %s::date - (%s * INTERVAL '1 day')
            )
            SELECT
                (SELECT close FROM bracket WHERE rn = 1),
                (SELECT close FROM bracket ORDER BY rn DESC LIMIT 1)
            """,
            (symbol, end_date, end_date, lookback_days + 5),
        )
        row = cur.fetchone()
        if not row or row[0] is None or row[1] is None:
            raise ValueError(
                f"Period return data missing for {symbol} on {end_date} ({lookback_days}d lookback) — insufficient price history"
            )
        recent = float(row[0])
        oldest = float(row[1])
        if oldest <= 0:
            raise ValueError(f"Invalid historical price for {symbol}: oldest close {oldest} <= 0")
        return (recent - oldest) / oldest

    # ============= QUALITY =============

    def _ibd_composite_score(self, symbol, cur):
        cur.execute(
            """
            SELECT composite_score, quality_score, growth_score, momentum_score
            FROM stock_scores WHERE symbol = %s LIMIT 1
            """,
            (symbol,),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            error_msg = f"IBD Composite missing for {symbol} - cannot score signal"
            logger.error(error_msg)
            raise ValueError(error_msg)
        composite = float(row[0])
        # ibd_composite_min = 0pts, ibd_composite_max = full pts
        quality_ibd_weight = FilterRegistry.get_weight("quality_ibd")
        ibd_min = FilterRegistry.get_threshold("ibd_composite_min")
        ibd_max = FilterRegistry.get_threshold("ibd_composite_max")
        pts = max(0.0, min(quality_ibd_weight, (composite - ibd_min) * quality_ibd_weight / (ibd_max - ibd_min)))

        # Assign letter grade using configurable thresholds from algo_config
        grade = GradeClassifier.classify_ibd_composite(composite)

        return pts, {
            "composite": round(composite, 1),
            "grade": grade,
            "quality": round(float(row[1]), 1) if row[1] is not None else None,
            "growth": round(float(row[2]), 1) if row[2] is not None else None,
            "momentum": round(float(row[3]), 1) if row[3] is not None else None,
        }

    def _financial_quality_score(self, symbol, cur):
        """Use stock_scores.quality_score as the financial quality signal."""
        cur.execute(
            """
            SELECT s.quality_score
            FROM stock_scores s
            WHERE s.symbol = %s LIMIT 1
            """,
            (symbol,),
        )
        row = cur.fetchone()
        if row is None:
            error_msg = f"Financial quality metrics missing for {symbol}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        fin_neutral = FilterRegistry.get_threshold("financial_quality_neutral")
        fin_max = FilterRegistry.get_threshold("financial_quality_max")
        q = float(row[0]) if row[0] is not None else fin_neutral
        # Linear scale: fin_neutral = 0 pts, fin_max = quality_financial pts
        quality_fin_weight = FilterRegistry.get_weight("quality_financial")
        pts = max(0.0, min(quality_fin_weight, (q - fin_neutral) * quality_fin_weight / (fin_max - fin_neutral)))
        return pts, round(q, 1)

    def _earnings_quality_score(self, symbol, cur):
        """Compute earnings quality score from earnings_metrics.

        Returns 0 score if data unavailable (graceful degradation).
        Raises on data retrieval errors.
        """
        cur.execute(
            """
            SELECT earnings_quality_score FROM earnings_metrics
            WHERE symbol = %s AND earnings_quality_score IS NOT NULL
            ORDER BY report_date DESC LIMIT 1
            """,
            (symbol,),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            error_msg = f"Earnings quality metrics missing for {symbol}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        score = float(row[0])
        pts = (score / 100.0) * FilterRegistry.get_weight("quality_earnings")
        return pts, round(score, 1)

    # ============= CATALYST =============

    def _growth_score(self, symbol, cur):
        cur.execute(
            """
            SELECT revenue_growth_3y_cagr, eps_growth_3y_cagr,
                   quarterly_growth_momentum, revenue_growth_yoy
            FROM growth_metrics
            WHERE symbol = %s
            ORDER BY date DESC LIMIT 1
            """,
            (symbol,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(
                f"Growth metrics unavailable for {symbol}. "
                "growth_metrics table empty or missing data. "
                "Cannot compute growth catalyst score without 3-year CAGR data."
            )
        rev_3y = float(row[0]) if row[0] is not None else 0.0
        eps_3y = float(row[1]) if row[1] is not None else 0.0
        mom = float(row[2]) if row[2] is not None else 0.0
        rev_yoy = float(row[3]) if row[3] is not None else 0.0
        # Allocate catalyst_growth weight across 3 metrics (EPS, revenue, momentum)
        catalyst_growth_weight = FilterRegistry.get_weight("catalyst_growth")
        pts_per_metric = catalyst_growth_weight / 3.0
        eps_threshold = FilterRegistry.get_threshold("eps_3y_cagr_threshold")
        rev_threshold = FilterRegistry.get_threshold("revenue_3y_cagr_threshold")
        eps_p = max(0.0, min(pts_per_metric, eps_3y / eps_threshold * pts_per_metric)) if eps_3y > 0 else 0.0
        rev_p = max(0.0, min(pts_per_metric, rev_3y / rev_threshold * pts_per_metric)) if rev_3y > 0 else 0.0
        mom_p = pts_per_metric if mom > 0 else 0.0
        return eps_p + rev_p + mom_p, {
            "eps_3y_cagr": round(eps_3y, 1),
            "rev_3y_cagr": round(rev_3y, 1),
            "rev_yoy": round(rev_yoy, 1),
            "momentum": round(mom, 1),
        }

    def _analyst_score(self, symbol, signal_date, cur):
        cur.execute(
            """
            SELECT
                COUNT(*) FILTER (WHERE LOWER(action) IN ('up','upgrade')),
                COUNT(*) FILTER (WHERE LOWER(action) IN ('down','downgrade'))
            FROM analyst_upgrade_downgrade
            WHERE symbol = %s
              AND action_date >= %s::date - INTERVAL '90 days'
              AND action_date <= %s
            """,
            (symbol, signal_date, signal_date),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(
                f"Analyst sentiment unavailable for {symbol}. "
                "analyst_upgrade_downgrade table empty or missing data. "
                "Cannot compute analyst sentiment catalyst score."
            )
        ups = int(row[0]) if row[0] is not None else 0
        downs = int(row[1]) if row[1] is not None else 0
        net = ups - downs
        # net score scaled from analyst_net_positive_threshold to analyst_net_full_score
        catalyst_analyst_weight = FilterRegistry.get_weight("catalyst_analyst")
        thresh_min = FilterRegistry.get_threshold("analyst_net_positive_threshold")
        thresh_max = FilterRegistry.get_threshold("analyst_net_full_score")
        pts = max(
            0.0, min(catalyst_analyst_weight, (net - thresh_min) * catalyst_analyst_weight / (thresh_max - thresh_min))
        )
        return pts, net

    def _insider_score(self, symbol, signal_date, cur):
        cur.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN LOWER(transaction_type) LIKE '%%buy%%' THEN value END), 0),
                COALESCE(SUM(CASE WHEN LOWER(transaction_type) LIKE '%%sale%%' OR LOWER(transaction_type) LIKE '%%sell%%' THEN value END), 0)
            FROM insider_transactions
            WHERE symbol = %s
              AND transaction_date >= %s::date - INTERVAL '60 days'
              AND transaction_date <= %s
              AND value IS NOT NULL
            """,
            (symbol, signal_date, signal_date),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(
                f"Insider transactions unavailable for {symbol}. "
                "insider_transactions table empty or missing data. "
                "Cannot compute insider activity catalyst score."
            )
        buys = float(row[0]) if row[0] is not None else 0
        sells = float(row[1]) if row[1] is not None else 0
        net = buys - sells
        if net <= 0:
            return 0.0, net
        catalyst_insider_weight = FilterRegistry.get_weight("catalyst_insider")
        insider_threshold = FilterRegistry.get_threshold("insider_buy_sell_threshold")
        pts = min(catalyst_insider_weight, net / insider_threshold * catalyst_insider_weight)
        return pts, net

    # ============= RISK =============

    def _extension_pct(self, symbol, signal_date, entry_price, cur):
        """Calculate entry price extension above 50-day SMA.

        Raises:
            ValueError: If 50-day SMA data is missing or invalid
        """
        cur.execute(
            "SELECT sma_50 FROM technical_data_daily WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1",
            (symbol, signal_date),
        )
        row = cur.fetchone()
        if not row or not row[0] or float(row[0]) <= 0:
            raise ValueError(f"50-day SMA not available for {symbol} on {signal_date}")
        sma_50 = float(row[0])
        return ((entry_price - sma_50) / sma_50) * 100.0

    def _extension_risk_score(self, ext_pct):
        if ext_pct is None:
            raise ValueError(
                "Extension percentage required for risk scoring. "
                "SMA_50 data unavailable. Cannot assess entry extension risk."
            )
        risk_ext_weight = FilterRegistry.get_weight("risk_extension")
        sweet_spot = FilterRegistry.get_threshold("extension_risk_sweet_spot_pct")
        moderate = FilterRegistry.get_threshold("extension_risk_moderate_pct")
        high = FilterRegistry.get_threshold("extension_risk_high_pct")

        if ext_pct < 0:
            return risk_ext_weight * 0.6  # below 50 = OK but not ideal
        if ext_pct <= sweet_spot:
            return risk_ext_weight  # sweet spot
        if ext_pct <= moderate:
            return risk_ext_weight * (1.0 - (ext_pct - sweet_spot) / (moderate - sweet_spot) * 0.5)
        if ext_pct <= high:
            return risk_ext_weight * 0.25
        return 0.0

    def _earnings_proximity_score(self, days_to_earnings, block_window):
        if days_to_earnings is None:
            raise ValueError(
                "Days to earnings required for risk scoring. "
                "Earnings calendar data unavailable. Cannot assess earnings-proximity risk."
            )
        risk_earnings_prox_weight = FilterRegistry.get_weight("risk_earnings_proximity")
        safe_days = FilterRegistry.get_threshold("earnings_proximity_safe_days")
        if days_to_earnings <= block_window:
            return 0.0
        if days_to_earnings >= safe_days:
            return risk_earnings_prox_weight
        return risk_earnings_prox_weight * (days_to_earnings - block_window) / (safe_days - block_window)

    def _avg_dollar_volume(self, symbol, signal_date, cur):
        """Calculate average daily dollar volume (close * volume) over 50 days.

        Raises:
            ValueError: If price/volume data is missing for the period
        """
        cur.execute(
            """
            SELECT AVG(close * volume) FROM price_daily
            WHERE symbol = %s AND date <= %s
              AND date >= %s::date - INTERVAL '50 days'
              AND volume > 0
            """,
            (symbol, signal_date, signal_date),
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            raise ValueError(
                f"Price/volume data missing for {symbol} on {signal_date} — cannot calculate average daily dollar volume"
            )
        return float(row[0])

    def _estimate_days_to_earnings(self, symbol, signal_date, cur):
        """Estimate days until next earnings. Tries calendar → estimates → quarterly estimate.

        Raises:
            ValueError: If no earnings data available through any method
        """
        # First, try to get actual estimated earnings date from earnings_calendar or earnings_estimates
        cur.execute(
            """
            SELECT earnings_date FROM earnings_calendar
            WHERE symbol = %s AND earnings_date > %s
            ORDER BY earnings_date ASC LIMIT 1
            """,
            (symbol, signal_date),
        )
        row = cur.fetchone()
        if row is not None and row[0] is not None:
            earnings_date = row[0]
            return (earnings_date - signal_date).days

        # Fallback: try earnings_estimates table
        cur.execute(
            """
            SELECT earnings_date FROM earnings_estimates
            WHERE symbol = %s AND earnings_date > %s AND estimated = true
            ORDER BY earnings_date ASC LIMIT 1
            """,
            (symbol, signal_date),
        )
        row = cur.fetchone()
        if row is not None and row[0] is not None:
            earnings_date = row[0]
            return (earnings_date - signal_date).days

        # Fallback: estimate based on last reported earnings using proper quarter math
        cur.execute(
            """
            SELECT earnings_date FROM earnings_history
            WHERE symbol = %s AND estimated = false ORDER BY earnings_date DESC LIMIT 1
            """,
            (symbol,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            raise ValueError(
                f"Earnings date not available for {symbol} on {signal_date} — no calendar, estimates, or history found"
            )

        last_report = row[0] if isinstance(row[0], _date) else row[0].date()

        # Standard quarterly spacing: Q1 (Apr), Q2 (Jul), Q3 (Oct), Q4 (Jan)
        # Find which quarter the last report was and estimate next
        month = last_report.month
        year = last_report.year

        # Estimate next earnings based on standard calendar
        if month < 4:
            next_q_date = _date(year, 4, 15)  # Q1
        elif month < 7:
            next_q_date = _date(year, 7, 15)  # Q2
        elif month < 10:
            next_q_date = _date(year, 10, 15)  # Q3
        else:  # month >= 10 (Q4)
            next_q_date = _date(year + 1, 1, 15)  # Q4

        # If next quarter estimate is in past, advance to following quarter
        signal_d = signal_date
        while next_q_date <= signal_d:
            if next_q_date.month == 1:
                next_q_date = _date(next_q_date.year, 4, 15)
            elif next_q_date.month == 4:
                next_q_date = _date(next_q_date.year, 7, 15)
            elif next_q_date.month == 7:
                next_q_date = _date(next_q_date.year, 10, 15)
            else:
                next_q_date = _date(next_q_date.year + 1, 1, 15)

        return (next_q_date - signal_d).days
