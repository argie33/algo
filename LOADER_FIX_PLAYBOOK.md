# Loader Failure Root Cause & Fix Playbook

## Current Situation

**Both morning and EOD pipelines fail on `stock_prices_daily` ECS task after exactly ~58 seconds**

- Morning pipeline: Failed 20:24-20:25:07 (58s)
- EOD pipeline: Failed 20:29-20:30:05 (58s) - SAME TASK RETRIED
- Data remains STALE (27 rows in price_daily vs 5000+ expected)
- Trading halted (Phase 7 blocked)

## Root Cause: 58-Second Timeout

The timing is **too consistent to be random**. Options:
1. ✓ ECS task health check failing (most likely)
2. ✓ ECS stopTimeout triggered
3. ✓ Step Functions runTask integration timeout
4. ✓ Loader code crashes/exits after 58 seconds

## Investigation Steps (Run in Order)

### STEP 1: Verify Loader Code Can Run Locally

**Status**: ✓ PASSED
- Loader imports successfully
- Config loads from database
- No initialization crashes

### STEP 2: Check ECS Task Health Check Configuration

**Configuration** (terraform/modules/loaders/main.tf lines 711-717):
```hcl
healthCheck = {
  command     = ["CMD-SHELL", "ps aux | grep -q '[p]ython.*stock_prices_daily' || exit 1"]
  interval    = 30        # Check every 30 seconds
  timeout     = 5         # 5 second timeout per check
  retries     = 2         # 2 failures = unhealthy
  startPeriod = 60        # 60 second grace period before first check
}
```

**Expected Timeline**:
- 0-60s: Grace period (no health checks)
- 60s: First health check
- 90s: Second health check (if first failed)

**Problem**: Task failing at 58s, which is BEFORE first health check should run.

### STEP 3: Check if Docker Container is Starting

The issue is the container is being STARTED but then failing before the python process fully initializes.

**What's happening**:
1. ECS launches container
2. `loaders/load_prices.py` script starts
3. Script loads config (imports modules, connects to database)
4. ...something fails around 58 seconds

**Most likely causes**:
- Database pool initialization hangs
- Config loading from database times out
- Alpaca/yfinance API initialization hangs
- Network connectivity issue to AWS services

### STEP 4: Check Network Configuration

ECS tasks are in a VPC with:
- Private subnets (no internet gateway)
- NAT gateway for egress
- Security group configured

**Possible issues**:
- NAT gateway not working → can't reach yfinance/Alpaca
- RDS connection timing out → database unreachable
- DNS resolution failing

### STEP 5: Check Alpaca/yfinance Connectivity

The price loader needs to reach:
- **Alpaca API** - market data endpoint
- **yfinance** - fallback data source
- **Database (RDS)** - read symbol list

**All three must work for loader to succeed**.

### STEP 6: Fix Based on Investigation

**Hypothesis 1**: Database Connection Hangs (Most Likely)

*Symptoms*: Loader starts, tries to connect to RDS, hangs for 58s, then ECS kills it

*Fix*:
```python
# Add connection timeout to database config
DB_CONNECT_TIMEOUT = 10  # seconds
```

**Hypothesis 2**: Alpaca/yfinance Network Access Fails

*Symptoms*: Loader starts, tries to fetch data, fails

*Fix*:
```bash
# From ECS task, test connectivity:
curl -s https://data.alpaca.markets/v2/market/quotes -H "Authorization: Bearer $APCA_API_KEY_ID"
curl -s "https://query1.finance.yahoo.com/v10/finance/quoteSummary/AAPL"
```

**Hypothesis 3**: Health Check Command Fails

*Symptoms*: Task starts container, health check can't find python process

*Fix*:
```bash
# Simplify health check to avoid ps command issues
healthCheck.command = ["CMD", "python3", "-c", "import sys; sys.exit(0)"]
```

## Actionable Next Steps

### IMMEDIATE (Next 15 minutes)

**Option A: Fix Database Connection Timeout**
```python
# File: utils/db/context.py
# Add connection timeout
conn = psycopg2.connect(
    host=host,
    dbname=dbname,
    user=user,
    password=password,
    timeout=10,  # NEW: 10 second connection timeout
    connect_timeout=10
)
```

**Option B: Fix Health Check**
```hcl
# File: terraform/modules/loaders/main.tf
healthCheck = {
  command     = ["CMD", "test", "-f", "/tmp/loader_running"]
  # OR: ["CMD-SHELL", "echo ok"]  # simple test
  interval    = 60        # Increase to 60 seconds
  timeout     = 10        # Increase to 10 seconds
  retries     = 3         # Increase retries
  startPeriod = 120       # Increase grace period to 2 minutes
}
```

**Option C: Add Logging to Diagnose**
```python
# Add to loaders/load_prices.py line 50
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.info("PriceLoader.__init__ START")
# ... after database config loaded
logger.info(f"Config loaded in {time.time() - start:.1f}s")
```

### MEDIUM-TERM (This hour)

1. Deploy fix (A, B, or C above)
2. Re-trigger pipeline: `python3 scripts/diagnose_and_fix_loaders.py`
3. Monitor for completion
4. Verify data loads
5. Resume orchestrator

### LONG-TERM (This week)

1. Add structured logging to all loaders
2. Implement loader initialization monitoring
3. Add metrics for loader startup time
4. Document loader requirements

## Testing Locally

```bash
# Test price loader locally with minimal config
cd ~/code/algo
export LOADER_INTERVALS=1d
export LOADER_ASSET_CLASSES=stock
export LOADER_PARALLELISM=1
export DB_HOST=localhost
python3 loaders/load_prices.py

# Expected output:
# [INFO] Loading prices for 1d/stock...
# [INFO] Fetched N symbols
# [INFO] Loaded M prices
```

## Key Insight

**The 58-second consistency is the key clue.**

- If it were random, we'd see variance
- If it were data-dependent, it would vary by symbol count
- 58 seconds = likely **network timeout** or **health check failure**

Most probable fix: **Increase database connection timeout + increase ECS health check grace period**.

## Decision Tree

```
Loader fails after 58s
├─ Check: Is python process still running?
│  ├─ YES → Health check failed → Simplify health check
│  └─ NO → Process crashed → Add logging to find crash point
├─ Check: Is database connection working?
│  ├─ YES → Alpaca/yfinance issue → Verify network connectivity
│  └─ NO → Database timeout → Increase connection timeout
├─ Check: Do environment secrets exist?
│  ├─ YES → All secrets loaded
│  └─ NO → Fix AWS Secrets Manager access
```

## References

- ECS Health Checks: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-ecs-taskdefinition-healthcheck.html
- Step Functions runTask.sync: https://docs.aws.amazon.com/step-functions/latest/dg/concepts-service-integrations.html
- Database Connection Timeouts: https://www.postgresql.org/docs/current/libpq-connect.html
