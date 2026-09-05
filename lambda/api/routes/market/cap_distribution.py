"""Handler for /api/market/cap-distribution.

Split out of lambda/api/routes/market.py 2026-09-05 (file-size-ratchet decomposition).
"""

from __future__ import annotations

from typing import Any

from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    db_route_handler,
    json_response,
    raise_api_error,
    safe_dict_convert,
    safe_json_serialize,
)


@db_route_handler("get cap distribution")
def _get_cap_distribution(cur: cursor) -> Any:
    # BUG FOUND 2026-08-11: this queried key_metrics for market_cap, but key_metrics has had
    # no active writer since 2026-05-21 (confirmed: not in loaders/loader_registry.py, not
    # scheduled anywhere) - this endpoint was silently serving ~3-month-stale market cap
    # categorization the whole time, with no error since the (frozen) table still had rows.
    # sec_valuations (written daily by load_sec_valuations.py, an actively-scheduled loader -
    # confirmed fresh, 5130 symbols with market_cap > 0) has the same symbol/market_cap shape
    # and is the real, current source of this data.
    # sector is in company_profile - stock_symbols has neither
    cur.execute("""
        SELECT ss.symbol, cp.sector, sv.market_cap,
            CASE
                WHEN sv.market_cap >= 200000000000 THEN 'mega_cap'
                WHEN sv.market_cap >= 10000000000 THEN 'large_cap'
                WHEN sv.market_cap >= 2000000000 THEN 'mid_cap'
                WHEN sv.market_cap >= 300000000 THEN 'small_cap'
                ELSE 'micro_cap'
            END AS market_cap_category
        FROM stock_symbols ss
        JOIN company_profile cp ON ss.symbol = cp.symbol AND cp.sector IS NOT NULL
        JOIN sec_valuations sv ON ss.symbol = sv.symbol AND sv.market_cap > 0
        WHERE ss.symbol NOT IN (SELECT symbol FROM etf_symbols)
        ORDER BY sv.market_cap DESC
        LIMIT 10000
    """)
    rows = cur.fetchall()

    if not rows:
        # Distinguish between "no stocks loaded" vs "data quality issue"
        # Check if company_profile or sec_valuations tables are empty
        cur.execute("SELECT COUNT(*) as cnt FROM company_profile WHERE sector IS NOT NULL")
        profile_row = safe_dict_convert(cur.fetchone())
        if not profile_row or "cnt" not in profile_row or profile_row["cnt"] is None:
            profile_count = None
        else:
            profile_count = int(profile_row["cnt"])

        cur.execute("SELECT COUNT(*) as cnt FROM sec_valuations WHERE market_cap > 0")
        metrics_row = safe_dict_convert(cur.fetchone())
        if not metrics_row or "cnt" not in metrics_row or metrics_row["cnt"] is None:
            metrics_count = None
        else:
            metrics_count = int(metrics_row["cnt"])

        if profile_count is None or metrics_count is None or profile_count == 0 or metrics_count == 0:
            raise_api_error(
                503,
                "incomplete_data",
                f"Market cap data not fully loaded. company_profile: {profile_count} records, "
                f"sec_valuations: {metrics_count} records. Data loaders may not have completed.",
            )

        return json_response(
            200,
            {
                "by_category": {},
                "by_sector": {},
                "summary": {
                    "total_stocks": 0,
                    "total_market_cap": 0,
                    "largest_cap": None,
                    "category_distribution": {},
                },
            },
        )

    stocks = [safe_json_serialize(dict(r)) for r in rows]

    # CRITICAL: Validate market cap data exists for all stocks before using in calculations
    # Market cap missing/None breaks sector concentration limits used by position sizing
    missing_cap = [s.get("symbol", "unknown") for s in stocks if "market_cap" not in s or s.get("market_cap") is None]
    if missing_cap:
        raise ValueError(
            f"[MARKET DATA CRITICAL] {len(missing_cap)} stocks missing market_cap: {missing_cap[:10]}. "
            f"Market cap required for sector concentration calculations used in position sizing. "
            f"Cannot compute accurate sector distribution without complete market cap data. "
            f"Check that price_daily loader populated market_cap for all universe symbols."
        )

    total_cap = sum(s["market_cap"] for s in stocks if s["market_cap"])
    if total_cap <= 0:
        raise ValueError(
            f"[MARKET DATA CRITICAL] Total market cap is {total_cap} (must be > 0). "
            f"All stocks have zero market cap - data quality issue. "
            f"Check price_daily loader."
        )

    by_category: dict[Any, dict[str, Any]] = {}
    by_sector: dict[Any, dict[str, Any]] = {}

    for stock in stocks:
        # Market cap guaranteed to exist by validation above; no .get() fallback
        cap = stock["market_cap"]
        if cap is None or cap <= 0:
            raise ValueError(
                f"[MARKET DATA CRITICAL] {stock.get('symbol', 'unknown')}: "
                f"market_cap is {cap} after validation passed. Data integrity error."
            )
        category = stock.get("market_cap_category", "unknown")
        sector = stock.get("sector", "unknown")

        if category not in by_category:
            by_category[category] = {"count": 0, "total_cap": 0, "stocks": []}
        by_category[category]["count"] += 1
        by_category[category]["total_cap"] += cap
        by_category[category]["stocks"].append(stock["symbol"])

        if sector not in by_sector:
            by_sector[sector] = {"count": 0, "total_cap": 0, "pct_of_market": 0}
        by_sector[sector]["count"] += 1
        by_sector[sector]["total_cap"] += cap

    for sector in by_sector:
        if total_cap > 0:
            by_sector[sector]["pct_of_market"] = round(by_sector[sector]["total_cap"] / total_cap * 100, 2)

    category_dist = {}
    for cat in by_category:
        if total_cap > 0:
            pct = by_category[cat]["total_cap"] / total_cap * 100
            category_dist[cat] = {
                "count": by_category[cat]["count"],
                "pct_of_market": round(pct, 2),
                "total_cap": by_category[cat]["total_cap"],
                "avg_cap": (
                    round(by_category[cat]["total_cap"] / by_category[cat]["count"], 0)
                    if by_category[cat]["count"] > 0
                    else 0
                ),
            }

    sector_dist = {}
    for sector in sorted(by_sector.keys(), key=lambda s: by_sector[s]["total_cap"], reverse=True):
        sector_dist[sector] = {
            "count": by_sector[sector]["count"],
            "total_cap": by_sector[sector]["total_cap"],
            "pct_of_market": by_sector[sector]["pct_of_market"],
            "avg_cap": (
                round(by_sector[sector]["total_cap"] / by_sector[sector]["count"], 0)
                if by_sector[sector]["count"] > 0
                else 0
            ),
        }

    freshness = check_data_freshness(cur, "stock_symbols", "created_at", warning_days=7)

    # CRITICAL FAIL-FAST: Market cap extremes must exist, no defaults to 0
    market_caps = [s["market_cap"] for s in stocks if s["market_cap"] and s["market_cap"] > 0]
    if not market_caps:
        raise ValueError(
            "[MARKET DATA CRITICAL] No valid market cap values found in stocks list. "
            "Cannot compute largest/smallest market cap without data. "
            "Check price_daily loader populated valid market caps."
        )

    largest_cap = max(market_caps)
    smallest_cap = min(market_caps)

    return json_response(
        200,
        {
            "by_category": {
                k: {
                    "count": v["count"],
                    "total_cap": v["total_cap"],
                    "pct_of_market": (round(v["total_cap"] / total_cap * 100, 2) if total_cap > 0 else None),
                    "avg_cap": (round(v["total_cap"] / v["count"], 0) if v["count"] > 0 else None),
                }
                for k, v in by_category.items()
            },
            "by_sector": sector_dist,
            "summary": {
                "total_stocks": len(stocks),
                "total_market_cap": total_cap,
                "largest_cap": largest_cap,
                "smallest_cap": smallest_cap,
                "category_distribution": category_dist,
            },
        },
        data_freshness=freshness,
    )
