# Batch 5 - Quick Diagnostic & Fix Guide

**Purpose:** Get logs, understand issues, fix them fast

---

## QUICK STATUS CHECK (Do This First)

### Option 1: Run the Status Script
```bash
bash get-batch5-status.sh
```

This will:
- ✓ Check GitHub Actions workflow
- ✓ List ECS tasks and their status
- ✓ Pull last 100 lines of CloudWatch logs
- ✓ Search for ERROR messages
- ✓ Check database row counts

### Option 2: Manual Checks (If script fails)

**GitHub Actions:** https://github.com/argie33/algo/actions
- Click "Data Loaders Pipeline"
- Look at latest run
- Check if "Execute Loaders" job is running/completed

**ECS Console:** AWS → ECS → Clusters → stocks-cluster
- Should see 4 tasks
- Status: RUNNING or STOPPED
- If STOPPED: check exit code (0 = success, non-zero = failure)

**CloudWatch:** AWS → CloudWatch → Log Groups → /aws/ecs/stocks-loader-tasks
- Should see log streams for each loader
- Latest timestamps should be recent
- Search for "ERROR" to find problems

---

## WHAT TO LOOK FOR

### ✅ GOOD SIGNS (Everything working)
```
✓ Tasks status: RUNNING or STOPPED with exit code 0
✓ Recent log entries (within last 5 minutes)
✓ Messages like "Loading symbol [1234/4982]..."
✓ Messages like "Inserting row for TICKER..."
✓ No "ERROR" in logs
✓ Database row counts increasing
```

### ❌ PROBLEM SIGNS (Need to fix)
```
✗ Tasks: STOPPED with exit code 1 (failure)
✗ No log entries (task crashed immediately)
✗ "ERROR - Failed to connect" (database issue)
✗ "ERROR - Connection refused" (network issue)
✗ "ERROR - No password supplied" (credentials issue)
✗ Task runtime: < 10 seconds (crashed)
✗ Database row counts: 0 (nothing loaded)
```

---

## COMMON ISSUES & FIXES

### Issue 1: "fe_sendauth: no password supplied"
**Problem:** DB_PASSWORD not in environment
**Fix:**
```bash
# Check GitHub Secrets
gh secret list | grep RDS_PASSWORD

# If missing, add it:
gh secret set RDS_PASSWORD --body "your_password_here"

# Retrigger workflow
git commit --allow-empty -m "Retrigger loaders" 
git push
```

### Issue 2: "Cannot connect to database"
**Problem:** RDS not accessible, network issue, or wrong host
**Fix:**
```bash
# Test connection
psql -h rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com \
     -U stocks -d stocks -c "SELECT 1"

# If fails: check RDS security group allows port 5432 from ECS security group
```

### Issue 3: Task exits immediately (< 10 seconds)
**Problem:** Loader crashed during startup
**Fix:**
1. Check CloudWatch logs for first ERROR message
2. Common causes:
   - Missing dependency (check Dockerfile)
   - Wrong trigger timestamp (re-push with new timestamp)
   - Missing table (run init_database.py locally first)

### Issue 4: Loader hangs (no new log lines for 5+ minutes)
**Problem:** API call timeout or database lock
**Fix:**
```bash
# Check if yfinance API is up
curl https://query1.finance.yahoo.com/v7/finance/quote?symbols=AAPL

# If down: wait and retry
# If up: check database for locks
#   SELECT * FROM pg_stat_activity WHERE state = 'idle in transaction'
```

### Issue 5: "Unique constraint violation"
**Problem:** Data already exists (not an error, expected)
**Fix:** This is NORMAL - ON CONFLICT DO UPDATE handles it, no action needed

### Issue 6: Database empty after 1+ hours
**Problem:** Loaders running but not inserting
**Fix:**
1. Check for SQL errors in logs
2. Verify table exists: `SELECT * FROM stock_symbols LIMIT 1`
3. Check if inserts are slow (check database CPU)

---

## GET LOGS FOR ANALYSIS

### Copy-Paste These Commands

**Get all logs from last hour:**
```bash
aws logs filter-log-events \
  --log-group-name /aws/ecs/stocks-loader-tasks \
  --start-time $(date -d '1 hour ago' +%s)000 \
  --query 'events[].[timestamp,message]' \
  --output text > batch5-logs.txt

# Send me the output
cat batch5-logs.txt
```

**Get only ERROR lines:**
```bash
aws logs filter-log-events \
  --log-group-name /aws/ecs/stocks-loader-tasks \
  --filter-pattern "ERROR" \
  --query 'events[].message' \
  --output text > batch5-errors.txt

# Send me the output
cat batch5-errors.txt
```

**Get task status:**
```bash
aws ecs list-tasks --cluster stocks-cluster --query 'taskArns' --output text | \
xargs aws ecs describe-tasks --cluster stocks-cluster --tasks \
  --query 'tasks[].[taskArn,lastStatus,desiredStatus,exitCode]' \
  --output table > batch5-tasks.txt

# Send me the output
cat batch5-tasks.txt
```

**Get database row counts:**
```bash
psql -h rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com \
     -U stocks -d stocks << EOF > batch5-rowcounts.txt
SELECT 'annual_cash_flow' as table_name, COUNT(*) as rows FROM annual_cash_flow
UNION
SELECT 'quarterly_cash_flow', COUNT(*) FROM quarterly_cash_flow
UNION
SELECT 'quality_metrics', COUNT(*) FROM quality_metrics
UNION
SELECT 'growth_metrics', COUNT(*) FROM growth_metrics
UNION
SELECT 'stock_scores', COUNT(*) FROM stock_scores;
EOF

# Send me the output
cat batch5-rowcounts.txt
```

---

## SHARE LOGS WITH ME (How to Get Help)

1. **Run the diagnostic script:**
   ```bash
   bash get-batch5-status.sh > batch5-status.txt 2>&1
   ```

2. **Get the logs:**
   ```bash
   aws logs filter-log-events \
     --log-group-name /aws/ecs/stocks-loader-tasks \
     --query 'events[].message' \
     --output text > batch5-logs.txt
   ```

3. **Share with me:**
   - Copy the contents of `batch5-status.txt`
   - Copy the contents of `batch5-logs.txt`
   - Tell me what you see

4. **I'll:**
   - Analyze the logs
   - Find root cause
   - Give you exact fixes to apply

---

## QUICK FIX CHECKLIST

### If tasks are STOPPED with exit code 0 (SUCCESS)
- ✓ Loaders completed successfully
- ✓ Check database for row counts
- ✓ Move to next phase (Phase 6)

### If tasks are STOPPED with exit code 1 (FAILURE)
1. [ ] Get logs: `aws logs filter-log-events --log-group-name /aws/ecs/stocks-loader-tasks`
2. [ ] Find first ERROR line
3. [ ] Copy ERROR and paste to me
4. [ ] I'll tell you the fix
5. [ ] Apply fix and retrigger

### If tasks are RUNNING
- ✓ Check logs for progress
- ✓ Look for latest symbol being processed
- ✓ Estimate completion time (1 symbol per 0.5 seconds typical)
- ✓ Let it run to completion

### If tasks not found
- [ ] Check if already STOPPED (completed)
- [ ] Check if workflow detected changes (GitHub Actions page)
- [ ] Check if new ECR images exist (AWS ECR console)
- [ ] Retrigger if needed: `git commit --allow-empty -m "Retrigger" && git push`

---

## ACTION ITEMS (In Order)

1. **RIGHT NOW:**
   - [ ] Run `bash get-batch5-status.sh`
   - [ ] Tell me what you see

2. **IF RUNNING:**
   - [ ] Wait for completion (5-7 hours typical)
   - [ ] Monitor logs every 30 min
   - [ ] Check for ERROR messages

3. **IF STOPPED (Exit code 0):**
   - [ ] Verify database row counts
   - [ ] Check Phase 6 can start
   - [ ] Celebrate! ✅

4. **IF STOPPED (Exit code 1):**
   - [ ] Get ERROR logs
   - [ ] Tell me the exact error
   - [ ] I'll give you fix
   - [ ] Apply and retrigger

---

## Real-Time Monitoring

While tasks are running, check progress every 30 minutes:

```bash
# Quick progress check
aws logs tail /aws/ecs/stocks-loader-tasks --follow --format short
```

This will show:
- New log lines as they appear
- Latest symbol being processed
- Any ERRORs in real-time
- Completion messages

---

## Next Steps After Completion

Once all 4 loaders complete with exit code 0:

1. **Verify data:**
   ```bash
   psql -h rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com \
        -U stocks -d stocks -c "
     SELECT COUNT(*) as annual_cash_flow_rows FROM annual_cash_flow;
     SELECT COUNT(*) as quality_metrics_rows FROM quality_metrics;
   "
   ```

2. **Check API responds to data:**
   ```bash
   curl https://your-api-url/api/diagnostics
   ```

3. **Plan Phase 6:**
   - Market analytics
   - Sentiment data
   - Economic indicators

---

**Status Report Template** (Copy this and fill it in)
```
BATCH 5 STATUS REPORT
====================

Current Time: [YOUR TIME]
Time Running: [DURATION]

GitHub Actions:
- Workflow: [RUNNING/STOPPED]
- Jobs completed: [#/#]

ECS Tasks:
- annualcashflow: [STATUS] - exit code [X]
- quarterlycashflow: [STATUS] - exit code [X]
- factormetrics: [STATUS] - exit code [X]
- stockscores: [STATUS] - exit code [X]

Latest Logs:
[PASTE 10 MOST RECENT LINES]

Errors Found:
[ANY ERROR MESSAGES]

Database Row Counts:
- annual_cash_flow: [X] rows
- quarterly_cash_flow: [X] rows
- quality_metrics: [X] rows
- stock_scores: [X] rows

Assessment:
[WHAT'S HAPPENING?]
```

---

**BOTTOM LINE:** Share the diagnostic output with me and I'll fix whatever's broken. Let's get this working! 🚀
