#!/usr/bin/env python3
"""
Simple Options Chains Loader - Fixed version
Only loads S&P 500, skips timeouts gracefully
"""

import logging
import sys
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from datetime import datetime
import yfinance as yf
from loader_utils import LoaderHelper

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


def load_options_for_symbol(symbol: str) -> list:
    """Load options chain for a single symbol"""
    try:
        ticker = yf.Ticker(symbol)

        # Get options expirations
        expirations = ticker.options if hasattr(ticker, 'options') else []

        if not expirations:
            return None  # No options available

        results = []

        # Load first 2 expirations (near term and next)
        for exp in expirations[:2]:
            try:
                chain = ticker.option_chain(exp)
                calls = chain.calls if chain.calls is not None else None
                puts = chain.puts if chain.puts is not None else None

                if calls is not None:
                    for _, row in calls.iterrows():
                        results.append({
                            'symbol': symbol,
                            'expiration': exp,
                            'option_type': 'CALL',
                            'strike': float(row.get('strike', 0)),
                            'last_price': float(row.get('lastPrice', 0)),
                            'bid': float(row.get('bid', 0)),
                            'ask': float(row.get('ask', 0)),
                            'volume': int(row.get('volume', 0)),
                            'open_interest': int(row.get('openInterest', 0)),
                            'loaded_at': datetime.now().isoformat()
                        })

                if puts is not None:
                    for _, row in puts.iterrows():
                        results.append({
                            'symbol': symbol,
                            'expiration': exp,
                            'option_type': 'PUT',
                            'strike': float(row.get('strike', 0)),
                            'last_price': float(row.get('lastPrice', 0)),
                            'bid': float(row.get('bid', 0)),
                            'ask': float(row.get('ask', 0)),
                            'volume': int(row.get('volume', 0)),
                            'open_interest': int(row.get('openInterest', 0)),
                            'loaded_at': datetime.now().isoformat()
                        })
            except Exception as e:
                logger.debug(f"[{symbol}] Expiration {exp} error: {str(e)[:30]}")

        return results if results else None

    except Exception as e:
        logger.debug(f"[{symbol}] Error: {str(e)[:50]}")
        return None


def main():
    helper = LoaderHelper(max_workers=2)  # Reduced workers for options (heavier calls)

    # Get all symbols
    symbols = helper.get_sp500_symbols()
    logger.info(f"Loading options for {len(symbols)} symbols")

    # Check which ones we already have
    conn = helper.get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT symbol FROM options_chains")
    existing = set(row[0] for row in cur.fetchall())
    cur.close()
    conn.close()

    # Only load missing ones
    to_load = [s for s in symbols if s not in existing]
    logger.info(f"  Already have: {len(existing)}")
    logger.info(f"  Need to load: {len(to_load)}")

    # Process with custom logic since we get lists back
    conn = helper.get_db_connection()
    cur = conn.cursor()

    for i, symbol in enumerate(to_load):
        if i % 50 == 0:
            logger.info(f"  Progress: {i}/{len(to_load)}")

        try:
            rows = load_options_for_symbol(symbol)
            if rows:
                for row in rows:
                    cur.execute("""
                        INSERT INTO options_chains
                        (symbol, expiration, option_type, strike, last_price, bid, ask, volume, open_interest, loaded_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, (
                        row['symbol'], row['expiration'], row['option_type'],
                        row['strike'], row['last_price'], row['bid'], row['ask'],
                        row['volume'], row['open_interest'], row['loaded_at']
                    ))
                helper.successful_symbols.append(symbol)
            else:
                helper.skipped_symbols.append(symbol)
        except Exception as e:
            logger.debug(f"[{symbol}] Insert error: {str(e)[:50]}")
            helper.failed_symbols.append(symbol)

    conn.commit()
    cur.close()
    conn.close()

    helper.report("OPTIONS LOADER")


if __name__ == '__main__':
    main()
