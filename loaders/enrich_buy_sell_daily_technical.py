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

from utils.db.context import DatabaseContext


logger = logging.getLogger(__name__)


def enrich_technical_data(
    since: date | None = None, symbols: list[str] | None = None, min_success_rate: float = 0.95
) -> dict:
    """
    Enrich buy_sell_daily with technical data from technical_data_daily.

    Fail-close: If enrichment success rate falls below min_success_rate, raises RuntimeError.
    This prevents buy_sell_daily from being marked complete with degraded signal quality.

    Args:
        since: Only update records from this date onward (default: 7 days ago)
        symbols: Only update these symbols (default: all)
        min_success_rate: Min fraction of records that must be enriched (0.0-1.0). Default 95%.

    Returns:
        Dict with stats: {updated: count, checked: count, errors: []}

    Raises:
        RuntimeError: If enrichment success rate < min_success_rate (fail-close)
    """
    stats: dict = {"updated": 0, "checked": 0, "errors": [], "nulls_remaining": 0}

    if since is None:
        since = date.today() - timedelta(days=7)

    try:
        with DatabaseContext("write") as cur:
            # Build WHERE clause
            where_parts = ["bsd.date >= %s"]
            params: list = [since]

            if symbols:
                placeholders = ",".join(["%s"] * len(symbols))
                where_parts.append(f"bsd.symbol IN ({placeholders})")
                params.extend(symbols)

            where_clause = " AND ".join(where_parts)

            # Find records with NULL technical data
            cur.execute(
                f"""
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

            # CLUSTER 4 FIX: Batch-fetch all technical data instead of per-symbol queries
            # N+1 Problem: Previous code executed 1 query per record (could be 10,000+ queries)
            # Solution: Fetch all relevant technical data in 1-2 queries, use local dict for lookups
            records_list = [(r[0], r[1], r[2]) for r in records_to_update]
            if records_list:
                symbols_set = {r[1] for r in records_list}
                min_date = min(r[2] for r in records_list)
                max_date = max(r[2] for r in records_list)

                # Fetch all technical data for the relevant symbols and date range
                # This single query replaces thousands of per-symbol queries
                placeholders = ",".join(["%s"] * len(symbols_set))
                cur.execute(
                    f"""
                    SELECT symbol, date, rsi, sma_50, sma_200, ema_21, atr, adx, mansfield_rs
                    FROM technical_data_daily
                    WHERE symbol IN ({placeholders})
                    AND date >= %s - INTERVAL '10 days'
                    AND date <= %s
                    ORDER BY symbol, date DESC
                """,
                    [*symbols_set, min_date, max_date],
                )

                # Build a nested dict: tech_data[symbol][date] = row_data
                tech_data_by_symbol_date: dict = {}
                tech_data_by_symbol_latest: dict = {}  # Fallback: latest data for each symbol
                for row in cur.fetchall():
                    symbol, row_date, rsi, sma_50, sma_200, ema_21, atr, adx, mansfield_rs = row
                    if symbol not in tech_data_by_symbol_date:
                        tech_data_by_symbol_date[symbol] = {}
                    if row_date not in tech_data_by_symbol_date[symbol]:
                        tech_data_by_symbol_date[symbol][row_date] = (
                            rsi,
                            sma_50,
                            sma_200,
                            ema_21,
                            atr,
                            adx,
                            mansfield_rs,
                        )
                    # Track latest data per symbol for fallback
                    if symbol not in tech_data_by_symbol_latest:
                        tech_data_by_symbol_latest[symbol] = (
                            rsi,
                            sma_50,
                            sma_200,
                            ema_21,
                            atr,
                            adx,
                            mansfield_rs,
                        )

            # Update each record with technical data (now using precomputed data)
            for record_id, symbol, signal_date in records_list:
                try:
                    # O(1) lookup: tech_data was precomputed for all symbols/dates
                    tech_row = None
                    if records_list:
                        # Try exact date first
                        if symbol in tech_data_by_symbol_date and signal_date in tech_data_by_symbol_date[symbol]:
                            tech_row = tech_data_by_symbol_date[symbol][signal_date]
                        # Fallback: use latest data for this symbol
                        elif symbol in tech_data_by_symbol_latest:
                            tech_row = tech_data_by_symbol_latest[symbol]

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
                        stats["nulls_remaining"] += 1
                        logger.debug(
                            f"{symbol} {signal_date}: No technical data available"
                        )
                except Exception as e:
                    error_msg = f"{symbol} {signal_date}: {str(e)[:100]}"
                    stats["errors"].append(error_msg)
                    stats["nulls_remaining"] += 1
                    logger.warning(error_msg)

            # Check if enrichment coverage meets minimum threshold (fail-close)
            checked: int = stats.get("checked", 0) or 0
            if checked > 0:
                updated: int = stats.get("updated", 0) or 0
                nulls: int = stats.get("nulls_remaining", 0) or 0
                success_rate = updated / checked
                logger.info(
                    f"Enrichment complete: {updated}/{checked} records updated "
                    f"({success_rate*100:.1f}%), {nulls} remain with NULL technical fields"
                )

                if success_rate < min_success_rate:
                    errors_sample = stats["errors"][:3] if stats.get("errors") else []
                    raise RuntimeError(
                        f"[ENRICHMENT] Technical data enrichment failed coverage threshold: "
                        f"{updated}/{checked} records enriched ({success_rate*100:.1f}%), "
                        f"need >={min_success_rate*100:.0f}%. {nulls} records have NULL technical fields. "
                        f"Cannot load buy_sell_daily with degraded signal quality—failing load to prevent silent data corruption. "
                        f"Errors: {errors_sample}"
                    )
            else:
                logger.info("No records requiring enrichment")

        return stats

    except RuntimeError:
        raise
    except Exception as e:
        logger.error(f"Enrichment failed: {e}")
        raise RuntimeError(f"[ENRICHMENT] Unexpected error during enrichment: {e}") from e


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
    parser.add_argument(
        "--min-success-rate",
        type=float,
        default=0.95,
        help="Min fraction of records that must be enriched (0.0-1.0), default: 0.95 (95%)",
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
        stats = enrich_technical_data(
            since=since, symbols=symbols, min_success_rate=args.min_success_rate
        )
        logger.info(f"Updated {stats['updated']} records")
        if stats["errors"]:
            logger.warning(f"{len(stats['errors'])} errors occurred")
            return 1
        return 0
    except RuntimeError as e:
        # Fail-close: enrichment didn't meet quality threshold
        logger.critical(f"Enrichment failed: {e}")
        return 1
    except Exception as e:
        logger.error(f"Failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
