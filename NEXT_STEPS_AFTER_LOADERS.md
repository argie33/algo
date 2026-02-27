# ✅ NEXT STEPS - After Data Loaders Complete

**When to follow this:** After `RUN_ALL_LOADERS.sh` completes (approx 21:15 CST Feb 26, 2026)

---

## 🎯 STEP 1: VERIFY DATA LOADED (5 minutes)

### Check Buy/Sell Signals Coverage
```bash
export PGPASSWORD="bed0elAn"
psql -h localhost -U stocks -d stocks -c "
  SELECT
    COUNT(DISTINCT symbol) as symbols_with_signals,
    ROUND(100 * COUNT(DISTINCT symbol) / 4988.0, 1) as percent_coverage,
    COUNT(*) as total_signal_records
  FROM buy_sell_daily;
"
```

**Expected Result:**
- ✅ 4,988 symbols with signals (100%)
- ✅ Thousands of signal records
- ✅ No "46 symbols" error

### If Got Only 46 Symbols
→ DO NOT PUSH YET
→ See troubleshooting section below

---

## 🚀 STEP 2: COMMIT & PUSH (2 minutes)

**Only if data loaded correctly:**

```bash
# Check what changed
git status

# Add documentation
git add DATA_LOADING_STATUS_FEB26_2026.md
git add NEXT_STEPS_AFTER_LOADERS.md

# Commit
git commit -m "docs: Data loading completion - all 4,988 stocks with signals"

# Push to GitHub
git push origin main
```

**This will trigger:**
- GitHub Actions: Data Loaders Pipeline
- Deploy infrastructure to AWS
- Build Docker images
- Run loaders in ECS

---

## 📊 STEP 3: MONITOR GITHUB ACTIONS (10 minutes)

### Check Workflow Status
```bash
# Check if workflow triggered
git log --oneline -3

# Visit in browser:
# https://github.com/argie33/algo/actions
```

### What to Look For
```
✅ Detect Changed Loaders       (should detect loadbuyselldaily.py)
✅ Deploy Infrastructure        (RDS/ECS setup)
✅ Update Container Image       (Docker build)
✅ Execute Loaders              (ECS tasks running)
✅ All workflows complete       (green checkmarks)
```

### If Workflow Fails
1. Check error logs in GitHub Actions
2. Identify what failed (most common: Docker build)
3. Fix in code
4. Commit and push again

---

## 🔍 STEP 4: VERIFY API HEALTH (5 minutes)

### Test Health Endpoint
```bash
# Get CloudFormation outputs
aws cloudformation describe-stacks \
  --stack-name stocks-app-stack \
  --query 'Stacks[0].Outputs' \
  --region us-east-1

# Test health endpoint
curl https://YOUR_API_URL/health

# Expected response:
# {
#   "database": "connected",
#   "tables": {
#     "stock_symbols": 4988,
#     "buy_sell_daily": 4988,
#     "stock_scores": 4988
#   }
# }
```

### If API Not Responding
→ Lambda may still be deploying (wait 5 minutes)
→ Check Lambda logs in CloudWatch

---

## 💻 STEP 5: TEST FRONTEND (5 minutes)

### Access Frontend
```
https://algo-stocks.example.com/
```

### Check Dashboard
1. Login with Cognito credentials
2. Visit Scores Dashboard
3. Verify all 4,988 stocks appear
4. Check trading signals column
5. Verify stock details page works

### If Frontend Shows Old Data
→ Frontend may be cached
→ Hard refresh: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)

---

## 🐛 TROUBLESHOOTING

### Problem: Still Only 46 Signals After Loader Completed

**Possible Cause 1: loadbuyselldaily.py Didn't Run**
```bash
# Check if it ran
grep -i "loadbuyselldaily\|buy_sell_daily" /tmp/loader_*.log

# If no output, loader didn't run
# Solution: Run manually
python3 loadbuyselldaily.py
```

**Possible Cause 2: Exchange Filter Still Wrong**
```bash
# Check the code
grep -n "WHERE.*exchange" loadbuyselldaily.py

# Should NOT have WHERE exchange IN (...)
# If it does, the fix didn't apply correctly
```

**Possible Cause 3: Database Connection Error**
```bash
# Check database is running
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM stock_symbols"

# Should return: 4988
```

**Possible Cause 4: Loaders Errored Out**
```bash
# Check for errors in log
tail -20 /tmp/loader_loadbuyselldaily.log | grep -i error

# If errors found:
# 1. Note the error message
# 2. Fix the code
# 3. Re-run: python3 loadbuyselldaily.py
```

---

## ✅ SUCCESS CRITERIA

All of these should be true:

- [ ] loadbuyselldaily.py completed without errors
- [ ] buy_sell_daily has 4,988+ symbols
- [ ] buy_sell_daily has 10,000+ signal records
- [ ] GitHub workflow triggered and succeeded
- [ ] ECS loaders executed in AWS
- [ ] API health endpoint works
- [ ] Frontend shows all 4,988 stocks
- [ ] Trading signals appear for stocks

---

## 📋 QUICK REFERENCE

### View Loader Logs
```bash
# Current status
tail -20 /tmp/loader_run.log

# Price loading progress
tail -20 /tmp/loader_loadpricedaily.log

# Check for errors
grep ERROR /tmp/loader_*.log

# Full log view
less /tmp/loader_run.log
```

### Database Queries
```bash
export PGPASSWORD="bed0elAn"

# Total data counts
psql -h localhost -U stocks -d stocks -c "
SELECT COUNT(*) FROM stock_symbols;
SELECT COUNT(*) FROM buy_sell_daily;
SELECT COUNT(*) FROM buy_sell_weekly;
SELECT COUNT(*) FROM stock_scores;
"

# Sample signals
psql -h localhost -U stocks -d stocks -c "
SELECT symbol, signal, date, score FROM buy_sell_daily LIMIT 10;
"
```

---

## 🎉 IF EVERYTHING WORKS

**Congratulations!** You now have:

✅ Complete data coverage (4,988 stocks)
✅ Trading signals for ALL stocks
✅ Production-ready database
✅ Deployed to AWS infrastructure
✅ Working web application
✅ Ready for real trading signals

**What to do next:**
1. Monitor the system in production
2. Verify signal quality
3. Run backtests on trading signals
4. Set up alerts for high-quality signals
5. Connect to trading platform (optional)

---

## 📞 GETTING HELP

**If loaders fail:**
1. Check log files in `/tmp/loader_*.log`
2. Run one loader manually to debug
3. Check database connectivity
4. Look for API rate limit errors

**If GitHub Actions fails:**
1. Check workflow logs on GitHub
2. Most common: Docker build issues
3. Check ECR registry connectivity

**If frontend shows wrong data:**
1. Check browser cache
2. Hard refresh
3. Check API endpoint
4. Verify database has data
