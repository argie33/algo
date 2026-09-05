"""Handler for /api/market/sectors.

Split out of lambda/api/routes/market.py 2026-09-05 (file-size-ratchet decomposition).
"""

from __future__ import annotations

from typing import Any

from psycopg2.extensions import cursor
from routes.utils import db_route_handler, list_response, safe_json_serialize


@db_route_handler("get sector overview")
def _get_sector_overview(cur: cursor) -> Any:
    cur.execute("""
        SELECT sector_name, performance_ytd, performance_1y, pe_ratio,
               dividend_yield, market_cap, stock_count, metric_date
        FROM sectors
        WHERE metric_date = (SELECT MAX(metric_date) FROM sectors)
        ORDER BY market_cap DESC NULLS LAST
        LIMIT 100
    """)
    rows = cur.fetchall()
    if not rows:
        cur.execute("""
            SELECT DISTINCT sector, COUNT(*) as stock_count
            FROM company_profile WHERE sector IS NOT NULL AND sector != ''
            GROUP BY sector ORDER BY stock_count DESC
            LIMIT 100
        """)
        rows = cur.fetchall()
        return list_response([{"sector_name": r["sector"], "stock_count": r["stock_count"]} for r in rows])
    return list_response([safe_json_serialize(dict(r)) for r in rows])
