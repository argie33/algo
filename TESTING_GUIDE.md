# Quick Start: End-to-End System Testing

**Goal**: Populate test data and run full orchestrator test (Phase 1-7) to verify all system features.

**Timeline**: 15 minutes

---

## Option A: FASTEST — GitHub Actions (Recommended)

### Step 1: Push Code

```bash
git push origin main
```

### Step 2: Trigger Workflow

1. Go to: https://github.com/YOUR_ORG/algo/actions
2. Select: **"Populate Test Data & Run Orchestrator"** workflow
3. Click: **"Run workflow"** button
4. Set:
   - Test date: `2026-04-15` (or any historical date)
   - Coverage: `95`
5. Click: **"Run workflow"**

### Step 3: Monitor

Watch logs in GitHub Actions. Workflow will:
1. ✅ Populate test data (2-3 min)
2. ✅ Invoke orchestrator (1-2 min)
3. ✅ Retrieve CloudWatch logs (Phase 1-7 results)

### Step 4: Check Results

In the workflow summary, look for:
```
✅ Phase 1: PASS (95% coverage)
✅ Phase 2: PASS (Circuit Breakers OK)
✅ Phase 3: PASS (Position Monitor OK)
✅ Phase 4: PASS (Exit Execution OK)
✅ Phase 5: PASS (Signal Generation OK)
✅ Phase 6: PASS (Entry Execution OK)
✅ Phase 7: PASS (Reconciliation OK)
```

**If all show ✅**: Your system is fully operational!

---

## Option B: Local Python (With AWS Credentials)

### Prerequisites

```bash
# Install dependencies
pip3 install psycopg2-binary

# Configure AWS
aws configure
# Enter: Access Key, Secret, Region (us-east-1), Format (json)
```

### Step 1: Get RDS Connection Info

```bash
cd terraform
terraform init
RDS_HOST=$(terraform output -raw rds_address)
RDS_PORT=$(terraform output -raw rds_port)
RDS_PASS=$(terraform output -raw rds_password)
cd ..
```

### Step 2: Populate Test Data

```bash
python3 tests/integration/populate_test_data.py \
  --date 2026-04-15 \
  --coverage 95 \
  --host "$RDS_HOST" \
  --port "$RDS_PORT" \
  --user stocks \
  --password "$RDS_PASS"
```

Expected:
```
✅ price_daily: 5225 rows (95.5%)
✅ technical_data_daily: 5225 rows
✅ trend_template_data: 5225 rows
✅ buy_sell_daily: 1567 signals
✅ signal_quality_scores: 1567 scores
🎯 Phase 1: PASSES (≥70% coverage)
```

### Step 3: Run Orchestrator Test

```bash
cd terraform
LAMBDA=$(terraform output -raw algo_lambda_function_name)
cd ..

aws lambda invoke \
  --function-name "$LAMBDA" \
  --invocation-type RequestResponse \
  --payload '{"date":"2026-04-15","test":"true"}' \
  /tmp/response.json

cat /tmp/response.json | python3 -m json.tool
```

### Step 4: View Logs

```bash
aws logs tail /aws/lambda/algo-algo-dev --follow | head -150
```

Look for:
```
[Phase 1] PASS ✅
[Phase 2] PASS ✅
[Phase 3] PASS ✅
...
[Phase 7] PASS ✅
```

---

## What Success Looks Like

### Phase 1: Data Freshness ✅
```
Universe coverage: 95.5% (PASSES ≥70%)
signal_quality_scores: 1567 rows populated
buy_sell_daily: 1567 signals
All required tables have data
```

### Phase 2: Circuit Breakers ✅
```
Drawdown check: OK (no limit exceeded)
Daily loss check: OK
Consecutive loss check: OK
VIX check: OK (market conditions favorable)
```

### Phase 3: Position Monitor ✅
```
Current positions: 0 open
Health scoring: Ready for entry signals
Trailing stops: Configured
```

### Phases 4-7: Execution ✅
```
Phase 4: Exit Execution → No exits (no open positions)
Phase 5: Signal Generation → 245 signals passed filters
Phase 6: Entry Execution → 3 entries executed (SPY, MSFT, AAPL)
Phase 7: Reconciliation → Portfolio synced, P&L recorded
```

---

## Verify APIs Are Working

After orchestrator succeeds:

```bash
# Get API URL from Terraform
cd terraform
API_URL=$(terraform output -raw api_url)
cd ..

# Test health
curl "$API_URL/api/health"

# Test orchestrator status
curl "$API_URL/api/algo/status"

# Test other endpoints
curl "$API_URL/api/algo/trades"
curl "$API_URL/api/algo/positions"
curl "$API_URL/api/signals/stocks"
```

Expected: All return JSON with 200 status code.

---

## Verify Frontend Loads

```bash
cd terraform
DOMAIN=$(terraform output -raw cloudfront_domain)
cd ..

# Open in browser
open "https://$DOMAIN"  # macOS
# or
start "https://$DOMAIN"  # Windows
```

Expected: React frontend loads with 22 pages, can navigate through:
- AlgoTradingDashboard
- TradeTracker
- PortfolioDashboard
- SignalAnalyzer
- RiskAnalyzer
- And 17+ more...

---

## If Phase 1 Fails

### Error: "Only 45% of universe updated"

Solution: Use 100% coverage:
```bash
python3 tests/integration/populate_test_data.py \
  --date 2026-04-15 \
  --coverage 100 \
  --host "$RDS_HOST" \
  --port "$RDS_PORT" \
  --user stocks \
  --password "$RDS_PASS"
```

### Error: "signal_quality_scores table empty"

Solution: Repopulate buy/sell signals:
```bash
python3 tests/integration/populate_test_data.py \
  --date 2026-04-15 \
  --coverage 95 \
  --signals 50 \  # Increase signal percentage
  --host "$RDS_HOST" \
  --port "$RDS_PORT" \
  --user stocks \
  --password "$RDS_PASS"
```

---

## Summary

**Recommended Path**:
1. ✅ Push code: `git push origin main`
2. ✅ Run GitHub Actions workflow (5 min)
3. ✅ Check Phase 1-7 in logs (should all be ✅)
4. ✅ Test APIs with curl (1 min)
5. ✅ Test frontend in browser (1 min)

**Total time**: ~10 minutes to full end-to-end verification.

---

**Status**: System is fully deployed. This guide shows how to verify it's working end-to-end.
