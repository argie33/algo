#!/usr/bin/env python3
"""Industry Ranking Loader - compute daily industry momentum rankings."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date
from typing import Dict

from utils.database_context import DatabaseContext
from utils.master_data_loader import MasterDataLoader

logger = logging.getLogger(__name__)

class IndustryRankingLoader(MasterDataLoader):
    """Compute industry rankings from daily price data."""

    def run(self, run_date: date = None) -> Dict:
        """Compute industry rankings for a given date."""
        if run_date is None:
            run_date = date.today()

        try:
            with DatabaseContext('write') as cur:
                # Get max date in price_daily
                cur.execute("SELECT MAX(date) FROM price_daily")
                result = cur.fetchone()
                max_price_date = result[0] if result else None
                if not max_price_date:
                    logger.warning("No price data available")
                    return {"success": False, "rows": 0}

                data_date = max_price_date

                # Compute 20-day momentum for every symbol in a single query using
                # window functions. ROW_NUMBER orders prices newest-first; we take
                # the most recent close (rn=1) and the oldest close in a 21-row
                # window (rn=LEAST(cnt,21)) so that symbols with fewer than 21
                # trading days in the window still get a valid return.
                cur.execute("""
                    WITH price_window AS (
                        SELECT
                            p.symbol,
                            f.industry,
                            p.close,
                            ROW_NUMBER() OVER (PARTITION BY p.symbol ORDER BY p.date DESC) AS rn,
                            COUNT(*)    OVER (PARTITION BY p.symbol)                        AS cnt
                        FROM price_daily p
                        JOIN stock_fundamentals f ON p.symbol = f.symbol
                        JOIN stock_symbols      s ON p.symbol = s.symbol
                        WHERE f.industry IS NOT NULL
                          AND p.date <= %s
                          AND p.date >= %s - INTERVAL '45 days'
                    )
                    SELECT
                        symbol,
                        industry,
                        MAX(close) FILTER (WHERE rn = 1)              AS current_close,
                        MAX(close) FILTER (WHERE rn = LEAST(cnt, 21)) AS old_close
                    FROM price_window
                    WHERE rn <= 21
                    GROUP BY symbol, industry
                    HAVING MAX(cnt) >= 2
                """, (data_date, data_date))

                symbol_rows = cur.fetchall()
                if not symbol_rows:
                    logger.warning(f"No industry data for {data_date}")
                    return {"success": False, "rows": 0}

                # Aggregate per-symbol momentum into per-industry average
                industry_momentum: Dict[str, list] = {}
                for symbol, industry, current_close, old_close in symbol_rows:
                    if not industry or not current_close or not old_close:
                        continue
                    momentum = (float(current_close) - float(old_close)) / float(old_close) * 100
                    industry_momentum.setdefault(industry, []).append(momentum)

                # Rank industries by avg momentum (rank 1 = strongest)
                ranked = sorted(
                    [
                        (industry, sum(scores) / len(scores), len(scores))
                        for industry, scores in industry_momentum.items()
                    ],
                    key=lambda x: x[1],
                    reverse=True,
                )

                # Delete existing rankings for this date, then bulk-insert
                cur.execute("DELETE FROM industry_ranking WHERE date_recorded = %s", (data_date,))

                inserted = 0
                for rank, (industry, momentum, _count) in enumerate(ranked, 1):
                    cur.execute("""
                        INSERT INTO industry_ranking
                            (industry, date_recorded, current_rank, momentum_score)
                        VALUES (%s, %s, %s, %s)
                    """, (industry, data_date, rank, round(momentum, 4)))
                    inserted += 1

                # Back-fill historical rank columns from prior days' records.
                # SwingTraderScore._sector_component() reads rank_4w_ago to compute
                # industry acceleration bonus/penalty â€" without this it's always 0.
                cur.execute("""
                    UPDATE industry_ranking today
                    SET
                        rank_1w_ago  = (
                            SELECT past.current_rank FROM industry_ranking past
                            WHERE past.industry      = today.industry
                              AND past.date_recorded <= today.date_recorded - INTERVAL '7 days'
                            ORDER BY past.date_recorded DESC LIMIT 1
                        ),
                        rank_4w_ago  = (
                            SELECT past.current_rank FROM industry_ranking past
                            WHERE past.industry      = today.industry
                              AND past.date_recorded <= today.date_recorded - INTERVAL '28 days'
                            ORDER BY past.date_recorded DESC LIMIT 1
                        ),
                        rank_12w_ago = (
                            SELECT past.current_rank FROM industry_ranking past
                            WHERE past.industry      = today.industry
                              AND past.date_recorded <= today.date_recorded - INTERVAL '84 days'
                            ORDER BY past.date_recorded DESC LIMIT 1
                        )
                    WHERE today.date_recorded = %s
                """, (data_date,))

                logger.info(f"Inserted {inserted} industry rankings for {data_date}")
                return {"success": True, "rows": inserted, "date": str(data_date)}

        except Exception as e:
            logger.error(f"Industry ranking load failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

def main():
    from datetime import date
    import argparse

    parser = argparse.ArgumentParser(description='Load industry ranking data')
    parser.add_argument('--symbols', type=str, help='(Unused - for compatibility)')
    parser.add_argument('--parallelism', type=int, help='(Unused - for compatibility)')
    parser.add_argument('--date', type=str, help='Date to load (YYYY-MM-DD)')
    args = parser.parse_args()

    run_date = None
    if args.date:
        run_date = date.fromisoformat(args.date)

    loader = IndustryRankingLoader()
    result = loader.run(run_date)

    if result["success"]:
        logger.info(f"SUCCESS: {result['rows']} industries ranked for {result.get('date')}")
        return 0
    else:
        logger.error(f"FAILED: {result.get('error', 'unknown error')}")
        return 1

if __name__ == '__main__':
    sys.exit(main())

