# Dashboard Data Quality Issues & Fixes

**Session 138 - 2026-07-14**

## Issues & Root Causes

### 1. Position Mismatch - "Positions: ░░░░3/15" vs Actual Count
**Observed**: Dashboard shows 3 positions when algo is flat or has different count
**Root Cause**: Portfolio snapshot has stale position_count from earlier Phase 9 run
- DB shows correct counts (2026-07-14 snapshot: 8 positions)
- But `/api/algo/positions` returns 0 items (calling AWS Lambda, which may be caching)
- `_get_actual_position_count()` in portfolio.py correctly uses positions endpoint over snapshot
- AWS Lambda `_positions_cache` is 5-minute TTL, may be returning stale data

**Fix**:
1. Check if AWS Lambda cache is stale by comparing latest snapshot vs actual positions
2. Clear positions cache if age > 300s
3. Ensure portfolio panel uses actual positions count (already implemented)

### 2. Growth Score = "--" for 641 Symbols
**Observed**: 641 out of 4,711 symbols (13.6%) show "--" for Growth column
**Root Cause**: growth_score is NULL in stock_scores because:
- Many symbols have incomplete growth_metrics data (all fields NULL)
- Growth score calculation requires growth metrics but fails gracefully when data unavailable
- Load process marks these as unavailable rather than computing a default

**Examples of NULL cases**:
- RADX, QNTM, VRXA, BWEB, OWLS: ALL score fields NULL (complete data gaps)
- SHOE: Partial data (Stab=38.6, Val=82.8, Mom=25.0) but growth_score NULL

**Fix**:
1. Verify growth_metrics loader is fetching SEC data for all symbols
2. Check if growth_metrics fetch is timing out or failing silently
3. Consider fallback: calculate growth_score from last_price_date and available fields
4. Add monitoring to alert when >10% of symbols missing growth data

### 3. Breadth Momentum: 50.00 for Multiple Days
**Observed**: `breadth_momentum_10d` = 50.0 for 2026-07-13, 2026-07-10, 2026-07-09
**Root Cause**: This IS a valid metric (50% up days in last 10 days), NOT a placeholder
- Calculated as: `df["up_day"].rolling(10, min_periods=1).mean() * 100`
- Value of 50.0 means exactly 5 out of 10 last days were up days
- Repeated value across days indicates market was balanced (50/50 up/down days)

**Actual Issue**: User expected breadth_momentum to vary more, or thought 50.0 was a default
- This is NOT a bug, just a feature of balanced market breadth

**Fix**: No code change needed. Document that 50.0 is valid. Monitor for genuine stale data (same value >7 days).

### 4. Put/Call Ratio: NULL (No Data)
**Observed**: All put_call_ratio values in market_health_daily are NULL
**Root Cause**: Put_call_ratio fetcher not returning data, or API call failing silently
- `market_health_fetchers.py` has `_fetch_put_call_ratio()` method
- Load process marks `put_call_ratio_data_unavailable=True` for all rows
- No fallback value or retry logic for transient failures

**Fix**:
1. Check `_fetch_put_call_ratio()` implementation - verify it's being called
2. Add logging to market_health_fetchers to track PCR fetch attempts
3. Verify data source (yfinance, polygon, other) is accessible
4. Add retry logic for transient API failures
5. Monitor PCR data freshness in health check

## Implementation Order

**High Priority** (Affects trading logic):
1. Fix growth_score NULL values (affects stock selection)
2. Fix put_call_ratio data (affects market regime detection)
3. Verify positions endpoint cache invalidation

**Medium Priority** (Display/UX):
4. Verify breadth_momentum is updating daily (not stuck at 50.0)
5. Add data freshness warnings to dashboard

**Low Priority** (Monitoring):
6. Document breadth_momentum value interpretation
7. Add PCR data availability monitoring

## Verification Steps

1. **Positions**: Run `python3 -c "from dashboard.api_data_layer import api_call; print(api_call('/api/algo/positions')['items'][:3])"`
2. **Growth Score**: Run `python3 -c "from dashboard.api_data_layer import api_call; scores = api_call('/api/algo/scores')['top']; print([s for s in scores if s['growth_score'] is None][:3])"`
3. **Breadth**: Check `market_health_daily` table: `SELECT DISTINCT breadth_momentum_10d FROM market_health_daily ORDER BY date DESC LIMIT 10`
4. **Put/Call**: Check `market_health_daily` table: `SELECT COUNT(*) as null_count FROM market_health_daily WHERE put_call_ratio IS NULL`

## Files Affected

- `dashboard/panels/portfolio.py` - Position display logic (line 177)
- `lambda/api/routes/algo_handlers/dashboard.py` - Positions cache
- `lambda/api/routes/algo_handlers/metrics.py` - Portfolio endpoint
- `loaders/load_stock_scores.py` - Growth score calculation
- `loaders/load_market_health_daily.py` - Breadth momentum and put_call calculation
- `loaders/market_health_fetchers.py` - Put_call_ratio fetch implementation
