#!/usr/bin/env python3
from utils.db.context import DatabaseContext

db = DatabaseContext('read')
with db as cur:
    # The EXACT query from the API for a single symbol
    query = """
        WITH max_price_date AS (
            SELECT MAX(date) AS max_date FROM price_daily
        )
        SELECT
            sc.symbol,
            COALESCE(ss.security_name, sc.symbol) AS company_name,
            cp.sector,
            cp.industry,
            sc.composite_score, sc.momentum_score, sc.quality_score,
            sc.value_score, sc.growth_score, sc.positioning_score, sc.stability_score,
            sc.rs_percentile, sc.data_completeness,
            sc.updated_at AS last_updated,
            pl.close AS current_price,
            pl.close AS price
        FROM stock_scores sc
        JOIN stock_symbols ss ON ss.symbol = sc.symbol
        LEFT JOIN company_profile cp ON cp.ticker = sc.symbol
        LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
        LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
        LEFT JOIN growth_metrics gm ON gm.symbol = sc.symbol
        LEFT JOIN stability_metrics sm ON sm.symbol = sc.symbol
        LEFT JOIN positioning_metrics pm ON pm.symbol = sc.symbol
        LEFT JOIN LATERAL (
            SELECT close, date
            FROM price_daily
            WHERE symbol = sc.symbol
            ORDER BY date DESC
            LIMIT 1
        ) pl ON true
        WHERE sc.composite_score > 0
        AND (ss.symbol NOT IN (SELECT symbol FROM etf_symbols) AND (ss.etf IS NULL OR ss.etf = 'N'))
        AND sc.data_completeness >= 70
        AND sc.symbol = %s
    """

    cur.execute(query, ("AMSC",))
    row = cur.fetchone()

    if row:
        print("API Query Result for AMSC:")
        print(f"  symbol: {row['symbol']}")
        print(f"  growth_score: {row['growth_score']}")
        print(f"  composite_score: {row['composite_score']}")
        print(f"  data_completeness: {row['data_completeness']}")
    else:
        print("NO RESULT - Symbol doesn't meet filters!")

        # Check why
        cur.execute("SELECT composite_score, data_completeness FROM stock_scores WHERE symbol = 'AMSC'")
        row = cur.fetchone()
        if row:
            print(f"  composite_score: {row['composite_score']} (need > 0)")
            print(f"  data_completeness: {row['data_completeness']} (need >= 70)")
