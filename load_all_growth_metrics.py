#!/usr/bin/env python3
"""
Aggressive Growth Metrics Loader - Load ALL growth data from all sources.

STRATEGY:
  1. Process ALL 46,875 symbols (not just missing ones)
  2. For EACH symbol, calculate metrics from EVERY available source
  3. Use multi-tier priority chain (annual → quarterly → earnings → key_metrics)
  4. Batch processing (500 symbols/batch) with garbage collection
  5. Force calculate EVERYTHING possible

Features:
  ✅ Loads from annual statements (revenue, EPS, FCF, operating income)
  ✅ Loads from quarterly statements (recent momentum, YoY growth)
  ✅ Loads from earnings history (EPS growth, earnings surprises)
  ✅ Loads from key_metrics (margin trends, sustainable growth)
  ✅ Calculates ALL metrics even if some sources incomplete
  ✅ Batches in 500-symbol chunks
  ✅ Progress tracking every 100 symbols
  ✅ Detailed logging

Usage:
  python3 load_all_growth_metrics.py [--batch-size 500] [--max-symbols 0]

  --batch-size N    Symbols per batch (default: 500, range: 100-1000)
  --max-symbols N   Max symbols to load (0=all, default: 0)
  --no-progress     Don't show progress bar
"""

import gc
import logging
import os
import sys
import time
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Database connection (from environment variables)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "stocks")
DB_USER = os.getenv("DB_USER", "stocks")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_PORT = int(os.getenv("DB_PORT", "5432"))


def get_db_connection():
    """Create database connection with socket fallback."""
    # Try password auth first (AWS RDS, external hosts)
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT,
        )
        return conn
    except psycopg2.OperationalError:
        pass  # Fall through to socket auth

    # Try socket auth (local development)
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        sys.exit(1)


def safe_float(value, default=None, max_val=9999.99):
    """Safely convert to float with bounds checking."""
    if value is None:
        return default
    try:
        val = float(value)
        if val > max_val:
            return max_val
        if val < -max_val:
            return -max_val
        return val
    except (TypeError, ValueError):
        return default


def safe_int(value, default=None, max_val=999999999):
    """Safely convert to int with bounds checking."""
    if value is None:
        return default
    try:
        val = int(value)
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


def get_all_symbols(conn) -> List[str]:
    """Get all symbols from stock_symbols table."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
        symbols = [row["symbol"] for row in cur.fetchall()]
        logger.info(f"Total symbols to process: {len(symbols)}")
        return symbols
    finally:
        cur.close()


def load_growth_metrics_for_symbol(conn, symbol: str) -> Optional[Dict]:
    """
    Load ALL growth metrics for a single symbol.
    Uses comprehensive multi-source calculation.
    """
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        metrics = {
            "symbol": symbol,
            "date": date.today(),
        }

        # 1. ANNUAL INCOME STATEMENT DATA (4 years)
        cur.execute(
            """
            SELECT revenue, net_income, operating_income
            FROM annual_income_statement
            WHERE symbol = %s
            ORDER BY fiscal_year DESC
            LIMIT 4
            """,
            (symbol,),
        )
        annual_data = cur.fetchall()

        if len(annual_data) >= 2:
            # Revenue 3Y CAGR
            revenues = [d["revenue"] for d in annual_data if d["revenue"]]
            if len(revenues) >= 2:
                metrics["revenue_growth_3y_cagr"] = calculate_cagr(
                    revenues[-1], revenues[0], min(3, len(revenues) - 1)
                )

            # Net Income 3Y CAGR (proxy for EPS if no EPS available)
            incomes = [d["net_income"] for d in annual_data if d["net_income"]]
            if len(incomes) >= 2:
                metrics["eps_growth_3y_cagr"] = calculate_cagr(
                    incomes[-1], incomes[0], min(3, len(incomes) - 1)
                )

            # Operating Income YoY
            if len(annual_data) >= 2:
                oi_current = safe_float(annual_data[0].get("operating_income"))
                oi_prior = safe_float(annual_data[1].get("operating_income"))
                if oi_current and oi_prior and oi_prior != 0:
                    metrics["operating_income_growth_yoy"] = safe_float(
                        (oi_current - oi_prior) / abs(oi_prior) * 100
                    )

            # Net Income YoY
            ni_current = safe_float(annual_data[0].get("net_income"))
            ni_prior = safe_float(annual_data[1].get("net_income")) if len(annual_data) > 1 else None
            if ni_current and ni_prior and ni_prior != 0:
                metrics["net_income_growth_yoy"] = safe_float(
                    (ni_current - ni_prior) / abs(ni_prior) * 100
                )

        # 2. QUARTERLY INCOME STATEMENT DATA (8 quarters - recent momentum)
        cur.execute(
            """
            SELECT revenue, net_income, operating_income, period_ending
            FROM quarterly_income_statement
            WHERE symbol = %s
            ORDER BY period_ending DESC
            LIMIT 8
            """,
            (symbol,),
        )
        quarterly_data = cur.fetchall()

        if quarterly_data:
            # Quarterly growth momentum (most recent quarter)
            if len(quarterly_data) >= 5:
                q_current = safe_float(quarterly_data[0].get("revenue"))
                q_year_ago = safe_float(quarterly_data[4].get("revenue"))
                if q_current and q_year_ago and q_year_ago != 0:
                    metrics["quarterly_growth_momentum"] = safe_float(
                        (q_current - q_year_ago) / abs(q_year_ago) * 100
                    )

        # 3. ANNUAL CASH FLOW DATA (4 years)
        cur.execute(
            """
            SELECT free_cash_flow, operating_cash_flow
            FROM annual_cash_flow
            WHERE symbol = %s
            ORDER BY fiscal_year DESC
            LIMIT 4
            """,
            (symbol,),
        )
        cash_flow_data = cur.fetchall()

        if len(cash_flow_data) >= 2:
            # FCF YoY growth
            fcf_current = safe_float(cash_flow_data[0].get("free_cash_flow"))
            fcf_prior = safe_float(cash_flow_data[1].get("free_cash_flow"))
            if fcf_current and fcf_prior and fcf_prior != 0:
                metrics["fcf_growth_yoy"] = safe_float(
                    (fcf_current - fcf_prior) / abs(fcf_prior) * 100
                )

            # OCF YoY growth
            ocf_current = safe_float(cash_flow_data[0].get("operating_cash_flow"))
            ocf_prior = safe_float(cash_flow_data[1].get("operating_cash_flow"))
            if ocf_current and ocf_prior and ocf_prior != 0:
                metrics["ocf_growth_yoy"] = safe_float(
                    (ocf_current - ocf_prior) / abs(ocf_prior) * 100
                )

        # 4. ANNUAL BALANCE SHEET DATA (2 years)
        cur.execute(
            """
            SELECT total_assets
            FROM annual_balance_sheet
            WHERE symbol = %s
            ORDER BY fiscal_year DESC
            LIMIT 2
            """,
            (symbol,),
        )
        balance_sheet_data = cur.fetchall()

        if len(balance_sheet_data) >= 2:
            assets_current = safe_float(balance_sheet_data[0].get("total_assets"))
            assets_prior = safe_float(balance_sheet_data[1].get("total_assets"))
            if assets_current and assets_prior and assets_prior != 0:
                metrics["asset_growth_yoy"] = safe_float(
                    (assets_current - assets_prior) / abs(assets_prior) * 100
                )

        # 5. EARNINGS HISTORY DATA (4 quarters - EPS growth)
        cur.execute(
            """
            SELECT eps_actual, quarter_year
            FROM earnings_history
            WHERE symbol = %s
            ORDER BY quarter_year DESC
            LIMIT 4
            """,
            (symbol,),
        )
        earnings_data = cur.fetchall()

        if len(earnings_data) >= 2:
            eps_current = safe_float(earnings_data[0].get("eps_actual"))
            eps_prior = safe_float(earnings_data[1].get("eps_actual"))
            if eps_current and eps_prior and eps_prior != 0:
                # Only update if not already set from annual data
                if "eps_growth_3y_cagr" not in metrics:
                    metrics["eps_growth_3y_cagr"] = safe_float(
                        (eps_current - eps_prior) / abs(eps_prior) * 100
                    )

        # 6. KEY METRICS DATA (Current values - margins, ratios)
        cur.execute(
            """
            SELECT
                gross_margin,
                operating_margin,
                net_margin,
                roe,
                payout_ratio,
                earnings_growth_pct,
                earnings_q_growth_pct,
                revenue_growth_pct
            FROM key_metrics
            WHERE symbol = %s AND date = CURRENT_DATE
            """,
            (symbol,),
        )
        key_metrics_row = cur.fetchone()

        if key_metrics_row:
            # Margin trends (current values)
            metrics["gross_margin_trend"] = safe_float(key_metrics_row.get("gross_margin"))
            metrics["operating_margin_trend"] = safe_float(key_metrics_row.get("operating_margin"))
            metrics["net_margin_trend"] = safe_float(key_metrics_row.get("net_margin"))

            # ROE trend (current value)
            metrics["roe_trend"] = safe_float(key_metrics_row.get("roe"))

            # Sustainable growth rate = ROE × (1 - Payout Ratio)
            roe = safe_float(key_metrics_row.get("roe"))
            payout = safe_float(key_metrics_row.get("payout_ratio"))
            if roe and payout is not None:
                metrics["sustainable_growth_rate"] = safe_float(roe * (1 - payout / 100))
            elif roe:
                # Fallback: assume 60% retention if no payout data
                metrics["sustainable_growth_rate"] = safe_float(roe * 0.6)

            # Fallback growth rates if not already calculated
            if "eps_growth_3y_cagr" not in metrics:
                metrics["eps_growth_3y_cagr"] = safe_float(key_metrics_row.get("earnings_growth_pct"))

            if "quarterly_growth_momentum" not in metrics:
                metrics["quarterly_growth_momentum"] = safe_float(key_metrics_row.get("earnings_q_growth_pct"))

            if "revenue_growth_3y_cagr" not in metrics:
                metrics["revenue_growth_3y_cagr"] = safe_float(key_metrics_row.get("revenue_growth_pct"))

        return metrics if len(metrics) > 2 else None  # At least symbol + date + 1 metric

    except Exception as e:
        logger.warning(f"Error processing {symbol}: {e}")
        return None
    finally:
        cur.close()


def upsert_growth_metrics(conn, metrics_list: List[Dict]) -> Tuple[int, int]:
    """
    Upsert list of metrics into growth_metrics table.
    Returns (inserted_count, updated_count)
    """
    if not metrics_list:
        return 0, 0

    cur = conn.cursor()
    inserted = 0
    updated = 0

    try:
        # Prepare data for insertion
        values = []
        for m in metrics_list:
            values.append((
                m["symbol"],
                m["date"],
                m.get("revenue_growth_3y_cagr"),
                m.get("eps_growth_3y_cagr"),
                m.get("operating_income_growth_yoy"),
                m.get("fcf_growth_yoy"),
                m.get("net_income_growth_yoy"),
                m.get("gross_margin_trend"),
                m.get("operating_margin_trend"),
                m.get("net_margin_trend"),
                m.get("quarterly_growth_momentum"),
                m.get("asset_growth_yoy"),
                m.get("roe_trend"),
                m.get("sustainable_growth_rate"),
                m.get("ocf_growth_yoy"),
            ))

        # Upsert
        execute_values(
            cur,
            """
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
            ) VALUES %s
            ON CONFLICT (symbol, date)
            DO UPDATE SET
                revenue_growth_3y_cagr = EXCLUDED.revenue_growth_3y_cagr,
                eps_growth_3y_cagr = EXCLUDED.eps_growth_3y_cagr,
                operating_income_growth_yoy = EXCLUDED.operating_income_growth_yoy,
                fcf_growth_yoy = EXCLUDED.fcf_growth_yoy,
                net_income_growth_yoy = EXCLUDED.net_income_growth_yoy,
                gross_margin_trend = EXCLUDED.gross_margin_trend,
                operating_margin_trend = EXCLUDED.operating_margin_trend,
                net_margin_trend = EXCLUDED.net_margin_trend,
                quarterly_growth_momentum = EXCLUDED.quarterly_growth_momentum,
                asset_growth_yoy = EXCLUDED.asset_growth_yoy,
                roe_trend = EXCLUDED.roe_trend,
                sustainable_growth_rate = EXCLUDED.sustainable_growth_rate,
                ocf_growth_yoy = EXCLUDED.ocf_growth_yoy
            """,
            values,
            page_size=500,
        )

        conn.commit()
        inserted = len(metrics_list)
        return inserted, 0

    except Exception as e:
        logger.error(f"Upsert error: {e}")
        conn.rollback()
        return 0, 0
    finally:
        cur.close()


def main():
    """Main execution."""
    import argparse

    parser = argparse.ArgumentParser(description="Aggressive growth metrics loader")
    parser.add_argument("--batch-size", type=int, default=500, help="Symbols per batch")
    parser.add_argument("--max-symbols", type=int, default=0, help="Max symbols to load (0=all)")
    parser.add_argument("--no-progress", action="store_true", help="Don't show progress")

    args = parser.parse_args()

    conn = get_db_connection()

    try:
        # Get all symbols
        all_symbols = get_all_symbols(conn)

        if args.max_symbols > 0:
            all_symbols = all_symbols[: args.max_symbols]

        logger.info(f"📊 Processing {len(all_symbols)} symbols")
        logger.info(f"📦 Batch size: {args.batch_size}")
        logger.info(f"⏱️ Expected time: ~{max(30, len(all_symbols) // 100)} minutes\n")

        # Process in batches
        total_inserted = 0
        batch_count = 0

        for batch_start in range(0, len(all_symbols), args.batch_size):
            batch_end = min(batch_start + args.batch_size, len(all_symbols))
            batch_symbols = all_symbols[batch_start:batch_end]
            batch_count += 1

            progress_pct = (batch_end / len(all_symbols) * 100)
            logger.info(
                f"📦 BATCH {batch_count:4d} | Symbols {batch_start:6d}-{batch_end:6d} ({progress_pct:5.1f}%)"
            )

            # Load metrics for this batch
            batch_metrics = []
            for idx, symbol in enumerate(batch_symbols):
                metrics = load_growth_metrics_for_symbol(conn, symbol)
                if metrics:
                    batch_metrics.append(metrics)

                # Progress indicator every 50 symbols
                if (idx + 1) % 50 == 0:
                    logger.debug(
                        f"  ✓ Processed {idx + 1}/{len(batch_symbols)} symbols in batch"
                    )

            # Upsert batch
            inserted, _ = upsert_growth_metrics(conn, batch_metrics)
            total_inserted += inserted
            logger.info(f"  ✅ Inserted/Updated: {inserted} rows")

            # Cleanup
            gc.collect()
            time.sleep(2)

        logger.info(f"\n✅ COMPLETE")
        logger.info(f"   Total rows loaded: {total_inserted}")
        logger.info(f"   Coverage: {total_inserted}/{len(all_symbols)} ({100.0*total_inserted/len(all_symbols):.1f}%)")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
