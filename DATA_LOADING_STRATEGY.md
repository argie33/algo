# 📊 COMPREHENSIVE DATA LOADING STRATEGY
**Goal:** Load 100% of data for 4,988 stocks + 4,998 ETFs to both LOCAL and AWS

---

## 🔴 CURRENT SITUATION

```
COVERAGE ANALYSIS:
├─ Total Stocks: 4,988
├─ Total ETFs: 4,998
├─ Stock Symbols Loaded: 4,988 ✅
├─ Stock Scores Loaded: 4,988 ✅
├─ Stock Prices Loaded: 134 (2.7%) ❌❌❌
├─ Stock Signals Loaded: 63 (1.3%) ❌❌❌
└─ Missing: 4,854 stocks need prices, 4,925 need signals
```

**Why So Slow Locally?**
- yfinance API is rate-limited (45-60 sec per batch of 20 symbols)
- Single-threaded local execution
- No parallelization (serial batches)
- At current rate: 4+ hours to load all 250 batches

---

## ✅ SOLUTION: AWS ECS PARALLEL DEPLOYMENT

Instead of slow serial loading locally, deploy loaders to **AWS ECS with 5-10 parallel workers**.

### Benefits
```
✅ 5-10x faster (parallel workers, not serial batches)
✅ AWS native - better bandwidth to data APIs
✅ Auto-recovery from failures
✅ CloudWatch logging for monitoring
✅ Can restart failed tasks automatically
✅ Horizontal scaling
```

---

## 📋 IMPLEMENTATION PLAN

### PHASE 1: PREPARE & COMMIT CODE (5 minutes)
```bash
# Create AWS deployment script
# Commit to GitHub
# Trigger AWS CloudFormation deployment
```

### PHASE 2: RUN LOADERS IN AWS ECS (2-3 hours)
```bash
# AWS ECS runs 5-10 instances in parallel
# Each loads independent chunks of symbols
# Total time: ~2-3 hours (vs 4+ hours local)
```

### PHASE 3: VERIFY COMPLETE COVERAGE (15 minutes)
```bash
# Query database for 100% coverage
# Check CloudWatch logs
# Alert on any failures
```

---

## 🚀 DETAILED EXECUTION STEPS

### STEP 1: Create AWS ECS Task Definition

The loaders need to run in ECS with proper environment variables:

```yaml
Environment:
  DB_HOST: stocks.coyohuyj0mg8.us-east-1.rds.amazonaws.com
  DB_USER: stocks
  DB_NAME: stocks
  DB_PASSWORD: (from Secrets Manager)
  AWS_REGION: us-east-1
  LOADER_TYPE: price_daily  # or buysell_daily
  SYMBOL_CHUNK: 1-1000      # Divide symbols among workers
```

### STEP 2: Deploy Loaders to GitHub

Push current code with any fixes needed:
```bash
git add .
git commit -m "chore: Prepare loaders for parallel AWS ECS deployment"
git push origin main
```

### STEP 3: Trigger AWS Deployment

Create CloudFormation stack to deploy ECS tasks:
```bash
aws cloudformation deploy \
  --template-file template-ecs-data-loaders.yml \
  --stack-name stocks-data-loaders \
  --capabilities CAPABILITY_NAMED_IAM
```

### STEP 4: Monitor CloudWatch Logs

```bash
# Watch real-time logs from all ECS tasks
aws logs tail /ecs/stocks-data-loaders --follow
```

---

## 📊 EXPECTED RESULTS

After 2-3 hours of parallel ECS processing:

```
Expected Coverage:
├─ Stock Prices: 4,800-4,900 symbols (96-98%)
├─ Stock Signals: 4,600-4,800 symbols (92-96%)
└─ API Failures: 50-100 symbols (2-4%) - acceptable

Why not 100%?
- Some symbols have IPO/new listings (no historical data)
- Some delisted (no active data)
- Some API calls fail (yfinance issues)
- Some have zero trading volume
```

---

## 🛠️ LOADER OPTIMIZATION NOTES

### loadpricedaily.py
- **Current:** 20 symbols/batch, serial
- **Optimized for ECS:** Parallel instances each handling 500-1000 symbols
- **Batch size:** Can increase to 50 symbols/batch in parallel context
- **Retry logic:** Already has exponential backoff

### loadbuyselldaily.py
- **Current:** 2 workers, processing 4,741 symbols serially
- **Optimized for ECS:** 10 workers, each processing 474 symbols = parallel
- **Computation:** Heavy (technical indicators) but CPU-bound, scales well

---

## 📈 MONITORING & RECOVERY

### Real-time Monitoring
```bash
# Dashboard: AWS Console → ECS → stocks-data-loaders
# Logs: CloudWatch Logs
# Metrics: Task count, success/failure rate
```

### Auto-Recovery
```bash
# Failed task? ECS automatically restarts
# Partial data? Unique constraint prevents duplicates
# Missing symbol? Can retry specific symbols later
```

### Manual Recovery (if needed)
```bash
# Identify which symbols failed
# Create retry file with failed symbols
# Launch single task to reprocess just those
```

---

## 📊 DATA INTEGRITY

### Prevents Duplicates
- All tables have PRIMARY KEY or UNIQUE constraints
- Duplicate inserts are silently ignored
- Safe to re-run loaders multiple times

### Maintains Referential Integrity
- All foreign keys already enforced
- Can't insert price without symbol existing
- Can't insert signal without price existing

---

## 🎯 SUCCESS CRITERIA

✅ Deployment complete
✅ All ECS tasks completed successfully
✅ Database verified:
   - 4,800+ stocks with prices
   - 4,600+ stocks with signals
   - Zero missing stock_scores (4,988)
✅ CloudWatch logs show clean completion
✅ Query times < 100ms for typical queries
✅ Ready for production API deployment

---

## 📌 IMPORTANT NOTES

1. **Local loaders will continue** - Safe to keep running (duplicates prevented)
2. **AWS takes priority** - Use AWS results as source of truth
3. **Partial failures expected** - 2-4% failure rate is normal for bulk API loading
4. **No data loss** - Everything already in database persists
5. **Ready for AWS deployment** - Can push to production immediately after

---

**Last Updated:** 2026-02-26 19:30 UTC
**Status:** Ready for AWS ECS deployment
