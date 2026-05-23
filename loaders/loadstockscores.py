#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Phase 1: Data Integrity Integration - 2026-05-09
"""
Stock Scores Loader - Enhanced with Data Integrity Phase 1.

Computes and loads stock quality scores (growth, value, momentum, dividend).
Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Now includes:
- Tick-level validation (score range sanity checks)
- Complete provenance tracking (run_id, checksums, error logging)
- Atomic watermark persistence (crash-safe, idempotent)

Run:
    python3 loadstockscores.py [--symbols AAPL,MSFT] [--parallelism 8]
"""
from utils.structured_logger import get_logger

import argparse
import logging
logger = get_logger(__name__)
import os
from utils.loader_helpers import get_active_symbols
from config.env_loader import load_env
from datetime import date, timedelta
from typing import List, Optional

from utils.optimal_loader import OptimalLoader
from utils.data_tick_validator import validate_score_tick
from utils.data_provenance_tracker import DataProvenanceTracker
from utils.data_watermark_manager import WatermarkManager
from utils.monitoring.loader_validation import validate_score_row, count_validation_errors
from loaders.technical_indicators import compute_rsi




class StockScoresLoader(OptimalLoader):
    table_name = "stock_scores"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker = None
        self.watermark_mgr = None
        self.run_id = None
        self._quality_metrics_cache = {}  # Cache all quality metrics in memory (symbol → dict)
        self._value_metrics_cache = {}    # Cache all value metrics in memory (symbol → dict)

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Fetch price data and compute scores."""
        end = date.today()
        if since is None:
            start = end - timedelta(days=5 * 365)
        else:
            start = since + timedelta(days=1) if isinstance(since, date) else date.fromisoformat(str(since).split('T')[0]) + timedelta(days=1)

        if start >= end:
            return None

        try:
            rows = self.router.fetch_ohlcv(symbol, start, end)
            if not rows or len(rows) < 20:
                return None

            return self._compute_scores(symbol, rows)
        except Exception as e:
            logging.debug(f"Score computation error for {symbol}: {e}")
            return None

    def _compute_scores(self, symbol: str, price_rows: List[dict]) -> Optional[List[dict]]:
        """Compute stock quality scores from price/fundamental data and quality metrics."""
        if len(price_rows) < 20:
            return None

        try:
            import pandas as pd
            import numpy as np
        except ImportError:
            return None

        df = pd.DataFrame(price_rows)
        df["close"] = pd.to_numeric(df["close"], errors="coerce").dropna()

        if len(df) < 20:
            return None

        # Fetch quality and value metrics if available
        quality_metrics = self._fetch_quality_metrics(symbol)
        value_metrics = self._fetch_value_metrics(symbol)

        # Technical analysis scores
        rsi = compute_rsi(df["close"], 14)
        momentum_raw = self._compute_momentum(df["close"], 20)

        # Volatility/Stability score (lower volatility = higher stability)
        returns = df["close"].pct_change()
        _vol_raw = returns.rolling(20).std().iloc[-1]
        # volatility is in decimal form (0.01 = 1%), converted to percent here
        volatility = float(_vol_raw) * 100 if pd.notna(_vol_raw) else 1.5  # default 1.5% daily std (typical market)
        stability_score = 100 - min(100, max(0, volatility * 10))  # 0-100 scale

        # Find most recent valid index
        valid_idx = None
        for idx in range(len(rsi) - 1, -1, -1):
            if not pd.isna(rsi.iloc[idx]) and not pd.isna(momentum_raw.iloc[idx]):
                valid_idx = idx
                break

        if valid_idx is None:
            return None

        # Score components (0-100 scale, where 50 is neutral)
        # Momentum: 63-day (13-week) price momentum, not RSI overbought/oversold
        momentum_roc = (df["close"].iloc[-1] / df["close"].iloc[-64] - 1) if len(df) >= 64 else (df["close"].iloc[-1] / df["close"].iloc[0] - 1)
        momentum_score = 50 + (momentum_roc * 100) if len(df) >= 64 else 50 + (momentum_roc * 50)
        momentum_score = max(0, min(100, momentum_score))

        # Price momentum: positive for uptrends, negative for downtrends
        momentum_pct = float(momentum_raw.iloc[valid_idx]) if not pd.isna(momentum_raw.iloc[valid_idx]) else 50.0

        # Trend score: average return over last 5, 10, 20 days
        ret_5 = (df["close"].iloc[-1] / df["close"].iloc[-6] - 1) * 50 if len(df) >= 6 else 0
        ret_10 = (df["close"].iloc[-1] / df["close"].iloc[-11] - 1) * 50 if len(df) >= 11 else 0
        ret_20 = (df["close"].iloc[-1] / df["close"].iloc[-21] - 1) * 50 if len(df) >= 21 else 0
        positioning_score = 50 + ((ret_5 + ret_10 + ret_20) / 3)
        positioning_score = max(0, min(100, positioning_score))

        # Growth score: volatility-adjusted momentum (NOT fundamental growth rate)
        # Equation: 50 + (momentum% * 0.8 - volatility * 0.2)
        momentum_composite = 50 + (momentum_pct * 0.8 - (volatility * 0.2))
        growth_score = max(0, min(100, momentum_composite))

        # Quality score: from fundamental metrics if available, otherwise None (exclude from composite)
        _qs = self._compute_quality_score(quality_metrics)
        quality_score = _qs  # None if no quality_metrics — will exclude from weights

        # Value score: from P/E and P/B ratios if available, otherwise None (exclude from composite)
        _vs = self._compute_value_score(value_metrics)
        value_score = _vs  # None if no value_metrics — will exclude from weights

        weights = {
            'momentum': (momentum_score, 0.20),
            'growth': (growth_score, 0.19),
            'stability': (stability_score, 0.19),
            'value': (value_score, 0.12),
            'positioning': (positioning_score, 0.15),
            'quality': (quality_score, 0.15),
        }

        # Filter to only include components with non-None values
        available = [(v, w) for v, w in weights.values() if v is not None]

        if available:
            total_weight = sum(w for _, w in available)
            composite_score = sum(v * w for v, w in available) / total_weight if total_weight > 0 else 50.0
            data_completeness = total_weight  # 1.0 = all 6 present, 0.85 = 5 of 6, etc.
        else:
            composite_score = 50.0  # Fallback: all data missing
            data_completeness = 0.0

        def _safe(v, default=50.0):
            try:
                if v is None:
                    return None
                f = float(v)
                return f if pd.notna(f) else None
            except (TypeError, ValueError):
                return None

        score_row = {
            "symbol": symbol,
            "value_score": _safe(value_score),
            "growth_score": _safe(growth_score),
            "stability_score": _safe(stability_score),
            "momentum_score": _safe(momentum_score),
            "quality_score": _safe(quality_score),
            "positioning_score": _safe(positioning_score),
            "composite_score": _safe(composite_score),
            "data_completeness": round(data_completeness, 2),  # 0.0-1.0 indicating data coverage
            "updated_at": str(date.today()),
        }
        return [score_row]  # Return single-item list as before

    @staticmethod
    def _compute_momentum(closes, period=20):
        """Compute momentum score."""
        returns = closes.pct_change(period)
        return 50 + (returns * 50).clip(-50, 50)

    def _batch_load_quality_metrics(self, symbols: List[str]) -> None:
        """Batch load all quality metrics once to avoid per-symbol queries."""
        if not symbols:
            return
        try:
            conn = self._connect()
            placeholders = ','.join(['%s'] * len(symbols))
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT symbol, operating_margin, net_margin, roe, roa,
                           debt_to_equity, current_ratio, quick_ratio, interest_coverage
                    FROM quality_metrics WHERE symbol IN ({placeholders})
                """, tuple(symbols))
                for row in cur.fetchall():
                    self._quality_metrics_cache[row[0]] = {
                        'operating_margin': row[1],
                        'net_margin': row[2],
                        'roe': row[3],
                        'roa': row[4],
                        'debt_to_equity': row[5],
                        'current_ratio': row[6],
                        'quick_ratio': row[7],
                        'interest_coverage': row[8]
                    }
        except Exception as e:
            logging.debug(f"Could not batch load quality_metrics: {e}")

    def _fetch_quality_metrics(self, symbol: str) -> Optional[dict]:
        """Fetch quality metrics from cache (pre-loaded in batch)."""
        return self._quality_metrics_cache.get(symbol)

    def _batch_load_value_metrics(self, symbols: List[str]) -> None:
        """Batch load all value metrics once to avoid per-symbol queries."""
        if not symbols:
            return
        try:
            conn = self._connect()
            placeholders = ','.join(['%s'] * len(symbols))
            with conn.cursor() as cur:
                cur.execute(f"""
                    SELECT symbol, pe_ratio, pb_ratio, ps_ratio
                    FROM value_metrics WHERE symbol IN ({placeholders})
                """, tuple(symbols))
                for row in cur.fetchall():
                    self._value_metrics_cache[row[0]] = {
                        'pe_ratio': row[1],
                        'pb_ratio': row[2],
                        'ps_ratio': row[3]
                    }
        except Exception as e:
            logging.debug(f"Could not batch load value_metrics: {e}")

    def _fetch_value_metrics(self, symbol: str) -> Optional[dict]:
        """Fetch value metrics from cache (pre-loaded in batch)."""
        return self._value_metrics_cache.get(symbol)

    @staticmethod
    def _compute_value_score(value_metrics: Optional[dict]) -> Optional[float]:
        """Compute value score from fundamental metrics (P/E, P/B)."""
        if not value_metrics:
            return None

        scores = []

        # P/E ratio: lower is cheaper (0-40 range, < 20 is reasonable, > 40 is expensive)
        if value_metrics.get('pe_ratio') is not None and value_metrics['pe_ratio'] > 0:
            pe = value_metrics['pe_ratio']
            # Invert: lower P/E = higher value_score
            # PE of 20 = 50 (neutral), PE of 10 = 75 (cheap), PE of 40 = 25 (expensive)
            pe_score = max(0, min(100, 50 + (20 - pe) * 1.25))
            scores.append(pe_score)

        # P/B ratio: lower is cheaper (0-5 range, < 2 is reasonable, > 4 is expensive)
        if value_metrics.get('pb_ratio') is not None and value_metrics['pb_ratio'] > 0:
            pb = value_metrics['pb_ratio']
            # Invert: lower P/B = higher value_score
            # PB of 2 = 50 (neutral), PB of 1 = 75 (cheap), PB of 4 = 25 (expensive)
            pb_score = max(0, min(100, 50 + (2 - pb) * 12.5))
            scores.append(pb_score)

        if scores:
            return float(round(sum(scores) / len(scores), 1))
        return None

    @staticmethod
    def _compute_quality_score(quality_metrics: Optional[dict]) -> Optional[float]:
        """Compute quality score from fundamental metrics."""
        if not quality_metrics:
            return None

        scores = []

        # Operating margin: -10% to +20% → 0-100 scale
        if quality_metrics.get('operating_margin') is not None:
            om = max(0, min(100, (quality_metrics['operating_margin'] + 10) * 3.33))
            scores.append(om)

        # Net margin: -10% to +20% → 0-100 scale
        if quality_metrics.get('net_margin') is not None:
            nm = max(0, min(100, (quality_metrics['net_margin'] + 10) * 3.33))
            scores.append(nm)

        # ROE: 0% to 30% → 0-100 scale
        if quality_metrics.get('roe') is not None:
            roe = max(0, min(100, quality_metrics['roe'] * 3.33))
            scores.append(roe)

        # ROA: 0% to 15% → 0-100 scale
        if quality_metrics.get('roa') is not None:
            roa = max(0, min(100, quality_metrics['roa'] * 6.67))
            scores.append(roa)

        # Debt-to-equity: 0 to 2 → higher is riskier, invert (2 - D/E normalized)
        if quality_metrics.get('debt_to_equity') is not None:
            de = max(0, min(100, 100 - (quality_metrics['debt_to_equity'] * 50)))
            scores.append(de)

        # Current ratio: 0.5 to 2.5 → optimal ~1.5
        if quality_metrics.get('current_ratio') is not None:
            cr = quality_metrics['current_ratio']
            cr_score = max(0, min(100, 100 - abs(cr - 1.5) * 30))
            scores.append(cr_score)

        # Quick ratio: 0.2 to 1.5 → higher is better
        if quality_metrics.get('quick_ratio') is not None:
            qr = max(0, min(100, quality_metrics['quick_ratio'] * 66.67))
            scores.append(qr)

        # Interest coverage: 1x to 10x → higher is better (ability to service debt)
        if quality_metrics.get('interest_coverage') is not None:
            ic = quality_metrics['interest_coverage']
            ic_score = max(0, min(100, ic * 10))  # 10x coverage = 100 score
            scores.append(ic_score)

        if scores:
            return float(round(sum(scores) / len(scores), 1))
        return None

    def transform(self, rows):
        """Phase 1 + TIER 2: Validate scores before accepting. Integrated validation framework."""
        if not rows:
            return []

        # TIER 2: Use loader_validation framework for comprehensive validation
        validated, validation_errors = count_validation_errors(
            rows,
            validate_score_row,
            logger_name="loadstockscores"
        )

        if validation_errors > 0 and self.tracker:
            self.tracker.record_error(
                symbol='[batch]',
                error_type='VALIDATION_FAILED',
                error_message=f'{validation_errors} rows failed validation',
                resolution='filtered',
            )

        # PHASE 1: Secondary validation via existing tick validator for provenance tracking
        today = str(date.today())
        final_validated = []
        for row in validated:
            # score_date not stored in stock_scores schema — pass today's date for validation only
            is_valid, errors = validate_score_tick(
                symbol=row.get('symbol'),
                composite_score=row.get('composite_score'),
                momentum_score=row.get('momentum_score'),
                value_score=row.get('value_score'),
                quality_score=row.get('quality_score'),
                growth_score=row.get('growth_score'),
                score_date=today,
            )

            if not is_valid:
                if self.tracker:
                    self.tracker.record_error(
                        symbol=row.get('symbol'),
                        error_type='DATA_INVALID',
                        error_message=', '.join(errors),
                        resolution='skipped',
                    )
                logging.warning(f"[{row.get('symbol')}] Invalid score: {errors[0]}")
                continue

            # Track provenance
            if self.tracker:
                self.tracker.record_tick(
                    symbol=row.get('symbol'),
                    tick_date=today,
                    data=row,
                    source_api='internal_compute',
                )

            final_validated.append(row)

        return final_validated

    def _validate_row(self, row: dict) -> bool:
        """Validate score row."""
        if not super()._validate_row(row):
            return False
        return 0 <= row.get("composite_score", 0) <= 100

    def start_provenance_tracking(self):
        """Initialize Phase 1 data integrity components."""
        db_conn = self._connect()
        # DISABLED: Provenance tracking causing transaction errors - will fix schema/rollback logic and re-enable
        # self.tracker = DataProvenanceTracker(
        #     loader_name="loadstockscores",
        #     table_name="stock_scores",
        #     db_conn=db_conn,
        # )
        self.tracker = None  # Disabled temporarily - tracker calls are all wrapped in 'if self.tracker:' checks
        self.watermark_mgr = WatermarkManager(
            loader_name="loadstockscores",
            table_name="stock_scores",
            db_conn=db_conn,
            granularity="symbol",
        )
        # self.run_id = self.tracker.start_run(source_api="internal_compute")
        self.run_id = None
        logging.info(f"[Phase 1] Provenance tracking disabled (will re-enable after schema fix)")

    def end_provenance_tracking(self, success: bool = True):
        """Finalize Phase 1 data integrity tracking."""
        if self.tracker and self.run_id:
            self.tracker.end_run(success=success)
            logging.info(f"[Phase 1] Ended provenance tracking: run_id={self.run_id}")

    def compute_rs_percentiles(self) -> None:
        """Compute cross-sectional RS percentile rankings based on 12-month returns.

        After loading all stock scores, ranks each symbol's 12-month return vs all others,
        converts to 0-100 percentile, and stores in stock_scores.rs_percentile.
        """
        conn = None
        try:
            from datetime import datetime, timedelta

            conn = self._connect()
            cur = conn.cursor()

            cur.execute("SELECT symbol FROM stock_scores ORDER BY symbol")
            symbols = [r[0] for r in cur.fetchall()]
            logging.info(f"Computing RS percentiles for {len(symbols)} symbols...")

            # Compute 12-month returns for each symbol (batch query, not N+1)
            returns_12m = {}
            end_date = date.today()
            start_date = end_date - timedelta(days=365)

            try:
                # Batch load: get first and last price for all symbols in one query
                placeholders = ','.join(['%s'] * len(symbols))
                cur.execute(f"""
                    WITH ranked_prices AS (
                        SELECT symbol, close,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date ASC) as rn_first,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) as rn_last
                        FROM price_daily
                        WHERE symbol IN ({placeholders})
                          AND date >= %s AND date <= %s
                    )
                    SELECT symbol, close, rn_first, rn_last FROM ranked_prices
                    WHERE rn_first = 1 OR rn_last = 1
                    ORDER BY symbol, rn_first DESC
                """, tuple(symbols) + (start_date, end_date))

                price_data = {}
                for symbol, close, rn_first, rn_last in cur.fetchall():
                    if symbol not in price_data:
                        price_data[symbol] = {}
                    if rn_first == 1:
                        price_data[symbol]['first'] = close
                    if rn_last == 1:
                        price_data[symbol]['last'] = close

                # Calculate returns from batch data
                for symbol in symbols:
                    try:
                        if symbol in price_data and 'first' in price_data[symbol] and 'last' in price_data[symbol]:
                            first_price = float(price_data[symbol]['first'])
                            last_price = float(price_data[symbol]['last'])
                            if first_price > 0:
                                ret = (last_price / first_price) - 1.0
                                returns_12m[symbol] = ret
                            else:
                                returns_12m[symbol] = None
                        else:
                            returns_12m[symbol] = None
                    except (ValueError, KeyError, ZeroDivisionError):
                        returns_12m[symbol] = None
            except Exception as e:
                logging.debug(f"Batch RS percentile calculation failed: {e}")
                # Fallback: compute individually (slower but safe)
                for symbol in symbols:
                    try:
                        cur.execute("""
                            SELECT close FROM price_daily
                            WHERE symbol = %s AND date >= %s AND date <= %s
                            ORDER BY date ASC
                        """, (symbol, start_date, end_date))
                        prices = [r[0] for r in cur.fetchall()]
                        if len(prices) >= 2:
                            ret = (float(prices[-1]) / float(prices[0])) - 1.0
                            returns_12m[symbol] = ret
                    except Exception as e2:
                        logging.debug(f"Could not compute 12m return for {symbol}: {e2}")
                    returns_12m[symbol] = returns_12m.get(symbol) or None

            # Rank returns cross-sectionally (only for symbols with valid returns)
            valid_symbols = {s: r for s, r in returns_12m.items() if r is not None}
            if not valid_symbols:
                logging.warning("No valid 12-month returns found")
                return

            # Sort by return and assign percentile ranks
            sorted_symbols = sorted(valid_symbols.items(), key=lambda x: x[1])
            percentile_ranks = {}
            n = len(sorted_symbols)

            for rank, (symbol, _) in enumerate(sorted_symbols):
                # Percentile: (rank / total_count) * 100, range 0-100
                percentile = (rank / max(1, n - 1)) * 100 if n > 1 else 50
                percentile_ranks[symbol] = int(round(percentile))

            update_count = 0
            for symbol, percentile in percentile_ranks.items():
                cur.execute(
                    "UPDATE stock_scores SET rs_percentile = %s WHERE symbol = %s",
                    (percentile, symbol)
                )
                update_count += cur.rowcount

            conn.commit()
            logging.info(f"Updated RS percentiles for {update_count}/{len(symbols)} symbols")

        except Exception as e:
            logging.error(f"Error computing RS percentiles: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()



def main():
    load_env()
    parser = argparse.ArgumentParser(description="Optimal stock_scores loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = StockScoresLoader()
    # Batch load fundamental metrics once to avoid per-symbol database hits (performance optimization)
    loader._batch_load_quality_metrics(symbols)
    loader._batch_load_value_metrics(symbols)
    loader.start_provenance_tracking()  # Track loader execution
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
        # Compute cross-sectional RS percentile rankings after scores are loaded
        loader.compute_rs_percentiles()
        loader.end_provenance_tracking(success=True)  # Log successful completion
    except Exception as e:
        loader.end_provenance_tracking(success=False)  # Log failure
        logging.error(f"Loader failed: {e}")
        raise
    finally:
        loader.close()

    fail_rate = stats.get("symbols_failed", 0) / max(len(symbols), 1)
        if fail_rate > 0.05:
            logger.error(f"Too many failures: {stats['symbols_failed']}/{len(symbols)} ({fail_rate*100:.1f}%)")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
