#!/usr/bin/env python3
"""Stock Scores Loader - Multi-factor composite stock scoring.

Computes composite stock scores by aggregating:
- Quality metrics (ROE, margins, debt-to-equity ratio)
- Growth metrics (revenue growth, EPS growth)
- Value metrics (P/E, P/B, P/S ratios, dividend yield)
- Momentum/Relative Strength (1m/3m/6m/12m returns)
- Positioning metrics (institutional ownership, short interest)
- Stability metrics (volatility, beta)

Each factor is normalized to 0-100 scale and weighted.
Final composite score is weighted average of all factors.

Run: python3 loaders/load_stock_scores.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

import sys
import argparse
from datetime import date
from typing import Optional, Dict
import logging

from utils.loaders.helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader
from utils.db.context import DatabaseContext
from utils.loaders.config import get_default_parallelism

logger = logging.getLogger(__name__)


class StockScoresLoader(OptimalLoader):
    """Compute and load multi-factor stock scores."""

    table_name = "stock_scores"
    primary_key = ("symbol",)
    watermark_field = None  # No date watermark, we compute all at once

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute stock scores for this symbol."""
        try:
            score_result = self._compute_stock_score(symbol)
            if score_result:
                return [score_result]
            return []
        except Exception as e:
            logger.debug(f"Stock score computation error for {symbol}: {e}")
            return []

    def _compute_stock_score(self, symbol: str) -> Optional[Dict]:
        """Compute composite stock score from REAL metrics only (no fake defaults).

        Only returns a score if stock has sufficient real data (>=50% completeness).
        Stocks without real data are skipped entirely (return None).

        Returns dict with keys: symbol, composite_score, quality_score, growth_score,
        value_score, momentum_score, positioning_score, stability_score, rs_percentile,
        data_completeness
        """
        try:
            with DatabaseContext("read") as cur:
                # Fetch all available metrics for this symbol
                quality = self._get_quality_metrics(cur, symbol)
                growth = self._get_growth_metrics(cur, symbol)
                value = self._get_value_metrics(cur, symbol)
                positioning = self._get_positioning_metrics(cur, symbol)
                stability = self._get_stability_metrics(cur, symbol)
                momentum = self._get_momentum_metrics(cur, symbol)

            # Compute individual factor scores from REAL data only (no defaults)
            # Scoring functions return None if metrics dict exists but has all NULL values
            quality_score = self._score_quality(quality)
            growth_score = self._score_growth(growth)
            value_score = self._score_value(value)
            positioning_score = self._score_positioning(positioning)
            stability_score = self._score_stability(stability)
            momentum_score = self._score_momentum(momentum)

            # Count data completeness: only non-None scores count as "real data"
            # (ignores empty rows with all NULLs which return None from scoring functions)
            real_scores = [
                s
                for s in [
                    quality_score,
                    growth_score,
                    value_score,
                    positioning_score,
                    stability_score,
                    momentum_score,
                ]
                if s is not None
            ]
            data_count = len(real_scores)
            # Cap at 99.99 to fit in NUMERIC(4,2) database column
            data_completeness = min(99.99, round((data_count / 6.0) * 100, 2))

            # SKIP stocks without sufficient real data (require >=50% completeness = 3+ metrics)
            min_required_metrics = 3
            if data_count < min_required_metrics:
                logger.debug(
                    f"{symbol}: insufficient data ({data_count}/6 metrics, {data_completeness:.0f}% complete) - skipping"
                )
                return None

            # Compute weighted composite score with NORMALIZED weights
            # When metrics are missing, redistribute their weight to available metrics
            # instead of filling with mean (which would double-count missing factors)
            base_weights = {
                "quality": 0.25,
                "growth": 0.20,
                "value": 0.20,
                "positioning": 0.15,
                "stability": 0.12,
                "momentum": 0.08,
            }

            # Calculate real scores and identify available metrics
            real_scores = [
                s
                for s in [
                    quality_score,
                    growth_score,
                    value_score,
                    positioning_score,
                    stability_score,
                    momentum_score,
                ]
                if s is not None
            ]
            if not real_scores:
                return None  # No real data at all

            # Build mapping of which scores are available
            score_availability = {
                "quality": quality_score is not None,
                "growth": growth_score is not None,
                "value": value_score is not None,
                "positioning": positioning_score is not None,
                "stability": stability_score is not None,
                "momentum": momentum_score is not None,
            }

            # Normalize weights: keep weights of available metrics, redistribute missing weights
            available_weight_sum = sum(
                w for k, w in base_weights.items() if score_availability[k]
            )
            normalized_weights = {}
            for key, weight in base_weights.items():
                if score_availability[key]:
                    # Scale up available weights to sum to 1.0
                    normalized_weights[key] = (
                        weight / available_weight_sum if available_weight_sum > 0 else 0
                    )
                else:
                    normalized_weights[key] = 0

            # Clamp all scores to 0-100 range (only actual computed scores, not filled)
            quality_score = max(
                0, min(100, quality_score if quality_score is not None else 0)
            )
            growth_score = max(
                0, min(100, growth_score if growth_score is not None else 0)
            )
            value_score = max(
                0, min(100, value_score if value_score is not None else 0)
            )
            positioning_score = max(
                0, min(100, positioning_score if positioning_score is not None else 0)
            )
            stability_score = max(
                0, min(100, stability_score if stability_score is not None else 0)
            )
            momentum_score = max(
                0, min(100, momentum_score if momentum_score is not None else 0)
            )

            # Compute weighted composite with normalized weights (sums to 1.0)
            composite_score = round(
                quality_score * normalized_weights["quality"]
                + growth_score * normalized_weights["growth"]
                + value_score * normalized_weights["value"]
                + positioning_score * normalized_weights["positioning"]
                + stability_score * normalized_weights["stability"]
                + momentum_score * normalized_weights["momentum"],
                2,
            )
            # Final clamp to ensure composite is in range
            composite_score = max(0, min(100, composite_score))

            # RS percentile is set to 0 here and updated in a batch pass
            # after all symbols are scored (see _update_rs_percentiles).
            rs_percentile = 0.0

            return {
                "symbol": symbol,
                "composite_score": composite_score,
                "quality_score": round(quality_score, 2),
                "growth_score": round(growth_score, 2),
                "value_score": round(value_score, 2),
                "momentum_score": round(momentum_score, 2),
                "positioning_score": round(positioning_score, 2),
                "stability_score": round(stability_score, 2),
                "rs_percentile": rs_percentile,
                "data_completeness": data_completeness,
            }

        except Exception as e:
            logger.warning(f"Stock score computation failed for {symbol}: {e}")
            return None

    def _get_quality_metrics(self, cur, symbol: str) -> Optional[Dict]:
        """Fetch quality metrics for symbol."""
        try:
            cur.execute(
                "SELECT roe, roa, operating_margin, net_margin, debt_to_equity, current_ratio, quick_ratio FROM quality_metrics WHERE symbol = %s",
                (symbol,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "roe": float(row[0]) if row[0] else None,
                    "roa": float(row[1]) if row[1] else None,
                    "operating_margin": float(row[2]) if row[2] else None,
                    "net_margin": float(row[3]) if row[3] else None,
                    "debt_to_equity": float(row[4]) if row[4] else None,
                    "current_ratio": float(row[5]) if row[5] else None,
                    "quick_ratio": float(row[6]) if row[6] else None,
                }
        except Exception as e:
            logger.warning(f"Failed to fetch metrics for {symbol}: {e}")
        return None

    def _get_growth_metrics(self, cur, symbol: str) -> Optional[Dict]:
        """Fetch growth metrics for symbol."""
        try:
            cur.execute(
                "SELECT revenue_growth_1y, revenue_growth_3y, revenue_growth_5y, eps_growth_1y, eps_growth_3y, eps_growth_5y FROM growth_metrics WHERE symbol = %s",
                (symbol,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "revenue_growth_1y": float(row[0]) if row[0] else None,
                    "revenue_growth_3y": float(row[1]) if row[1] else None,
                    "revenue_growth_5y": float(row[2]) if row[2] else None,
                    "eps_growth_1y": float(row[3]) if row[3] else None,
                    "eps_growth_3y": float(row[4]) if row[4] else None,
                    "eps_growth_5y": float(row[5]) if row[5] else None,
                }
        except Exception as e:
            logger.warning(f"Failed to fetch metrics for {symbol}: {e}")
        return None

    def _get_value_metrics(self, cur, symbol: str) -> Optional[Dict]:
        """Fetch value metrics for symbol."""
        try:
            cur.execute(
                "SELECT pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield FROM value_metrics WHERE symbol = %s",
                (symbol,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "pe_ratio": float(row[0]) if row[0] else None,
                    "pb_ratio": float(row[1]) if row[1] else None,
                    "ps_ratio": float(row[2]) if row[2] else None,
                    "peg_ratio": float(row[3]) if row[3] else None,
                    "dividend_yield": float(row[4]) if row[4] else None,
                    "fcf_yield": float(row[5]) if row[5] else None,
                }
        except Exception as e:
            logger.warning(f"Failed to fetch metrics for {symbol}: {e}")
        return None

    def _get_positioning_metrics(self, cur, symbol: str) -> Optional[Dict]:
        """Fetch positioning metrics for symbol."""
        try:
            cur.execute(
                "SELECT institutional_ownership, insider_ownership, short_interest_percent FROM positioning_metrics WHERE symbol = %s",
                (symbol,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "institutional_ownership": float(row[0]) if row[0] else None,
                    "insider_ownership": float(row[1]) if row[1] else None,
                    "short_interest": float(row[2]) if row[2] else None,
                }
        except Exception as e:
            logger.warning(f"Failed to fetch metrics for {symbol}: {e}")
        return None

    def _get_stability_metrics(self, cur, symbol: str) -> Optional[Dict]:
        """Fetch stability metrics for symbol."""
        try:
            cur.execute(
                "SELECT volatility_252d, volatility_60d, volatility_30d, beta, debt_to_assets FROM stability_metrics WHERE symbol = %s",
                (symbol,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "volatility_252d": float(row[0]) if row[0] else None,
                    "volatility_60d": float(row[1]) if row[1] else None,
                    "volatility_30d": float(row[2]) if row[2] else None,
                    "beta": float(row[3]) if row[3] else None,
                    "debt_to_assets": float(row[4]) if row[4] else None,
                }
        except Exception as e:
            logger.warning(f"Failed to fetch metrics for {symbol}: {e}")
        return None

    def _get_momentum_metrics(self, cur, symbol: str) -> Optional[Dict]:
        """Fetch momentum/RS metrics for symbol using DATE-based lookups (not OFFSET).

        Uses date arithmetic to find approximate prices at 1m/3m/6m/12m ago.
        More robust than OFFSET which breaks on data gaps or different row counts.
        """
        try:
            # Get recent price performance from price_daily table using calendar date lookups
            cur.execute(
                """
                SELECT
                    (SELECT close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1) as current,
                    (SELECT close FROM price_daily WHERE symbol = %s AND date <= CURRENT_DATE - INTERVAL '1 month' ORDER BY date DESC LIMIT 1) as price_1m_ago,
                    (SELECT close FROM price_daily WHERE symbol = %s AND date <= CURRENT_DATE - INTERVAL '3 months' ORDER BY date DESC LIMIT 1) as price_3m_ago,
                    (SELECT close FROM price_daily WHERE symbol = %s AND date <= CURRENT_DATE - INTERVAL '6 months' ORDER BY date DESC LIMIT 1) as price_6m_ago,
                    (SELECT close FROM price_daily WHERE symbol = %s AND date <= CURRENT_DATE - INTERVAL '1 year' ORDER BY date DESC LIMIT 1) as price_12m_ago
            """,
                (symbol, symbol, symbol, symbol, symbol),
            )
            row = cur.fetchone()

            if row and row[0]:
                prices = {
                    "current": float(row[0]) if row[0] else None,
                    "price_1m_ago": float(row[1]) if row[1] else None,
                    "price_3m_ago": float(row[2]) if row[2] else None,
                    "price_6m_ago": float(row[3]) if row[3] else None,
                    "price_12m_ago": float(row[4]) if row[4] else None,
                }

                # Calculate returns; None if historical price unavailable (e.g. recent IPO)
                momentum_1m = (
                    ((prices["current"] / prices["price_1m_ago"] - 1) * 100)
                    if prices["price_1m_ago"]
                    else None
                )
                momentum_3m = (
                    ((prices["current"] / prices["price_3m_ago"] - 1) * 100)
                    if prices["price_3m_ago"]
                    else None
                )
                momentum_6m = (
                    ((prices["current"] / prices["price_6m_ago"] - 1) * 100)
                    if prices["price_6m_ago"]
                    else None
                )
                momentum_12m = (
                    ((prices["current"] / prices["price_12m_ago"] - 1) * 100)
                    if prices["price_12m_ago"]
                    else None
                )

                return {
                    "momentum_1m": momentum_1m,
                    "momentum_3m": momentum_3m,
                    "momentum_6m": momentum_6m,
                    "momentum_12m": momentum_12m,
                }
        except Exception as e:
            logger.warning(f"Failed to fetch metrics for {symbol}: {e}")
        return None

    def _score_quality(self, metrics: Optional[Dict]) -> Optional[float]:
        """Score quality metrics on 0-100 scale. Returns None if no real data."""
        if not metrics:
            return None

        scores = []

        # ROE: higher is better (target 15%+, cap at 40%)
        if metrics.get("roe"):
            roe = min(metrics["roe"], 40)
            scores.append(min(100, (roe / 40) * 100))

        # ROA: higher is better (target 5%+, cap at 20%)
        if metrics.get("roa") and metrics["roa"] > 0:
            roa = min(metrics["roa"], 20)
            scores.append(min(100, (roa / 20) * 100))

        # Net margin: higher is better (target 10%+, cap at 30%)
        if metrics.get("net_margin") and metrics["net_margin"] > 0:
            nm = min(metrics["net_margin"], 30)
            scores.append(min(100, (nm / 30) * 100))

        # Operating margin: higher is better (target 10%+, cap at 30%)
        if metrics.get("operating_margin") and metrics["operating_margin"] > 0:
            om = min(metrics["operating_margin"], 30)
            scores.append(min(100, (om / 30) * 100))

        # Debt-to-equity: lower is better (target <1.0)
        if metrics.get("debt_to_equity") is not None and metrics["debt_to_equity"] >= 0:
            de = min(metrics["debt_to_equity"], 5)
            score = max(0, 100 - (de * 20))
            scores.append(min(100, score))

        # Current ratio: above 1.5 is good, above 2.0 is excellent
        if metrics.get("current_ratio") and metrics["current_ratio"] > 0:
            cr = metrics["current_ratio"]
            if cr >= 2.0:
                scores.append(100)
            elif cr >= 1.5:
                scores.append(80)
            elif cr >= 1.0:
                scores.append(60)
            else:
                scores.append(max(0, cr * 60))

        return sum(scores) / len(scores) if scores else None

    def _score_growth(self, metrics: Optional[Dict]) -> Optional[float]:
        """Score growth metrics on 0-100 scale. Returns None if no real data.

        Uses weighted blend: 1Y growth (60%) + 3Y CAGR (30%) + 5Y CAGR (10%).
        Longer-term growth signals more durable earnings quality.
        """
        if not metrics:
            return None

        weighted_sum = 0.0
        total_weight = 0.0

        def _score_single_growth(val, cap):
            """Score a single growth rate capped at `cap`%."""
            if val is None:
                return None
            if val <= 0:
                # Negative growth: map [-50, 0] → [0, 40]
                return max(0, 40 + (val / 50) * 40)
            return min(100, (val / cap) * 100)

        # 1-year EPS growth: target 25%+ for growth stocks (highest weight)
        eps_1y = _score_single_growth(metrics.get("eps_growth_1y"), 50)
        if eps_1y is not None:
            weighted_sum += eps_1y * 0.35
            total_weight += 0.35

        # 1-year revenue growth: target 15%+
        rev_1y = _score_single_growth(metrics.get("revenue_growth_1y"), 30)
        if rev_1y is not None:
            weighted_sum += rev_1y * 0.25
            total_weight += 0.25

        # 3-year EPS CAGR: sustained growth signal
        eps_3y = _score_single_growth(metrics.get("eps_growth_3y"), 35)
        if eps_3y is not None:
            weighted_sum += eps_3y * 0.20
            total_weight += 0.20

        # 3-year revenue CAGR: sustained top-line growth
        rev_3y = _score_single_growth(metrics.get("revenue_growth_3y"), 20)
        if rev_3y is not None:
            weighted_sum += rev_3y * 0.15
            total_weight += 0.15

        # 5-year EPS CAGR: long-term compounding quality (lower weight)
        eps_5y = _score_single_growth(metrics.get("eps_growth_5y"), 30)
        if eps_5y is not None:
            weighted_sum += eps_5y * 0.05
            total_weight += 0.05

        return weighted_sum / total_weight if total_weight > 0 else None

    def _score_value(self, metrics: Optional[Dict]) -> Optional[float]:
        """Score value metrics on 0-100 scale. Returns None if no real data.

        Uses P/E (primary), P/B (secondary), FCF yield (secondary), dividend yield (bonus).
        Peak zone for growth stocks: P/E 15-30, P/B < 5, positive FCF yield.
        """
        if not metrics:
            return None

        weighted_sum = 0.0
        total_weight = 0.0

        # P/E ratio: sweet spot 15-30 for growth momentum stocks
        if metrics.get("pe_ratio") and metrics["pe_ratio"] > 0:
            pe = metrics["pe_ratio"]
            if pe <= 10:
                pe_score = 40 + pe * 2    # very cheap / possibly value trap
            elif pe <= 20:
                pe_score = 60 + (pe - 10) * 4   # good range
            elif pe <= 35:
                pe_score = 100 - (pe - 20) * 2   # growth premium zone → 70 at pe=35
            else:
                pe_score = max(0, 70 - (pe - 35) * 1.4)  # expensive → 0 at pe~85
            weighted_sum += pe_score * 0.50
            total_weight += 0.50

        # P/B ratio: lower is better for value; < 3 is reasonable for most sectors
        if metrics.get("pb_ratio") and metrics["pb_ratio"] > 0:
            pb = metrics["pb_ratio"]
            if pb <= 1.0:
                pb_score = 100
            elif pb <= 3.0:
                pb_score = 100 - ((pb - 1.0) / 2.0) * 30   # 100→70 in [1,3]
            elif pb <= 7.0:
                pb_score = 70 - ((pb - 3.0) / 4.0) * 40    # 70→30 in [3,7]
            else:
                pb_score = max(0, 30 - (pb - 7.0) * 3)
            weighted_sum += pb_score * 0.25
            total_weight += 0.25

        # FCF yield: positive FCF yield is healthy; > 3% is good
        if metrics.get("fcf_yield") is not None and metrics["fcf_yield"] > 0:
            fcf_pct = metrics["fcf_yield"] * 100  # stored as decimal fraction
            fcf_score = min(100, fcf_pct * 20)    # 5% FCF yield = 100 score
            weighted_sum += fcf_score * 0.15
            total_weight += 0.15

        # Dividend yield: bonus signal for income/quality (optional)
        if metrics.get("dividend_yield") and metrics["dividend_yield"] > 0:
            div = min(metrics["dividend_yield"] * 100, 6)   # decimal → percent, cap 6%
            div_score = min(100, div * 16.7)
            weighted_sum += div_score * 0.10
            total_weight += 0.10

        return weighted_sum / total_weight if total_weight > 0 else None

    def _score_positioning(self, metrics: Optional[Dict]) -> Optional[float]:
        """Score positioning metrics on 0-100 scale. Returns None if no real data."""
        if not metrics:
            return None

        weighted_sum = 0.0
        total_weight = 0.0

        # Institutional ownership: higher is better (target 50%+, cap at 95%)
        if metrics.get("institutional_ownership"):
            io = min(metrics["institutional_ownership"], 95)
            weighted_sum += io * 0.55
            total_weight += 0.55

        # Insider ownership: moderate insider ownership (5-20%) is a positive signal
        if metrics.get("insider_ownership") is not None:
            ins = metrics["insider_ownership"] * 100  # stored as decimal fraction
            if ins >= 20:
                ins_score = 100
            elif ins >= 5:
                ins_score = 60 + (ins - 5) / 15 * 40
            elif ins >= 1:
                ins_score = 40 + (ins - 1) / 4 * 20
            else:
                ins_score = ins * 40
            weighted_sum += min(100, ins_score) * 0.20
            total_weight += 0.20

        # Short interest: lower is better (target <5%)
        if metrics.get("short_interest"):
            si = metrics["short_interest"]
            if si < 5:
                score = 100 - (si * 10)
            elif si < 15:
                score = 50 - ((si - 5) * 2)
            else:
                score = 30
            weighted_sum += max(0, min(100, score)) * 0.25
            total_weight += 0.25

        return weighted_sum / total_weight if total_weight > 0 else None

    def _score_stability(self, metrics: Optional[Dict]) -> Optional[float]:
        """Score stability metrics on 0-100 scale. Returns None if no real data.

        Uses 12-month volatility (primary), beta vs market (secondary),
        and debt-to-assets (tertiary solvency signal).
        """
        if not metrics:
            return None

        weighted_sum = 0.0
        total_weight = 0.0

        # 12-month (252-day) annualized volatility: lower is better
        # Swing traders can tolerate moderate volatility; penalty starts above 25%
        if metrics.get("volatility_252d") and metrics["volatility_252d"] > 0:
            vol = metrics["volatility_252d"]
            if vol <= 0.15:
                vol_score = 100
            elif vol <= 0.30:
                vol_score = 100 - ((vol - 0.15) / 0.15) * 50   # 100→50 in [15%,30%]
            elif vol <= 0.60:
                vol_score = 50 - ((vol - 0.30) / 0.30) * 40    # 50→10 in [30%,60%]
            else:
                vol_score = max(0, 10 - (vol - 0.60) * 20)
            weighted_sum += vol_score * 0.50
            total_weight += 0.50

        # 60-day volatility: recent stability proxy (higher weight than 12m for swing traders)
        if metrics.get("volatility_60d") and metrics["volatility_60d"] > 0:
            vol60 = metrics["volatility_60d"]
            if vol60 <= 0.15:
                v60_score = 100
            elif vol60 <= 0.30:
                v60_score = 100 - ((vol60 - 0.15) / 0.15) * 50
            elif vol60 <= 0.60:
                v60_score = 50 - ((vol60 - 0.30) / 0.30) * 40
            else:
                v60_score = max(0, 10 - (vol60 - 0.60) * 20)
            weighted_sum += v60_score * 0.25
            total_weight += 0.25

        # Beta: close to 1.0 is best, target 0.8-1.2 for market-correlated swing trading
        if metrics.get("beta") and metrics["beta"] > 0:
            beta = metrics["beta"]
            diff = min(abs(beta - 1.0), 2.0)
            beta_score = max(0, 100 - (diff * 50))
            weighted_sum += beta_score * 0.15
            total_weight += 0.15

        # Debt-to-assets: lower is better (target < 0.5)
        if metrics.get("debt_to_assets") is not None and metrics["debt_to_assets"] >= 0:
            dta = min(metrics["debt_to_assets"], 1.0)
            dta_score = max(0, 100 - (dta * 100))
            weighted_sum += dta_score * 0.10
            total_weight += 0.10

        return weighted_sum / total_weight if total_weight > 0 else None

    def _score_momentum(self, metrics: Optional[Dict]) -> Optional[float]:
        """Score momentum metrics on 0-100 scale. Returns None if no real data.

        Weights favor recent momentum (1m/3m) over longer-term (12m) for swing trading.
        Normalizes by total weight of available timeframes so partial data doesn't
        deflate the score.
        """
        if not metrics:
            return None

        # Named weights â€" recent timeframes matter more for swing trading
        WEIGHTS = {
            "momentum_1m": 0.30,
            "momentum_3m": 0.30,
            "momentum_6m": 0.25,
            "momentum_12m": 0.15,
        }

        weighted_sum = 0.0
        total_weight = 0.0
        for key, w in WEIGHTS.items():
            if metrics.get(key):
                weighted_sum += self._pct_to_score(metrics[key]) * w
                total_weight += w

        return weighted_sum / total_weight if total_weight > 0 else None

    @staticmethod
    def _pct_to_score(pct_return: float) -> float:
        """Convert percentage return to 0-100 score."""
        # -20% = 0, 0% = 50, +20% = 100
        # Clamp to 0-100 range
        score = 50 + (pct_return / 0.4)
        return max(0, min(100, score))

    def update_rs_percentiles(self):
        """Batch pass: rank all stocks by momentum_score and write true RS percentile.

        Uses PERCENT_RANK() so a stock scoring higher than 90% of peers gets rs_percentile=90.
        Must run after all per-symbol scores are loaded.
        """
        try:
            with DatabaseContext("write") as cur:
                cur.execute("""
                    UPDATE stock_scores ss
                    SET rs_percentile = ranked.pct
                    FROM (
                        SELECT symbol,
                               ROUND(
                                   (PERCENT_RANK() OVER (ORDER BY momentum_score))::NUMERIC * 100,
                                   2
                               ) AS pct
                        FROM stock_scores
                    ) ranked
                    WHERE ss.symbol = ranked.symbol
                """)
            logger.info("RS percentiles updated via batch rank")
        except Exception as e:
            logger.warning(f"RS percentile batch update failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="Load stock scores")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument(
        "--parallelism",
        type=int,
        default=get_default_parallelism("stock_scores"),
        help="Parallel workers",
    )
    args = parser.parse_args()

    try:
        all_symbols = (
            args.symbols.split(",")
            if args.symbols
            else get_active_symbols(timeout_secs=60)
        )
        # Filter out ETFs from both sources (stock_symbols.etf column and etf_symbols table)
        # This ensures ETFs are excluded even if etf_symbols table is unpopulated
        with DatabaseContext("read") as cur:
            cur.execute("""
                SELECT symbol FROM stock_symbols WHERE COALESCE(etf, 'N') = 'Y'
                UNION
                SELECT symbol FROM etf_symbols
            """)
            etf_symbol_set = {row[0] for row in cur.fetchall()}
        symbols = [s for s in all_symbols if s not in etf_symbol_set]
        logger.info(
            f"Filtering out {len(all_symbols) - len(symbols)} ETFs from {len(all_symbols)} total symbols"
        )

        loader = StockScoresLoader()
        stats = loader.run(symbols, parallelism=args.parallelism)
        logger.info("Stock scores load completed")

        fail_rate = stats.get("symbols_failed", 0) / max(len(symbols), 1)
        if fail_rate > 0.05:
            logger.error(f"Too many failures: {stats['symbols_failed']}/{len(symbols)}")
            return 1

        loader.update_rs_percentiles()
        return 0
    except Exception as e:
        logger.error(f"Stock scores load failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
