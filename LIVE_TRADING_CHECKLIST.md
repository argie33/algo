# Live Trading Checklist

**Before setting `ALGO_LIVE_TRADING = I_UNDERSTAND_REAL_MONEY`:**

## Account & Permissions Setup
- [ ] Alpaca account created with live trading access (not paper)
- [ ] API keys generated and stored in AWS Secrets Manager
- [ ] Account funding sufficient (minimum $25k for day trading, per SEC rules)
- [ ] Account registration complete with Alpaca (verify status)
- [ ] Broker fee structure understood (commissions, margin rates)

## Configuration Verification
- [ ] `ALGO_LIVE_TRADING = I_UNDERSTAND_REAL_MONEY` set in local PowerShell profile
- [ ] `ALPACA_PAPER_TRADING = false` (not true)
- [ ] `APCA_API_BASE_URL = https://api.alpaca.markets` (not paper URL)
- [ ] All credentials loaded from AWS Secrets Manager (never hardcoded)
- [ ] Database credentials correct and rotated recently

## Risk Controls — Position Sizing
- [ ] Max portfolio risk per trade: 2% (in `config/trading_config.py`)
- [ ] Position size calculator tested with live prices
- [ ] Drawdown circuit breaker limit: 5% (stops trading if portfolio down 5%)
- [ ] Daily loss limit: 2% (stops trading if day loss exceeds 2%)
- [ ] Max positions: limit enforced in orchestrator (Phase 6)

## Risk Controls — Signal Quality
- [ ] Minimum signal tier: 2 only (no tier 1 or unranked trades)
- [ ] Signal attribution running (Phase 7): tracks component IC
- [ ] Weight optimization: dynamically adjusts component weights
- [ ] Stale signal rejection: signals older than 1 day discarded
- [ ] Data freshness: circuit breaker halts if price data > 7 days old

## Risk Controls — Market Conditions
- [ ] VIX circuit breaker: stops trading if VIX > 30
- [ ] Market stage check: respects bull/bear/sideways regimes
- [ ] Trading day validation: skips weekends and US market holidays
- [ ] Pre-market/post-market: trades only during 9:30 AM - 4:00 PM ET

## Data Quality
- [ ] Price data freshness verified (< 1 day old)
- [ ] Technical indicators calculated correctly (RSI, MACD, SMA, EMA, ATR)
- [ ] Company fundamentals in database (balance sheets, cash flow)
- [ ] Sentiment data present (if used in signals)
- [ ] No missing required columns in `technical_data_daily`, `buy_sell_daily`

## Orchestrator Pipeline
- [ ] Phase 1 (Data Patrol): runs and logs data freshness
- [ ] Phase 2 (Circuit Breakers): all breakers tested (VIX, drawdown, daily loss)
- [ ] Phase 3 (Filter Pipeline): reduces universe to qualified candidates
- [ ] Phase 4 (Rank Signals): signal scores ranked by quality
- [ ] Phase 5 (Signal Generation): rules produce buy/sell signals
- [ ] Phase 6 (Trade Execution): position sizes calculated, orders submitted
- [ ] Phase 7 (Reconciliation): performance tracked, component IC updated

## Order Execution
- [ ] Order types set correctly: market orders (not limit) for execution speed
- [ ] Order time-in-force: day orders (reset each trading day)
- [ ] Slippage tolerance understood: real market execution vs backtest
- [ ] Commission impact: accounted for in position sizing (Alpaca: ~$0/trade)
- [ ] Partial fills: orchestrator handles correctly (updates positions)

## Monitoring & Alerts
- [ ] CloudWatch dashboards configured (Lambda errors, data loader status)
- [ ] Email alerts set up for trading errors (Orchestrator Phase 6 failures)
- [ ] Daily profit/loss report generated (Phase 7 output)
- [ ] Position tracking enabled: view open positions in AWS RDS
- [ ] Error logs accessible: CloudWatch Logs for Lambda troubleshooting

## Broker Account Safety
- [ ] Trade restrictions: account API keys limited to trading API only
- [ ] IP whitelisting: if available, restrict API calls to known IPs
- [ ] Account monitoring: check Alpaca dashboard for unexpected positions
- [ ] Liquidity check: avoid illiquid stocks (volume > 100k shares/day)
- [ ] Margin: understand margin requirements and available buying power

## Emergency Shutdown
- [ ] **HALT command**: Set `ALGO_LIVE_TRADING = HALT` to stop all orders immediately
- [ ] **Manual liquidation**: Command to close all positions and stop trading
- [ ] **Alpaca account locks**: Understand how to lock account from web UI
- [ ] **RDS backup**: recent snapshot taken before trading begins
- [ ] **Runbook access**: emergency contact list and procedures documented

## Pre-Trading Day (Morning Routine)
- [ ] Verify account funding (sufficient cash for position sizing)
- [ ] Check Alpaca API status (is broker responsive?)
- [ ] Review overnight news (major market events, earnings surprises)
- [ ] Verify data loaded fresh: price loader ran at 4AM ET
- [ ] Verify orchestrator ready: Phase 1 check passes
- [ ] View previous day's performance (P&L, component IC)

## First Trade (Live, Small Position)
- [ ] Start with MINIMUM position size (1 share or $500 allocation)
- [ ] Monitor order execution: verify order submitted and filled
- [ ] Check position: appears in Alpaca dashboard within 1 minute
- [ ] Monitor Phase 7: performance recorded in database
- [ ] Review exit: system closes position or manually close to test workflow

## Gradual Scale-Up
- [ ] Week 1: Single position at a time, max 0.5% portfolio risk
- [ ] Week 2-3: 2-3 concurrent positions if consistent profitability
- [ ] Month 1+: Scale to configured risk parameters (2% per trade)
- [ ] **NEVER** exceed configured position sizing limits

## Ongoing Monitoring (Daily)
- [ ] Morning: Check dashboard for overnight errors
- [ ] Midday: Verify trades executing as expected
- [ ] End of day: Review positions and P&L
- [ ] Evening: Check component weights (Phase 7 optimization)
- [ ] Weekly: Review signal quality (IC values, attribution)

## Quarterly Credential Rotation
- [ ] Rotate Alpaca API keys
- [ ] Rotate database password
- [ ] Rotate AWS IAM keys (if using static keys — should not)
- [ ] Update Secrets Manager entries
- [ ] Update all deployed Lambdas with new credentials

**DO NOT trade live until ALL checklist items are verified.**

**In case of emergency: Execute shutdown procedure immediately.**
