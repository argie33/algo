# Growth Metrics Loader - Strict No-Fallback Fixes

## Summary of Changes

Fixed `/home/stocks/algo/loadgrowthmetrics.py` to enforce **STRICT NO-FALLBACK POLICY**:
- ✅ Every metric requires specific data from specific sources
- ✅ If source data is missing/insufficient: metric stays NULL
- ✅ No approximations, no proxies, no assumptions
- ✅ Detailed logging explains exactly WHY metrics are NULL

## Problem Before

Your 71.3 score had 8 N/A values because:
- Silent failures with bare `except: pass` blocks
- No validation that required data exists
- No logging about WHY metrics were NULL
- Implicit fallbacks using revenue for operating income calculations

## Solution Implemented

### 1. Data Availability Diagnostics
Added `check_data_availability()` function that inspects database BEFORE calculation:
- Checks if revenue_estimates exists
- Checks if key_metrics has data
- Counts quarters in quarterly_income_statement
- Lists available item_names
- Checks for payout_ratio in quality_metrics

### 2. Strict Validation for Each Metric

#### Operating Income Growth YoY
**Required**: 5 quarters of "Operating Income" data
**If missing**: Logs "Insufficient Op Income data: X quarters (need 5)"
```
No fallback to revenue growth
No proxy calculations
Stays NULL if any quarter is invalid
```

#### FCF Growth YoY
**Required**: 5 quarters of "Free Cash Flow" data
**If missing**: Logs specific reason (insufficient data, invalid values, zero division)

#### Net Income Growth YoY
**Required**: 5 quarters of "Net Income" data with valid numeric values
**If missing**: Logs which quarter failed and why

#### Margin Trends (Gross/Operating/Net)
**Required**:
- 5+ quarters of financial data
- Revenue available for both periods
- Specific margin items (Gross Profit, Operating Income, Net Income) for current AND year-ago quarters
**If missing**: Logs which specific item is missing and which quarter

#### Quarterly Growth Momentum
**Required**:
- 8 quarters of revenue data
- Previous quarter revenue > 0
- Year-ago previous quarter revenue > 0
**If missing**: Logs specific data gap

#### Asset Growth YoY
**Required**: 5 quarters of "Total Assets" with positive year-ago value
**If missing**: Logs reason (insufficient, invalid, or zero division)

### 3. New Logging Function

Added `log_metric_unavailable()` for consistent diagnostic output:
```python
log_metric_unavailable(symbol, metric_name, reason)
```

Example output:
```
DEBUG: XYZ: ❌ net_income_growth_yoy = NULL → Insufficient data: 2 quarters (need 5)
DEBUG: XYZ: ❌ gross_margin_trend = NULL → Missing Gross Profit data (current: None, yoy: 150000)
```

## Data Requirements by Metric

| Metric | Source Table | Required Item/Field | Quarters Needed | Notes |
|--------|--------------|-------------------|-----------------|-------|
| Revenue Growth 3Y CAGR | key_metrics | revenue_growth_pct | N/A | Direct from yfinance |
| EPS Growth 3Y CAGR | key_metrics | earnings_growth_pct | N/A | Direct from yfinance |
| Op Income YoY | quarterly_income_statement | "Operating Income" | 5 | YoY = Q0 vs Q4 |
| FCF YoY | quarterly_cash_flow | "Free Cash Flow" | 5 | YoY = Q0 vs Q4 |
| NI YoY | quarterly_income_statement | "Net Income" | 5 | YoY = Q0 vs Q4 |
| Gross Margin Trend | quarterly_income_statement | "Gross Profit", "Total Revenue" | 5 | Both quarters needed |
| Op Margin Trend | quarterly_income_statement | "Operating Income", "Total Revenue" | 5 | Both quarters needed |
| Net Margin Trend | quarterly_income_statement | "Net Income", "Total Revenue" | 5 | Both quarters needed |
| Quarterly Momentum | quarterly_income_statement | "Total Revenue" | 8 | Q vs Q-1, YoY-Q vs YoY-Q-1 |
| Asset Growth YoY | quarterly_balance_sheet | "Total Assets" | 5 | YoY = Q0 vs Q4 |
| ROE Trend | key_metrics | return_on_equity_pct | N/A | Direct from yfinance |
| Sustainable Growth | key_metrics + quality_metrics | ROE + payout_ratio | N/A | ROE × (1 - Payout) |

## Diagnostic Tools Added

### 1. `/home/stocks/algo/diagnose_growth_metrics_data.py`
Python diagnostic that checks database before running loader:
```bash
python3 diagnose_growth_metrics_data.py
```
Shows what data exists for each metric and why metrics might be NULL.

### 2. `/home/stocks/algo/diagnose_growth_data.sh`
Quick SQL-based diagnostic:
```bash
./diagnose_growth_data.sh
```
Shows raw table statistics and available item_names.

## Why Metrics Are Likely NULL

Your 8 N/A values suggest:
1. **quarterly_income_statement table is empty or sparse**
   - No Operating Income records → operating_income_growth_yoy = NULL
   - No Gross Profit records → gross_margin_trend = NULL
   - < 5 quarters → all quarterly calculations fail

2. **quarterly_cash_flow table is missing/empty**
   - No "Free Cash Flow" item → fcf_growth_yoy = NULL

3. **quarterly_balance_sheet table is missing/empty**
   - No "Total Assets" → asset_growth_yoy = NULL

## Next Steps

To populate missing metrics:

1. **Run data loaders** (in order):
   ```bash
   python3 loadearningsmetrics.py      # Populates earnings_history
   python3 loadfundamentalmetrics.py   # Populates quarterly tables
   ```

2. **Or use yfinance directly**:
   ```bash
   python3 calculate_growth_metrics_yfinance.py  # Alternative data source
   ```

3. **Then run growth metrics**:
   ```bash
   python3 loadgrowthmetrics.py
   ```

## Testing

Run diagnostic to verify data:
```bash
./diagnose_growth_data.sh
python3 diagnose_growth_metrics_data.py
```

Then check logs when running loadgrowthmetrics.py:
```bash
python3 loadgrowthmetrics.py 2>&1 | grep -i "null\|unavailable"
```

## Code Quality

✅ All metrics have explicit validation
✅ Every NULL metric has a traceable reason in logs
✅ No implicit fallbacks or proxy calculations
✅ Clear separation of required vs optional data
✅ Comprehensive error messages for debugging

## Files Modified

- `/home/stocks/algo/loadgrowthmetrics.py` - Main loader with strict validation
- `/home/stocks/algo/diagnose_growth_metrics_data.py` - Diagnostic tool
- `/home/stocks/algo/diagnose_growth_data.sh` - SQL diagnostic tool
