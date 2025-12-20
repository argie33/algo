#!/usr/bin/env python3
"""
Selective Growth Metrics Loader - Load only for symbols with missing data.
Processes in batches to avoid context window errors and memory issues.

Usage:
  python selective_growth_loader.py [--batch-size 500] [--symbols SYMBOL,SYMBOL,...]

  --batch-size N        Process N symbols per batch (default: 500)
  --symbols S1,S2,...   Load only specific symbols (comma-separated)
  --check-only         Just show what would be loaded, don't load
"""

import gc
import logging
import os
import sys
import time
from datetime import date
from typing import Dict, List, Optional, Set, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Database connection (from environment variables)
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'stocks')
DB_USER = os.getenv('DB_USER', 'stocks')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_PORT = int(os.getenv('DB_PORT', '5432'))


def get_db_connection():
    """Create database connection."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        sys.exit(1)


def get_symbols_missing_growth_metrics(conn, limit: Optional[int] = None) -> List[str]:
    """
    Get list of symbols missing growth metrics data.

    Returns symbols where growth_metrics table is empty or all values are NULL.
    """
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        query = """
        SELECT DISTINCT s.symbol
        FROM stock_symbols s
        WHERE NOT EXISTS (
            SELECT 1 FROM growth_metrics gm
            WHERE gm.symbol = s.symbol
            AND gm.date = CURRENT_DATE
            AND (
                gm.revenue_growth_3y_cagr IS NOT NULL
                OR gm.eps_growth_3y_cagr IS NOT NULL
                OR gm.operating_income_growth_yoy IS NOT NULL
                OR gm.fcf_growth_yoy IS NOT NULL
                OR gm.net_income_growth_yoy IS NOT NULL
            )
        )
        ORDER BY s.symbol
        """

        if limit:
            query += f" LIMIT {limit}"

        cur.execute(query)
        symbols = [row["symbol"] for row in cur.fetchall()]
        logger.info(f"Found {len(symbols)} symbols missing growth metrics")
        return symbols
    finally:
        cur.close()


def get_available_upstream_data(conn, symbols: List[str]) -> Dict[str, List[str]]:
    """
    For given symbols, identify which upstream data is available.
    Returns dict of {data_source: [symbols_with_that_source]}
    """
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        results = {
            "annual_statements": [],
            "quarterly_statements": [],
            "key_metrics_only": [],
        }

        symbol_list = "(" + ",".join([f"'{s}'" for s in symbols]) + ")"

        # Check annual statements
        cur.execute(
            f"SELECT DISTINCT symbol FROM annual_income_statement WHERE symbol IN {symbol_list}"
        )
        results["annual_statements"] = [row["symbol"] for row in cur.fetchall()]

        # Check quarterly statements
        cur.execute(
            f"SELECT DISTINCT symbol FROM quarterly_income_statement WHERE symbol IN {symbol_list}"
        )
        results["quarterly_statements"] = [row["symbol"] for row in cur.fetchall()]

        # Check key_metrics only (no statements)
        annual_set = set(results["annual_statements"])
        quarterly_set = set(results["quarterly_statements"])
        all_symbols = set(symbols)
        key_metrics_only = all_symbols - annual_set - quarterly_set
        results["key_metrics_only"] = list(key_metrics_only)

        return results
    finally:
        cur.close()


def safe_float(value, default=None, max_val=9999.99):
    """Safely convert to float with bounds checking."""
    if value is None:
        return default
    try:
        val = float(value)
        # Clip to reasonable bounds to avoid extreme values
        if val > max_val:
            return max_val
        if val < -max_val:
            return -max_val
        return val
    except (TypeError, ValueError):
        return default


def calculate_cagr(start_value: Optional[float], end_value: Optional[float], years: int) -> Optional[float]:
    """Calculate CAGR (Compound Annual Growth Rate)."""
    if start_value is None or end_value is None:
        return None
    if start_value <= 0 or years <= 0:
        return None

    try:
        cagr = (pow(end_value / start_value, 1 / years) - 1) * 100
        return safe_float(cagr)
    except:
        return None


def load_growth_metrics_for_batch(conn, symbols: List[str]) -> Tuple[int, int]:
    """
    Load growth metrics for a batch of symbols.
    Returns (rows_inserted, rows_updated)
    """
    cur = conn.cursor(cursor_factory=RealDictCursor)
    insert_count = 0
    update_count = 0

    try:
        logger.info(f"Processing batch of {len(symbols)} symbols")

        for symbol in symbols:
            try:
                metrics = {}

                # 1. Get 3-year revenue CAGR from annual statements
                cur.execute("""
                    SELECT revenue
                    FROM annual_income_statement
                    WHERE symbol = %s
                    ORDER BY fiscal_year DESC
                    LIMIT 4
                """, (symbol,))
                revenues = [row["revenue"] for row in cur.fetchall()]
                if len(revenues) >= 2:
                    metrics["revenue_growth_3y_cagr"] = calculate_cagr(
                        revenues[-1], revenues[0], 3
                    )

                # 2. Get EPS growth from earnings history or quarterly data
                cur.execute("""
                    SELECT eps_actual, quarter_year
                    FROM earnings_history
                    WHERE symbol = %s
                    ORDER BY quarter_year DESC
                    LIMIT 4
                """, (symbol,))
                earnings = cur.fetchall()
                if len(earnings) >= 2:
                    # Calculate YoY EPS growth (Q1 2025 vs Q1 2024, etc)
                    recent_eps = earnings[0]["eps_actual"]
                    prev_year_eps = next(
                        (e["eps_actual"] for e in earnings if
                         e["quarter_year"] // 100 == earnings[0]["quarter_year"] // 100 - 1),
                        None
                    )
                    if recent_eps and prev_year_eps:
                        metrics["eps_growth_3y_cagr"] = safe_float(
                            (recent_eps - prev_year_eps) / abs(prev_year_eps) * 100
                        )

                # 3. Get FCF growth from annual cash flow
                cur.execute("""
                    SELECT free_cash_flow
                    FROM annual_cash_flow
                    WHERE symbol = %s
                    ORDER BY fiscal_year DESC
                    LIMIT 2
                """, (symbol,))
                fcf_data = cur.fetchall()
                if len(fcf_data) >= 2:
                    fcf_yoy = (fcf_data[0]["free_cash_flow"] - fcf_data[1]["free_cash_flow"]) / abs(fcf_data[1]["free_cash_flow"]) * 100
                    metrics["fcf_growth_yoy"] = safe_float(fcf_yoy)

                # 4. Get quarterly growth momentum from key_metrics
                cur.execute("""
                    SELECT earnings_q_growth_pct, earnings_growth_pct
                    FROM key_metrics
                    WHERE symbol = %s AND date = CURRENT_DATE
                """, (symbol,))
                key_metrics_row = cur.fetchone()
                if key_metrics_row:
                    metrics["quarterly_growth_momentum"] = safe_float(
                        key_metrics_row.get("earnings_q_growth_pct")
                    )
                    if not metrics.get("eps_growth_3y_cagr"):
                        metrics["eps_growth_3y_cagr"] = safe_float(
                            key_metrics_row.get("earnings_growth_pct")
                        )

                # 5. Upsert into growth_metrics
                if any(v is not None for v in metrics.values()):
                    values = [symbol, date.today()]
                    values.extend([metrics.get(col) for col in [
                        "revenue_growth_3y_cagr",
                        "eps_growth_3y_cagr",
                        "operating_income_growth_yoy",
                        "fcf_growth_yoy",
                        "net_income_growth_yoy",
                        "gross_margin_trend",
                        "operating_margin_trend",
                        "net_margin_trend",
                        "quarterly_growth_momentum",
                        "asset_growth_yoy",
                        "roe_trend",
                        "sustainable_growth_rate",
                        "ocf_growth_yoy",
                    ]])

                    cur.execute("""
                        INSERT INTO growth_metrics (
                            symbol, date,
                            revenue_growth_3y_cagr,
                            eps_growth_3y_cagr,
                            operating_income_growth_yoy,
                            fcf_growth_yoy,
                            net_income_growth_yoy,
                            gross_margin_trend,
                            operating_margin_trend,
                            net_margin_trend,
                            quarterly_growth_momentum,
                            asset_growth_yoy,
                            roe_trend,
                            sustainable_growth_rate,
                            ocf_growth_yoy
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol, date)
                        DO UPDATE SET
                            revenue_growth_3y_cagr = EXCLUDED.revenue_growth_3y_cagr,
                            eps_growth_3y_cagr = EXCLUDED.eps_growth_3y_cagr,
                            fcf_growth_yoy = EXCLUDED.fcf_growth_yoy,
                            quarterly_growth_momentum = EXCLUDED.quarterly_growth_momentum
                    """, tuple(values))

                    if cur.rowcount > 0:
                        if cur.statusmessage.startswith("INSERT"):
                            insert_count += 1
                        else:
                            update_count += 1

            except Exception as e:
                logger.warning(f"Error processing {symbol}: {e}")
                continue

        conn.commit()
        logger.info(f"Batch complete: {insert_count} inserted, {update_count} updated")

    except Exception as e:
        logger.error(f"Batch processing error: {e}")
        conn.rollback()
    finally:
        cur.close()

    return insert_count, update_count


def main():
    """Main execution."""
    import argparse

    parser = argparse.ArgumentParser(description="Selective growth metrics loader")
    parser.add_argument("--batch-size", type=int, default=500, help="Symbols per batch")
    parser.add_argument("--symbols", type=str, help="Specific symbols (comma-separated)")
    parser.add_argument("--check-only", action="store_true", help="Show what would load, don't load")

    args = parser.parse_args()

    conn = get_db_connection()

    try:
        # Get symbols to process
        if args.symbols:
            symbols = args.symbols.split(",")
        else:
            symbols = get_symbols_missing_growth_metrics(conn)

        if not symbols:
            logger.info("No symbols missing growth metrics - all up to date!")
            return

        # Show data availability
        upstream = get_available_upstream_data(conn, symbols)
        print(f"\n📊 UPSTREAM DATA AVAILABILITY (for {len(symbols)} symbols missing growth metrics)")
        print("-" * 80)
        print(f"  Annual statements available:    {len(upstream['annual_statements']):6} symbols")
        print(f"  Quarterly statements available: {len(upstream['quarterly_statements']):6} symbols")
        print(f"  Key metrics only:                {len(upstream['key_metrics_only']):6} symbols")
        print(f"  Total to process:                {len(symbols):6} symbols")
        print("-" * 80 + "\n")

        if args.check_only:
            logger.info("Check-only mode: Not loading data")
            return

        # Process in batches
        total_inserted = 0
        total_updated = 0
        batch_size = args.batch_size

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            logger.info(f"\n📦 BATCH {i//batch_size + 1}/{(len(symbols)-1)//batch_size + 1}")

            inserted, updated = load_growth_metrics_for_batch(conn, batch)
            total_inserted += inserted
            total_updated += updated

            # Force garbage collection between batches
            gc.collect()
            time.sleep(1)  # Brief pause between batches

        logger.info(f"\n✅ COMPLETE")
        logger.info(f"   Total inserted: {total_inserted}")
        logger.info(f"   Total updated:  {total_updated}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
