# Batch 5 - Complete Log Analysis & Learning Guide

**Purpose:** Understand what's happening in AWS by reading the logs
**Audience:** Anyone wanting to learn from execution logs

---

## Where Logs Live

### 1. GitHub Actions Logs (High Level)
**URL:** https://github.com/argie33/algo/actions/workflows/deploy-app-stocks.yml

**Shows:**
- When workflow starts, stops, succeeds, fails
- Which step is running
- Why steps fail (common issues)
- Overall execution time

### 2. CloudWatch Logs (Detailed Execution)
**AWS Console → CloudWatch → Log Groups**

**Log Group:** `/aws/ecs/stocks-loader-tasks`

**Shows:**
- Every single print() statement from the loader
- Database operations in real-time
- Symbols being processed
- Errors as they occur
- Final completion messages

### 3. ECS Task Details (Task Level)
**AWS Console → ECS → Clusters → stocks-cluster**

**Shows:**
- Task status (RUNNING, STOPPED, FAILED)
- Exit code (0 = success, non-zero = failure)
- When task started and stopped
- CPU/memory usage
- Container details

---

## What to Expect in Logs

### PHASE 1: GitHub Actions Workflow Starts

**GitHub Actions shows:**
```
✓ Checkout code
✓ Check infrastructure changes
  └─ Output: "changed=true"
✓ Generate loader matrix
  └─ Output: "Generated matrix: {"include":[...]}"
```

**What this means:** Workflow detected your 4 changed loader files.

---

### PHASE 2: Infrastructure Deployment

**GitHub Actions shows:**
```
✓ Deploy Infrastructure
  └─ CloudFormation creating ECS resources
  └─ Output: "Infrastructure deployment FORCED..."
```

**CloudWatch logs:** (One log stream per loader)
```
[No logs yet - containers haven't started]
```

**What this means:** AWS is setting up task definitions and ECR repositories.

---

### PHASE 3: Docker Build & Push

**GitHub Actions shows:**
```
✓ Build and push Docker image
  └─ Building image: stocks-app-registry:annualcashflow-latest
  └─ Pushing to ECR...
  └─ Output: "Image pushed successfully"
```

**This happens 4 times** (one per loader)

**CloudWatch logs:** (Still no logs - building offline)

**What this means:** Docker images are being built locally, then pushed to AWS ECR registry.

---

### PHASE 4: Task Execution Starts

**GitHub Actions shows:**
```
✓ Execute loader task
  ├─ Getting task definition
  ├─ Updating task definition with image + environment
  ├─ Registering new task definition revision
  ├─ Launching ECS task
  └─ Output: "Started task: arn:aws:ecs:..."
```

**CloudWatch logs NOW APPEAR:**
```
2026-04-29 08:45:30,123 - INFO - Starting loadannualcashflow.py
2026-04-29 08:45:30,124 - INFO - Using environment variables for database config
2026-04-29 08:45:30,456 - INFO - Connecting to database...
```

**ECS Console shows:**
```
Task Status: PROVISIONING → PENDING → ACTIVATING → RUNNING
Task Age: 30 seconds
Container Status: PROVISIONING → RUNNING
```

**What this means:** Loader has started and is about to connect to the database.

---

### PHASE 5: Database Connection

**SUCCESS PATH (What you want to see):**
```
2026-04-29 08:45:31,100 - INFO - Using environment variables for database config
2026-04-29 08:45:31,456 - INFO - DB connection successful
2026-04-29 08:45:31,500 - INFO - Creating tables if not exist...
2026-04-29 08:45:32,123 - INFO - Table check complete
```

**FAILURE PATH (What to avoid):**
```
2026-04-29 08:45:31,100 - INFO - Using environment variables for database config
2026-04-29 08:45:31,234 - ERROR - Failed to connect to database: fe_sendauth: no password supplied
```

**What this means:**
- SUCCESS: Database credentials were valid, connection established
- FAILURE: Database password missing or incorrect (check GitHub secrets)

**Most common cause of FAILURE:** DB_PASSWORD not set in GitHub secrets

---

### PHASE 6: Symbol Loading

**NORMAL PROGRESS:**
```
2026-04-29 08:45:35,000 - INFO - Loading cash flows for 4982 stocks...
2026-04-29 08:45:35,100 - INFO - [1/4982] Loading AAPL...
2026-04-29 08:45:35,600 - INFO - [2/4982] Loading MSFT...
2026-04-29 08:45:36,100 - INFO - [3/4982] Loading GOOGL...
...
2026-04-29 09:15:22,500 - INFO - [100/4982] Loading XYZ...
```

**Every ~0.5 seconds you should see:**
- One new symbol being processed
- Log lines incrementing the symbol count [N/4982]

**SLOW PROGRESS (> 2 seconds per symbol):**
- Might mean database is slow
- Or yfinance API is slow
- Normal - will still complete, just takes longer

**NO NEW LINES FOR > 5 MINUTES:**
- Possible hang/freeze
- Check if yfinance API is up
- Might need to restart task

**FAILURE (sudden stop):**
```
2026-04-29 09:45:12,500 - INFO - [2501/4982] Loading ABC...
2026-04-29 09:45:12,700 - ERROR - Error loading cash flow for ABC: timeout
2026-04-29 09:45:12,800 - INFO - Continuing with next symbol...
```

**What this means:**
- Individual symbol failed (OK, loader continues)
- If you see 100+ errors - might be a systemic issue

---

### PHASE 7: Data Insertion

**YOU SHOULD SEE:**
```
2026-04-29 09:45:32,100 - INFO - [2500/4982] Loading XYZ...
2026-04-29 09:45:32,123 - DEBUG - Inserting row for XYZ, 2025...
2026-04-29 09:45:32,234 - DEBUG - Inserting row for XYZ, 2024...
2026-04-29 09:45:32,345 - DEBUG - Inserting row for XYZ, 2023...
```

**Database commits happen every 10 symbols:**
```
2026-04-29 09:45:35,000 - INFO - Committing batch (10 symbols)
```

**What this means:** Rows are being inserted into the database.

---

### PHASE 8: Completion

**SUCCESS COMPLETION:**
```
2026-04-29 11:15:45,100 - INFO - Completed: 18420 rows inserted
2026-04-29 11:15:45,200 - INFO - annualcashflow loader finished successfully
```

**FAILURE COMPLETION:**
```
2026-04-29 11:15:45,100 - ERROR - Error: Database connection lost
2026-04-29 11:15:45,200 - ERROR - Failed to complete: connection timeout
```

**GitHub Actions shows:**
```
✓ Wait for task completion
✓ Check task result
  └─ Task stopped with exit code: 0 ✓ (SUCCESS)
  └─ OR exit code: 1 ✗ (FAILURE)
```

**ECS Console shows:**
```
Task Status: STOPPED
Exit Code: 0 (Success) or Non-zero (Failure)
Task Runtime: 1h 15m 23s
```

**What this means:**
- Exit code 0 = Loader completed successfully
- Exit code 1 = Loader encountered an error and stopped

---

## Log Patterns to Learn From

### Pattern 1: Rate Limiting
```
2026-04-29 10:15:30,100 - INFO - [1500/4982] Loading TICKER...
2026-04-29 10:15:30,600 - WARNING - Rate limited, waiting 5s...
2026-04-29 10:15:35,600 - INFO - Retry attempt 1 for TICKER
2026-04-29 10:15:36,100 - INFO - [1501/4982] Loading TICKER... (retry successful)
```

**What this teaches:** 
- Loader hits yfinance rate limit (too many requests)
- Loader waits 5 seconds
- Loader retries and succeeds
- This is NORMAL and EXPECTED

### Pattern 2: Missing Data
```
2026-04-29 10:20:15,100 - INFO - [2000/4982] Loading SMALL_CAP...
2026-04-29 10:20:15,600 - INFO - No data found for SMALL_CAP
2026-04-29 10:20:15,700 - INFO - Skipping SMALL_CAP (no data)
2026-04-29 10:20:16,100 - INFO - [2001/4982] Loading NEXT_TICKER...
```

**What this teaches:**
- Some stocks don't have data in yfinance
- Loader skips them gracefully
- This is NORMAL and EXPECTED
- These stocks just won't have entries in tables

### Pattern 3: Database Error (NOT CRITICAL)
```
2026-04-29 10:30:15,100 - INFO - Inserting row for TICKER, 2025...
2026-04-29 10:30:15,234 - ERROR - Unique constraint violation for TICKER, 2025
2026-04-29 10:30:15,300 - INFO - Row already exists (updating instead)
```

**What this teaches:**
- Database already had data for this key
- ON CONFLICT DO UPDATE handled it
- Data updated instead of inserted
- This is NORMAL and EXPECTED

### Pattern 4: Connection Loss (CRITICAL)
```
2026-04-29 10:45:30,100 - INFO - [3000/4982] Loading TICKER...
2026-04-29 10:45:31,234 - ERROR - Connection to database lost
2026-04-29 10:45:31,234 - ERROR - Traceback: psycopg2.OperationalError: server closed the connection unexpectedly
2026-04-29 10:45:31,300 - ERROR - Fatal error - cannot continue
```

**What this teaches:**
- Connection to RDS was lost
- Loader cannot recover
- Exit code: 1 (FAILURE)
- Need to investigate: network, RDS availability, credentials

---

## How to Read Real Logs

### Step 1: Find the Log Stream
**AWS Console → CloudWatch → Log Groups → /aws/ecs/stocks-loader-tasks**

You'll see 4 log streams:
- `loader-annualcashflow-TASK_ID`
- `loader-quarterlycashflow-TASK_ID`
- `loader-factormetrics-TASK_ID`
- `loader-stockscores-TASK_ID`

### Step 2: Click the Appropriate Stream
Select the loader you want to monitor (e.g., `loader-annualcashflow-*`)

### Step 3: Read from Top to Bottom
- First lines = startup
- Middle lines = data loading
- Last lines = completion

### Step 4: Look for Key Indicators

**Search for: "Starting load"**
```
Tells you when loader started
```

**Search for: "Using environment variables"**
```
Confirms DB credentials loaded from environment
```

**Search for: "Connecting to database"**
```
Should see "Database connection successful"
```

**Search for: "Loading symbols"**
```
Shows how many symbols will be processed
```

**Search for: "ERROR"**
```
Find any errors that occurred
```

**Search for: "Completed:"**
```
Shows final row count loaded
```

---

## Real-Time Monitoring Strategy

### Every 5 Minutes (During Execution)
1. Go to GitHub Actions page
2. Check "Execute Loaders" job status
3. Look at "Logs" tab
4. Search for latest symbol being processed
5. Verify it's incrementing (e.g., [2500/4982] → [2501/4982] → [2502/4982])

### Every 30 Minutes (During Execution)
1. Go to CloudWatch Log Groups
2. Check each loader's log stream
3. Search for "ERROR" - should find few/none
4. Look at latest timestamp - should be recent
5. Estimate progress based on symbol count

### Every 1-2 Hours
1. Check ECS Console
2. Look at task memory/CPU usage
3. Verify no tasks have unexpectedly STOPPED
4. Check "CloudWatch" tab on task details

### At Completion (T+5-7 hours)
1. Verify all 4 tasks show exit code 0
2. Query database to count rows
3. Spot-check 5 stocks for data quality

---

## Learning Checklist

✅ Can you find GitHub Actions workflow?  
✅ Can you interpret workflow job status (✓/✗)?  
✅ Can you access CloudWatch Log Groups?  
✅ Can you find the right log stream?  
✅ Can you search logs for keywords (ERROR, Completed)?  
✅ Can you identify progress indicators?  
✅ Do you understand exit codes?  
✅ Can you spot rate limiting vs real errors?  
✅ Do you know what "missing data" means?  
✅ Can you identify critical errors vs warnings?  

---

## Summary

**To understand what's happening:**

1. **GitHub Actions** = Workflow orchestration level (high level)
2. **CloudWatch Logs** = Loader execution level (detailed)
3. **ECS Console** = Task resource level (CPU/memory)
4. **Database** = Data results level (confirmation)

**Key Log Messages:**
- `Starting load...` = Beginning
- `Loading symbols...` = In progress
- `ERROR` = Something wrong (check severity)
- `Completed: X rows` = Success

**Expected Behaviors:**
- Rate limiting = NORMAL (yfinance limit, recovers)
- Missing data = NORMAL (some stocks don't have data)
- Slow progress = NORMAL (network, API delays)
- Sudden errors = CRITICAL (database, credentials)

Now go check the logs and learn what's happening! 🚀
