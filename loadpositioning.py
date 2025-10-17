#!/usr/bin/env python3
"""
Positioning Data Loader
Loads institutional holdings and positioning data from yfinance

Available data:
- Institutional holdings (top holders with % held and changes)
- Insider ownership percentages
- Short interest metrics
- Float and shares outstanding

Critical for positioning scores in ScoresDashboard
Trigger: Ensure this loader runs daily to populate positioning_metrics table

Author: Financial Dashboard System
"""

import json
import logging
import os
import sys
import time
from datetime import date, datetime
from typing import Dict, List, Optional

import pandas as pd
import psycopg2
import yfinance as yf
from psycopg2.extras import RealDictCursor, execute_values

# Script configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


def get_db_config():
    """Get database configuration - works in AWS and locally"""
    if os.environ.get("DB_SECRET_ARN"):
        import boto3
        secret_str = boto3.client("secretsmanager").get_secret_value(
            SecretId=os.environ["DB_SECRET_ARN"]
        )["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"],
        }
    else:
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", "5432")),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", "password"),
            "dbname": os.environ.get("DB_NAME", "stocks"),
        }


def safe_float(value, default=None):
    """Convert to float safely"""
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value, default=None):
    """Convert to int safely"""
    if value is None or pd.isna(value):
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def get_positioning_data(symbol: str) -> Optional[Dict]:
    """Get positioning data for a symbol from yfinance"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        if not info:
            logging.warning(f"No info data for {symbol}")
            return None

        # Get major holders summary
        major_holders = ticker.major_holders

        # Extract positioning metrics from info
        data = {
            'symbol': symbol,
            'date': date.today(),

            # Institutional ownership
            'institutional_ownership': safe_float(info.get('heldPercentInstitutions')),
            'institutional_float_held': safe_float(info.get('institutionsFloatPercentHeld')),
            'institution_count': safe_int(info.get('institutionsCount')),

            # Insider ownership
            'insider_ownership': safe_float(info.get('heldPercentInsiders')),

            # Short interest
            'shares_short': safe_int(info.get('sharesShort')),
            'shares_short_prior_month': safe_int(info.get('sharesShortPriorMonth')),
            'short_ratio': safe_float(info.get('shortRatio')),
            'short_percent_of_float': safe_float(info.get('shortPercentOfFloat')),
            'short_interest_date': info.get('dateShortInterest'),

            # Shares data
            'float_shares': safe_int(info.get('floatShares')),
            'shares_outstanding': safe_int(info.get('sharesOutstanding')),
        }

        # Calculate short interest change
        if data['shares_short'] and data['shares_short_prior_month']:
            data['short_interest_change'] = (
                (data['shares_short'] - data['shares_short_prior_month']) /
                data['shares_short_prior_month']
            )
        else:
            data['short_interest_change'] = None

        return data

    except Exception as e:
        logging.error(f"Error getting positioning data for {symbol}: {e}")
        return None


def get_institutional_holders(symbol: str) -> List[Dict]:
    """Get institutional holders for a symbol - matches existing schema"""
    try:
        ticker = yf.Ticker(symbol)
        inst_holders = ticker.institutional_holders

        if inst_holders is None or inst_holders.empty:
            return []

        holders = []
        for _, row in inst_holders.iterrows():
            # Map to existing schema: symbol, institution_type, institution_name,
            # position_size, position_change_percent, market_share, filing_date, quarter

            date_reported = row.get('Date Reported')
            if date_reported:
                # Extract quarter from date (e.g., "2024-06-30" -> "2024Q2")
                year = date_reported.year
                quarter_num = (date_reported.month - 1) // 3 + 1
                quarter = f"{year}Q{quarter_num}"
            else:
                quarter = None

            # Determine institution type from name (simple heuristic)
            inst_name = str(row.get('Holder', ''))
            if any(x in inst_name.lower() for x in ['vanguard', 'fidelity', 'blackrock', 'state street']):
                inst_type = 'MUTUAL_FUND'
            elif any(x in inst_name.lower() for x in ['berkshire', 'hedge', 'capital', 'partners']):
                inst_type = 'HEDGE_FUND'
            elif any(x in inst_name.lower() for x in ['pension', 'retirement', 'insurance']):
                inst_type = 'PENSION_FUND'
            else:
                inst_type = 'INSTITUTIONAL'

            holders.append({
                'symbol': symbol,
                'institution_type': inst_type,
                'institution_name': inst_name,
                'position_size': safe_float(row.get('Value')),  # Value in dollars
                'position_change_percent': safe_float(row.get('pctChange')) * 100 if row.get('pctChange') else None,  # Convert to percentage
                'market_share': safe_float(row.get('pctHeld')),  # Percent held as decimal
                'filing_date': date_reported,
                'quarter': quarter,
            })

        return holders

    except Exception as e:
        logging.error(f"Error getting institutional holders for {symbol}: {e}")
        return []


def get_retail_sentiment(symbol: str) -> Optional[Dict]:
    """Generate retail sentiment data from available yfinance data"""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        if not info:
            return None

        # Calculate sentiment based on available metrics
        # Use short interest, institutional ownership, and recommendations as proxies
        # NO FALLBACKS: Only use real data from yfinance

        short_pct = safe_float(info.get('shortPercentOfFloat'))
        inst_own = safe_float(info.get('heldPercentInstitutions'))
        rec_mean = safe_float(info.get('recommendationMean'))  # 1=Strong Buy, 5=Strong Sell

        # If any critical metric is missing, return None (no calculation with partial data)
        if short_pct is None or inst_own is None or rec_mean is None:
            logging.debug(f"{symbol}: Missing required sentiment data (short={short_pct}, inst={inst_own}, rec={rec_mean})")
            return None

        # Calculate bullish/bearish sentiment
        # Lower short interest = more bullish
        # Higher institutional ownership = more bullish
        # Lower recommendation mean = more bullish

        # Bullish factors
        bullish_score = 0.0
        if short_pct < 0.02:  # Low short interest
            bullish_score += 30
        elif short_pct < 0.05:
            bullish_score += 15

        if inst_own > 0.7:  # High institutional ownership
            bullish_score += 30
        elif inst_own > 0.5:
            bullish_score += 15

        if rec_mean < 2.0:  # Strong buy recommendations
            bullish_score += 40
        elif rec_mean < 2.5:
            bullish_score += 20

        # Bearish factors
        bearish_score = 0.0
        if short_pct > 0.10:  # High short interest
            bearish_score += 40
        elif short_pct > 0.05:
            bearish_score += 20

        if rec_mean > 3.5:  # Sell recommendations
            bearish_score += 40
        elif rec_mean > 3.0:
            bearish_score += 20

        # Calculate neutral (remainder)
        total = bullish_score + bearish_score
        if total < 100:
            neutral_score = 100 - total
        else:
            # Normalize if over 100
            factor = 100.0 / total
            bullish_score *= factor
            bearish_score *= factor
            neutral_score = 0

        # Net sentiment (-100 to +100)
        net_sentiment = bullish_score - bearish_score

        # Sentiment change (would need historical data, using None for now - NO FALLBACK)
        sentiment_change = None

        return {
            'symbol': symbol,
            'date': date.today(),
            'bullish_percentage': bullish_score,
            'bearish_percentage': bearish_score,
            'neutral_percentage': neutral_score,
            'net_sentiment': net_sentiment,
            'sentiment_change': sentiment_change,
            'source': 'yfinance_derived',
        }

    except Exception as e:
        logging.error(f"Error calculating retail sentiment for {symbol}: {e}")
        return None


def create_tables(cur, conn):
    """Create positioning tables - institutional_positioning already exists, just add retail_sentiment"""
    logging.info("Creating positioning tables...")

    # Main positioning metrics table
    positioning_sql = """
    CREATE TABLE IF NOT EXISTS positioning_metrics (
        symbol VARCHAR(20),
        date DATE,
        institutional_ownership DECIMAL(8,6),
        institutional_float_held DECIMAL(8,6),
        institution_count INTEGER,
        insider_ownership DECIMAL(8,6),
        shares_short BIGINT,
        shares_short_prior_month BIGINT,
        short_ratio DECIMAL(8,2),
        short_percent_of_float DECIMAL(8,6),
        short_interest_change DECIMAL(8,6),
        short_interest_date BIGINT,
        float_shares BIGINT,
        shares_outstanding BIGINT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
    );
    """

    # Retail sentiment table (institutional_positioning already exists in the database)
    retail_sentiment_sql = """
    CREATE TABLE IF NOT EXISTS retail_sentiment (
        symbol VARCHAR(20),
        date DATE,
        bullish_percentage DECIMAL(5,2),
        bearish_percentage DECIMAL(5,2),
        neutral_percentage DECIMAL(5,2),
        net_sentiment DECIMAL(6,2),
        sentiment_change DECIMAL(6,2),
        source VARCHAR(50),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (symbol, date)
    );
    """

    cur.execute(positioning_sql)
    cur.execute(retail_sentiment_sql)

    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_positioning_symbol ON positioning_metrics(symbol);",
        "CREATE INDEX IF NOT EXISTS idx_positioning_date ON positioning_metrics(date DESC);",
        "CREATE INDEX IF NOT EXISTS idx_positioning_inst_own ON positioning_metrics(institutional_ownership DESC);",
        "CREATE INDEX IF NOT EXISTS idx_positioning_short ON positioning_metrics(short_percent_of_float DESC);",
        "CREATE INDEX IF NOT EXISTS idx_retail_sentiment_symbol ON retail_sentiment(symbol);",
        "CREATE INDEX IF NOT EXISTS idx_retail_sentiment_date ON retail_sentiment(date DESC);",
        "CREATE INDEX IF NOT EXISTS idx_retail_sentiment_net ON retail_sentiment(net_sentiment DESC);",
    ]

    for index_sql in indexes:
        cur.execute(index_sql)

    conn.commit()
    logging.info("Positioning tables created successfully")


def load_positioning_data(symbols: List[str], conn, cur, batch_size: int = 20):
    """Load positioning data for symbols"""
    total_processed = 0
    total_metrics = 0
    total_inst_holders = 0
    total_retail_sentiment = 0

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(symbols) + batch_size - 1) // batch_size

        logging.info(f"Processing batch {batch_num}/{total_batches}: {len(batch)} symbols")

        positioning_data = []
        institutional_data = []
        retail_sentiment_data = []

        for symbol in batch:
            try:
                # Get positioning metrics
                pos_data = get_positioning_data(symbol)
                if pos_data:
                    positioning_data.append(pos_data)

                # Get institutional holders
                inst_holders = get_institutional_holders(symbol)
                institutional_data.extend(inst_holders)

                # Get retail sentiment
                retail_sent = get_retail_sentiment(symbol)
                if retail_sent:
                    retail_sentiment_data.append(retail_sent)

                total_processed += 1

                # Respect API rate limits
                time.sleep(0.5)

            except Exception as e:
                logging.error(f"Error processing {symbol}: {e}")

        # Insert positioning metrics
        if positioning_data:
            try:
                metrics_rows = []
                for item in positioning_data:
                    metrics_rows.append((
                        item['symbol'],
                        item['date'],
                        item.get('institutional_ownership'),
                        item.get('institutional_float_held'),
                        item.get('institution_count'),
                        item.get('insider_ownership'),
                        item.get('shares_short'),
                        item.get('shares_short_prior_month'),
                        item.get('short_ratio'),
                        item.get('short_percent_of_float'),
                        item.get('short_interest_change'),
                        item.get('short_interest_date'),
                        item.get('float_shares'),
                        item.get('shares_outstanding'),
                    ))

                insert_sql = """
                    INSERT INTO positioning_metrics (
                        symbol, date, institutional_ownership, institutional_float_held,
                        institution_count, insider_ownership, shares_short, shares_short_prior_month,
                        short_ratio, short_percent_of_float, short_interest_change,
                        short_interest_date, float_shares, shares_outstanding
                    ) VALUES %s
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        institutional_ownership = EXCLUDED.institutional_ownership,
                        institutional_float_held = EXCLUDED.institutional_float_held,
                        institution_count = EXCLUDED.institution_count,
                        insider_ownership = EXCLUDED.insider_ownership,
                        shares_short = EXCLUDED.shares_short,
                        short_ratio = EXCLUDED.short_ratio,
                        short_percent_of_float = EXCLUDED.short_percent_of_float,
                        updated_at = CURRENT_TIMESTAMP
                """
                execute_values(cur, insert_sql, metrics_rows)
                total_metrics += len(metrics_rows)

            except Exception as e:
                logging.error(f"Error inserting positioning metrics: {e}")
                conn.rollback()

        # Insert institutional holders - match existing schema
        if institutional_data:
            try:
                inst_rows = []
                for item in institutional_data:
                    inst_rows.append((
                        item['symbol'],
                        item['institution_type'],
                        item['institution_name'],
                        item.get('position_size'),
                        item.get('position_change_percent'),
                        item.get('market_share'),
                        item.get('filing_date'),
                        item.get('quarter'),
                    ))

                # Match existing schema: symbol, institution_type, institution_name, position_size,
                # position_change_percent, market_share, filing_date, quarter
                insert_sql = """
                    INSERT INTO institutional_positioning (
                        symbol, institution_type, institution_name, position_size,
                        position_change_percent, market_share, filing_date, quarter
                    ) VALUES %s
                    ON CONFLICT (id) DO NOTHING
                """
                execute_values(cur, insert_sql, inst_rows)
                total_inst_holders += len(inst_rows)

            except Exception as e:
                logging.error(f"Error inserting institutional holders: {e}")
                logging.error(f"Sample data: {inst_rows[0] if inst_rows else 'No data'}")
                conn.rollback()

        # Insert retail sentiment
        if retail_sentiment_data:
            try:
                retail_rows = []
                for item in retail_sentiment_data:
                    retail_rows.append((
                        item['symbol'],
                        item['date'],
                        item.get('bullish_percentage'),
                        item.get('bearish_percentage'),
                        item.get('neutral_percentage'),
                        item.get('net_sentiment'),
                        item.get('sentiment_change'),
                        item.get('source'),
                    ))

                insert_sql = """
                    INSERT INTO retail_sentiment (
                        symbol, date, bullish_percentage, bearish_percentage,
                        neutral_percentage, net_sentiment, sentiment_change, source
                    ) VALUES %s
                    ON CONFLICT (symbol, date) DO UPDATE SET
                        bullish_percentage = EXCLUDED.bullish_percentage,
                        bearish_percentage = EXCLUDED.bearish_percentage,
                        neutral_percentage = EXCLUDED.neutral_percentage,
                        net_sentiment = EXCLUDED.net_sentiment,
                        updated_at = CURRENT_TIMESTAMP
                """
                execute_values(cur, insert_sql, retail_rows)
                total_retail_sentiment += len(retail_rows)

            except Exception as e:
                logging.error(f"Error inserting retail sentiment: {e}")
                conn.rollback()

        conn.commit()
        logging.info(f"Batch {batch_num} complete: {len(positioning_data)} metrics, {len(institutional_data)} institutional, {len(retail_sentiment_data)} retail sentiment")

        # Pause between batches
        time.sleep(2)

    return total_processed, total_metrics, total_inst_holders, total_retail_sentiment


if __name__ == "__main__":
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

    # Create tables
    create_tables(cur, conn)

    # Get symbols to process
    cur.execute("""
        SELECT symbol FROM stock_symbols
        WHERE symbol IS NOT NULL
        LIMIT 10
    """)
    symbols = [row["symbol"] for row in cur.fetchall()]

    if not symbols:
        logging.warning("No symbols found. Run loadsymbols.py first.")
        sys.exit(1)

    logging.info(f"Loading positioning data for {len(symbols)} symbols")

    # Load data
    start_time = time.time()
    processed, metrics_inserted, inst_holders, retail_inserted = load_positioning_data(symbols, conn, cur)
    end_time = time.time()

    # Statistics
    cur.execute("SELECT COUNT(DISTINCT symbol) FROM positioning_metrics")
    total_metrics_symbols = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(*) FROM institutional_positioning")
    total_inst = cur.fetchone()["count"]

    cur.execute("SELECT COUNT(DISTINCT symbol) FROM retail_sentiment")
    total_retail_symbols = cur.fetchone()["count"]

    logging.info("=" * 60)
    logging.info("POSITIONING DATA LOADING COMPLETE")
    logging.info("=" * 60)
    logging.info(f"Symbols processed: {processed}")
    logging.info(f"Positioning metrics inserted: {metrics_inserted}")
    logging.info(f"Institutional holders inserted: {inst_holders}")
    logging.info(f"Retail sentiment inserted: {retail_inserted}")
    logging.info(f"Total symbols in positioning_metrics: {total_metrics_symbols}")
    logging.info(f"Total symbols in retail_sentiment: {total_retail_symbols}")
    logging.info(f"Total institutional records: {total_inst}")
    logging.info(f"Processing time: {(end_time - start_time):.1f} seconds")

    # Sample results
    cur.execute("""
        SELECT p.symbol,
               p.institutional_ownership,
               p.insider_ownership,
               p.short_percent_of_float,
               p.short_interest_change,
               p.institution_count,
               r.net_sentiment
        FROM positioning_metrics p
        LEFT JOIN retail_sentiment r ON p.symbol = r.symbol AND p.date = r.date
        WHERE p.institutional_ownership IS NOT NULL
        ORDER BY p.institutional_ownership DESC
        LIMIT 10
    """)

    logging.info("\nTop 10 Stocks by Institutional Ownership:")
    for row in cur.fetchall():
        inst_own = row["institutional_ownership"]
        insider_own = row["insider_ownership"]
        short_pct = row["short_percent_of_float"]
        net_sent = row["net_sentiment"]

        # Only log if we have real data (NO FALLBACK)
        if inst_own is not None and insider_own is not None and short_pct is not None and net_sent is not None:
            logging.info(
                f"  {row['symbol']:6}: "
                f"Inst={inst_own:.1%}, Insider={insider_own:.1%}, Short={short_pct:.1%}, Sentiment={net_sent:+.1f}"
            )

    cur.close()
    conn.close()
    logging.info("Database connection closed")
