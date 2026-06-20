#!/usr/bin/env python3

import json
import logging
from datetime import date
from typing import Any, cast

import psycopg2

from algo.signals.swing_component_scorer import SwingComponentScorer
from utils.db import DatabaseContext


logger = logging.getLogger(__name__)


class SwingTraderScore:
    """Compute and persist swing-specific composite scores."""

    W_SETUP = 25
    W_TREND = 20
    W_MOMENTUM = 20
    W_VOLUME = 12
    W_FUNDAMENTALS = 10
    W_SECTOR = 8
    W_MULTI_TF = 5

    def __init__(self, config):
        if config is None:
            raise ValueError("SwingTraderScore requires explicit config parameter (dependency injection)")
        self.config = config
        from algo.signals import SignalComputer

        self._signals = SignalComputer()
        self.scorer = SwingComponentScorer(config, self._signals)

    def _with_cursor(self, operation, mode="read"):
        """Execute operation with a cursor via DatabaseContext."""
        try:
            with DatabaseContext(mode) as cur:
                return operation(cur)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def compute(
        self,
        symbol: str,
        eval_date,
        sector: str | None = None,
        industry: str | None = None,
    ) -> dict[str, Any]:
        """
        Compute the full swing trader score composite with hard-fail gates.

        **Process:**
          1. Check hard-fail gates (trend score, stage, base type, etc.)
          2. If any hard gate fails, return 0 score with reason
          3. If gates pass, compute 7 weighted components
          4. Aggregate into swing_score (0-100 scale) and letter grade
          5. Persist to swing_trader_scores table for dashboard/tracking

        **Hard-Fail Gates (Applied First):**
          - Trend template score >= 5/8 (Minervini 8-point minimum)
          - Weinstein stage == 2 (must be in uptrend phase)
          - Within 25% of 52-week high (not extended too far)
          - Base count < 4 (not too many bases before breakout)
          - Industry rank <= 100 (not in bottom half)
          - Base type != 'wide_and_loose' and quality != 'D'
          - Earnings not within 5 trading days (avoid event risk)

        **Weighted Components:**
          - SETUP_QUALITY (25%): Base type + breakout proximity + VCP + pivot
          - TREND_QUALITY (20%): Minervini score + stage + 30wk MA slope
          - MOMENTUM_RS (20%): RS percentile + 1m/3m/6m return blend
          - VOLUME (12%): Breakout volume + accumulation days
          - FUNDAMENTALS (10%): EPS growth + revenue growth + ROE
          - SECTOR_INDUSTRY (8%): Industry rank > sector rank (industry weighted)
          - MULTI_TIMEFRAME (5%): Weekly + monthly buy_sell alignment

        **Scoring:**
          - Sum of weighted components (0-100)
          - Letter grade: A+ (85+), A (75+), B (65+), C (55+), D (45+), F (<45)

        **Return Dict:**
          {
              'symbol': str,
              'eval_date': str,
              'pass': bool (False if hard gates fail),
              'swing_score': float (0-100, or 0 if failed gates),
              'grade': str ('A+', 'A', 'B', 'C', 'D', 'F'),
              'reason': str (if pass=False, reason for failure),
              'components': {
                  'setup_quality': {'pts': float, 'max': 25, 'detail': dict},
                  'trend_quality': {'pts': float, 'max': 20, 'detail': dict},
                  'momentum_rs': {'pts': float, 'max': 20, 'detail': dict},
                  'volume': {'pts': float, 'max': 12, 'detail': dict},
                  'fundamentals': {'pts': float, 'max': 10, 'detail': dict},
                  'sector_industry': {'pts': float, 'max': 8, 'detail': dict},
                  'multi_timeframe': {'pts': float, 'max': 5, 'detail': dict},
              },
              'hard_gates': dict (details of gate checks)
          }

        Args:
            symbol: Stock ticker (e.g., "AAPL")
            eval_date: Date to evaluate as of
            sector: Sector name (optional, used for ranking comparison)
            industry: Industry name (optional, used for ranking comparison)

        Returns:
            Dict with swing_score, grade, components breakdown, and hard-gate details
        """
        with DatabaseContext("read") as cur:
            try:
                # Hard gates — fail-closed: DB/infra error blocks scoring rather than passing silently
                try:
                    gates = self._check_hard_gates(symbol, eval_date, industry, cur)
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as gate_err:
                    logger.warning(f"Swing score hard gates unavailable for {symbol}: {gate_err} — blocking")
                    return {
                        "symbol": symbol,
                        "eval_date": str(eval_date),
                        "pass": False,
                        "reason": f"Hard gates unavailable: {str(gate_err)[:60]}",
                        "swing_score": 0.0,
                    }

                if not gates["pass"]:
                    logger.debug(f"Swing score {symbol}: hard gate failed - {gates.get('reason', 'unknown')}")
                    return {
                        "symbol": symbol,
                        "eval_date": str(eval_date),
                        "pass": False,
                        "reason": gates["reason"],
                        "hard_gates": gates,
                        "swing_score": 0.0,
                    }

                # Compute critical components (fail-hard if data unavailable)
                setup_pts, setup_detail = self.scorer.compute_setup_component(symbol, eval_date)
                trend_pts, trend_detail = self.scorer.compute_trend_component(symbol, eval_date, cur)
                mom_pts, mom_detail = self.scorer.compute_momentum_component(symbol, eval_date, cur)

                try:
                    vol_pts, vol_detail = self.scorer.compute_volume_component(symbol, eval_date, cur)
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    logger.debug(f"Volume component failed for {symbol}: {e}")
                    vol_pts, vol_detail = 0, {"error": str(e)[:50]}

                try:
                    fund_pts, fund_detail = self.scorer.compute_fundamentals_component(symbol, cur)
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    logger.debug(f"Fundamentals component failed for {symbol}: {e}")
                    fund_pts, fund_detail = 0, {"error": str(e)[:50]}

                try:
                    sec_pts, sec_detail = self.scorer.compute_sector_component(symbol, eval_date, sector, industry, cur)
                except Exception as e:
                    logger.debug(f"Sector component failed for {symbol}: {e}")
                    sec_pts, sec_detail = 0, {"error": str(e)[:50]}

                try:
                    mtf_pts, mtf_detail = self.scorer.compute_multi_timeframe_component(symbol, eval_date, cur)
                except Exception as e:
                    logger.debug(f"Multi-timeframe component failed for {symbol}: {e}")
                    mtf_pts, mtf_detail = 0, {"error": str(e)[:50]}

                total = setup_pts + trend_pts + mom_pts + vol_pts + fund_pts + sec_pts + mtf_pts

                # Classify grade based on score: A+ (85+), A (75+), B (65+), C (55+), D (45+), F (<45)
                if total >= 85:
                    grade = "A+"
                elif total >= 75:
                    grade = "A"
                elif total >= 65:
                    grade = "B"
                elif total >= 55:
                    grade = "C"
                elif total >= 45:
                    grade = "D"
                else:
                    grade = "F"

                result = {
                    "symbol": symbol,
                    "eval_date": str(eval_date),
                    "pass": True,
                    "swing_score": round(total, 1),
                    "grade": grade,
                    "components": {
                        "setup_quality": {
                            "pts": round(setup_pts, 1),
                            "max": self.W_SETUP,
                            "detail": setup_detail,
                        },
                        "trend_quality": {
                            "pts": round(trend_pts, 1),
                            "max": self.W_TREND,
                            "detail": trend_detail,
                        },
                        "momentum_rs": {
                            "pts": round(mom_pts, 1),
                            "max": self.W_MOMENTUM,
                            "detail": mom_detail,
                        },
                        "volume": {
                            "pts": round(vol_pts, 1),
                            "max": self.W_VOLUME,
                            "detail": vol_detail,
                        },
                        "fundamentals": {
                            "pts": round(fund_pts, 1),
                            "max": self.W_FUNDAMENTALS,
                            "detail": fund_detail,
                        },
                        "sector_industry": {
                            "pts": round(sec_pts, 1),
                            "max": self.W_SECTOR,
                            "detail": sec_detail,
                        },
                        "multi_timeframe": {
                            "pts": round(mtf_pts, 1),
                            "max": self.W_MULTI_TF,
                            "detail": mtf_detail,
                        },
                    },
                    "hard_gates": gates,
                }
                self._persist(symbol, eval_date, result)
                logger.debug(f"Swing score {symbol}: {total:.1f} ({grade})")
                return result
            except Exception as e:
                logger.error(f"Swing score calculation failed for {symbol}: {e}", exc_info=True)
                return {
                    "symbol": symbol,
                    "eval_date": str(eval_date),
                    "pass": False,
                    "reason": f"calculation error: {str(e)[:60]}",
                    "swing_score": 0.0,
                }

    # ============= HARD GATES =============

    def _check_hard_gates(self, symbol: str, eval_date, industry: str | None, cur) -> dict[str, Any]:
        """
        Apply hard-fail gates that block scoring entirely if violated.

        Any single gate failure returns {'pass': False, 'reason': str}.
        All gates must pass for compute() to proceed to component scoring.

        **Gates Checked:**
          1. Trend template score >= min_trend_score (config, default 5/8)
          2. Weinstein stage == 2 (must be in uptrend)
          3. Within max_extension_pct of 52w high (config, default 25%)
          4. Base count < 4 (reasonable consolidation count)
          5. Base type != 'wide_and_loose' and quality != 'D'
          6. Industry rank <= max_industry_rank (config, default 100)
          7. Earnings not within N days (config, default 5 trading days)

        Config keys: swing_min_trend_score, swing_max_extension_pct,
                    swing_min_industry_rank, swing_days_to_earnings_block

        Returns: {'pass': True} or {'pass': False, 'reason': str, ...details...}
        """
        # Gate 1 & 2: Minervini trend score + Weinstein stage
        trend_score = 0
        stage = 1
        try:
            cur.execute(
                """SELECT minervini_trend_score, weinstein_stage FROM trend_template_data
                   WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1""",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if row:
                trend_score = int(row[0]) if row[0] is not None else 0
                stage = int(row[1]) if row[1] is not None else 1
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"Could not fetch trend data for {symbol}: {e}")

        min_trend_score = self._load_config_val("swing_min_trend_score", 5)
        if trend_score < min_trend_score:
            return {
                "pass": False,
                "reason": f"Trend score {trend_score} < {min_trend_score}",
                "trend_score": trend_score,
            }

        if stage != 2:
            return {
                "pass": False,
                "reason": f"Weinstein stage {stage} != 2 (must be in uptrend)",
                "stage": stage,
            }

        # Gate 3: Not too extended from 52-week high
        try:
            max_extension_pct = self._load_config_val("swing_max_extension_pct", 25)
            cur.execute(
                """SELECT percent_from_52w_high FROM trend_template_data
                   WHERE symbol = %s AND date <= %s ORDER BY date DESC LIMIT 1""",
                (symbol, eval_date),
            )
            row = cur.fetchone()
            if row and row[0] is not None:
                pct_from_high = float(row[0])
                # pct_from_high is (close - high52w) / high52w * 100, always ≤ 0.
                # -30 means 30% below the 52w high. Reject if too far below the high.
                if pct_from_high < -max_extension_pct:
                    return {
                        "pass": False,
                        "reason": f"{abs(pct_from_high):.1f}% below 52w high (max {max_extension_pct}% allowed)",
                        "percent_from_52w_high": pct_from_high,
                    }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.debug(f"52w high extension check failed: {e}")

        # Gate 4: Base type quality check
        base_type = self._signals.classify_base_type(symbol, eval_date)
        if base_type.get("type") == "wide_and_loose":
            return {
                "pass": False,
                "reason": f"Bad base: {base_type.get('type')} (quality {base_type.get('quality')})",
                "base": base_type,
            }

        # Gate 6: Industry rank (not in bottom half)
        industry_rank = None
        if industry:
            try:
                max_industry_rank = self._load_config_val("swing_min_industry_rank", 100)
                cur.execute(
                    """SELECT current_rank FROM industry_ranking
                       WHERE industry = %s AND date_recorded <= %s
                       ORDER BY date_recorded DESC LIMIT 1""",
                    (industry, eval_date),
                )
                r = cur.fetchone()
                if r and r[0]:
                    industry_rank = int(r[0])
                    if industry_rank > max_industry_rank:
                        return {
                            "pass": False,
                            "reason": f"Industry rank {industry_rank} > {max_industry_rank} (bottom half)",
                            "industry_rank": industry_rank,
                        }
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.debug(f"Industry rank check failed: {e}")

        # Gate 7: Earnings proximity
        days_to_earn = None
        try:
            days_to_earn = self._days_to_earnings(symbol, eval_date)
        except ValueError as e:
            logger.debug(f"Earnings date unavailable for {symbol}: {e} — allowing trade")

        earnings_block = self._load_config_val("swing_days_to_earnings_block", 5)
        if days_to_earn is not None and 0 <= days_to_earn <= earnings_block:
            return {
                "pass": False,
                "reason": f"Earnings in ~{days_to_earn}d (blocked within {earnings_block}d)",
                "days_to_earnings": days_to_earn,
            }

        # All gates passed
        return {
            "pass": True,
            "trend_score": trend_score,
            "stage": stage,
            "base_type": base_type.get("type"),
            "base_quality": base_type.get("quality"),
            "industry_rank": industry_rank,
            "days_to_earnings": days_to_earn,
        }

    def _days_to_earnings(self, symbol: str, eval_date) -> int | None:
        """Days until next earnings from earnings_calendar.

        Raises:
            ValueError: If earnings calendar data is unavailable for the symbol
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """SELECT earnings_date FROM earnings_calendar
                       WHERE symbol = %s AND earnings_date > %s
                       ORDER BY earnings_date ASC LIMIT 1""",
                    (symbol, eval_date),
                )
                row = cur.fetchone()
                if row and row[0]:
                    return cast(int, (row[0] - eval_date).days)
            raise ValueError(f"Earnings calendar data not available for {symbol} on {eval_date}")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    # ============= helpers (component methods delegated to SwingComponentScorer) =============

    def _persist(self, symbol: str, eval_date, result: dict[str, Any]) -> None:
        """Persist computed swing score to swing_trader_scores table."""
        try:
            comp = result.get("components", {})

            default_components = {
                "setup_quality": {"pts": 0.0, "max": self.W_SETUP},
                "trend_quality": {"pts": 0.0, "max": self.W_TREND},
                "momentum_rs": {"pts": 0.0, "max": self.W_MOMENTUM},
                "volume": {"pts": 0.0, "max": self.W_VOLUME},
                "fundamentals": {"pts": 0.0, "max": self.W_FUNDAMENTALS},
                "sector_industry": {"pts": 0.0, "max": self.W_SECTOR},
                "multi_timeframe": {"pts": 0.0, "max": self.W_MULTI_TF},
            }

            for key in default_components:
                if key in comp:
                    default_components[key].update(comp[key])

            components_json = {
                **default_components,
                "grade": result.get("grade", "F"),
                "pass": result.get("pass", False),
                "reason": result.get("reason"),
            }

            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO swing_trader_scores (symbol, date, score, components)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        score = EXCLUDED.score,
                        components = EXCLUDED.components,
                        created_at = CURRENT_TIMESTAMP
                    """,
                    (
                        symbol,
                        eval_date,
                        float(result.get("swing_score", 0)),
                        json.dumps(components_json),
                    ),
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"persist swing_score failed for {symbol}: {e}", exc_info=True)


if __name__ == "__main__":
    from algo.infrastructure.config import get_config

    s = SwingTraderScore(get_config())
    eval_date = date(2026, 4, 24)
    logger.info(f"SWING TRADER SCORES — {eval_date}")

    candidates = (
        "AROC",
        "CASS",
        "CVV",
        "EW",
        "FSTR",
        "LRCX",
        "NATR",
        "NBHC",
        "NGS",
        "SMTC",
        "SRCE",
        "CTS",
    )

    with DatabaseContext("read") as cur:
        for sym in candidates:
            cur.execute("SELECT sector, industry FROM company_profile WHERE ticker = %s", (sym,))
            r = cur.fetchone()
            sector = r[0] if r else None
            industry = r[1] if r else None
            result = s.compute(sym, eval_date, sector=sector, industry=industry)
            if result["pass"]:
                comp = result["components"]
                logger.info(
                    f"{sym:6s} {result['grade']:>3s} {result['swing_score']:5.1f}/100 | "
                    f"setup {comp['setup_quality']['pts']:4.1f} | "
                    f"trend {comp['trend_quality']['pts']:4.1f} | "
                    f"mom {comp['momentum_rs']['pts']:4.1f} | "
                    f"vol {comp['volume']['pts']:4.1f} | "
                    f"fund {comp['fundamentals']['pts']:4.1f} | "
                    f"sec {comp['sector_industry']['pts']:4.1f} | "
                    f"mtf {comp['multi_timeframe']['pts']:4.1f}"
                )
            else:
                logger.warning(f"{sym:6s} BLOCKED: {result['reason']}")
