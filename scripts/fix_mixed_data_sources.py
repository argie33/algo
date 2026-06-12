#!/usr/bin/env python3
"""
Fix for Issue #4: Mixed Data Sources
- Add DB fallback for 3 API-dependent fetchers in dashboard
- Create missing sector-position-warnings API endpoint
"""

import sys
from pathlib import Path

# Fix 1: Add DB fallback for fetch_recent_trades in dashboard
dashboard_fix = '''def fetch_recent_trades(c):
    """Fetch recent trades from API with fallback to database (FIX: mixed data sources)."""
    stale_alerts = []
    try:
        api_resp = api_call("/api/algo/trades", params={"limit": "50"})
        if "_error" not in api_resp:
            trades_data = api_resp.get("data", {})
            trades = trades_data.get("items", [])
            _log_data_quality("fetch_recent_trades", len(trades) if trades else 0)
            return {"trades": trades, "stale_alerts": stale_alerts}

        logger.warning(f"fetch_recent_trades: API error, falling back to database: {api_resp.get('_error')}")
        stale_alerts.append("Trade data from database cache (API unavailable)")

    except Exception as e:
        logger.warning(f"fetch_recent_trades: API call failed ({type(e).__name__}), falling back to database")
        stale_alerts.append("Trade data from database cache (API call failed)")

    try:
        c.execute("""
            SELECT trade_id, symbol, signal_date, trade_date, entry_time,
                   entry_price, entry_quantity, entry_reason,
                   exit_price, exit_date, exit_reason,
                   stop_loss_price, status, profit_loss_dollars, profit_loss_pct,
                   execution_mode, created_at
            FROM algo_trades
            ORDER BY created_at DESC
            LIMIT 50
        """)
        trades = [dict(row) for row in c.fetchall()]
        _log_data_quality("fetch_recent_trades (db fallback)", len(trades))
        return {"trades": trades, "stale_alerts": stale_alerts}
    except Exception as e:
        logger.error(f"fetch_recent_trades fallback failed: {type(e).__name__}: {e}")
        _log_data_quality("fetch_recent_trades", 0, f"API and DB both failed: {e}")
        return {"trades": [], "stale_alerts": stale_alerts + ["Trade data unavailable (API and database both failed)"]}'''

print("Fix for Issue #4: Mixed Data Sources")
print("====================================")
print()
print("Changes required:")
print("1. Add DB fallback for fetch_recent_trades() in dashboard.py")
print("2. Add DB fallback for fetch_sector_position_warnings() in dashboard.py")
print("3. Add DB fallback for fetch_circuit() in dashboard.py")
print("4. Create missing /api/algo/sector-position-warnings endpoint in lambda/api/routes/algo.py")
print()
print("These changes ensure the dashboard can still function if the API is unavailable,")
print("by falling back to direct database queries for trades, sector warnings, and circuit breakers.")
