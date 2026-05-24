# Live Trading Checklist

## ⚠️ BEFORE ENABLING LIVE TRADING

**DO NOT proceed if any step is unclear. Use paper mode by default.**

### Step 1: Verify Environment
- [ ] PowerShell profile reloaded: Close and reopen terminal
- [ ] `echo $env:ALPACA_PAPER_TRADING` → should output `false`
- [ ] `echo $env:ALGO_LIVE_TRADING` → should output `I_UNDERSTAND_REAL_MONEY`
- [ ] `echo $env:APCA_API_BASE_URL` → should output `https://api.alpaca.markets`
- [ ] `aws sts get-caller-identity` → returns your AWS account (creds valid)

### Step 2: Verify Alpaca Account Setup
- [ ] Log in to Alpaca: https://app.alpaca.markets
- [ ] Account type: **Live** (not Paper)
- [ ] Buying power > $0 (check dashboard)
- [ ] API keys rotated in last 90 days
- [ ] No existing open positions (or intentional ones only)

### Step 3: Verify Algorithm Config
- [ ] `algo/algo_orchestrator.py` → `execution_mode = "auto"` (not disabled)
- [ ] `algo/algo_signals.py` → signal rules reviewed (enable only ones you want)
- [ ] Position size limits: `max_shares_per_trade`, `max_total_exposure` set conservatively
- [ ] Stop-loss rules in place (prevent runaway losses)

### Step 4: Verify Data Pipeline
- [ ] Run price loaders: `manual-invoke-loaders.yml` → select 1-2 loaders (e.g., yfinance)
- [ ] Wait 2 min, then check: `SELECT COUNT(*) FROM price_data_daily WHERE date = CURRENT_DATE`
- [ ] If > 0 rows: ✅ data flowing
- [ ] If 0 rows: ❌ Stop. Debug loaders. Do NOT enable live trading.

### Step 5: Test with Small Trade
- [ ] Set `ALGO_LIVE_TRADING=I_UNDERSTAND_REAL_MONEY`
- [ ] Manually invoke `test-orchestrator.yml` (single execution)
- [ ] Check orchestrator logs in CloudWatch
- [ ] Look for: "Placing order" → order placed successfully
- [ ] Check Alpaca dashboard: new position appears (should be small: 1–5 shares)
- [ ] If successful: you're ready for automated runs
- [ ] If failed: revert `ALGO_LIVE_TRADING` to unset, debug error, try again

### Step 6: Enable Scheduled Trading
- [ ] Confirm Step 5 test trade succeeded
- [ ] Keep `ALGO_LIVE_TRADING=I_UNDERSTAND_REAL_MONEY` (do not unset)
- [ ] EventBridge schedules resume: 9:30A ET, 5:30P ET trading windows
- [ ] Monitor first 3 days: CloudWatch logs, Alpaca dashboard, daily P&L
- [ ] If stable: ✅ Live trading enabled
- [ ] If errors: Stop orchestrator, revert config, debug

---

## Fallback: Use Paper Mode (Zero Financial Risk)

**If unsure at ANY step:** Use paper trading to test.

- [ ] Set `ALPACA_PAPER_TRADING=true`
- [ ] Unset `ALGO_LIVE_TRADING` (or set to empty string)
- [ ] Set `APCA_API_BASE_URL=https://paper-api.alpaca.markets`
- [ ] Run orchestrator → all trades execute against paper account ($100K default)
- [ ] Test signals, rules, execution without real money risk
- [ ] When confident: flip back to live trading using checklist above

---

## Emergency: Stop Live Trading Immediately

**If anything goes wrong:**

1. Stop orchestrator: Don't queue next scheduled run
   - Go to EventBridge → disable `algo-morning-trading` and `algo-evening-trading` rules
2. Close all open positions (manual in Alpaca dashboard)
3. Rotate Alpaca API keys immediately
4. Unset `ALGO_LIVE_TRADING`
5. Open GitHub Issue with: error logs, what went wrong, actions taken
6. Do post-mortem before re-enabling

---

## Monitor During Live Trading

| Metric | Check | Frequency |
|--------|-------|-----------|
| Orchestrator execution | CloudWatch logs: `algo-algo-dev` Lambda | After each run (9:30A, 5:30P) |
| Trade execution | Alpaca dashboard: Orders + Positions | 5 min after each run |
| Data freshness | `SELECT MAX(timestamp) FROM price_data_daily` | Daily morning |
| Account health | Alpaca: Buying power, margin usage, P&L | Daily EOD |
| Errors/alerts | GitHub Issues (if new) | Continuous |

