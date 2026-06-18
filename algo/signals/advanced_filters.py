#!/usr/bin/env python3

import logging
from datetime import date as _date

from algo.signals import SignalComputer
from utils.db import DatabaseContext
from utils.signals import GradeClassifier


logger = logging.getLogger(__name__)


class AdvancedFilters:
    """Quality boosters that turn 'qualifying' signals into 'best' signals."""

    # ---- Score weights (sum = 100) ----
    W_MOMENTUM_RS = 15  # Mansfield RS vs SPY
    W_MOMENTUM_SECTOR = 10
    W_MOMENTUM_INDUSTRY = 5
    W_MOMENTUM_VOLUME = 5
    W_MOMENTUM_PRICE_TREND = 5

    W_QUALITY_IBD = 15
    W_QUALITY_FIN = 8
    W_QUALITY_EARNINGS = 7

    W_CATALYST_GROWTH = 7
    W_CATALYST_ANALYST = 5
    W_CATALYST_INSIDER = 3

    W_RISK_EXTENSION = 13
    W_RISK_EARNINGS_PROX = 2

    def __init__(self, config):
        self.config = config
        self._strong_sectors = None
        self._strong_industries = None
        self._market_breadth = None
        self._sector_full_ranking = None
        self._signals = None  # SignalComputer, lazy-init

    def _load_config_val(self, key: str, default):
        """Load a config value from AlgoConfig, with fallback to default."""
        try:
            val = self.config.get(key)
            return val if val is not None else default
        except Exception as e:
            logger.debug(f"_load_config_val({key}) failed: {e}")
            return default

    # ---------- Pre-load: market context ----------

    def load_market_context(self, eval_date):
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
            top_n = int(self.config.get("strong_sector_top_n", 5))
            self._sector_full_ranking = {row[0]: int(row[1]) for row in sectors}
            self._strong_sectors = {
                row[0]: float(row[2]) for row in sectors[:top_n] if row[2] is not None
            }

            # Graceful degradation: if no sector data, continue with empty dict
            if not self._strong_sectors:
                logger.warning(
                    f"No sector ranking data available for {eval_date} — sector filters disabled"
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
                self._strong_industries = {
                    row[0]: float(row[1]) for row in industries[:cutoff_idx]
                }
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

    def evaluate_candidate(self, symbol, signal_date, entry_price, sector, industry):
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
            max_subscores = {
                "momentum": 40.0,
                "quality": 30.0,
                "catalyst": 15.0,
                "risk": 15.0,
            }
            hard_fail = None

            # ===== HARD-FAIL gates (independent) =====

            # H1. Earnings proximity
            days_to_earnings = self._estimate_days_to_earnings(symbol, signal_date, cur)
            components["days_to_earnings"] = days_to_earnings
            block_window = int(self.config.get("block_days_before_earnings", 5))
            if days_to_earnings is None:
                # No earnings calendar data — warn but don't block.
                # Pre-tier EarningsBlackout already catches known proximity windows.
                # Blocking on unknown earnings would eliminate many valid setups.
                logger.debug(
                    f"  {symbol}: No earnings calendar data, skipping earnings gate"
                )
            elif 0 <= days_to_earnings <= block_window:
                hard_fail = (
                    f"Earnings in ~{days_to_earnings}d (block window {block_window}d)"
                )

            # H2. Over-extended
            ext_pct = self._extension_pct(symbol, signal_date, entry_price, cur)
            components["extension_pct"] = ext_pct
            max_extension = float(self.config.get("max_extension_above_50ma_pct", 15.0))
            if ext_pct is not None and ext_pct > max_extension:
                hard_fail = (
                    hard_fail
                    or f"{ext_pct:.1f}% above 50-DMA (max {max_extension:.0f})"
                )

            # H4. Liquidity (institutional must)
            avg_dollar_vol = self._avg_dollar_volume(symbol, signal_date, cur)
            components["avg_dollar_volume"] = avg_dollar_vol
            min_liq = float(self.config.get("min_avg_daily_dollar_volume", 500_000))
            if avg_dollar_vol is not None and avg_dollar_vol < min_liq:
                hard_fail = (
                    hard_fail
                    or f"Liquidity ${avg_dollar_vol/1e6:.1f}M < ${min_liq/1e6:.1f}M"
                )

            # H5. Strong-sector requirement (off by default)
            if self.config.get("require_strong_sector", False):
                if sector and sector not in (self._strong_sectors or {}):
                    hard_fail = (
                        hard_fail
                        or f'Sector "{sector}" not in top {len(self._strong_sectors or {})}'
                    )

            # ===== SOFT scoring (always computed, even when hard-failed) =====

            # MOMENTUM (40)
            rs_pts, rs_value = self._mansfield_rs_score(symbol, signal_date, cur)
            components["relative_strength"] = {
                "pts": round(rs_pts, 1),
                "excess_vs_spy": rs_value,
            }
            subscores["momentum"] += rs_pts

            sec_pts = self._sector_momentum_score(sector)
            components["sector_strength"] = round(sec_pts, 1)
            subscores["momentum"] += sec_pts

            ind_pts = self._industry_momentum_score(industry)
            components["industry_strength"] = round(ind_pts, 1)
            subscores["momentum"] += ind_pts

            vol_pts, vol_ratio = self._volume_confirmation_score(
                symbol, signal_date, cur
            )
            components["volume_ratio"] = vol_ratio
            subscores["momentum"] += vol_pts

            trend_pts = self._price_trend_score(symbol, signal_date, cur)
            components["price_trend_pts"] = round(trend_pts, 1)
            subscores["momentum"] += trend_pts

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
            ext_pts = self._extension_risk_score(ext_pct)
            components["extension_pts"] = round(ext_pts, 1)
            subscores["risk"] += ext_pts

            ep_pts = self._earnings_proximity_score(days_to_earnings, block_window)
            components["earnings_proximity_pts"] = round(ep_pts, 1)
            subscores["risk"] += ep_pts

            composite_score = min(100.0, sum(subscores.values()))
            return {
                "pass": hard_fail is None,
                "reason": hard_fail or "all advanced gates passed",
                "composite_score": round(composite_score, 1),
                "subscores": {k: round(v, 1) for k, v in subscores.items()},
                "subscore_max": max_subscores,
                "components": components,
            }

    # ============= MOMENTUM =============

    def _mansfield_rs_score(self, symbol, signal_date, cur):
        # Use proper percentile ranking instead of linear excess return
        if self._signals is None:
            self._signals = SignalComputer()

        rs_percentile = self._signals._rs_percentile_vs_spy(
            cur, symbol, signal_date, lookback=60
        )
        if rs_percentile is None:
            return 0.0, None

        pts = (rs_percentile / 100.0) * self.W_MOMENTUM_RS
        return pts, round(rs_percentile, 1)

    def _sector_momentum_score(self, sector):
        if not sector or not self._strong_sectors:
            return 0.0
        rank = (
            self._sector_full_ranking.get(sector, 99)
            if self._sector_full_ranking
            else 99
        )
        # Top sector = 10pts, rank 5 = 5pts, rank 11 = 0pts
        return max(0.0, self.W_MOMENTUM_SECTOR * (1.0 - (rank - 1) / 10.0))

    def _industry_momentum_score(self, industry):
        if not industry or not self._strong_industries:
            return 0.0
        return self.W_MOMENTUM_INDUSTRY if industry in self._strong_industries else 0.0

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
            return 0.0, None
        vol = float(row[0])
        avg = float(row[1])
        if avg <= 0:
            return 0.0, None
        ratio = vol / avg
        # 1.5x = full points
        pts = max(
            0.0,
            min(self.W_MOMENTUM_VOLUME, (ratio - 0.8) * self.W_MOMENTUM_VOLUME / 0.7),
        )
        return pts, round(ratio, 2)

    def _price_trend_score(self, symbol, signal_date, cur):
        """Multi-timeframe alignment (Elder Triple Screen):
        +2 pts each if 5d return positive, 20d return positive,
        +1 pt if also a BUY signal on weekly timeframe (very strong combo).
        """
        r5 = self._period_return(symbol, signal_date, 5, cur)
        r20 = self._period_return(symbol, signal_date, 20, cur)
        if r5 is None or r20 is None:
            return 0.0
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
        except Exception as e:
            logging.debug(
                f"Weekly alignment check failed for {symbol}: {e} (continuing without bonus)"
            )
            # Continue without bonus — don't halt on weekly alignment check failure

        return min(score, self.W_MOMENTUM_PRICE_TREND)

    def _setup_quality_score(self, symbol, signal_date):
        """Bonus pts for entering on a real base breakout / VCP (canonical swing setup).

        +3 pts: in identified base AND breakout imminent (within 2% of pivot)
        +2 pts: VCP confirmed (sequential range narrowing)
        +1 pt:  pivot breakout fired today on volume
        +1 pt:  Minervini power trend (20%+ in 21 days)
        Capped at 5.
        """
        try:
            if self._signals is None:
                self._signals = SignalComputer()
            base = self._signals.base_detection(symbol, signal_date)
            vcp = self._signals.vcp_detection(symbol, signal_date)
            pivot = self._signals.pivot_breakout(symbol, signal_date)
            power = self._signals.power_trend(symbol, signal_date)
        except Exception as e:
            return 0.0, {"error": str(e)[:60]}

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
            return None
        recent = float(row[0])
        oldest = float(row[1])
        return (recent - oldest) / oldest if oldest > 0 else None

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
            return 0.0, {"composite": None, "grade": "NA"}
        composite = float(row[0])
        # 40 = 0pts, 90+ = full pts
        pts = max(
            0.0, min(self.W_QUALITY_IBD, (composite - 40.0) * self.W_QUALITY_IBD / 50.0)
        )

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
            return 0.0, None
        q = float(row[0]) if row[0] is not None else 50.0
        # Linear scale: 50 = 0 pts (neutral quality), 100 = W_QUALITY_FIN pts (maximum)
        pts = max(0.0, min(self.W_QUALITY_FIN, (q - 50.0) * self.W_QUALITY_FIN / 50.0))
        return pts, round(q, 1)

    def _earnings_quality_score(self, symbol, cur):
        try:
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
                return 0.0, None
            score = float(row[0])
            pts = (score / 100.0) * self.W_QUALITY_EARNINGS
            return pts, round(score, 1)
        except Exception as e:
            logger.debug(f"Earnings quality score calculation failed: {e}")
            return 0.0, None

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
            return 0.0, {}
        rev_3y = float(row[0]) if row[0] is not None else 0.0
        eps_3y = float(row[1]) if row[1] is not None else 0.0
        mom = float(row[2]) if row[2] is not None else 0.0
        rev_yoy = float(row[3]) if row[3] is not None else 0.0
        # 3 pts each for EPS 3y >20%, rev 3y >15%, positive momentum (within W_CATALYST_GROWTH=7)
        eps_p = max(0.0, min(2.5, eps_3y / 20.0 * 2.5)) if eps_3y > 0 else 0.0
        rev_p = max(0.0, min(2.5, rev_3y / 15.0 * 2.5)) if rev_3y > 0 else 0.0
        mom_p = 2.0 if mom > 0 else 0.0
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
            return 0.0, 0
        ups = int(row[0]) if row[0] is not None else 0
        downs = int(row[1]) if row[1] is not None else 0
        net = ups - downs
        # +5 net = full; -3 net = 0
        pts = max(
            0.0, min(self.W_CATALYST_ANALYST, (net + 3) * self.W_CATALYST_ANALYST / 8.0)
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
            return 0.0, 0
        buys = float(row[0]) if row[0] is not None else 0
        sells = float(row[1]) if row[1] is not None else 0
        net = buys - sells
        if net <= 0:
            return 0.0, net
        pts = min(self.W_CATALYST_INSIDER, net / 500_000.0 * self.W_CATALYST_INSIDER)
        return pts, net

    # ============= RISK =============

    def _extension_pct(self, symbol, signal_date, entry_price, cur):
        cur.execute(
            "SELECT sma_50 FROM technical_data_daily WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1",
            (symbol, signal_date),
        )
        row = cur.fetchone()
        if not row or not row[0] or float(row[0]) <= 0:
            return None
        sma_50 = float(row[0])
        return ((entry_price - sma_50) / sma_50) * 100.0

    def _extension_risk_score(self, ext_pct):
        if ext_pct is None:
            return 0.0
        if ext_pct < 0:
            return self.W_RISK_EXTENSION * 0.6  # below 50 = OK but not ideal
        if ext_pct <= 5:
            return self.W_RISK_EXTENSION  # sweet spot
        if ext_pct <= 10:
            return self.W_RISK_EXTENSION * (1.0 - (ext_pct - 5) / 5.0 * 0.5)
        if ext_pct <= 15:
            return self.W_RISK_EXTENSION * 0.25
        return 0.0

    def _earnings_proximity_score(self, days_to_earnings, block_window):
        if days_to_earnings is None:
            return self.W_RISK_EARNINGS_PROX * 0.5
        if days_to_earnings <= block_window:
            return 0.0
        if days_to_earnings >= 30:
            return self.W_RISK_EARNINGS_PROX
        return (
            self.W_RISK_EARNINGS_PROX
            * (days_to_earnings - block_window)
            / (30 - block_window)
        )

    def _avg_dollar_volume(self, symbol, signal_date, cur):
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
            return None
        return float(row[0])

    def _estimate_days_to_earnings(self, symbol, signal_date, cur):
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
            return None

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
        signal_d = signal_date if isinstance(signal_date, _date) else signal_date
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
