#!/usr/bin/env python3
"""
Positioning Metrics Calculator

Calculates derived positioning metrics from base institutional/insider/short data.
Works with positioning_metrics table created by loaddailycompanydata.py
Trigger: 2025-10-26 AWS deployment - positioning metrics calculator

Calculates:
- Institutional Quality Score: Based on holder types and concentration
- Smart Money Score: Based on insider activity + institutional positioning
- Insider Sentiment Score: Based on recent buy/sell activity
- Short Squeeze Score: Based on short interest and ratio
- Composite Positioning Score: Weighted combination of all positioning factors

Author: Financial Dashboard System
"""

import sys
import time
import logging
import json
import os
import gc
import resource
from datetime import datetime, date
from typing import Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
import numpy as np

# Script configuration
SCRIPT_NAME = "loadpositioning.py"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def log_mem(stage: str):
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    mb = usage / 1024 if sys.platform.startswith("linux") else usage / (1024 * 1024)
    logging.info(f"[MEM] {stage}: {mb:.1f} MB RSS")

def get_db_config():
    """Get database configuration"""
    try:
        import boto3
        secret_str = boto3.client("secretsmanager") \
                         .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
        sec = json.loads(secret_str)
        return {
            "host": sec["host"],
            "port": int(sec.get("port", 5432)),
            "user": sec["username"],
            "password": sec["password"],
            "dbname": sec["dbname"]
        }
    except Exception:
        return {
            "host": os.environ.get("DB_HOST", "localhost"),
            "port": int(os.environ.get("DB_PORT", 5432)),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", ""),
            "dbname": os.environ.get("DB_NAME", "stocks")
        }

def safe_float(value, default=None):
    """Convert to float safely - returns None if data unavailable (no fake defaults)"""
    if value is None or pd.isna(value):
        return default
    try:
        f = float(value)
        if np.isnan(f) or np.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default

def safe_int(value, default=None):
    """Convert to int safely - returns None if data unavailable (no fake defaults)"""
    if value is None or pd.isna(value):
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def calculate_institutional_quality_score(conn, symbol: str) -> float:
    """
    Calculate quality score based on institutional holder types.
    Uses data from institutional_positioning table.
    Returns None if no real institutional positioning data available.
    """
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get institutional holders with types
        cur.execute("""
            SELECT institution_type, position_size
            FROM institutional_positioning
            WHERE symbol = %s
            ORDER BY position_size DESC NULLS LAST
        """, (symbol,))

        holders = cur.fetchall()

        if not holders:
            return None  # No real data - return None instead of fake 0.5

        # Quality scoring by institution type
        quality_scores = {
            'HEDGE_FUND': 0.9,      # Active managers - high quality
            'PENSION_FUND': 0.85,    # Long-term holders - good quality
            'MUTUAL_FUND': 0.7,      # Passive/active mix
            'BANK': 0.6,             # Conservative holders
            'INDIVIDUAL': 0.5,       # Variable quality
        }

        # REAL DATA ONLY - only count holders with actual position data
        positions = [safe_float(h.get('position_size')) for h in holders if h.get('position_size') is not None]
        if not positions:
            return None  # No real position data - return None instead of fake 0.5

        total_position = sum(positions)
        if total_position <= 0:
            return None  # No real position data

        # Weighted quality score - REAL DATA ONLY
        quality_score = 0
        for holder in holders:
            position_size = safe_float(holder.get('position_size'))
            if position_size is None or position_size <= 0:
                continue  # Skip holders without real position data

            holder_type = holder.get('institution_type', 'INDIVIDUAL').upper()
            weight = position_size / total_position
            score = quality_scores.get(holder_type, 0.5)
            quality_score += score * weight

        return min(max(quality_score, 0), 1)

    except Exception as e:
        logging.warning(f"Could not calculate institutional quality for {symbol}: {e}")
        return None  # Error - return None instead of fake 0.5

def calculate_insider_sentiment_score(conn, symbol: str) -> float:
    """
    Calculate insider sentiment from recent buy/sell activity.
    Uses data from insider_transactions table.
    Returns None if no real insider transaction data available.
    """
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get recent insider transactions (last 90 days)
        cur.execute("""
            SELECT transaction_type, value
            FROM insider_transactions
            WHERE symbol = %s
            AND transaction_date >= CURRENT_DATE - INTERVAL '90 days'
            ORDER BY transaction_date DESC
        """, (symbol,))

        transactions = cur.fetchall()

        if not transactions:
            return None  # No real data - return None instead of fake 0.0

        total_buy_value = 0
        total_sell_value = 0

        for tx in transactions:
            # REAL DATA ONLY - skip transactions without value data
            value = safe_float(tx.get('value'))
            if value is None or value <= 0:
                continue  # Skip transactions without real value data

            tx_type = str(tx.get('transaction_type', '')).upper()

            if 'BUY' in tx_type:
                total_buy_value += value
            elif 'SELL' in tx_type:
                total_sell_value += value

        total_value = total_buy_value + total_sell_value

        if total_value == 0:
            return None  # No real value data - return None instead of fake 0.0

        # Sentiment: +1 (all buys) to -1 (all sells)
        sentiment = (total_buy_value - total_sell_value) / total_value

        return min(max(sentiment, -1), 1)

    except Exception as e:
        logging.warning(f"Could not calculate insider sentiment for {symbol}: {e}")
        return None  # Error - return None instead of fake 0.0

def calculate_smart_money_score(conn, symbol: str, institutional_quality: float, insider_sentiment: float) -> float:
    """
    Calculate smart money score combining:
    - Institutional quality (what KIND of institutions hold it)
    - Insider sentiment (are insiders buying or selling)
    - Institutional ownership (HOW MUCH is held)
    Returns None if insufficient real data available.
    """
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get institutional ownership
        cur.execute("""
            SELECT institutional_ownership_pct, institutional_holders_count
            FROM positioning_metrics
            WHERE symbol = %s
            AND date = CURRENT_DATE
        """, (symbol,))

        row = cur.fetchone()

        if not row:
            return None  # No real data - return None instead of fake 0.5

        # REAL DATA ONLY - get actual values, not defaults
        inst_ownership = safe_float(row.get('institutional_ownership_pct'))
        inst_count = safe_int(row.get('institutional_holders_count'))

        # Build score from ONLY real data components
        score_components = []
        component_weights = []

        # Normalize institutional ownership (0-1) - ONLY if data exists
        if inst_ownership is not None and inst_ownership > 0:
            ownership_score = min(inst_ownership / 100, 1.0)
            score_components.append(ownership_score)
            component_weights.append(0.25)

        # Institution count is good up to ~500 - ONLY if data exists
        if inst_count is not None and inst_count > 0:
            count_score = min(inst_count / 500, 1.0)
            score_components.append(count_score)
            component_weights.append(0.15)

        # Add institutional quality - ONLY if real data
        if institutional_quality is not None:
            score_components.append(institutional_quality)
            component_weights.append(0.35)

        # Add insider sentiment - ONLY if real data
        if insider_sentiment is not None:
            sentiment_score = max(insider_sentiment, 0)
            score_components.append(sentiment_score)
            component_weights.append(0.25)

        # Return None if no real data, or weighted average of what we have
        if not score_components:
            return None  # No real data available

        # Combine available components with normalized weights
        total_weight = sum(component_weights)
        smart_score = sum(c * w for c, w in zip(score_components, component_weights)) / total_weight

        return min(max(smart_score, 0), 1)

    except Exception as e:
        logging.warning(f"Could not calculate smart money score for {symbol}: {e}")
        return None  # Error - return None instead of fake 0.5

def calculate_short_squeeze_score(short_pct: float, short_ratio: float) -> float:
    """
    Calculate short squeeze potential.
    High when: short interest is high AND days to cover is low (ratio < 5)
    Returns None if no real short data available.
    """
    # If both are None/missing, we have no real data
    if short_pct is None and short_ratio is None:
        return None

    # Normalize short percentage (0-30% is realistic range)
    short_score = min(short_pct / 30, 1.0) if short_pct else 0

    # Ratio: lower is better for squeeze (more pressure to buy back quickly)
    # Below 2 = very high pressure, above 10 = low pressure
    ratio_score = max(0, 1 - (short_ratio / 10)) if short_ratio else 0

    # Combined squeeze score
    squeeze_score = (short_score * 0.6 + ratio_score * 0.4)

    return min(max(squeeze_score, 0), 1)

def calculate_composite_positioning_score(
    institutional_quality: float,
    smart_money: float,
    insider_sentiment: float,
    short_squeeze: float,
    institutional_ownership: float
) -> float:
    """
    Calculate final composite positioning score (0-1).
    Weights:
    - Institutional Quality: 25%
    - Smart Money Score: 25%
    - Insider Sentiment: 20%
    - Short Squeeze: 15%
    - Institutional Ownership: 15%
    Returns None if insufficient real data available.
    """
    # Count how many real data points we have
    real_data_count = sum([
        institutional_quality is not None,
        smart_money is not None,
        insider_sentiment is not None,
        short_squeeze is not None,
        institutional_ownership is not None
    ])

    # If we have less than 2 real data points, we don't have enough for a composite score
    if real_data_count < 2:
        return None

    # Normalize institutional ownership (scale to 0-1)
    ownership_normalized = min(institutional_ownership / 100, 1.0) if institutional_ownership else 0

    # Only include real data in the composite (None values don't contribute)
    composite = 0
    weights_applied = 0

    if institutional_quality is not None:
        composite += institutional_quality * 0.25
        weights_applied += 0.25

    if smart_money is not None:
        composite += smart_money * 0.25
        weights_applied += 0.25

    if insider_sentiment is not None:
        composite += (insider_sentiment + 1) / 2 * 0.20  # Convert -1..1 to 0..1
        weights_applied += 0.20

    if short_squeeze is not None:
        composite += short_squeeze * 0.15
        weights_applied += 0.15

    if institutional_ownership is not None:
        composite += ownership_normalized * 0.15
        weights_applied += 0.15

    # Normalize by actual weights applied
    if weights_applied > 0:
        composite = composite / weights_applied

    return min(max(composite, 0), 1)

def process_symbol_positioning(conn, symbol: str) -> bool:
    """Process and calculate positioning metrics for a symbol"""
    try:
        # Get base positioning data
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT
                symbol, date,
                institutional_ownership_pct,
                short_interest_pct,
                short_ratio
            FROM positioning_metrics
            WHERE symbol = %s
            AND date = CURRENT_DATE
        """, (symbol,))

        row = cur.fetchone()
        if not row:
            return False

        # Calculate derived metrics - REAL DATA ONLY
        institutional_quality = calculate_institutional_quality_score(conn, symbol)
        insider_sentiment = calculate_insider_sentiment_score(conn, symbol)
        smart_money = calculate_smart_money_score(conn, symbol, institutional_quality, insider_sentiment)

        # Only calculate short squeeze if we have real short data
        short_interest_pct = safe_float(row.get('short_interest_pct'))
        short_ratio = safe_float(row.get('short_ratio'))
        short_squeeze = calculate_short_squeeze_score(short_interest_pct, short_ratio)

        # Only calculate composite if we have real ownership data
        inst_ownership_pct = safe_float(row.get('institutional_ownership_pct'))
        composite = calculate_composite_positioning_score(
            institutional_quality,
            smart_money,
            insider_sentiment,
            short_squeeze,
            inst_ownership_pct
        )

        # Update positioning_metrics with calculated scores
        cur.execute("""
            UPDATE positioning_metrics
            SET
                institutional_quality_score = %s,
                insider_sentiment_score = %s,
                smart_money_score = %s,
                short_squeeze_score = %s,
                composite_positioning_score = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE symbol = %s
            AND date = CURRENT_DATE
        """, (
            institutional_quality,
            insider_sentiment,
            smart_money,
            short_squeeze,
            composite,
            symbol
        ))

        conn.commit()
        return True

    except Exception as e:
        logging.error(f"Error processing {symbol}: {e}")
        conn.rollback()
        return False

def main():
    """Main function"""
    start_time = time.time()

    try:
        logging.info(f"Starting {SCRIPT_NAME}...")
        log_mem("startup")

        # Connect to database
        config = get_db_config()
        conn = psycopg2.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            dbname=config["dbname"]
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get all symbols that have positioning data
        logging.info("Loading positioning metrics for all symbols...")
        cur.execute("""
            SELECT DISTINCT symbol FROM positioning_metrics
            WHERE date = CURRENT_DATE
            ORDER BY symbol
        """)

        symbols = [row['symbol'] for row in cur.fetchall()]
        total_symbols = len(symbols)

        logging.info(f"Found {total_symbols} symbols to process")

        if total_symbols == 0:
            logging.warning("No positioning data found for today")
            cur.close()
            conn.close()
            return

        # Process symbols in batches
        batch_size = 50
        batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]

        success_count = 0
        for batch_idx, batch in enumerate(batches, 1):
            log_mem(f"Positioning batch {batch_idx} start")
            logging.info(f"Processing positioning batch {batch_idx}/{len(batches)}: {len(batch)} symbols")

            batch_success = 0
            for symbol in batch:
                if process_symbol_positioning(conn, symbol):
                    batch_success += 1

            success_count += batch_success
            logging.info(f"Positioning batch {batch_idx} processed {batch_success}/{len(batch)} symbols successfully")
            log_mem(f"Positioning batch {batch_idx} end")
            gc.collect()

        cur.close()
        conn.close()

        elapsed = time.time() - start_time
        logging.info(f"✅ {SCRIPT_NAME} completed: {success_count}/{total_symbols} symbols processed in {elapsed:.1f}s")

    except Exception as e:
        logging.error(f"❌ Error in {SCRIPT_NAME}: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
