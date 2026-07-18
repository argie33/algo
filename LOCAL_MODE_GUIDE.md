# Local Mode Data Freshness Guide

## Problem Solved ✅
Data freshness issues in LOCAL_MODE have been addressed with three key fixes:

1. **Universe Table Reference** → Fixed to use `stock_symbols` (10,594 real tradeable stocks)
2. **Phase 1 Staleness Detection** → Now checks actual data dates, not just loader status
3. **Watermark Bypass** → Added `--force-refresh` flag to loaders

## What Changed

### Phase 1 Failsafe (LOCAL_MODE)
- Detects when table data is >24h old
- Automatically triggers loader refresh for stale tables
- Properly handles datetime/date conversions
- Reports: "technical_data_daily data stale: 25.5h old" → triggers refresh

### Loader Script `--force-refresh` Flag
```bash
python3 scripts/run_loader.py prices --force-refresh
python3 scripts/run_loader.py technical --force-refresh
python3 scripts/run_loader.py market_status --force-refresh
```

When `--force-refresh` is used:
1. Sets `TECH_FULL_REFRESH=true` environment variable (bypasses watermarks)
2. Marks loader as RUNNING in `data_loader_status`
3. Runs the loader on full universe
4. Marks loader as COMPLETED (updates watermark timestamp)

### Data Freshness Check
```bash
python3 check_system_health.py  # Shows data ages
```

## Trade-offs: Full Universe vs Speed

### Problem: 10K+ Symbol Universe is Slow
```
price_daily:          ~2 min for 10K symbols (yfinance API calls)
technical_data_daily: ~10 min for 10K symbols (vectorized compute)
stock_scores:         ~5 min for 10K symbols
market_status:        ~30 sec (market-wide, not per-symbol)
value_metrics:        ~20 min (SEC API + yfinance)
```

**Total full refresh: 30-50 minutes** for complete data update

### Solution Strategies for Local Dev

#### Option 1: Small Test Subset (Recommended for Dev)
Edit `scripts/run_loader.py`:
```python
# Add a quick subset function
TEST_SYMBOLS = ["AAPL", "SPY", "QQQ", "MSFT", "NVDA", "TSLA", "NVDA"]

def run_price_loader(symbols=None, backfill_days=1):
    if not symbols:
        # Use test subset for development
        os.environ["USE_TEST_SUBSET"] = "true"
        symbols = TEST_SYMBOLS
    ...
```

**Trade-off:** Data is only for 7 symbols, but refreshes in seconds
**Best for:** Testing logic, quick iteration, dashboard visualization

#### Option 2: Scheduled Overnight Refresh
Run full refresh in background:
```bash
# Terminal dedicated to data refresh
while true; do
  echo "$(date): Starting full refresh..."
  python3 scripts/run_loader.py prices --force-refresh
  python3 scripts/run_loader.py technical --force-refresh
  python3 scripts/run_loader.py market_status --force-refresh
  python3 scripts/run_loader.py value_quality_growth --force-refresh
  echo "$(date): Refresh complete. Sleeping 6h..."
  sleep 21600  # 6 hours
done
```

**Trade-off:** Data refreshes every 6h, but you keep current data for most of the day
**Best for:** Realistic local testing, minimal setup

#### Option 3: Accept 1-2 Day Lag
Just run orchestrator normally:
```bash
python3 scripts/run_local_orchestrator.py --morning
```

Data will be 1-2 days old, but system works correctly. This is acceptable for:
- Testing trading logic (doesn't depend on current data)
- Backtesting scenarios
- Strategy prototyping
- Unit testing individual phases

**Trade-off:** Data is old, but everything else works
**Best for:** Fastest iteration, acceptance testing

#### Option 4: Parallel Processing for Speed
Modify loaders to process symbols in batches:
```bash
# Run multiple loaders in parallel
python3 scripts/run_loader.py prices --force-refresh &
python3 scripts/run_loader.py technical --force-refresh &
python3 scripts/run_loader.py market_status --force-refresh &
wait  # Wait for all to complete
```

Could reduce total time to ~20 min (if APIs permit parallelism)

## Current Architecture Limitations

### Why Full Universe is Slow

1. **Price Loader** (2 min)
   - 10,594 symbols × yfinance API calls
   - Rate-limited by yfinance (20 calls/min)
   - Sequential batching: 10K symbols ÷ 20 batch size = 500 batches × 0.24s/batch ≈ 2 min

2. **Technical Indicators** (10 min)
   - Fetches ALL price history (400 days) for ALL symbols
   - Computes SMA, RSI, MACD, ATR, ADX, Bollinger Bands
   - 10K symbols × 6 indicators × complex math = vectorized pandas operations

3. **Value/Quality/Growth** (20 min)
   - Requires SEC API calls for quality/growth metrics
   - yfinance snapshot for value metrics
   - Both have rate limits and latency

### Production (AWS) vs Local (Dev)
- **AWS**: Orchestrator runs on schedule, loaders in ECS (can use Spot for cost)
- **Local**: Sequential loaders on laptop CPU, no parallelism, yfinance API limits

## Recommended Workflow

For local development, use **Option 1 + Optional Option 4**:

```bash
# Terminal 1: Test subset loader (quick)
python3 start_dashboard_dev.py -w 20

# Terminal 2: Full orchestrator with test subset
LOCAL_MODE=true python3 scripts/run_local_orchestrator.py --morning

# Optional: Background refresh every 6h
nohup bash -c 'while true; do python3 scripts/run_loader.py prices --force-refresh &> /tmp/loader.log; sleep 21600; done' &
```

Result:
- Dashboard shows current data (5 symbols)
- Orchestrator runs in < 1 min (test subset)
- Full data refreshes in background every 6h if you want

## Commands Reference

### Manual refresh (full universe)
```bash
# With watermark bypass + status update
python3 scripts/run_loader.py prices --force-refresh
python3 scripts/run_loader.py technical --force-refresh
python3 scripts/run_loader.py market_status --force-refresh
python3 scripts/run_loader.py value_quality_growth --force-refresh
python3 scripts/run_loader.py scores --force-refresh
```

### Manual refresh (quick test)
```bash
# Edit scripts/run_loader.py to use TEST_SYMBOLS, then:
python3 scripts/run_loader.py prices --force-refresh
```

### Check data ages
```bash
python3 check_system_health.py
```

### Run orchestrator locally
```bash
LOCAL_MODE=true python3 scripts/run_local_orchestrator.py --morning
```

## Next Steps to Fully Solve This

1. **Subset Mode Implementation** - Add official `--subset` flag to loaders
2. **Async Refresh** - Move background refresh to daemon process
3. **Database Cache** - Cache recent price data locally to reduce API calls
4. **Incremental Updates** - Only refresh changed symbols instead of full universe
5. **Parallel Processing** - Use multiprocessing/asyncio for symbol batches

These are medium-term improvements that would make local development faster without losing production fidelity.
