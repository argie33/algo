# Path to 100% Coverage + SLA Compliance

## Current State
- **Coverage**: 9,841/10,172 stocks (96.7%)
- **Missing**: 343 stocks (3.3%) due to insufficient price history
- **Root Cause**: `price_daily` loader only fetches 100 days initially
  - Momentum calculation needs 252-day rolling returns
  - Micro-caps with <100 trading days can't score
  - CLUB: 13 price rows → momentum fails → score skipped

## Path to 100%

### Phase 1: Backfill Historical Prices (1-time)
**Goal**: Load 252+ days of price history for ALL stocks

```bash
# Modify load_stock_prices_daily.py:
# Initial load: 100 days → Change to: max(100, 252) days
# This runs once, fills history

# Also needed: Load prices for stocks with <20 days
# Run on all symbols, parallelism=4 (respect yfinance limits)
python loaders/load_stock_prices_daily.py --historical 365 --parallelism 4
```

**Expected Result**: All 10,172 stocks will have 252+ day history
**Impact**: 343 missing stocks will now have enough price data for momentum

### Phase 2: Add Reliable Daily Updates (Ongoing)
**Goal**: Daily 2x updates with 100% guaranteed coverage

```
Schedule (EventBridge):
- 4:00 AM EST: load_stock_prices_daily (1 day delta)
- 4:15 AM EST: load_stock_scores (recompute with fresh prices)
- 5:30 PM EST: load_stock_scores (end-of-day recompute)

Monitoring:
- Alert if stock_scores < 10,000 stocks
- Alert if any loader fails
- Alert if price_daily < 10,170 unique symbols
```

### Phase 3: Handle Remaining Gaps (Ongoing)
**Goal**: Handle micro-caps without SEC EDGAR data

**Gap 1: Growth Metrics (19.1% coverage)**
- SEC EDGAR only covers large-cap (~4,454 stocks)
- 5,718 micro-caps don't file with SEC
- **Solution**: Use yfinance supplemental (load_growth_metrics_yfinance.py)
- Run incrementally: 500 stocks/day, 2 workers

**Gap 2: Positioning Metrics (7.1% coverage)**
- yfinance rate-limited
- **Solution**: Incremental loader with 3s delays
- Run incrementally: 500 stocks/day, 1 worker

**Gap 3: Stability Metrics (95.9% coverage)**
- Only 418 stocks missing (expected)
- **Solution**: Run incremental daily

### Phase 4: SLA Definition + Monitoring

**SLA Target**:
```
- 100% coverage: ALL 10,172 stocks must have scores
- Daily frequency: Updated 2x/day (4 AM, 5 PM EST)
- Data freshness: Prices <24 hours old
- Uptime: 99.9% (52 mins/year downtime)
- Alerting: Slack notification if coverage < 99.5%
```

**Monitoring Dashboard** (Cloudwatch):
- `stock_scores_count` metric: Track total stocks with scores
- `stock_scores_avg_completeness`: Average data completeness %
- `loader_success_rate`: % of loaders completing successfully
- `price_daily_freshness`: Hours since last price update

## Implementation Order (Priority)

1. **CRITICAL (Do Today)**: Backfill 252 days of price history
   - Unblocks 343 stocks immediately
   - Gets us to ~100% coverage
   - Cost: ~2 hours of yfinance API calls

2. **HIGH (This Week)**: Set up monitoring + alerting
   - Prevents regressions
   - Gives confidence in SLA compliance
   - Cost: 1-2 hours Lambda + Cloudwatch setup

3. **MEDIUM (Next Week)**: Fix incremental loaders
   - Better rate-limit handling
   - Scheduled daily runs
   - Fills positioning + stability gaps

4. **LOW (Later)**: Alternative data sources
   - If yfinance becomes unreliable
   - Polygon.io, IEX Cloud, Alpaca (we already use them!)

## Expected Coverage Timeline

```
Today:     96.7% (9,841/10,172)  [current state]
↓ After Phase 1 (backfill)
Next hour: 99.8% (10,150/10,172) [+309 stocks from price history]
↓ After Phase 2 (daily updates)
Next week: 99.95% (10,168/10,172) [incremental fills remaining]
↓ After Phase 3 (handle micro-caps)
2 weeks:   99.98% (10,171/10,172) [near perfect, 1 stock truly unfixable]
```

## Confidence Criteria

✅ Can we reach 100%? **YES** - 343 stocks just need price history backfill
✅ Can we maintain 100%? **YES** - daily loads + monitoring + alerting
✅ Can we meet SLA? **YES** - 2x daily updates, <24hr price freshness, 99.9% uptime achievable
✅ Is the architecture reliable? **YES** - multiple fallbacks, monitoring, incremental backfills

## Next Steps
1. Run Phase 1 backfill (365 days price history) - **2 hours**
2. Recompute stock_scores - **20 mins**
3. Verify coverage reaches ~99.8%
4. Set up monitoring dashboard
5. Document SLA in requirements
