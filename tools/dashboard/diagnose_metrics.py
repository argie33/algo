#!/usr/bin/env python3
"""Diagnostic script to identify why VIX and concentration are missing/wrong.

Run: python -m tools.dashboard.diagnose_metrics
"""

import logging

from tools.dashboard.api_data_layer import api_call
from tools.dashboard.error_boundary import has_error


logging.basicConfig(level=logging.DEBUG)

print("\n" + "=" * 80)
print("DIAGNOSTICS: VIX and Concentration Data")
print("=" * 80 + "\n")

# 1. Check what the markets endpoint returns
print("1. MARKETS API (/api/algo/markets)")
print("-" * 80)
try:
    mkt_response = api_call("/api/algo/markets")
    if has_error(mkt_response):
        print(f"ERROR: {mkt_response.get('_error')}")
    else:
        mkt_data = mkt_response.get("data")
        if not mkt_data:
            print("ERROR: No data in markets response")
        else:
            market_health = mkt_data.get("market_health")
            if not market_health:
                print("ERROR: No market_health in data")
            else:
                print(f"market_health keys: {list(market_health.keys())}")
                print(f"vix_level value: {market_health.get('vix_level')}")
                print(f"vix_level type: {type(market_health.get('vix_level'))}")

                if market_health.get("vix_level") is None:
                    print("\n[ERROR] vix_level is NULL in API response!")
                    print("  -> Check if load_market_health_daily has run")
                    print("  -> Check if market_health_daily table has data")
except Exception as e:
    print(f"EXCEPTION: {type(e).__name__}: {e}")

# 2. Check what the risk metrics endpoint returns
print("\n2. RISK METRICS API (/api/algo/risk-metrics)")
print("-" * 80)
try:
    risk_response = api_call("/api/algo/risk-metrics")
    if has_error(risk_response):
        print(f"ERROR: {risk_response.get('_error')}")
    else:
        risk_data = risk_response.get("data")
        if not risk_data:
            print("ERROR: No data in risk metrics response")
        else:
            conc5 = risk_data.get("top_5_concentration")

            print(f"top_5_concentration value: {conc5}")
            print(f"top_5_concentration type: {type(conc5)}")

            print("\nAll risk metrics:")
            for key in [
                "var_pct_95",
                "cvar_pct_95",
                "stressed_var_pct",
                "portfolio_beta",
                "top_5_concentration",
                "report_date",
            ]:
                val = risk_data.get(key)
                print(f"  {key}: {val} (type: {type(val).__name__})")

            if conc5 is None or conc5 == 0:
                print("\n[ERROR] top_5_concentration is None or 0!")
                print("  -> Check if concentration_report() ran in algo/risk/var.py")
                print("  -> Check if positions have current_price values")
                print("  -> Check if portfolio_value > 0")
except Exception as e:
    print(f"EXCEPTION: {type(e).__name__}: {e}")

# 3. Check positions data
print("\n3. POSITIONS API (/api/algo/positions)")
print("-" * 80)
try:
    pos_response = api_call("/api/algo/positions")
    if has_error(pos_response):
        print(f"ERROR: {pos_response.get('_error')}")
    else:
        pos_data = pos_response.get("data")
        if not pos_data:
            print("ERROR: No data in positions response")
        else:
            items = pos_data.get("items")

            print(f"Total positions: {len(items) if items else 0}")

            if items:
                # Check first position for required fields
                first = items[0]
                print("\nFirst position example:")
                print(f"  symbol: {first.get('symbol')}")
                print(f"  quantity: {first.get('quantity')}")
                print(
                    f"  current_price: {first.get('current_price')} (type: {type(first.get('current_price')).__name__})"
                )
                print(f"  position_value: {first.get('position_value')}")

                # Count how many have NULL current_price
                missing_price = sum(1 for p in items if p.get("current_price") is None)
                if missing_price > 0:
                    print(f"\n[ERROR] {missing_price}/{len(items)} positions have NULL current_price!")
                    print("  -> These are excluded from concentration calculation")
                    print("  -> Check how position_price is populated in positions API")
            else:
                print("[ERROR] No positions returned!")
except Exception as e:
    print(f"EXCEPTION: {type(e).__name__}: {e}")

# 4. Check portfolio data
print("\n4. PORTFOLIO API (/api/algo/portfolio)")
print("-" * 80)
try:
    port_response = api_call("/api/algo/portfolio")
    if has_error(port_response):
        print(f"ERROR: {port_response.get('_error')}")
    else:
        port_data = port_response.get("data")
        if not port_data:
            print("ERROR: No data in portfolio response")
        else:
            print(f"total_portfolio_value: {port_data.get('total_portfolio_value')}")
            print(f"position_count: {port_data.get('position_count')}")
            print(f"largest_position_pct: {port_data.get('largest_position_pct')}")

            pv = port_data.get("total_portfolio_value")
            if pv is None or pv <= 0:
                print(f"\n[ERROR] total_portfolio_value is {pv}!")
                print("  -> This makes concentration calculation impossible")
except Exception as e:
    print(f"EXCEPTION: {type(e).__name__}: {e}")

print("\n" + "=" * 80)
print("END DIAGNOSTICS")
print("=" * 80 + "\n")
