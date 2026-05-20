# Live Deployment Verification - Get Algo Running LIVE with Fresh Data in AWS

## Goal
Algo running LIVE (not dry-run) in AWS with fresh data automatically every day before market open, with all loaders working on schedule.

## Current Status
- ✅ Code changes committed (DNS diagnostics + Route 53 Resolver workaround)
- ✅ Loaders implemented & scheduled in Terraform
- ✅ Orchestrator scheduled 2x daily in Terraform
- ⏳ GitHub Actions deploy-code workflow running (auto-triggered on push)
- ❌ DNS error still blocking orchestrator ← **CRITICAL BLOCKER**
- ❌ No confirmed LIVE trade execution in AWS

## What Blocks the Goal

### 1. DNS Resolution (CRITICAL)
**Symptom**: `Failed to connect to database after 3 attempts: could not translate host name...`

**What's deployed**:
- DNS diagnostics in `utils/db_connection.py` (logs details when DNS fails)
- Route 53 Resolver workaround (reconfigures `/etc/resolv.conf` to use 169.254.169.253)
- Commits: `4c2ac2eb0`, `80f0323df`, `f386bb8c5`, `17cf09b68`

**What needs to happen**:
1. Wait for GitHub Actions `deploy-code` workflow to complete
2. The workflow will:
   - Build `algo-orchestrator-layer` with the new diagnostics
   - Publish layer to AWS Lambda
   - Update Lambda to use new layer
3. Test orchestrator to see if it can now connect to RDS

### 2. Loaders Execution (NOT VERIFIED)
**Configured in Terraform**:
- Price loader: `cron(30 8 ? * MON-FRI *)` = 3:30 AM ET (before market open ✓)
- Technicals/metrics: various times during day
- 2x daily orchestrator: 9:30 AM ET (morning) + 5:30 PM ET (evening)

**What needs to happen**:
1. Verify infrastructure is deployed with loaders & schedules
2. Check if loaders actually ran and provided data in AWS
3. Verify fresh data exists in RDS before orchestrator runs

### 3. Orchestrator LIVE Execution (NOT VERIFIED)
**Configured**:
- `orchestrator_dry_run = false` → LIVE mode
- `alpaca_paper_trading = false` → Real Alpaca trading
- `enable_morning_orchestrator = true` → Morning + evening runs

**What needs to happen**:
1. Fix DNS so orchestrator can connect to RDS
2. Test orchestrator execution with LIVE mode
3. Verify trades placed in real Alpaca account
4. Monitor CloudWatch logs for all 7 phases completing

## Step-by-Step Verification Plan

### Phase 1: Deploy DNS Fix (IMMEDIATE)
```bash
# DNS fix already committed. GitHub Actions should be running:
# 1. deploy-code workflow builds algo-orchestrator-layer
# 2. Publishes layer with updated diagnostics
# 3. Updates Lambda with new layer
# 
# Timeline: ~5-10 minutes
# Check: https://github.com/argie33/algo/actions
```

### Phase 2: Test Orchestrator Connection (AFTER Phase 1)
```bash
# Once deploy-code workflow completes, run:
gh workflow run test-orchestrator.yml

# This will:
# 1. Invoke orchestrator Lambda
# 2. Wait for CloudWatch logs
# 3. Check if Phase 7 appears (orchestrator completed)
# 4. Display full log output

# Expected: 
# - ✓ No DNS error in logs
# - ✓ Phase 1-7 all execute successfully
# - ✓ Trades placed in Alpaca (check logs for "Trade executed" or "Order placed")
```

### Phase 3: Verify Data Freshness (BEFORE 9:30 AM ET)
```sql
-- Check if loaders have provided fresh data in AWS RDS:
SELECT
  'price_daily' as table_name,
  COUNT(*) as row_count,
  MAX(date) as latest_date,
  CURRENT_DATE - MAX(date) as days_old
FROM price_daily
UNION ALL
SELECT
  'technical_data_daily',
  COUNT(*),
  MAX(date),
  CURRENT_DATE - MAX(date)
FROM technical_data_daily
UNION ALL
SELECT
  'buy_sell_daily',
  COUNT(*),
  MAX(date),
  CURRENT_DATE - MAX(date)
FROM buy_sell_daily;

-- Expected: All tables have data from TODAY (days_old = 0)
```

### Phase 4: Monitor Live Execution
```bash
# Monitor orchestrator logs in real-time:
aws logs tail /aws/lambda/algo-algo-dev --follow

# Look for:
# - [OK] Phase 1: DATA FRESHNESS CHECK
# - [OK] Phase 2: CIRCUIT BREAKERS
# - [OK] Phase 3: POSITION MONITOR
# - [OK] Phase 4: EXIT EXECUTION
# - [OK] Phase 5: SIGNAL GENERATION
# - [OK] Phase 6: ENTRY EXECUTION
# - [OK] Phase 7: RECONCILIATION

# If any phase fails with error, logs will show exactly why
```

## Success Criteria

The goal is satisfied when:

1. **Orchestrator connects to RDS without DNS error** ✓
   - CloudWatch logs show no "Name or service not known" error
   - At least Phase 1 completes successfully

2. **All 7 phases execute successfully** ✓
   - Phase 1: Data freshness check passes
   - Phases 2-7: All execute without errors
   - Logs show "[OK] Phase N" for all phases

3. **LIVE trades are placed in Alpaca** ✓
   - Logs show "Trade executed" or "Order placed"
   - Alpaca account shows new positions/orders created
   - Verify `alpaca_paper_trading = false` (LIVE mode, not paper)

4. **Fresh data available before market open** ✓
   - Price data loaded by 4 AM ET
   - Technicals computed by 9 AM ET
   - Orchestrator runs at 9:30 AM ET with fresh data
   - Next morning before 9:30 AM, same cycle repeats

5. **Loaders scheduled and running daily** ✓
   - EventBridge schedules created for all loaders
   - Loaders execute at scheduled times
   - Data appears in RDS tables after each run

## If DNS Still Fails After Deploy

The workaround attempted:
1. Logs detailed diagnostics showing which DNS servers exist
2. Tries to reconfigure /etc/resolv.conf with AWS Route 53 Resolver

**If still fails**:
- Check CloudWatch logs for diagnostic output
- Look for actual IP addresses that can be resolved
- May need to use RDS Proxy as alternative connection path
- Last resort: Use pre-resolved IP instead of hostname (not recommended for RDS)

## Timeline

- **Now**: GitHub Actions deploy-code running (auto-triggered by git push)
- **5-10 min**: Lambda layer published with DNS fixes
- **10-15 min**: First test can run (after Lambda updates)
- **~1 min**: Orchestrator test execution time
- **Before market open (~9:30 AM ET)**: Loaders + morning orchestrator run daily

## What Each Loader Provides

Essential loaders (must have fresh data):
- `loadpricedaily.py` - Stock prices (4 AM ET) ← **CRITICAL**
- `load_technical_data_daily.py` - RSI, SMA, EMA, ATR, etc. (computed after prices)
- `loadbuyselldaily.py` - Buy/sell signals based on technicals (computed after technicals)

Supporting loaders (enhance signals):
- `load_signal_quality_scores.py` - Signal confidence metrics
- `load_market_health_daily.py` - Market condition indicators
- `load_swing_trader_scores.py` - Swing trading momentum scores

Historical loaders (weekly/monthly):
- Earnings calendar
- Balance sheet data
- Cash flow data
- Income statement data

## Next Actions for User

1. **Wait 10 minutes** for GitHub Actions deploy-code to complete
2. **Run test**: `gh workflow run test-orchestrator.yml`
3. **Check logs** for DNS errors and Phase completion
4. **If successful**: Monitor for 2-3 days to confirm fresh data loads daily
5. **If fails**: Share CloudWatch logs so we can diagnose further

---

**Goal Achievement Checklist**:
- [ ] GitHub Actions deploy-code workflow completed
- [ ] test-orchestrator.yml runs without DNS error
- [ ] All 7 phases complete successfully
- [ ] Trades placed in Alpaca account (LIVE mode)
- [ ] Fresh data available in RDS (date = today)
- [ ] Loaders running automatically on schedule
- [ ] Morning orchestrator executes before market open (9:30 AM ET)
- [ ] 2-3 days confirmed working with fresh data
