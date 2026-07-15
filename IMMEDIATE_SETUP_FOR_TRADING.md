# Immediate Setup for Trading - Action Plan

## Current Status
✅ All code fixes deployed (commits a1aafb6cd + b54268aad)  
✅ All components tested and working  
✅ System health check: PASS  
⏳ **BLOCKED: Waiting for Alpaca API credentials**

## Your Action Required (5 minutes)

### Step 1: Get Alpaca API Keys
1. Go to https://app.alpaca.markets/
2. Log in to your account
3. Click **"Paper Trading"** (recommended) or Live if you have funded account
4. Navigate to **API Keys** section
5. Copy these two values:
   - **Key ID** (format: `PK_PAPER_xxxxx...`)
   - **Secret Key** (long alphanumeric string)

### Step 2: Add to GitHub Secrets (2 minutes)
1. Open https://github.com/argie33/algo/settings/secrets/actions
2. Click **"New repository secret"**
3. Create secret #1:
   - Name: `ALPACA_API_KEY_ID`
   - Value: [Paste your Key ID from Step 1]
   - Click Add
4. Create secret #2:
   - Name: `ALPACA_API_SECRET_KEY`
   - Value: [Paste your Secret Key from Step 1]
   - Click Add

### Step 3: Deploy (1 minute)
Choose one:

**Option A - Auto Deploy (recommended):**
```bash
git push
# GitHub Actions automatically runs CI → deploy
# Check: https://github.com/argie33/algo/actions
```

**Option B - Manual Trigger:**
1. Go to https://github.com/argie33/algo/actions/workflows/deploy-all-infrastructure.yml
2. Click "Run workflow" → green button
3. Watch deployment (takes 5-10 minutes)

### Step 4: Verify (1 minute after deploy)
```bash
python scripts/run_local_orchestrator.py --morning
```

Look for these messages in the logs:
```
[PHASE 8] Alpaca credentials loaded successfully
[PHASE 8] Entered X positions
[PHASE 8] Trades executed: X
```

## After Credentials Are Set Up

### Morning Routine (Auto-runs via scheduler)
The system runs automatically:
- **2:00 AM ET (morning):** Load prices + technical data
- **4:05 PM ET (EOD):** Load quality/growth/value metrics

### Manual Test
```bash
# Test full pipeline locally
python scripts/run_local_orchestrator.py --morning

# Or with auto-refresh every 30s
python start_dashboard_dev.py -w 30

# Check dashboard at http://localhost:3001
# See positions, P&L, signal metrics
```

### Monitor Production (AWS)
```bash
# Check EventBridge Scheduler (should run 2x daily)
python scripts/verify_eventbridge_scheduler.py

# Check data staleness
python scripts/monitor_data_staleness.py

# Monitor logs
aws logs tail /aws/lambda/algo-orchestrator --follow
```

## Troubleshooting

### "Alpaca credentials not available"
- ✓ Did you add both ALPACA_API_KEY_ID AND ALPACA_API_SECRET_KEY to GitHub Secrets?
- ✓ Did GitHub Actions finish deploying (check https://github.com/argie33/algo/actions)?
- ✓ Did Terraform create the algo/alpaca secret? (check AWS Secrets Manager)

### "No positions entering"
- Check Phase 8 logs: `[PHASE 8] Entering positions for 9 signals`
- If 0 signals: check Phase 7 (signal generation)
- If signals exist but not entering: check position sizing logic

### "Orchestrator not running on schedule"
- Check EventBridge Scheduler: `python scripts/verify_eventbridge_scheduler.py`
- Check CloudWatch logs for the morning/EOD pipeline runs

## Architecture Reference

```
GitHub Secrets (ALPACA_API_KEY_ID, APCA_API_SECRET_KEY)
         ↓
GitHub Actions (reads secrets)
         ↓
Terraform (TF_VAR_alpaca_api_key_id, secret_key)
         ↓
AWS Secrets Manager (algo/alpaca secret created)
         ↓
ECS Orchestrator Task (fetches at runtime)
         ↓
Phase 8 Entry Execution (executes trades via Alpaca API)
         ↓
Positions appear in Alpaca + database
```

## System Features (Ready to Use)

- ✅ **9 automated signals daily** from stock screening
- ✅ **Position sizing** (regime-aware, drawdown-adjusted)
- ✅ **Risk management** (circuit breakers, exposure limits, stop losses)
- ✅ **Dashboard monitoring** (positions, P&L, metrics)
- ✅ **Data validation** (staleness checks, completeness validation)
- ✅ **Audit logging** (every trade, every phase)

## Done! Now You Just Need Credentials

Everything is ready. The only thing blocking full operation is your Alpaca API keys.

**Total time to full operation:** ~10 minutes from this point
1. Get keys from Alpaca (2 min)
2. Add to GitHub Secrets (2 min)  
3. Deploy via GitHub Actions (5 min)
4. Test (1 min)

Then trades will execute automatically on schedule! 🚀
