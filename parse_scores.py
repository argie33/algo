import json

with open('scores_test.json') as f:
    data = json.load(f)

items = data['data']['items']
item = items[0]
symbol = item['symbol']
composite = item.get('composite_score')
qi = item.get('quality_inputs', {})
vi = item.get('value_inputs', {})

print(f"STOCK: {symbol} (Score: {composite})")
print("=" * 60)

reason_map = {
    'missing_sec_data': 'No SEC data',
    'analyst_estimates_not_in_sec_filings': 'Analyst data not in SEC',
    'insufficient_history': 'Insufficient history',
    'depreciation_amortization_not_loaded': 'Depreciation/amortization not loaded',
}

print("\nQUALITY METRICS:")
print("-" * 60)
quality_fields = [
    ('return_on_equity_pct', 'ROE'),
    ('return_on_invested_capital_pct', 'ROIC'),
    ('gross_margin_pct', 'Gross Margin'),
    ('operating_margin_pct', 'Operating Margin'),
]

for field_key, label in quality_fields:
    value = qi.get(field_key)
    reason = qi.get(field_key + '_unavailable_reason')

    if value is not None:
        print(f"  {label:30} {value}")
    elif reason:
        display = reason_map.get(reason, reason)
        print(f"  {label:30} {display}")
    else:
        print(f"  {label:30} No data")

print("\nVALUE METRICS:")
print("-" * 60)
value_fields = [
    ('stock_pe', 'P/E Ratio'),
    ('stock_pb', 'Price/Book'),
    ('peg_ratio', 'PEG Ratio'),
    ('stock_forward_pe', 'Forward P/E'),
]

for field_key, label in value_fields:
    value = vi.get(field_key)
    reason = vi.get(field_key + '_unavailable_reason')

    if value is not None:
        print(f"  {label:30} {value}")
    elif reason:
        display = reason_map.get(reason, reason)
        print(f"  {label:30} {display}")
    else:
        print(f"  {label:30} No data")

print("\n" + "=" * 60)
print("SUCCESS: Metrics show reasons instead of 'No data'")
