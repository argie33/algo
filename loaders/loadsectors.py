#!/usr/bin/env python3
# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
Sectors & Industries Loader - Optimal Pattern.

Loads sector classifications and performance metrics.
Inherits watermarks, dedup, multi-source routing, parallelism, and bulk COPY.

Run:
    python3 loadsectors.py [--parallelism 4]
"""


from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import argparse
import logging
import os
import sys
from datetime import date
from typing import List, Optional

from optimal_loader import OptimalLoader

# >>> dotenv-autoload >>>
from pathlib import Path as _DotenvPath
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _DotenvPath(__file__).resolve().parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass
# <<< dotenv-autoload <<<

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class SectorsLoader(OptimalLoader):
    table_name = "sector_performance"
    primary_key = ("sector", "date")
    watermark_field = "date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute sector performance metrics from price_daily + company_profile."""
        import psycopg2
        conn = None
        try:
            conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", "5432")),
                user=os.getenv("DB_USER", "stocks"),
                password=credential_manager.get_db_credentials()["password"],
                database=os.getenv("DB_NAME", "stocks"),
            )
            with conn.cursor() as cur:
                cur.execute("""
                    WITH price_lookback AS (
                        SELECT pd.symbol, pd.date, pd.close,
                               LAG(pd.close, 252) OVER (PARTITION BY pd.symbol ORDER BY pd.date) AS c_1y,
                               ROW_NUMBER() OVER (PARTITION BY pd.symbol ORDER BY pd.date DESC) AS rn
                        FROM price_daily pd
                        WHERE pd.date >= CURRENT_DATE - INTERVAL '400 days'
                          AND pd.close > 0
                    ),
                    latest AS (
                        SELECT symbol, close, c_1y FROM price_lookback WHERE rn = 1
                    ),
                    ytd_starts AS (
                        SELECT DISTINCT ON (symbol) symbol, close AS ytd_open
                        FROM price_daily
                        WHERE date >= DATE_TRUNC('year', CURRENT_DATE)
                          AND close > 0
                        ORDER BY symbol, date ASC
                    ),
                    sector_agg AS (
                        SELECT cp.sector,
                               COUNT(*) AS stock_count,
                               AVG(CASE WHEN ys.ytd_open > 0
                                        THEN (l.close - ys.ytd_open) / ys.ytd_open * 100
                                   END) AS perf_ytd,
                               AVG(CASE WHEN l.c_1y > 0
                                        THEN (l.close - l.c_1y) / l.c_1y * 100
                                   END) AS perf_1y
                        FROM latest l
                        JOIN company_profile cp ON cp.ticker = l.symbol
                        LEFT JOIN ytd_starts ys ON ys.symbol = l.symbol
                        WHERE cp.sector IS NOT NULL AND cp.sector <> ''
                        GROUP BY cp.sector
                        HAVING COUNT(*) >= 3
                    )
                    SELECT sector, stock_count, perf_ytd, perf_1y FROM sector_agg ORDER BY sector
                """)
                rows = cur.fetchall()

            today = date.today()
            return [
                {
                    "sector": r[0],
                    "date": today,
                    "return_pct": round(float(r[2] or 0), 4),  # YTD return
                    "relative_strength": round((float(r[3] or 0) - 100) / 100, 4),  # 1Y as RS proxy
                }
                for r in rows
            ]
        except Exception as e:
            logging.warning(f"Sector metrics query failed: {e}")
            return None
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def transform(self, rows):
        """Rows are clean."""
        return rows

    def _validate_row(self, row: dict) -> bool:
        """Validate sector row."""
        if not super()._validate_row(row):
            return False
        return row.get("sector") is not None and row.get("return_pct") is not None


def main():
    parser = argparse.ArgumentParser(description="Optimal sectors loader")
    parser.add_argument("--parallelism", type=int, default=8, help="Concurrent workers")
    args = parser.parse_args()

    loader = SectorsLoader()
    try:
        stats = loader.run(["sectors"], parallelism=args.parallelism)
    finally:
        loader.close()

    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
