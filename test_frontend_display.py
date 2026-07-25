#!/usr/bin/env python3
"""Test what the frontend will actually display for scores data.

Simulates the StockScoreAccordion React component's rendering logic.
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


# Frontend's reason mapping (from StockScoreAccordion.jsx)
REASON_MAP = {
    "missing_sec_data": "No SEC data",
    "insufficient_history": "Insufficient history",
    "no_analyst_estimates": "Analyst data unavailable",
    "analyst_estimates_not_in_sec_filings": "Analyst data not in SEC",
    "ebitda_not_extracted": "Not extracted",
    "depreciation_amortization_not_loaded": "Depreciation/amortization not loaded",
    "non_dividend_paying_stock": "Non-dividend payer",
    "api_error": "Data fetch error",
    "unprofitable_stock": "Unprofitable stock",
    "missing_price_or_shares": "Missing price/shares",
    "missing_finra_data": "FINRA data unavailable",
    "missing_price_data": "Price data unavailable",
}


# Frontend schemas from StockScoreAccordion.jsx
QUALITY_SCHEMA = [
    {'key': 'return_on_equity_pct', 'label': 'ROE', 'used': True},
    {'key': 'return_on_assets_pct', 'label': 'ROA', 'used': True},
    {'key': 'return_on_invested_capital_pct', 'label': 'ROIC', 'used': True},
    {'key': 'profit_margin_pct', 'label': 'Profit Margin', 'used': True},
    {'key': 'operating_margin_pct', 'label': 'Operating Margin', 'used': True},
    {'key': 'debt_to_equity', 'label': 'Debt / Equity', 'used': True},
]

VALUE_SCHEMA = [
    {'key': 'stock_pe', 'label': 'P/E', 'used': True},
    {'key': 'stock_forward_pe', 'label': 'Forward P/E'},
    {'key': 'stock_pb', 'label': 'P/B', 'used': True},
    {'key': 'stock_ps', 'label': 'P/S', 'used': True},
    {'key': 'stock_ev_ebitda', 'label': 'EV / EBITDA'},
    {'key': 'peg_ratio', 'label': 'PEG', 'used': True},
    {'key': 'stock_dividend_yield', 'label': 'Dividend Yield'},
    {'key': 'fcf_yield', 'label': 'FCF Yield', 'used': True},
]

GROWTH_SCHEMA = [
    {'key': 'revenue_growth_1y_pct', 'label': 'Revenue Growth 1Y'},
    {'key': 'eps_growth_1y_pct', 'label': 'EPS Growth 1Y'},
]

MOMENTUM_SCHEMA = [
    {'key': 'momentum_3m', 'label': 'Momentum (3M)', 'used': True},
    {'key': 'momentum_6m', 'label': 'Momentum (6M)', 'used': True},
]

POSITIONING_SCHEMA = [
    {'key': 'institutional_ownership_pct', 'label': 'Inst. Ownership'},
    {'key': 'insider_ownership_pct', 'label': 'Insider Ownership'},
    {'key': 'short_interest_pct', 'label': 'Short Interest %'},
]

STABILITY_SCHEMA = [
    {'key': 'volatility_12m', 'label': 'Volatility (12M)'},
    {'key': 'beta', 'label': 'Beta'},
]


def format_reason(reason):
    """Format a reason code for display."""
    if not reason:
        return None
    return REASON_MAP.get(reason, reason)


def simulate_input_row(schema_item, inputs_obj):
    """Simulate InputRow component rendering."""
    key = schema_item['key']
    value = inputs_obj.get(key)

    # Frontend's reason extraction logic (from InputsCard)
    reason = inputs_obj.get(key + "_unavailable_reason")
    if not reason and key.endswith("_pct"):
        reason = inputs_obj.get(key[:-4] + "_unavailable_reason")
    if not reason and key.endswith("_val"):
        reason = inputs_obj.get(key[:-4] + "_unavailable_reason")
    if not reason and key.endswith("_12m"):
        reason = inputs_obj.get(key[:-4] + "_unavailable_reason")

    reason_display = format_reason(reason)

    # Determine what gets displayed
    if value is not None:
        display = f"VALUE: {value}"
    elif reason_display:
        display = f"REASON: {reason_display}"
    else:
        display = "NO DATA"

    return {
        'key': key,
        'label': schema_item['label'],
        'value': value,
        'reason': reason,
        'reason_display': reason_display,
        'displayed_as': display,
    }


def test_stock_display(symbol='AAPL'):
    """Test what will be displayed for a given stock."""
    import requests

    print("\n" + "="*70)
    print(f"FRONTEND DISPLAY TEST: {symbol}")
    print("="*70)

    try:
        # Fetch from API
        response = requests.get(f"http://localhost:3001/api/scores/stockscores?symbol={symbol}")
        if response.status_code != 200:
            print(f"API returned {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return

        data = response.json()
        if not data.get('data', {}).get('items'):
            print(f"No data for {symbol}")
            return

        stock = data['data']['items'][0]
        print(f"\n{symbol}: {stock.get('company_name')}")
        print(f"  Composite Score: {stock.get('composite_score')}")
        print(f"  Data Completeness: {stock.get('data_completeness')}%")

        # Test each factor panel
        factors = [
            ('Quality', 'quality_inputs', QUALITY_SCHEMA),
            ('Value', 'value_inputs', VALUE_SCHEMA),
            ('Growth', 'growth_inputs', GROWTH_SCHEMA),
            ('Momentum', 'momentum_inputs', MOMENTUM_SCHEMA),
            ('Positioning', 'positioning_inputs', POSITIONING_SCHEMA),
            ('Stability', 'stability_inputs', STABILITY_SCHEMA),
        ]

        for factor_name, inputs_key, schema in factors:
            inputs_obj = stock.get(inputs_key, {})
            if not inputs_obj:
                print(f"\n  [{factor_name}] NO INPUTS OBJECT IN RESPONSE!")
                continue

            print(f"\n  [{factor_name}] ({inputs_key}):")
            rows = []
            for schema_item in schema:
                if schema_item.get('used'):  # Only show "Used in Score" rows for brevity
                    row = simulate_input_row(schema_item, inputs_obj)
                    rows.append(row)
                    print(f"    [OK] {row['label']:20} -> {row['displayed_as']}")

            # Count "No Data" rows
            no_data_count = sum(1 for r in rows if r['displayed_as'] == 'NO DATA')
            if no_data_count > 0:
                print(f"    [WARN] {no_data_count}/{len(rows)} rows showing 'NO DATA' (should be 0!)")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Test a few stocks
    for symbol in ['AAPL', 'MSFT', 'GOOGL']:
        try:
            test_stock_display(symbol)
        except Exception as e:
            print(f"Failed to test {symbol}: {e}")

    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print("\nIf you see 'NO DATA' in the output above, it means:")
    print("1. The value is NULL in the database, AND")
    print("2. The reason field is also NULL or missing")
    print("\nThis should be rare (<2%) for quality metrics with 86%+ completeness.")
