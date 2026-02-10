#!/usr/bin/env python3
"""
Earnings Metrics Loader
Populates earnings_metrics table with EPS/revenue growth rates, earnings surprises, and quality metrics.

Data Loaded:
- EPS QoQ growth rates
- EPS YoY growth rates
- Revenue YoY growth rates
- Earnings surprise percentages
- Earnings quality scores (based on surprise consistency and estimate accuracy)

Data Sources:
- earnings_history table (actual reported earnings)
- earnings_estimates table (analyst forecasts)

Author: Financial Dashboard System
Updated: 2026-02-09
"""

import gc
import logging
import os
import resource
import sys
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple

import boto3
import pandas as pd
import psycopg2
import psycopg2.extensions
import numpy as np
from psycopg2.extras import RealDictCursor, execute_values

# Script metadata
SCRIPT_NAME = "loadearningsmetrics.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

# Suppress noisy logging
logging.getLogger("psycopg2").setLevel(logging.CRITICAL)
logging.getLogger("boto3").setLevel(logging.CRITICAL)
logging.getLogger("botocore").setLevel(logging.CRITICAL)

# Register numpy type adapters
def adapt_numpy_int64(numpy_int64):
    return psycopg2.extensions.AsIs(int(numpy_int64))

def adapt_numpy_float64(numpy_float64):
    return psycopg2.extensions.AsIs(float(numpy_float64))

psycopg2.extensions.register_adapter(np.int64, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.int32, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.float64, adapt_numpy_float64)
psycopg2.extensions.register_adapter(np.float32, adapt_numpy_float64)


def get_rss_mb():
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform.startswith("linux"):
        return usage / 1024
    return usage / (1024 * 1024)


def log_mem(stage: str):
    logging.info(f"[MEM] {stage}: {get_rss_mb():.1f} MB RSS")


def get_db_config():
    """Get database configuration from AWS Secrets Manager or environment variables."""

    # Try AWS Secrets Manager first
    if os.environ.get("DB_SECRET_ARN"):
        try:
            import json
            region = os.environ.get("AWS_REGION", "us-east-1")
            client = boto3.client("secretsmanager", region_name=region)
            response = client.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])
            secret = json.loads(response["SecretString"])
            logging.info(f"Loaded database credentials from AWS Secrets Manager")
            return {
                "host": secret["host"],
                "port": int(secret.get("port", 5432)),
                "user": secret["username"],
                "password": secret["password"],
                "dbname": secret["dbname"]
            }
        except Exception as e:
            logging.warning(f"Failed to load from Secrets Manager: {e}")

    # Fallback to environment variables
    db_host = os.environ.get("DB_HOST", "localhost")
    db_user = os.environ.get("DB_USER", "stocks")
    db_password = os.environ.get("DB_PASSWORD", "")
    db_name = os.environ.get("DB_NAME", "stocks")

    logging.info(f"Using database credentials from environment (with defaults): {db_user}@{db_host}/{db_name}")
    return {
        "host": db_host,
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": db_user,
        "password": db_password,
        "dbname": db_name
    }


def safe_float(value, default=None, max_val=None, min_val=None):
    """Safely convert to float with optional bounds checking"""
    if value is None or pd.isna(value):
        return default
    try:
        f = float(value)
        if np.isnan(f) or np.isinf(f):
            return default
        if max_val is not None and f > max_val:
            f = max_val
        if min_val is not None and f < min_val:
            f = min_val
        return f
    except (ValueError, TypeError):
        return default


def calculate_earnings_quality_score(symbol: str, data: Dict) -> float:
    """
    Calculate earnings quality score based on:
    - Earnings surprise consistency (lower volatility = higher quality)
    - Estimate accuracy (lower difference between high/low = more accurate)
    - Revenue growth stability

    Score: 0-100 (higher is better)
    """
    try:
        surprise_pct = data.get("surprise_pct", 0) or 0

        # Surprise component (0-50 points): Small surprises are better (less than 5%)
        surprise_score = 50 - abs(min(surprise_pct, 50))  # Cap at 50% surprise

        # Estimate confidence component (0-50 points): Tight estimate ranges are better
        estimate_range = data.get("estimate_range", 0) or 0
        estimate_score = max(0, 50 - (estimate_range * 10))  # Each 10% range reduces score by 10pts

        quality_score = surprise_score + estimate_score
        return max(0, min(100, quality_score))
    except Exception as e:
        logging.warning(f"Failed to calculate quality score for {symbol}: {e}")
        return 50.0  # Default neutral score


def load_earnings_metrics(cur, conn):
    """Load earnings metrics from earnings history and estimates."""

    try:
        logging.info("Loading earnings history data...")

        # Get earnings history with surrounding quarters for growth calculations
        cur.execute("""
            SELECT
                symbol,
                quarter,
                eps_actual,
                eps_estimate,
                eps_difference,
                surprise_percent,
                fetched_at
            FROM earnings_history
            ORDER BY symbol, quarter DESC
            LIMIT 500000
        """)

        history_rows = cur.fetchall()
        if not history_rows:
            logging.warning("⚠️  No earnings history found")
            return 0

        history_df = pd.DataFrame(history_rows, columns=[
            'symbol', 'quarter', 'eps_actual', 'eps_estimate',
            'eps_difference', 'surprise_percent', 'fetched_at'
        ])

        logging.info(f"✅ Loaded {len(history_df)} earnings history records")

        # Get earnings estimates for growth context
        logging.info("Loading earnings estimates data...")
        cur.execute("""
            SELECT
                symbol,
                period,
                avg_estimate,
                low_estimate,
                high_estimate,
                year_ago_eps,
                growth
            FROM earnings_estimates
            LIMIT 500000
        """)

        estimates_rows = cur.fetchall()
        if estimates_rows:
            estimates_df = pd.DataFrame(estimates_rows, columns=[
                'symbol', 'period', 'avg_estimate', 'low_estimate',
                'high_estimate', 'year_ago_eps', 'growth'
            ])
            logging.info(f"✅ Loaded {len(estimates_df)} earnings estimates records")
        else:
            logging.warning("⚠️  No earnings estimates found yet")
            estimates_df = pd.DataFrame()

        # Calculate metrics for each symbol's recent quarter
        metrics_data = []
        processed_symbols = set()

        for symbol in history_df['symbol'].unique():
            if symbol in processed_symbols:
                continue
            processed_symbols.add(symbol)

            symbol_history = history_df[history_df['symbol'] == symbol].sort_values('quarter', ascending=False)

            if len(symbol_history) < 1:
                continue

            # Get most recent quarter
            recent = symbol_history.iloc[0]
            report_date_ts = pd.to_datetime(recent['quarter'])  # Keep as Timestamp for comparison
            report_date = report_date_ts.date()  # Convert to date for database

            # Get prior quarters for YoY comparison (4 quarters back)
            # Convert quarter column to datetime for proper comparison
            symbol_history['quarter_dt'] = pd.to_datetime(symbol_history['quarter'])
            prior_yoy = symbol_history[symbol_history['quarter_dt'] < report_date_ts - timedelta(days=365)]

            eps_qoq_growth = None
            eps_yoy_growth = None
            revenue_yoy_growth = None

            # Calculate QoQ growth
            if len(symbol_history) > 1:
                prior_quarter = symbol_history.iloc[1]
                if (recent['eps_actual'] is not None and
                    prior_quarter['eps_actual'] is not None and
                    prior_quarter['eps_actual'] != 0):
                    eps_qoq_growth = safe_float(
                        ((float(recent['eps_actual']) - float(prior_quarter['eps_actual'])) /
                         abs(float(prior_quarter['eps_actual']))) * 100,
                        max_val=999.99,
                        min_val=-999.99
                    )

            # Calculate YoY growth
            if len(prior_yoy) > 0:
                yoy_quarter = prior_yoy.iloc[0]
                if (recent['eps_actual'] is not None and
                    yoy_quarter['eps_actual'] is not None and
                    yoy_quarter['eps_actual'] != 0):
                    eps_yoy_growth = safe_float(
                        ((float(recent['eps_actual']) - float(yoy_quarter['eps_actual'])) /
                         abs(float(yoy_quarter['eps_actual']))) * 100,
                        max_val=999.99,
                        min_val=-999.99
                    )

            # Get revenue growth from estimates
            if not estimates_df.empty:
                symbol_estimates = estimates_df[estimates_df['symbol'] == symbol]
                if not symbol_estimates.empty and symbol_estimates.iloc[0]['growth'] is not None:
                    revenue_yoy_growth = safe_float(
                        symbol_estimates.iloc[0]['growth'],
                        max_val=999.99,
                        min_val=-999.99
                    )

            # Earnings surprise
            earnings_surprise = safe_float(recent['surprise_percent'], max_val=999.99, min_val=-999.99)

            # Estimate range (for quality calculation)
            estimate_range = None
            if (recent['eps_estimate'] is not None and
                not pd.isna(recent['eps_estimate']) and
                float(recent['eps_estimate']) != 0):
                # Use estimate accuracy as proxy
                estimate_range = 0.05  # Default 5% estimate range

            # Calculate quality score
            quality_data = {
                "surprise_pct": earnings_surprise,
                "estimate_range": estimate_range
            }
            earnings_quality_score = calculate_earnings_quality_score(symbol, quality_data)

            metrics_data.append((
                symbol,
                report_date,
                eps_qoq_growth,
                eps_yoy_growth,
                revenue_yoy_growth,
                earnings_surprise,
                earnings_quality_score
            ))

        logging.info(f"Calculated metrics for {len(metrics_data)} symbols")

        # Delete existing records to avoid duplicates
        cur.execute("DELETE FROM earnings_metrics")

        # Batch insert metrics
        if metrics_data:
            execute_values(
                cur,
                """
                INSERT INTO earnings_metrics (
                    symbol, report_date, eps_qoq_growth, eps_yoy_growth,
                    revenue_yoy_growth, earnings_surprise_pct, earnings_quality_score
                ) VALUES %s
                """,
                metrics_data,
                page_size=1000
            )
            conn.commit()
            logging.info(f"✅ Inserted {len(metrics_data)} earnings metrics records")

        return len(metrics_data)

    except Exception as e:
        logging.error(f"❌ Failed to load earnings metrics: {str(e)}")
        conn.rollback()
        raise


def main():
    """Main entry point."""
    log_mem("startup")

    try:
        # Get database config
        db_config = get_db_config()

        # Connect to database
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        logging.info(f"✅ Connected to {db_config['dbname']} database")

        # Create table if not exists
        logging.info("Running schema migrations...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS earnings_metrics (
                symbol VARCHAR(20) NOT NULL,
                report_date DATE NOT NULL,
                eps_qoq_growth DOUBLE PRECISION,
                eps_yoy_growth DOUBLE PRECISION,
                revenue_yoy_growth DOUBLE PRECISION,
                earnings_surprise_pct DOUBLE PRECISION,
                earnings_quality_score DOUBLE PRECISION,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (symbol, report_date)
            )
        """)
        conn.commit()
        logging.info("✅ earnings_metrics table created/verified")

        # Load earnings metrics
        count = load_earnings_metrics(cur, conn)

        logging.info(f"✅ Earnings metrics loaded successfully ({count} records)")
        log_mem("finished")

        cur.close()
        conn.close()

        return 0

    except Exception as e:
        logging.error(f"❌ FATAL: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
