# Local Loader Emulation Guide

Since EventBridge Scheduler isn't available locally, here's how to emulate loader schedules:

## Quick Start - Fill Data Gaps

```bash
# Terminal 1: Refresh prices (5-10 min)
cd loaders && python load_prices.py

# Terminal 2: Refresh market exposure (2-5 min) - fills market_exposure_daily gap
cd loaders && python load_market_exposure_daily.py

# Terminal 3: Refresh technical indicators (15-25 min)
cd loaders && python load_technical_indicators.py
```

## Loader Pipelines (AWS EventBridge Schedule Emulation)

### Morning Pipeline (2 AM ET)
Loads prices and technical indicators needed for day's analysis:
```bash
cd loaders
python load_prices.py                      # Alpaca prices (5-10 min)
python load_technical_indicators.py        # SMA, RSI, ATR from prices (15-25 min)
```

### Reference Pipeline (9:15 AM ET)
Static reference data:
```bash
cd loaders
python load_market_constituents.py         # Stock symbols lists (< 1 min)
python load_economic_data.py               # FRED + DXY economic data (1-2 min)
```

### EOD Pipeline (4:05 PM ET)
Detailed fundamental analysis:
```bash
cd loaders
python load_financial_statements.py        # SEC EDGAR data (20-30 min)
python load_quality_growth_metrics.py      # Consolidated quality+growth (10-15 min)
python load_yfinance_derived_metrics.py    # Value metrics from yfinance (5-10 min)
python load_yfinance_snapshot.py           # Dividend/split/quote data (30-45 min) ⚠️ SLOW
```

### Computed Metrics Pipeline (7 PM ET)
Aggregated scores and signals:
```bash
cd loaders
python load_market_health_daily.py         # VIX, breadth, yield curve (2-5 min)
python load_buy_sell_daily.py              # Buy/sell signals (5-10 min)
python load_stock_scores.py                # Composite scoring (10-15 min)
python load_sector_performance.py          # Sector returns (2-5 min)
python load_trend_analysis.py              # Minervini/Weinstein trends (30-45 min)
python load_risk_metrics_daily.py          # Risk metrics (5-10 min)
python load_market_exposure_daily.py       # Market regime + exposure (2-5 min) ⚠️ FILLS GAP
python load_algo_metrics_daily.py          # Portfolio metrics (< 1 min)
```

## Current Data Gaps

| Table | Status | Missing Since | Action |
|-------|--------|---|---|
| **etf_price_daily** | 🔴 STALE (2.3d) | Morning | Run `load_prices.py` |
| **market_exposure_daily** | 🔴 STALE (48h) | EOD/Computed | Run `load_market_exposure_daily.py` |
| **technical_data_daily** | ✅ FRESH | - | (Runs in orchestrator) |
| **stock_scores** | ✅ FRESH | - | (Runs in orchestrator) |

## Full Refresh (All Loaders)

To do a complete data refresh locally:
```bash
cd loaders

# Morning pipeline (15 min)
echo "=== MORNING PIPELINE ===" && \
python load_prices.py && \
python load_technical_indicators.py

# Reference pipeline (1-2 min)
echo "=== REFERENCE PIPELINE ===" && \
python load_market_constituents.py && \
python load_economic_data.py

# EOD pipeline (45 min - SLOW due to yfinance)
echo "=== EOD PIPELINE ===" && \
python load_financial_statements.py && \
python load_quality_growth_metrics.py && \
python load_yfinance_derived_metrics.py && \
python load_yfinance_snapshot.py

# Computed metrics pipeline (60 min)
echo "=== COMPUTED METRICS PIPELINE ===" && \
python load_market_health_daily.py && \
python load_buy_sell_daily.py && \
python load_stock_scores.py && \
python load_sector_performance.py && \
python load_trend_analysis.py && \
python load_risk_metrics_daily.py && \
python load_market_exposure_daily.py && \
python load_algo_metrics_daily.py
```

**Total Time:** ~2 hours for complete refresh

## Parallel Execution (Faster)

Some loaders can run in parallel (different tables):
```bash
# Terminal 1 (Morning, 15 min)
cd loaders && python load_prices.py && python load_technical_indicators.py

# Terminal 2 (Reference, 2 min)
cd loaders && python load_market_constituents.py && python load_economic_data.py

# Terminal 3 (EOD, 45 min - let it run while others go)
cd loaders && python load_yfinance_snapshot.py

# Terminal 4 (Computed, run after EOD deps ready)
cd loaders && python load_market_health_daily.py && python load_market_exposure_daily.py && python load_stock_scores.py
```

## System Architecture Context

- **18 Total Loaders:** All independent data fetch + compute tasks
- **4 Scheduled Pipelines:** Grouped to minimize overlaps and dependencies
- **Data Flow:** Raw fetch → Validate → Compute → Persist to PostgreSQL
- **Orchestrator Phases 1-9:** Consume already-loaded data (don't load)
- **EventBridge Scheduler:** Normally triggers pipelines on AWS schedule

## Future: Automated Local Scheduler

Could create Python scheduler to run pipelines automatically:
```python
# Pseudo-code for schedule-based runner
import schedule
schedule.every().day.at("02:00").do(run_morning_pipeline)
schedule.every().day.at("09:15").do(run_reference_pipeline)
schedule.every().day.at("16:05").do(run_eod_pipeline)
schedule.every().day.at("19:00").do(run_computed_pipeline)
```

## Troubleshooting

**Loader hangs/slow:**
- `load_yfinance_snapshot.py`: Can take 30-45 min on first run (rate limiting)
- Solution: Skip or run in background, focus on critical morning loaders first

**Data still stale after running loaders:**
- Check PostgreSQL is running: `psql dbname=stocks -c "SELECT 1"`
- Check loader log output for errors
- Some loaders depend on prior loaders (e.g., technical depends on prices)

**How to check if loader worked:**
```bash
python check_system_health.py   # Show data freshness
```

