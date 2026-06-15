#!/usr/bin/env python3
"""
Enrich buy_sell_daily with technical indicators from technical_data_daily.

This loader populates NULL technical columns in buy_sell_daily with data from
technical_data_daily. Fixes signals that were created before technical data
was available or when the technical_data_daily loader was incomplete.

Run: python3 loaders/enrich_buy_sell_daily_technical.py [--since YYYY-MM-DD] [--symbols SYM1,SYM2]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

def enrich_technical_data(
    since: Optional[date] = None, symbols: Optional[List[str]] = None
) -> dict:
    """
    Enrich buy_sell_daily with technical data from technical_data_daily.

    Args:
        since: Only update records from this date onward (default: 7 days ago)
        symbols: Only update these symbols (default: all)

    Returns:
        Dict with stats: {updated: count, checked: count, errors: []}
    """
    stats = {"updated": 0, "checked": 0, "errors": []}

    if since is None:
        since = date.today() - timedelta(days=7)

    try:
        with DatabaseContext("write") as cur:
            # Build WHERE clause
            where_parts = ["bsd.date >= %s"]
            params = [since]

            if symbols:
                placeholders = ",".join(["%s"] * len(symbols))
                where_parts.append(f"bsd.symbol IN ({placeholders})")
                params.extend(symbols)

            where_clause = " AND ".join(where_parts)

            # Find records with NULL technical data
            cur.execute(
                """
                SELECT bsd.id, bsd.symbol, bsd.date,
                       COUNT(CASE WHEN bsd.rsi IS NULL THEN 1 END) as has_null_rsi
                FROM buy_sell_daily bsd
                WHERE {where_clause}
                AND (bsd.rsi IS NULL OR bsd.sma_50 IS NULL OR bsd.sma_200 IS NULL
                     OR bsd.ema_21 IS NULL OR bsd.atr IS NULL OR bsd.adx IS NULL)
                GROUP BY bsd.id, bsd.symbol, bsd.date
            """,
                params,
            )

            records_to_update = cur.fetchall()
            stats["checked"] = len(records_to_update)

            if not records_to_update:
                logger.info(f"No records with NULL technical data found since {since}")
                return stats

            logger.info(
                f"Found {len(records_to_update)} records with NULL technical data, enriching..."
            )

            # Update each record with technical data
            for record_id, symbol, signal_date in [
                (r[0], r[1], r[2]) for r in records_to_update
            ]:
                try:
                    # Fetch technical data for this symbol and date
                    cur.execute(
                        """
                        SELECT rsi, sma_50, sma_200, ema_21, atr, adx, mansfield_rs
                        FROM technical_data_daily
                        WHERE symbol = %s AND date = %s
                    """,
                        (symbol, signal_date),
                    )

                    tech_row = cur.fetchone()
                    if not tech_row:
                        # Try previous day's data if current day missing
                        cur.execute(
                            """
                            SELECT rsi, sma_50, sma_200, ema_21, atr, adx, mansfield_rs
                            FROM technical_data_daily
                            WHERE symbol = %s AND date <= %s
                            ORDER BY date DESC
                            LIMIT 1
                        """,
                            (symbol, signal_date),
                        )
                        tech_row = cur.fetchone()

                    if tech_row:
                        rsi, sma_50, sma_200, ema_21, atr, adx, mansfield_rs = tech_row
                        cur.execute(
                            """
                            UPDATE buy_sell_daily
                            SET rsi = COALESCE(rsi, %s),
                                sma_50 = COALESCE(sma_50, %s),
                                sma_200 = COALESCE(sma_200, %s),
                                ema_21 = COALESCE(ema_21, %s),
                                atr = COALESCE(atr, %s),
                                adx = COALESCE(adx, %s),
                                mansfield_rs = COALESCE(mansfield_rs, %s)
                            WHERE id = %s
                        """,
                            (
                                rsi,
                                sma_50,
                                sma_200,
                                ema_21,
                                atr,
                                adx,
                                mansfield_rs,
                                record_id,
                            ),
                        )
                        stats["updated"] += 1
                    else:
                        logger.debug(
                            f"{symbol} {signal_date}: No technical data available"
                        )
                except Exception as e:
                    error_msg = f"{symbol} {signal_date}: {str(e)[:100]}"
                    stats["errors"].append(error_msg)
                    logger.warning(error_msg)

        logger.info(
            f"Enrichment complete: {stats['updated']} records updated, {len(stats['errors'])} errors"
        )
        return stats

    except Exception as e:
        logger.error(f"Enrichment failed: {e}")
        raise

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Enrich buy_sell_daily with technical data"
    )
    parser.add_argument(
        "--since",
        type=str,
        help="Update from this date (YYYY-MM-DD), default: 7 days ago",
    )
    parser.add_argument(
        "--symbols", type=str, help="Comma-separated symbols to update (default: all)"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    since = None
    if args.since:
        try:
            since = datetime.strptime(args.since, "%Y-%m-%d").date()
        except ValueError:
            logger.error(f"Invalid date format: {args.since}. Use YYYY-MM-DD")
            return 1

    symbols = None
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]

    try:
        stats = enrich_technical_data(since=since, symbols=symbols)
        logger.info(f"Updated {stats['updated']} records")
        if stats["errors"]:
            logger.warning(f"{len(stats['errors'])} errors occurred")
            return 1
        return 0
    except Exception as e:
        logger.error(f"Failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
