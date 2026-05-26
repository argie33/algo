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

from config.env_loader import load_env
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
        """Compute composite stock score from available metrics.

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

            # Compute individual factor scores (0-100)
            quality_score = self._score_quality(quality)
            growth_score = self._score_growth(growth)
            value_score = self._score_value(value)
            positioning_score = self._score_positioning(positioning)
            stability_score = self._score_stability(stability)
            momentum_score = self._score_momentum(momentum)

            # Count data completeness
            data_count = sum([
                1 if quality else 0,
                1 if growth else 0,
                1 if value else 0,
                1 if positioning else 0,
                1 if stability else 0,
                1 if momentum else 0,
            ])
            data_completeness = round((data_count / 6.0) * 100, 2)

            # Compute weighted composite score (0-100)
            weights = {
                'quality': 0.25,
                'growth': 0.20,
                'value': 0.20,
                'positioning': 0.15,
                'stability': 0.12,
                'momentum': 0.08,
            }

            composite_score = round(
                quality_score * weights['quality'] +
                growth_score * weights['growth'] +
                value_score * weights['value'] +
                positioning_score * weights['positioning'] +
                stability_score * weights['stability'] +
                momentum_score * weights['momentum'],
                2
            )

            # Calculate RS percentile (dummy for now - would need full market rank)
            rs_percentile = round(momentum_score * 1.0, 2)  # Simple proxy

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
        """Fetch momentum/RS metrics for symbol."""
        try:
            # Get recent price performance from price_daily table
            cur.execute("""
                SELECT
                    (SELECT close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1) as current,
                    (SELECT close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1 OFFSET 20) as price_1m_ago,
                    (SELECT close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1 OFFSET 60) as price_3m_ago,
                    (SELECT close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1 OFFSET 126) as price_6m_ago,
                    (SELECT close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1 OFFSET 252) as price_12m_ago
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

                # Calculate returns
                momentum_1m = ((prices['current'] / prices['price_1m_ago'] - 1) * 100) if prices['price_1m_ago'] else 0
                momentum_3m = ((prices['current'] / prices['price_3m_ago'] - 1) * 100) if prices['price_3m_ago'] else 0
                momentum_6m = ((prices['current'] / prices['price_6m_ago'] - 1) * 100) if prices['price_6m_ago'] else 0
                momentum_12m = ((prices['current'] / prices['price_12m_ago'] - 1) * 100) if prices['price_12m_ago'] else 0

                return {
                    'momentum_1m': momentum_1m,
                    'momentum_3m': momentum_3m,
                    'momentum_6m': momentum_6m,
                    'momentum_12m': momentum_12m,
                }
        except Exception:
            pass
        return None

    def _score_quality(self, metrics: Optional[Dict]) -> float:
        """Score quality metrics on 0-100 scale."""
        if not metrics:
            return 50  # Default middle score

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
            de = metrics['debt_to_equity']
            if de > 0:
                scores.append(max(0, 100 - (de * 20)))

        return sum(scores) / len(scores) if scores else 50

    def _score_growth(self, metrics: Optional[Dict]) -> float:
        """Score growth metrics on 0-100 scale."""
        if not metrics:
            return 50

        scores = []

        # 1-year EPS growth: target 10%+
        if metrics.get('eps_growth_1y'):
            eps = min(metrics['eps_growth_1y'], 50)
            scores.append(min(100, (eps / 50) * 100))

        # 1-year revenue growth: target 5%+
        if metrics.get('revenue_growth_1y'):
            rev = min(metrics['revenue_growth_1y'], 30)
            scores.append(min(100, (rev / 30) * 100))

        return sum(scores) / len(scores) if scores else 50

    def _score_value(self, metrics: Optional[Dict]) -> float:
        """Score value metrics on 0-100 scale."""
        if not metrics:
            return 50

        scores = []

        # P/E ratio: target 15-25, lower is better but not too low
        if metrics.get('pe_ratio') and metrics['pe_ratio'] > 0:
            pe = metrics['pe_ratio']
            if pe < 10:
                scores.append(50 + (10 - pe) * 5)
            elif pe < 30:
                scores.append(100 - (pe - 15) * 2)
            else:
                scores.append(max(0, 100 - (pe - 30)))

        # Dividend yield: higher is better (target 2%+)
        if metrics.get('dividend_yield'):
            div = min(metrics['dividend_yield'] * 100, 5)  # Cap at 5%
            scores.append(min(100, div * 20))

        return sum(scores) / len(scores) if scores else 50

    def _score_positioning(self, metrics: Optional[Dict]) -> float:
        """Score positioning metrics on 0-100 scale."""
        if not metrics:
            return 50

        scores = []

        # Institutional ownership: higher is better (target 50%+)
        if metrics.get('institutional_ownership'):
            io = min(metrics['institutional_ownership'], 100)
            scores.append(io)

        # Short interest: lower is better (target <5%)
        if metrics.get('short_interest'):
            si = metrics['short_interest']
            scores.append(max(0, 100 - (si * 10)))

        return sum(scores) / len(scores) if scores else 50

    def _score_stability(self, metrics: Optional[Dict]) -> float:
        """Score stability metrics on 0-100 scale."""
        if not metrics:
            return 50

        scores = []

        # Volatility: lower is better (inverse relationship)
        if metrics.get('volatility_252d'):
            vol = metrics['volatility_252d']
            # 30%+ volatility is high, <15% is low
            if vol > 0:
                scores.append(max(0, 100 - (vol / 0.3 * 100)))

        # Beta: close to 1.0 is best, target 0.8-1.2
        if metrics.get('beta'):
            beta = metrics['beta']
            if beta > 0:
                diff = abs(beta - 1.0)
                scores.append(max(0, 100 - (diff * 50)))

        return sum(scores) / len(scores) if scores else 50

    def _score_momentum(self, metrics: Optional[Dict]) -> float:
        """Score momentum metrics on 0-100 scale."""
        if not metrics:
            return 50

        scores = []
        weights = [0.2, 0.2, 0.3, 0.3]  # Weight recent returns more heavily

        if metrics.get('momentum_1m'):
            scores.append(self._pct_to_score(metrics['momentum_1m']))
        if metrics.get('momentum_3m'):
            scores.append(self._pct_to_score(metrics['momentum_3m']))
        if metrics.get('momentum_6m'):
            scores.append(self._pct_to_score(metrics['momentum_6m']))
        if metrics.get('momentum_12m'):
            scores.append(self._pct_to_score(metrics['momentum_12m']))

        if scores:
            return sum(s * w for s, w in zip(scores, weights[-len(scores):]))
        return 50

    @staticmethod
    def _pct_to_score(pct_return: float) -> float:
        """Convert percentage return to 0-100 score."""
        # -20% = 0, 0% = 50, +20% = 100
        return max(0, min(100, 50 + (pct_return / 0.4)))


def main():
    load_env()
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
        return 0
    except Exception as e:
        logger.error(f"Stock scores load failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
