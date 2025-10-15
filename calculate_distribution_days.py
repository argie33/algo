#!/usr/bin/env python3
"""
Calculate Distribution Days from price_daily table
Following well-architected best practices - uses local database instead of external APIs

This script:
1. Fetches historical data from price_daily table (not yfinance)
2. Calculates IBD Distribution Days using local data
3. Updates distribution_days table with results

Author: Financial Dashboard System
Updated: 2025-01-16
"""

import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict

import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


def get_db_config():
    """Get database configuration"""
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 5432)),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", "password"),
        "dbname": os.environ.get("DB_NAME", "stocks"),
    }


def get_historical_data_from_db(conn, symbol: str, days: int = 365) -> pd.DataFrame:
    """
    Fetch historical price data from price_daily table

    Args:
        conn: Database connection
        symbol: Stock symbol
        days: Number of days to fetch

    Returns:
        DataFrame with date, close, volume columns
    """
    query = """
        SELECT
            date,
            close,
            volume
        FROM price_daily
        WHERE symbol = %s
        AND date >= CURRENT_DATE - INTERVAL '%s days'
        ORDER BY date ASC
    """

    try:
        df = pd.read_sql_query(query, conn, params=(symbol, days))

        if df.empty:
            logging.warning(f"No historical data found for {symbol}")
            return pd.DataFrame()

        # Convert to format expected by calculation (date as index, Close and Volume columns)
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        df = df.rename(columns={'close': 'Close', 'volume': 'Volume'})

        logging.info(f"Fetched {len(df)} days of data for {symbol} from price_daily table")
        return df

    except Exception as e:
        logging.error(f"Error fetching data for {symbol}: {e}")
        return pd.DataFrame()


def calculate_distribution_days(hist: pd.DataFrame, lookback_days: int = 25) -> Dict[str, Any]:
    """
    Calculate IBD Distribution Days over specified lookback period.

    IBD Distribution Day Criteria:
    - Major index down 0.2% or more
    - Volume higher than previous day
    - Track over 25 trading days
    - Remove if: (1) older than 25 days, or (2) index rallies 6%+ from distribution day close

    Args:
        hist: Historical price/volume data (DataFrame with Close and Volume columns)
        lookback_days: Number of trading days to look back (default 25)

    Returns:
        Dict with distribution day count, details, and signal status
    """
    if hist.empty or len(hist) < 2:
        return {"count": 0, "days": [], "signal": "INSUFFICIENT_DATA", "lookback_period": lookback_days}

    distribution_days = []

    # Look back through the specified period
    for i in range(1, min(len(hist), lookback_days + 1)):
        current_idx = len(hist) - i
        prev_idx = current_idx - 1

        if prev_idx < 0:
            break

        # Calculate price change percentage
        current_close = hist["Close"].iloc[current_idx]
        prev_close = hist["Close"].iloc[prev_idx]
        price_change_pct = (current_close / prev_close - 1) * 100

        # Check volume comparison
        current_volume = hist["Volume"].iloc[current_idx] if "Volume" in hist.columns else 0
        prev_volume = hist["Volume"].iloc[prev_idx] if "Volume" in hist.columns else 0
        volume_higher = current_volume > prev_volume

        # IBD criteria: down 0.2%+ on higher volume
        if price_change_pct <= -0.2 and volume_higher and current_volume > 0:
            dist_day = {
                "date": hist.index[current_idx].strftime("%Y-%m-%d"),
                "close": float(current_close),
                "change_pct": float(price_change_pct),
                "volume": int(current_volume),
                "volume_ratio": float(current_volume / prev_volume) if prev_volume > 0 else 1.0,
                "days_ago": i - 1,
            }

            # Check if this distribution day should be removed due to 6%+ rally
            # Look forward from distribution day to see if there was a 6%+ rally
            rally_occurred = False
            for j in range(current_idx + 1, len(hist)):
                if (hist["Close"].iloc[j] / current_close - 1) >= 0.06:
                    rally_occurred = True
                    break

            if not rally_occurred:
                distribution_days.append(dist_day)

    # Determine signal based on distribution day count
    count = len(distribution_days)
    if count >= 6:
        signal = "UNDER_PRESSURE"
    elif count >= 5:
        signal = "CAUTION"
    elif count >= 3:
        signal = "ELEVATED"
    else:
        signal = "NORMAL"

    return {
        "count": count,
        "days": distribution_days,
        "signal": signal,
        "lookback_period": lookback_days,
    }


def save_distribution_days_to_db(conn, cur, symbol: str, dist_data: Dict[str, Any]):
    """
    Save distribution days to database

    Args:
        conn: Database connection
        cur: Database cursor
        symbol: Stock symbol
        dist_data: Distribution days calculation result
    """
    try:
        signal = dist_data.get("signal", "UNKNOWN")

        # Clear old distribution days for this symbol
        cur.execute("DELETE FROM distribution_days WHERE symbol = %s", (symbol,))

        # Insert each distribution day
        inserted_count = 0
        for day in dist_data.get("days", []):
            try:
                cur.execute(
                    """
                    INSERT INTO distribution_days
                    (symbol, date, close_price, change_pct, volume, volume_ratio, days_ago, signal)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        close_price = EXCLUDED.close_price,
                        change_pct = EXCLUDED.change_pct,
                        volume = EXCLUDED.volume,
                        volume_ratio = EXCLUDED.volume_ratio,
                        days_ago = EXCLUDED.days_ago,
                        signal = EXCLUDED.signal
                    """,
                    (
                        symbol,
                        day.get("date"),
                        day.get("close"),
                        day.get("change_pct"),
                        day.get("volume"),
                        day.get("volume_ratio"),
                        day.get("days_ago"),
                        signal,
                    ),
                )
                inserted_count += 1
            except Exception as e:
                logging.error(f"Error inserting day {day.get('date')} for {symbol}: {e}")

        conn.commit()
        logging.info(f"Saved {inserted_count} distribution days for {symbol} (Signal: {signal})")

    except Exception as e:
        logging.error(f"Error saving distribution days for {symbol}: {e}")
        conn.rollback()


def main():
    """Main execution function"""
    logging.info("=" * 60)
    logging.info("Distribution Days Calculator - Using price_daily table")
    logging.info("=" * 60)

    # Major indices to track
    major_indices = {
        "^GSPC": "S&P 500",
        "^IXIC": "NASDAQ Composite",
        "^DJI": "Dow Jones Industrial Average",
    }

    # Connect to database
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        dbname=cfg["dbname"],
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Process each major index
    for symbol, name in major_indices.items():
        logging.info(f"\nProcessing {name} ({symbol})...")

        try:
            # Fetch data from price_daily table (NOT from yfinance)
            hist = get_historical_data_from_db(conn, symbol, days=365)

            if hist.empty:
                logging.warning(f"Skipping {symbol} - no data in price_daily table")
                continue

            # Calculate distribution days
            dist_days = calculate_distribution_days(hist)

            # Display results
            logging.info(f"  Count: {dist_days['count']}")
            logging.info(f"  Signal: {dist_days['signal']}")
            logging.info(f"  Lookback Period: {dist_days['lookback_period']} days")

            if dist_days['days']:
                logging.info(f"  Distribution Days (most recent):")
                for i, day in enumerate(dist_days['days'][:5], 1):
                    logging.info(
                        f"    {i}. {day['date']}: {day['change_pct']:.2f}% on "
                        f"{day['volume_ratio']:.2f}x volume ({day['days_ago']} days ago)"
                    )

            # Save to database
            save_distribution_days_to_db(conn, cur, symbol, dist_days)

        except Exception as e:
            logging.error(f"Error processing {symbol}: {e}")
            conn.rollback()

    # Verify results
    logging.info("\n" + "=" * 60)
    logging.info("Verification - Distribution Days in Database")
    logging.info("=" * 60)

    for symbol, name in major_indices.items():
        cur.execute(
            """
            SELECT COUNT(*) as count, signal
            FROM distribution_days
            WHERE symbol = %s
            GROUP BY signal
            """,
            (symbol,),
        )
        result = cur.fetchone()
        if result:
            logging.info(f"{name} ({symbol}): {result['count']} days, Signal: {result['signal']}")
        else:
            logging.info(f"{name} ({symbol}): No distribution days found")

    cur.close()
    conn.close()
    logging.info("\n✅ Distribution Days calculation complete!")
    logging.info("Data source: price_daily table (local database)")


if __name__ == "__main__":
    main()
