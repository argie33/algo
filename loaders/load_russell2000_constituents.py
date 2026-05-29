#!/usr/bin/env python3
"""
Load Russell 2000 constituents and mark them in stock_symbols table.

Fetches the current Russell 2000 constituent list from Wikipedia and updates
the is_russell2000 flag in stock_symbols to identify which symbols are in the index.

Russell 2000: Small-cap index of the 2,000 smallest stocks in the Russell 3000.
Typically stocks ranked 1001-3000 by market cap.
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database_context import DatabaseContext
import pandas as pd
import requests
from io import StringIO

logging.basicConfig(level=logging.INFO, format="%(asctime)s] %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("load_russell2000_constituents")

# Russell 2000 Wikipedia table URL
RUSSELL2000_URL = "https://en.wikipedia.org/wiki/Russell_2000"

def get_russell2000_symbols():
    """Fetch Russell 2000 constituent symbols from Wikipedia."""
    try:
        logger.info("Fetching Russell 2000 constituents from Wikipedia")

        # Use proper User-Agent to avoid 403 Forbidden
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        # Fetch the page with proper headers
        response = requests.get(RUSSELL2000_URL, headers=headers, timeout=15)
        response.raise_for_status()

        # Parse tables from the response text
        tables = pd.read_html(StringIO(response.text))
        if not tables:
            logger.error("Could not find Russell 2000 table on Wikipedia")
            return None

        # Find the constituents table (usually contains many rows)
        # Russell 2000 is the second major Russell index, so look for the largest table
        largest_table = None
        largest_size = 0
        for table in tables:
            if len(table) > largest_size and 'Symbol' in table.columns or 'Ticker' in table.columns:
                largest_table = table
                largest_size = len(table)

        if largest_table is None:
            logger.warning("Could not find Russell 2000 constituents table")
            # Try the first table as fallback
            df = tables[0] if tables else None
            if df is None:
                return None
        else:
            df = largest_table

        # Extract symbols
        symbol_col = None
        if "Symbol" in df.columns:
            symbol_col = "Symbol"
        elif "Ticker" in df.columns:
            symbol_col = "Ticker"
        elif "Ticker symbol" in df.columns:
            symbol_col = "Ticker symbol"
        else:
            logger.error(f"Could not find symbol column. Columns: {df.columns.tolist()}")
            return None

        symbols = df[symbol_col].str.strip().tolist()
        symbols = [s for s in symbols if s and len(s) <= 5]  # Filter invalid symbols

        logger.info(f"Fetched {len(symbols)} Russell 2000 constituents from Wikipedia")
        return symbols
    except Exception as e:
        logger.error(f"Error fetching Russell 2000 list: {e}")
        return None


def mark_russell2000_symbols(conn, symbols):
    """Mark symbols in stock_symbols table as Russell 2000 members."""
    if not symbols:
        logger.warning("No Russell 2000 symbols to mark")
        return 0

    try:
        with conn.cursor() as cur:
            # First, reset all is_russell2000 flags to FALSE
            cur.execute("UPDATE stock_symbols SET is_russell2000 = FALSE")
            reset_count = cur.rowcount
            logger.info(f"Reset is_russell2000 flag for {reset_count} symbols")

            # Now mark the Russell 2000 symbols
            placeholders = ",".join(["%s"] * len(symbols))
            sql = f"""
                UPDATE stock_symbols
                SET is_russell2000 = TRUE
                WHERE symbol IN ({placeholders})
            """
            cur.execute(sql, symbols)
            marked_count = cur.rowcount
            logger.info(f"Marked {marked_count} symbols as Russell 2000 members")

            # Verify: check how many symbols are now marked
            cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE is_russell2000 = TRUE")
            total_marked = cur.fetchone()[0]
            logger.info(f"Total symbols marked as Russell 2000: {total_marked}")

            # Also track Russell 2000 in universe column for filtering
            sql_universe = f"""
                UPDATE stock_symbols
                SET universe = 'Russell 2000'
                WHERE symbol IN ({placeholders})
            """
            cur.execute(sql_universe, symbols)
            logger.info(f"Updated universe field for {cur.rowcount} symbols")

            conn.commit()
            return marked_count
    except Exception as e:
        logger.error(f"Error marking Russell 2000 symbols: {e}")
        conn.rollback()
        return 0


def main():
    """Main entry point."""
    symbols = get_russell2000_symbols()
    if not symbols:
        logger.error("Failed to fetch Russell 2000 symbols")
        return False

    try:
        conn = get_db_connection()
        marked = mark_russell2000_symbols(conn, symbols)
        conn.close()

        if marked > 0:
            logger.info(f"Successfully marked {marked} symbols as Russell 2000 constituents")
            return True
        else:
            logger.warning("No symbols were marked as Russell 2000")
            return False
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
