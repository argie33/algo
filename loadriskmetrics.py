#!/usr/bin/env python3
# Risk Metrics Loader - Feeder metrics for holding risk calculation
"""
Risk Metrics Feeder Loader
Calculates base risk metrics needed for holding risk assessment.
These metrics are then used by loadstockscores.py to calculate final risk_score.

Base Metrics Calculated:
- volatility_12m_pct: 12-month annualized volatility (%)
- max_drawdown_52w_pct: Maximum drawdown from 52W high (%)
- volatility_risk_component: Downside volatility (std of negative returns only)

Data Sources:
- momentum_metrics: volatility, price vs MAs, 52W positioning
- yfinance: Historical prices (for downside volatility calculation)

Note: Beta comes from daily stock loader (via .ticker data)
Final risk_score (40% vol + 27% technical + 33% drawdown)
is calculated in loadstockscores.py, not here
"""

import concurrent.futures
import gc
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from decimal import Decimal

import boto3
import numpy as np
import psycopg2
import psycopg2.extensions
from psycopg2 import pool
from psycopg2.extras import execute_values

# Register numpy adapters
def adapt_numpy_int64(val):
    return psycopg2.extensions.AsIs(int(val))

def adapt_numpy_float64(val):
    return psycopg2.extensions.AsIs(float(val))

psycopg2.extensions.register_adapter(np.int64, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.int32, adapt_numpy_int64)
psycopg2.extensions.register_adapter(np.float64, adapt_numpy_float64)
psycopg2.extensions.register_adapter(np.float32, adapt_numpy_float64)

SCRIPT_NAME = os.path.basename(__file__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(funcName)s] %(message)s",
    stream=sys.stdout,
)

MAX_WORKERS = min(os.cpu_count() or 1, 4)
DB_POOL_MIN = 2
DB_POOL_MAX = 10


def get_db_config():
    """Fetch database credentials"""
    if os.environ.get("USE_LOCAL_DB") == "true" or not os.environ.get("DB_SECRET_ARN"):
        logging.info("Using local database configuration")
        return (
            os.environ.get("DB_USER", "postgres"),
            os.environ.get("DB_PASSWORD", "password"),
            os.environ.get("DB_HOST", "localhost"),
            int(os.environ.get("DB_PORT", "5432")),
            os.environ.get("DB_NAME", "stocks"),
        )
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])
    sec = json.loads(resp["SecretString"])
    return (sec["username"], sec["password"], sec["host"], int(sec["port"]), sec["dbname"])


def safe_numeric(value):
    """Safely convert value to float"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        if np.isnan(value) or np.isinf(value):
            return None
        return float(value)
    if isinstance(value, str):
        if value.strip() == "" or value.strip().lower() == "nan":
            return None
        try:
            return float(value)
        except ValueError:
            return None
    return None


def initialize_db():
    """Initialize database"""
    user, pwd, host, port, db = get_db_config()
    conn = psycopg2.connect(host=host, port=port, user=user, password=pwd, dbname=db)
    cursor = conn.cursor()

    # Update last_run
    cursor.execute(
        "INSERT INTO last_updated (script_name, last_run) VALUES (%s, CURRENT_TIMESTAMP) "
        "ON CONFLICT (script_name) DO UPDATE SET last_run = CURRENT_TIMESTAMP;",
        (SCRIPT_NAME,),
    )
    conn.commit()

    logging.info("Initializing risk_metrics table...")

    # Clear existing data to recalculate
    cursor.execute("DELETE FROM risk_metrics;")
    conn.commit()

    # Verify table exists with correct schema
    cursor.execute("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_name = 'risk_metrics'
    """)
    if cursor.fetchone()[0] == 0:
        logging.error("risk_metrics table not found!")
        conn.close()
        return []

    # Get symbols
    cursor.execute("SELECT symbol FROM stock_symbols WHERE (etf IS NULL OR etf != 'Y');")
    symbols = [r[0] for r in cursor.fetchall()]
    logging.info(f"Found {len(symbols)} symbols.")

    cursor.close()
    conn.close()
    return symbols


def create_connection_pool():
    """Create database connection pool"""
    user, pwd, host, port, db = get_db_config()
    return pool.ThreadedConnectionPool(
        DB_POOL_MIN, DB_POOL_MAX, host=host, port=port, user=user, password=pwd, dbname=db
    )


def calculate_downside_volatility(symbol):
    """Calculate downside volatility (only negative returns)"""
    try:
        # Get 1 year of daily data
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=365)

        data = yf.download(symbol, start=start_date, end=end_date, progress=False)
        if data is None or len(data) < 20:
            return None

        # Calculate daily returns
        close_col = 'Adj Close' if 'Adj Close' in data.columns else 'Close'
        returns = data[close_col].pct_change().dropna()

        # Filter for only negative returns
        downside_returns = returns[returns < 0]

        if len(downside_returns) < 20:
            return None

        # Calculate downside volatility (std of negative returns)
        downside_vol = downside_returns.std()

        # Annualize: multiply by sqrt(252 trading days)
        annualized_downside_vol = downside_vol * np.sqrt(252) * 100

        return safe_numeric(float(annualized_downside_vol))
    except Exception as e:
        logging.debug(f"Downside volatility calc failed for {symbol}: {e}")
        return None


def process_symbol(symbol, conn_pool):
    """Calculate and store base risk metrics for a symbol"""
    try:
        conn = conn_pool.getconn()
        cursor = conn.cursor()

        current_date = datetime.now().date()

        # Get volatility and technical data
        cursor.execute("""
            SELECT volatility_12m, sma_50, sma_200, current_price, high_52w
            FROM momentum_metrics
            WHERE symbol = %s
            ORDER BY date DESC LIMIT 1
        """, (symbol,))
        mom_data = cursor.fetchone()

        if not mom_data:
            conn_pool.putconn(conn)
            return 0

        volatility_12m = safe_numeric(mom_data[0])
        sma_50 = safe_numeric(mom_data[1])
        sma_200 = safe_numeric(mom_data[2])
        current_price = safe_numeric(mom_data[3])
        high_52w = safe_numeric(mom_data[4])

        # Calculate base metrics ONLY - no scoring here
        # These will be used by loadstockscores.py to calculate final risk_score

        # Base Metric 1: Volatility (12-month annualized)
        volatility_metric = volatility_12m  # Store as-is

        # Base Metric 2: Drawdown (52W High)
        drawdown_metric = None
        if high_52w and current_price and high_52w > 0:
            drawdown_metric = ((high_52w - current_price) / high_52w) * 100

        # Base Metric 3: Downside Volatility (only negative returns)
        downside_vol_metric = calculate_downside_volatility(symbol)

        # Note: Beta comes from daily stock loader (as per requirements)
        # Not fetching here to avoid yfinance rate limiting

        # Store the base metrics
        if volatility_metric is not None or drawdown_metric is not None or downside_vol_metric is not None:
            cursor.execute(
                """
                INSERT INTO risk_metrics
                (symbol, date, volatility_12m_pct, max_drawdown_52w_pct, volatility_risk_component)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (symbol, date) DO UPDATE SET
                    volatility_12m_pct = EXCLUDED.volatility_12m_pct,
                    max_drawdown_52w_pct = EXCLUDED.max_drawdown_52w_pct,
                    volatility_risk_component = EXCLUDED.volatility_risk_component,
                    fetched_at = CURRENT_TIMESTAMP
                """,
                (symbol, current_date, volatility_metric, drawdown_metric, downside_vol_metric),
            )
            conn.commit()
            details = []
            if volatility_metric is not None:
                details.append(f"Vol {volatility_metric:.1f}%")
            if drawdown_metric is not None:
                details.append(f"DD {drawdown_metric:.1f}%")
            if downside_vol_metric is not None:
                details.append(f"DnVol {downside_vol_metric:.1f}%")
            logging.info(f"✅ {symbol}: {', '.join(details)}")
        else:
            logging.info(f"⚠️  {symbol}: Insufficient data")

        conn_pool.putconn(conn)
        return 1

    except Exception as e:
        logging.error(f"❌ Error processing {symbol}: {e}")
        try:
            conn_pool.putconn(conn)
        except:
            pass
        return 0


def main():
    """Main execution"""
    start_time = time.time()
    logging.info("=" * 80)
    logging.info("Risk Metrics Feeder Loader")
    logging.info("=" * 80)
    logging.info("Calculating Base Risk Metrics Only:")
    logging.info("  • volatility_12m_pct (12-month annualized volatility)")
    logging.info("  • max_drawdown_52w_pct (drawdown from 52W high)")
    logging.info("  • Technical positioning inputs (price vs MAs)")
    logging.info("")
    logging.info("Final risk_score (40% vol + 27% tech + 33% drawdown)")
    logging.info("will be calculated in loadstockscores.py")
    logging.info("=" * 80)

    symbols = initialize_db()
    if not symbols:
        logging.error("No symbols found!")
        return

    conn_pool = create_connection_pool()
    total_records = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_symbol, sym, conn_pool): sym for sym in symbols}
        for future in concurrent.futures.as_completed(futures):
            try:
                total_records += future.result()
            except Exception as e:
                logging.error(f"Executor error: {e}")

    conn_pool.closeall()
    gc.collect()

    elapsed = time.time() - start_time
    logging.info("=" * 80)
    logging.info(f"✅ Risk Metrics Loader Complete!")
    logging.info(f"   Records Inserted: {total_records}")
    logging.info(f"   Symbols Processed: {len(symbols)}")
    logging.info(f"   Success Rate: {(total_records/len(symbols)*100):.1f}%")
    logging.info(f"   Execution Time: {elapsed:.2f}s")
    logging.info("=" * 80)


if __name__ == "__main__":
    main()
