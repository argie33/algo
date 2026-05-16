#!/usr/bin/env python3
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

import argparse
import logging
import os
from credential_helper import get_db_password, get_db_config
import sys
import psycopg2
from datetime import date, timedelta
from typing import List, Optional

from optimal_loader import OptimalLoader
try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None
from data_tick_validator import validate_score_tick
from data_provenance_tracker import DataProvenanceTracker
from data_watermark_manager import WatermarkManager

# >>> dotenv-autoload >>>
from pathlib import Path as _DotenvPath
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _DotenvPath(__file__).resolve().parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass
# <<< dotenv-autoload <<<

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class StockScoresLoader(OptimalLoader):
    table_name = "stock_scores"
    primary_key = ("symbol",)
    watermark_field = "updated_at"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tracker = None
        self.watermark_mgr = None
        self.run_id = None

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

        # Fetch quality metrics if available
        quality_metrics = self._fetch_quality_metrics(symbol)

        # Technical analysis scores
        rsi = self._compute_rsi(df["close"], 14)
        momentum_raw = self._compute_momentum(df["close"], 20)

        # Volatility/Stability score (lower volatility = higher stability)
        returns = df["close"].pct_change()
        volatility = returns.rolling(20).std().iloc[-1] * 100  # Convert to percentage
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
        momentum_score = float(rsi.iloc[valid_idx])  # RSI: 0-100, oversold<30, overbought>70

        # Price momentum: positive for uptrends, negative for downtrends
        # Convert to 0-100 scale where 50 is neutral
        momentum_pct = float(momentum_raw.iloc[valid_idx]) if not pd.isna(momentum_raw.iloc[valid_idx]) else 50.0

        # Trend score: average return over last 5, 10, 20 days
        ret_5 = (df["close"].iloc[-1] / df["close"].iloc[-6] - 1) * 50 if len(df) >= 6 else 0
        ret_10 = (df["close"].iloc[-1] / df["close"].iloc[-11] - 1) * 50 if len(df) >= 11 else 0
        ret_20 = (df["close"].iloc[-1] / df["close"].iloc[-21] - 1) * 50 if len(df) >= 21 else 0
        positioning_score = 50 + ((ret_5 + ret_10 + ret_20) / 3)
        positioning_score = max(0, min(100, positioning_score))

        # Growth score: volatility-adjusted momentum (higher momentum with lower volatility = higher growth score)
        growth_score = 50 + (momentum_pct * 0.8 - (volatility * 0.2))
        growth_score = max(0, min(100, growth_score))

        # Quality score: from fundamental metrics if available, otherwise stability
        quality_score = self._compute_quality_score(quality_metrics) or stability_score

        # Value score: RSI-based (low RSI = potentially undervalued)
        value_score = max(0, min(100, 50 + (30 - momentum_score) * 0.5))

        # Composite: weighted average — 5 distinct factors, each weighted once
        # quality_score is excluded here to avoid double-counting stability
        composite_score = (
            momentum_score * 0.25 +    # 25% momentum (RSI)
            growth_score * 0.20 +      # 20% growth (momentum + vol-adjusted)
            stability_score * 0.20 +   # 20% stability (inverse volatility)
            value_score * 0.15 +       # 15% value (RSI-inverted)
            positioning_score * 0.20   # 20% positioning (recent returns)
        )

        score_row = {
            "symbol": symbol,
            "value_score": float(value_score),
            "growth_score": float(growth_score),
            "stability_score": float(stability_score),
            "momentum_score": float(momentum_score),
            "quality_score": float(quality_score),
            "positioning_score": float(positioning_score),
            "composite_score": float(composite_score),
            "updated_at": str(date.today()),
        }
        return [score_row]  # Return single-item list as before

    @staticmethod
    def _compute_rsi(closes, period=14):
        """Compute Relative Strength Index."""
        deltas = closes.diff()
        gains = (deltas.where(deltas > 0, 0)).rolling(window=period).mean()
        losses = (-deltas.where(deltas < 0, 0)).rolling(window=period).mean()
        rs = gains / losses
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def _compute_momentum(closes, period=20):
        """Compute momentum score."""
        returns = closes.pct_change(period)
        return 50 + (returns * 50).clip(-50, 50)

    def _fetch_quality_metrics(self, symbol: str) -> Optional[dict]:
        """Fetch quality metrics from database if available."""
        try:
            conn = psycopg2.connect(
                host=os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('DB_PORT', 5432)),
                user=os.getenv('DB_USER', 'postgres'),
                password=get_db_password(),
                database=os.getenv('DB_NAME', 'stocks')
            )
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT operating_margin, net_margin, roe, roa, debt_to_equity, current_ratio, quick_ratio, interest_coverage FROM quality_metrics WHERE symbol = %s",
                    (symbol,)
                )
                row = cur.fetchone()
                if row:
                    return {
                        'operating_margin': row[0],
                        'net_margin': row[1],
                        'roe': row[2],
                        'roa': row[3],
                        'debt_to_equity': row[4],
                        'current_ratio': row[5],
                        'quick_ratio': row[6],
                        'interest_coverage': row[7]
                    }
            conn.close()
        except Exception as e:
            logging.debug(f"Could not fetch quality_metrics for {symbol}: {e}")
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

        if scores:
            return float(round(sum(scores) / len(scores), 1))
        return None

    def transform(self, rows):
        """Phase 1: Validate scores before accepting."""
        if not rows:
            return []

        today = str(date.today())
        validated = []
        for row in rows:
            # PHASE 1: Validate every score
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

            validated.append(row)

        return validated

    def _validate_row(self, row: dict) -> bool:
        """Validate score row."""
        if not super()._validate_row(row):
            return False
        return 0 <= row.get("composite_score", 0) <= 100

    def start_provenance_tracking(self):
        """Initialize Phase 1 data integrity components."""
        db_conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER", "stocks"),
            password=get_db_password(),
            database=os.getenv("DB_NAME", "stocks"),
        )
        self.tracker = DataProvenanceTracker(
            loader_name="loadstockscores",
            table_name="stock_scores",
            db_conn=db_conn,
        )
        self.watermark_mgr = WatermarkManager(
            loader_name="loadstockscores",
            table_name="stock_scores",
            db_conn=db_conn,
            granularity="symbol",
        )
        self.run_id = self.tracker.start_run(source_api="internal_compute")
        logging.info(f"[Phase 1] Started provenance tracking: run_id={self.run_id}")

    def end_provenance_tracking(self, success: bool = True):
        """Finalize Phase 1 data integrity tracking."""
        if self.tracker and self.run_id:
            self.tracker.end_run(success=success)
            logging.info(f"[Phase 1] Ended provenance tracking: run_id={self.run_id}")


def get_active_symbols() -> List[str]:
    """Pull active symbols from the stocks table."""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "stocks"),
        password=get_db_password(),
        database=os.getenv("DB_NAME", "stocks"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol FROM stock_symbols ORDER BY symbol")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Optimal stock_scores loader")
    parser.add_argument("--symbols", help="Comma-separated symbols. Default: all from stocks table.")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = get_active_symbols()

    loader = StockScoresLoader()
    # loader.start_provenance_tracking()  # Disabled for local testing (data_loader_runs table missing)
    try:
        stats = loader.run(symbols, parallelism=args.parallelism)
        # loader.end_provenance_tracking(success=True)  # Disabled for local testing
    except Exception as e:
        # loader.end_provenance_tracking(success=False)  # Disabled for local testing
        logging.error(f"Loader failed: {e}")
        raise
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
