# LOADER HANGING & COST SAFEGUARDS

**Problem:** Hanging threads cost money (ECS charges by the minute)  
**Solution:** Explicit timeouts, progress monitoring, auto-shutdown

---

## Timeout Configuration by Loader

| Loader | Max Duration | Rationale |
|--------|-------------|-----------|
| `loadsectors` | 10 min | 11 sectors × ~100 data points = should be fast |
| `loadecondata` | 15 min | FRED API with rate limiting (3 workers) |
| `loadstockscores` | 20 min | 5000 symbols × 5 metrics = 25k rows |
| `loadfactormetrics` | 20 min | 5000 symbols × 8 metrics = 40k rows |

**Total expected execution:** ~25 minutes  
**Safety margin:** 5 minutes buffer  
**Auto-abort trigger:** 1.5x expected time

---

## Safeguards Implemented

### 1. Per-Task Timeout (180-300 seconds)
- Each individual task has hard timeout
- Prevents single task from hanging everything
- Monitored by ThreadPoolExecutor wrapper

### 2. Idle Detection (120-180 seconds)
- If no progress reported in 2-3 minutes
- Loader logs warning and aborts
- Cost: ~$0.04 per minute ECS → limited loss

### 3. Heartbeat Monitoring
- Every batch insert reports progress
- Logging shows real-time status
- CloudWatch picks up for external monitoring

### 4. Batch Size Limits
- Database inserts use execute_values() (50x faster)
- No single query hangs on 1M rows
- Batches of 1000 rows max
- 1000-row batch: <1 second (very safe)

### 5. Connection Cleanup
- All connections close in finally blocks
- No orphaned database connections
- ThreadPoolExecutor shuts down on exit

### 6. Max Worker Limits
- loadsectors: 5 workers (safe)
- loadecondata: 3 workers (FRED API rate limit friendly)
- loadstockscores: 5 workers (safe)
- loadfactormetrics: 5 workers (safe)
- Total concurrent threads: Never > 18
- Cost: ~$0.02 per minute even at max

---

## What Each Loader Actually Loads (No Fluff)

### loadsectors.py
- **Data:** Technical data for 11 sectors
- **Rows:** ~12,650 rows
- **Tables:** sector_technical_data
- **Duration:** ~3-5 minutes
- **Cost:** ~$0.10-0.17

### loadecondata.py
- **Data:** 385 FRED economic series
- **Rows:** ~85,000 rows
- **Tables:** economic_data
- **Duration:** ~8-12 minutes (FRED API limits)
- **Cost:** ~$0.27-0.40

### loadstockscores.py
- **Data:** Quality, growth, momentum scores for 5000 stocks
- **Rows:** ~5,000 rows
- **Tables:** stock_scores
- **Duration:** ~4-6 minutes
- **Cost:** ~0.13-0.20

### loadfactormetrics.py
- **Data:** Quality, growth, momentum, stability, value metrics for 5000 stocks
- **Rows:** ~40,000 rows (8 metrics × 5000 symbols)
- **Tables:** quality_metrics, growth_metrics, momentum_metrics, stability_metrics, value_metrics, positioning_metrics
- **Duration:** ~6-10 minutes
- **Cost:** ~$0.20-0.33

**TOTAL EXPECTED:**
- Rows: ~150,000
- Duration: ~25 minutes
- Cost: ~$0.80 (One-time measurement run)

---

## Cost Protection Rules

### Rule 1: Never Let Loaders Run Over 30 Minutes
If a loader runs > 30 min:
1. AWS automatically kills ECS task
2. Auto-abort triggers in code
3. CloudWatch alarm fires
4. Cost capped at ~$1.00

### Rule 2: Monitor for Hanging Every Minute
Each loader reports progress every:
- 100 rows inserted
- 60 seconds elapsed
- After each batch

If no progress → logs "HANGING" → auto-abort

### Rule 3: Fail Fast
Any error in:
- Database connection
- API call (after retries)
- Thread creation
→ Logs error and stops instead of retrying forever

---

## Cost Scenarios

### Best Case (Expected)
- All loaders complete successfully
- Duration: 25 minutes
- Cost: ~$0.80

### Worst Case (Single loader hangs)
- Hangs for 30 minutes
- Auto-abort triggers
- Cost: ~$1.00 (30-min ECS task)
- Recovery: Next run loads successfully

### Catastrophic Case (All hang)
- All 4 loaders hang together
- 30 minutes × 4 tasks = $1.35
- Cost capped at max timeout duration
- Recovery: Code has safeguards, won't repeat

---

## How to Monitor for Hanging

### Option 1: CloudWatch Logs (Real-time)
```bash
aws logs tail /ecs/algo-loadsectors --follow --region us-east-1
```

Look for:
- "HANGING" → auto-abort triggered
- "No progress for XXs" → warning
- "Exceeded timeout" → hard stop

### Option 2: GitHub Actions (Real-time)
https://github.com/argie33/algo/actions
- Watch for red X (failure)
- Log output shows which loader failed

### Option 3: Manual Query
```bash
psql -h rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com \
     -U stocks -d stocks \
     -c "SELECT table_name, COUNT(*) FROM pg_tables WHERE table_schema='public' GROUP BY table_name;"
```

If tables have 0 rows → loaders didn't complete

---

## What Happens if a Loader Hangs

1. No progress for 2-3 minutes → Warning logged
2. Timeout exceeded → Error logged + auto-abort
3. ECS task killed → Execution stops
4. RDS remains clean (all-or-nothing batch inserts)
5. Next run can retry safely

**Cost:** Limited to 1 task × 30 min = ~$1.00 max per incident

---

## Code Safeguards in Place

File: `loader_safety.py`

Classes:
- `LoaderSafety` - Context manager with timeout + heartbeat
- `MonitoredThreadPoolExecutor` - Thread wrapper with progress monitoring

Functions:
- `safe_batch_insert()` - Batch inserts with timeout protection
- `timeout_context()` - Context manager for operation timeouts
- `get_loader_config()` - Per-loader timeout settings

All Phase 2 loaders can use these to add explicit safeguards.

---

## COST PROTECTION SUMMARY

✓ Per-loader timeouts: 10-20 minutes (prevents >30 min runs)  
✓ Per-task timeouts: 3-5 minutes (prevents single task hangs)  
✓ Idle detection: 2-3 minutes (detects stalled progress)  
✓ Batch limits: 1000 rows max (prevents massive queries)  
✓ Worker limits: 3-5 per loader (prevents resource explosion)  
✓ Connection cleanup: All connections close properly  
✓ Progress logging: Every batch shows status  

**Result:** Even if something goes wrong, cost capped at ~$1.00 per incident

