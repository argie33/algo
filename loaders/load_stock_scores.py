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
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
from datetime import date, timedelta
from typing import List, Optional, Dict
import logging

from utils.structured_logger import get_logger
from utils.loader_helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader
from utils.db_connection import get_db_connection

logger = get_logger(__name__)


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
            conn = get_db_connection()
            cur = conn.cursor()

            # Fetch all available metrics for this symbol
            quality = self._get_quality_metrics(cur, symbol)
            growth = self._get_growth_metrics(cur, symbol)
            value = self._get_value_metrics(cur, symbol)
            positioning = self._get_positioning_metrics(cur, symbol)
            stability = self._get_stability_metrics(cur, symbol)
            momentum = self._get_momentum_metrics(cur, symbol)

            cur.close()
            conn.close()

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
            real_scores = [s for s in [quality_score, growth_score, value_score, positioning_score, stability_score, momentum_score] if s is not None]
            data_count = len(real_scores)
            # Cap at 99.99 to fit in NUMERIC(4,2) database column
            data_completeness = min(99.99, round((data_count / 6.0) * 100, 2))

            # SKIP stocks without sufficient real data (require >=50% completeness = 3+ metrics)
            min_required_metrics = 3
            if data_count < min_required_metrics:
                logger.debug(f"{symbol}: insufficient data ({data_count}/6 metrics, {data_completeness:.0f}% complete) - skipping")
                return None

            # Compute weighted composite score with NORMALIZED weights
            # When metrics are missing, redistribute their weight to available metrics
            # instead of filling with mean (which would double-count missing factors)
            base_weights = {
                'quality': 0.25,
                'growth': 0.20,
                'value': 0.20,
                'positioning': 0.15,
                'stability': 0.12,
                'momentum': 0.08,
            }

            # Calculate real scores and identify available metrics
            real_scores = [s for s in [quality_score, growth_score, value_score, positioning_score, stability_score, momentum_score] if s is not None]
            if not real_scores:
                return None  # No real data at all

            # Build mapping of which scores are available
            score_availability = {
                'quality': quality_score is not None,
                'growth': growth_score is not None,
                'value': value_score is not None,
                'positioning': positioning_score is not None,
                'stability': stability_score is not None,
                'momentum': momentum_score is not None,
            }

            # Normalize weights: keep weights of available metrics, redistribute missing weights
            available_weight_sum = sum(w for k, w in base_weights.items() if score_availability[k])
            normalized_weights = {}
            for key, weight in base_weights.items():
                if score_availability[key]:
                    # Scale up available weights to sum to 1.0
                    normalized_weights[key] = weight / available_weight_sum if available_weight_sum > 0 else 0
                else:
                    normalized_weights[key] = 0

            # Clamp all scores to 0-100 range (only actual computed scores, not filled)
            quality_score = max(0, min(100, quality_score if quality_score is not None else 0))
            growth_score = max(0, min(100, growth_score if growth_score is not None else 0))
            value_score = max(0, min(100, value_score if value_score is not None else 0))
            positioning_score = max(0, min(100, positioning_score if positioning_score is not None else 0))
            stability_score = max(0, min(100, stability_score if stability_score is not None else 0))
            momentum_score = max(0, min(100, momentum_score if momentum_score is not None else 0))

            # Compute weighted composite with normalized weights (sums to 1.0)
            composite_score = round(
                quality_score * normalized_weights['quality'] +
                growth_score * normalized_weights['growth'] +
                value_score * normalized_weights['value'] +
                positioning_score * normalized_weights['positioning'] +
                stability_score * normalized_weights['stability'] +
                momentum_score * normalized_weights['momentum'],
                2
            )
            # Final clamp to ensure composite is in range
            composite_score = max(0, min(100, composite_score))

            # RS percentile is set to 0 here and updated in a batch pass
            # after all symbols are scored (see _update_rs_percentiles).
            rs_percentile = 0.0

            return {
                'symbol': symbol,
                'composite_score': composite_score,
                'quality_score': round(quality_score, 2),
                'growth_score': round(growth_score, 2),
                'value_score': round(value_score, 2),
                'momentum_score': round(momentum_score, 2),
                'positioning_score': round(positioning_score, 2),
                'stability_score': round(stability_score, 2),
                'rs_percentile': rs_percentile,
                'data_completeness': data_completeness,
            }

        except Exception as e:
            logger.debug(f"Stock score computation failed for {symbol}: {e}")
            return None

    def _get_quality_metrics(self, cur, symbol: str) -> Optional[Dict]:
        """Fetch quality metrics for symbol."""
        try:
            cur.execute(
                "SELECT roe, roa, operating_margin, net_margin, debt_to_equity FROM quality_metrics WHERE symbol = %s",
                (symbol,)
            )
            row = cur.fetchone()
            if row:
                return {
                    'roe': float(row[0]) if row[0] else None,
                    'roa': float(row[1]) if row[1] else None,
                    'operating_margin': float(row[2]) if row[2] else None,
                    'net_margin': float(row[3]) if row[3] else None,
                    'debt_to_equity': float(row[4]) if row[4] else None,
                }
        except Exception:
            pass
        return None

    def _get_growth_metrics(self, cur, symbol: str) -> Optional[Dict]:
        """Fetch growth metrics for symbol."""
        try:
            cur.execute(
                "SELECT revenue_growth_1y, revenue_growth_3y, eps_growth_1y, eps_growth_3y FROM growth_metrics WHERE symbol = %s",
                (symbol,)
            )
            row = cur.fetchone()
            if row:
                return {
                    'revenue_growth_1y': float(row[0]) if row[0] else None,
                    'revenue_growth_3y': float(row[1]) if row[1] else None,
                    'eps_growth_1y': float(row[2]) if row[2] else None,
                    'eps_growth_3y': float(row[3]) if row[3] else None,
                }
        except Exception:
            pass
        return None

    def _get_value_metrics(self, cur, symbol: str) -> Optional[Dict]:
        """Fetch value metrics for symbol."""
        try:
            cur.execute(
                "SELECT pe_ratio, pb_ratio, ps_ratio, dividend_yield FROM value_metrics WHERE symbol = %s",
                (symbol,)
            )
            row = cur.fetchone()
            if row:
                return {
                    'pe_ratio': float(row[0]) if row[0] else None,
                    'pb_ratio': float(row[1]) if row[1] else None,
                    'ps_ratio': float(row[2]) if row[2] else None,
                    'dividend_yield': float(row[3]) if row[3] else None,
                }
        except Exception:
            pass
        return None

    def _get_positioning_metrics(self, cur, symbol: str) -> Optional[Dict]:
        """Fetch positioning metrics for symbol."""
        try:
            cur.execute(
                "SELECT institutional_ownership, short_interest_percent FROM positioning_metrics WHERE symbol = %s",
                (symbol,)
            )
            row = cur.fetchone()
            if row:
                return {
                    'institutional_ownership': float(row[0]) if row[0] else None,
                    'short_interest': float(row[1]) if row[1] else None,
                }
        except Exception:
            pass
        return None

    def _get_stability_metrics(self, cur, symbol: str) -> Optional[Dict]:
        """Fetch stability metrics for symbol."""
        try:
            cur.execute(
                "SELECT volatility_252d, beta FROM stability_metrics WHERE symbol = %s",
                (symbol,)
            )
            row = cur.fetchone()
            if row:
                return {
                    'volatility_252d': float(row[0]) if row[0] else None,
                    'beta': float(row[1]) if row[1] else None,
                }
        except Exception:
            pass
        return None

    def _get_momentum_metrics(self, cur, symbol: str) -> Optional[Dict]:
        """Fetch momentum/RS metrics for symbol using DATE-based lookups (not OFFSET).

        Uses date arithmetic to find approximate prices at 1m/3m/6m/12m ago.
        More robust than OFFSET which breaks on data gaps or different row counts.
        """
        try:
            # Get recent price performance from price_daily table using calendar date lookups
            cur.execute("""
                SELECT
                    (SELECT close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1) as current,
                    (SELECT close FROM price_daily WHERE symbol = %s AND date <= CURRENT_DATE - INTERVAL '1 month' ORDER BY date DESC LIMIT 1) as price_1m_ago,
                    (SELECT close FROM price_daily WHERE symbol = %s AND date <= CURRENT_DATE - INTERVAL '3 months' ORDER BY date DESC LIMIT 1) as price_3m_ago,
                    (SELECT close FROM price_daily WHERE symbol = %s AND date <= CURRENT_DATE - INTERVAL '6 months' ORDER BY date DESC LIMIT 1) as price_6m_ago,
                    (SELECT close FROM price_daily WHERE symbol = %s AND date <= CURRENT_DATE - INTERVAL '1 year' ORDER BY date DESC LIMIT 1) as price_12m_ago
            """, (symbol, symbol, symbol, symbol, symbol))
            row = cur.fetchone()

            if row and row[0]:
                prices = {
                    'current': float(row[0]) if row[0] else None,
                    'price_1m_ago': float(row[1]) if row[1] else None,
                    'price_3m_ago': float(row[2]) if row[2] else None,
                    'price_6m_ago': float(row[3]) if row[3] else None,
                    'price_12m_ago': float(row[4]) if row[4] else None,
                }

                # Calculate returns; None if historical price unavailable (e.g. recent IPO)
                momentum_1m = ((prices['current'] / prices['price_1m_ago'] - 1) * 100) if prices['price_1m_ago'] else None
                momentum_3m = ((prices['current'] / prices['price_3m_ago'] - 1) * 100) if prices['price_3m_ago'] else None
                momentum_6m = ((prices['current'] / prices['price_6m_ago'] - 1) * 100) if prices['price_6m_ago'] else None
                momentum_12m = ((prices['current'] / prices['price_12m_ago'] - 1) * 100) if prices['price_12m_ago'] else None

                return {
                    'momentum_1m': momentum_1m,
                    'momentum_3m': momentum_3m,
                    'momentum_6m': momentum_6m,
                    'momentum_12m': momentum_12m,
                }
        except Exception:
            pass
        return None

    def _score_quality(self, metrics: Optional[Dict]) -> Optional[float]:
        """Score quality metrics on 0-100 scale. Returns None if no real data."""
        if not metrics:
            return None

        scores = []

        # ROE: higher is better (target 15%+)
        if metrics.get('roe'):
            roe = min(metrics['roe'], 30)  # Cap at 30%
            scores.append(min(100, (roe / 30) * 100))

        # Operating margin: higher is better (target 10%+)
        if metrics.get('operating_margin'):
            om = min(metrics['operating_margin'], 20)
            scores.append(min(100, (om / 20) * 100))

        # Debt-to-equity: lower is better (target <1.0)
        if metrics.get('debt_to_equity'):
            de = min(metrics['debt_to_equity'], 5)  # Cap at 5.0 to prevent extreme negatives
            if de > 0:
                score = max(0, 100 - (de * 20))
                scores.append(min(100, score))

        return sum(scores) / len(scores) if scores else None

    def _score_growth(self, metrics: Optional[Dict]) -> Optional[float]:
        """Score growth metrics on 0-100 scale. Returns None if no real data."""
        if not metrics:
            return None

        scores = []

        # 1-year EPS growth: target 10%+
        if metrics.get('eps_growth_1y'):
            eps = min(metrics['eps_growth_1y'], 50)
            scores.append(min(100, (eps / 50) * 100))

        # 1-year revenue growth: target 5%+
        if metrics.get('revenue_growth_1y'):
            rev = min(metrics['revenue_growth_1y'], 30)
            scores.append(min(100, (rev / 30) * 100))

        return sum(scores) / len(scores) if scores else None

    def _score_value(self, metrics: Optional[Dict]) -> Optional[float]:
        """Score value metrics on 0-100 scale. Returns None if no real data."""
        if not metrics:
            return None

        scores = []

        # P/E ratio: peak zone 15-25 for growth momentum stocks
        # Continuous piecewise linear — no score jumps at breakpoints
        if metrics.get('pe_ratio') and metrics['pe_ratio'] > 0:
            pe = metrics['pe_ratio']
            if pe <= 10:
                pe_score = 40 + pe * 2          # 40 at pe=0 → 60 at pe=10
            elif pe <= 20:
                pe_score = 60 + (pe - 10) * 4  # 60 at pe=10 → 100 at pe=20
            elif pe <= 40:
                pe_score = 100 - (pe - 20) * 2.5  # 100 at pe=20 → 50 at pe=40
            else:
                pe_score = max(0, 50 - (pe - 40) * 1.25)  # 50 at pe=40 → 0 at pe=80
            scores.append(pe_score)

        # Dividend yield: higher is better (target 2%+)
        # yfinance returns dividendYield as decimal fraction (0.0229 = 2.29%); convert to percent
        if metrics.get('dividend_yield'):
            div = min(metrics['dividend_yield'] * 100, 5)  # Decimal → percent, cap at 5%
            scores.append(min(100, div * 20))

        return sum(scores) / len(scores) if scores else None

    def _score_positioning(self, metrics: Optional[Dict]) -> Optional[float]:
        """Score positioning metrics on 0-100 scale. Returns None if no real data."""
        if not metrics:
            return None

        scores = []

        # Institutional ownership: higher is better (target 50%+)
        if metrics.get('institutional_ownership'):
            io = min(metrics['institutional_ownership'], 100)
            scores.append(io)

        # Short interest: lower is better (target <5%)
        # Use piecewise scoring instead of linear (which was too harsh)
        if metrics.get('short_interest'):
            si = metrics['short_interest']
            if si < 5:
                # Normal range: -10 points per 1% short
                score = 100 - (si * 10)
            elif si < 15:
                # High range (5-15%): slower penalty (-2 per 1% above 5%)
                score = 50 - ((si - 5) * 2)
            else:
                # Very high (15%+): floor at 30 (possible contrarian value, not zero)
                score = 30
            scores.append(max(0, min(100, score)))

        return sum(scores) / len(scores) if scores else None

    def _score_stability(self, metrics: Optional[Dict]) -> Optional[float]:
        """Score stability metrics on 0-100 scale. Returns None if no real data."""
        if not metrics:
            return None

        scores = []

        # Volatility: lower is better (inverse relationship)
        if metrics.get('volatility_252d'):
            vol = min(metrics['volatility_252d'], 0.3)  # Cap at 30%
            # 30%+ volatility is high, <15% is low
            if vol > 0:
                score = max(0, 100 - (vol / 0.3 * 100))
                scores.append(min(100, score))

        # Beta: close to 1.0 is best, target 0.8-1.2
        if metrics.get('beta'):
            beta = metrics['beta']
            if beta > 0:
                diff = min(abs(beta - 1.0), 2.0)  # Cap difference at 2.0
                score = max(0, 100 - (diff * 50))
                scores.append(min(100, score))

        return sum(scores) / len(scores) if scores else None

    def _score_momentum(self, metrics: Optional[Dict]) -> Optional[float]:
        """Score momentum metrics on 0-100 scale. Returns None if no real data.

        Weights favor recent momentum (1m/3m) over longer-term (12m) for swing trading.
        Normalizes by total weight of available timeframes so partial data doesn't
        deflate the score.
        """
        if not metrics:
            return None

        # Named weights — recent timeframes matter more for swing trading
        WEIGHTS = {'momentum_1m': 0.30, 'momentum_3m': 0.30, 'momentum_6m': 0.25, 'momentum_12m': 0.15}

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
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
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
                conn.commit()
            logger.info("RS percentiles updated via batch rank")
        except Exception as e:
            logger.warning(f"RS percentile batch update failed: {e}")
        finally:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description="Load stock scores")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--parallelism", type=int, default=8, help="Parallel workers")
    args = parser.parse_args()

    try:
        symbols = (args.symbols.split(",") if args.symbols else get_active_symbols(timeout_secs=60))
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
