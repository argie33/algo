# Performance & Risk Metrics Loaders

## Overview

Two new loaders calculate and cache metrics that the dashboard previously computed on-the-fly:

- **`load_algo_performance_daily.py`** — Rolling sharpe ratio, sortino, calmar ratio, win rate, expectancy, max drawdown
- **`load_algo_risk_daily.py`** — Value-at-Risk (95%), CVaR, stressed VaR, portfolio beta, concentration risk

These run **hourly during market hours** (10 AM - 4:30 PM ET) to keep metrics reasonably current, reducing dashboard computation burden.

## Why Separate Loaders?

**Before:** Dashboard recalculated all metrics on every load
- Slow dashboard during peak market hours
- Calculation logic mixed with display logic
- No caching — same work repeated dozens of times/hour

**After:** Pre-calculated metrics cached in tables
- Dashboard loads in <100ms (table lookup only)
- Metrics are "close enough" for display (hourly freshness)
- Real-time P&L still calculated per-load (based on current prices)
- Calculation logic centralized in loaders (easier to maintain)

## Scheduling (EventBridge)

### During Market Hours (Mon-Fri 10 AM - 4:30 PM ET)

Run both loaders **hourly at :00 minutes**:

```yaml
# EventBridge rules
performance-metrics-hourly:
  schedule: "cron(0 10-16 ? * MON-FRI *)"  # 10 AM - 4 PM ET
  target: load_algo_performance_daily.py

risk-metrics-hourly:
  schedule: "cron(0 10-16 ? * MON-FRI *)"  # 10 AM - 4 PM ET
  target: load_algo_risk_daily.py
```

### After Market Close (4 PM)

Run once more at 5 PM to capture end-of-day metrics:

```yaml
performance-metrics-eod:
  schedule: "cron(0 21 ? * MON-FRI *)"  # 5 PM ET (21:00 UTC)
  target: load_algo_performance_daily.py

risk-metrics-eod:
  schedule: "cron(0 21 ? * MON-FRI *)"  # 5 PM ET
  target: load_algo_risk_daily.py
```

**Note:** Times are in UTC (ET -4 hours during EDT, -5 during EST). Adjust as needed for your timezone.

## Dashboard Behavior

### Freshness Checks

Dashboard looks for `updated_at` timestamp in metrics tables:
- ✅ **Fresh** (<2 hours old): Use table data immediately
- ⚠️ **Stale** (>2 hours old): Log warning, don't use (wait for fresh data)
- ❌ **Missing**: Return empty, dashboard shows "--"

### Fallback Strategy

If table data is unavailable/stale during market hours, dashboard **does not** recalculate on-the-fly. This prevents:
- Slow dashboard loads during peak market hours
- Inconsistent metrics across simultaneous dashboard loads
- Calculation errors hiding underneath real-time display

Instead: Dashboard displays "--" for unavailable metrics, user can refresh after loader runs.

Outside market hours (before 10 AM, after 4:30 PM): On-the-fly calculation acceptable since dashboard is not actively used.

## Table Schema

### `algo_performance_daily`

```sql
CREATE TABLE algo_performance_daily (
  report_date DATE PRIMARY KEY,
  rolling_sharpe_252d FLOAT,
  rolling_sortino_252d FLOAT,
  calmar_ratio FLOAT,
  win_rate_50t FLOAT,
  avg_win_r_50t FLOAT,
  avg_loss_r_50t FLOAT,
  expectancy FLOAT,
  max_drawdown_pct FLOAT,
  total_trades INT,
  win_rate_all FLOAT,
  updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_perf_date ON algo_performance_daily (report_date DESC);
CREATE INDEX idx_perf_updated ON algo_performance_daily (updated_at DESC);
```

### `algo_risk_daily`

```sql
CREATE TABLE algo_risk_daily (
  report_date DATE PRIMARY KEY,
  var_pct_95 FLOAT,
  cvar_pct_95 FLOAT,
  stressed_var_pct FLOAT,
  portfolio_beta FLOAT,
  top_5_concentration FLOAT,
  position_count INT,
  updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_risk_date ON algo_risk_daily (report_date DESC);
CREATE INDEX idx_risk_updated ON algo_risk_daily (updated_at DESC);
```

## Metrics Definitions

### Performance Metrics

**Rolling Sharpe (252-day):** Annualized excess return per unit risk
- Formula: `(mean_return / std_return) * sqrt(252)`
- Uses: Daily portfolio snapshots (last 252 trading days)
- Confidence: High if >20 snapshots, low if <10

**Rolling Sortino (252-day):** Like Sharpe but only penalizes downside volatility
- Formula: `(mean_return / std_downside) * sqrt(252)`
- More meaningful for asymmetric strategies

**Calmar Ratio:** Cumulative return / max drawdown
- Measures risk-adjusted return over peak-to-trough loss

**Win Rate (50T):** % of wins in last 50 closed trades
- Short-term performance indicator
- More responsive to recent changes than all-time win rate

**Expectancy:** Expected value per trade
- Formula: `(win_rate * avg_win_R) - ((1 - win_rate) * avg_loss_R)`
- In units of R-multiples

**Max Drawdown:** Peak-to-trough decline as % of peak equity
- Calculated from daily portfolio snapshots only
- Does NOT include intraday gaps (e.g., -15% at 10am, recover by close)

### Risk Metrics

**Value at Risk (95%):** Maximum loss at 95% confidence level
- Calculated as 5th percentile of daily returns
- Used in portfolio limit setting

**Conditional VaR (95%):** Expected loss given a loss worse than VaR
- Average of worst 5% of daily returns

**Stressed VaR:** Average of worst 10% of days
- Captures tail risk more aggressively than standard VaR

**Portfolio Beta:** Market sensitivity
- Beta > 1: moves more than market
- Beta < 1: moves less than market
- Beta ~ 0: market-neutral

**Concentration (Top 5):** % of portfolio in largest 5 positions
- Used to monitor single-position risk
- Threshold: Flag if >40% concentrated

## Maintenance

### Troubleshooting

**Metrics missing/stale during market hours:**
1. Check loader CloudWatch logs for errors
2. Verify database connection (RDS availability)
3. Check if `algo_trades` or `algo_portfolio_snapshots` have stale data
4. Manually trigger loader: `python loaders/load_algo_performance_daily.py`

**Metrics don't match dashboard calculations:**
1. Check `updated_at` timestamp (may be using old data)
2. Verify table has data for current date
3. Compare SQL queries between loader and dashboard (should be identical)

**Loader runs slow (>5 minutes):**
1. Check if `algo_trades` table is unindexed (add index on `status`, `exit_date`)
2. Check if `algo_portfolio_snapshots` is very large (should be <1000 rows/year)
3. Consider reducing precision (store 1 decimal instead of 3 for smaller storage)

### Future Improvements

1. **Intraday Updates:** During trading hours, update metrics every 30 minutes instead of hourly
2. **Streaming Updates:** Trigger loader on every trade close (instead of scheduled)
3. **Prediction Metrics:** Add projected return/risk based on current positions
4. **Multi-day Rolling:** Cache last 7 days of metrics for trend analysis
5. **Alert Thresholds:** Trigger notification if sharpe drops >10% in a day

## Related Docs

- `steering/algo.md` — Overall system schedule & architecture
- `tools/dashboard/dashboard.py` — Dashboard freshness validation logic
- `loaders/load_algo_performance_daily.py` — Performance metrics implementation
- `loaders/load_algo_risk_daily.py` — Risk metrics implementation
