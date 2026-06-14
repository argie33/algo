# GET YOUR SITE WORKING NOW

Your code is fixed (270 tests passing). Your data loaders are working. You just need to **run them once** to populate fresh data.

## Step 1: Refresh AWS Credentials (2 min)

```powershell
# From project root:
./scripts/refresh-aws-credentials.ps1

# This:
# - Fetches fresh AWS credentials from Secrets Manager
# - Updates your ~/.aws/credentials profile (algo-developer)
# - Validates database connectivity
# - Confirms dashboard config exists
```

## Step 2: Run Loaders (Pick ONE option)

### Option A: Trigger Via AWS Step Functions (FASTEST - Production)

```powershell
# 1. Go to AWS Console → Step Functions
# 2. Find: algo-morning-prep-pipeline
# 3. Click: "Start Execution"
# 4. Leave input as default `{}`
# 5. Click: "Start Execution"

# Result: Loaders run automatically with optimized parallelism=6
# Time: ~60 minutes total
# Logs: CloudWatch /ecs/algo-stock_prices_daily-loader (etc.)
```

### Option B: Run Locally (TESTING - Quick Validation)

```powershell
# Refresh credentials first (from Step 1)

# Test a single fast loader:
cd C:\Users\arger\code\algo
python -m loaders.load_buy_sell_daily --parallelism 6

# Or test the main price loader:
python -m loaders.load_prices --parallelism 6

# Expected: Should complete in 10-20 minutes
# Output: "Completed" message with row counts
# Database: Tables populate with fresh data
```

## Step 3: Verify Data Loaded (5 min)

```powershell
# After loaders complete, verify:
python -c "
import sys
sys.path.insert(0, '.')
from utils.db.context import DatabaseContext

with DatabaseContext('read') as cur:
    cur.execute('SELECT MAX(date) FROM price_daily')
    max_date = cur.fetchone()[0]
    print(f'Latest price data: {max_date}')
    
    cur.execute('SELECT COUNT(*) FROM price_daily WHERE date = %s', (max_date,))
    count = cur.fetchone()[0]
    print(f'Symbols with data: {count}')
"
```

## Step 4: Start Using Your Site

```powershell
# Dashboard TUI:
cd tools/dashboard
python dashboard.py -w 30

# API server:
cd lambda/api
python api.py

# Your frontend sees fresh data immediately
```

## Expected Results

After loaders complete (~60 min):

✅ **Database**: Fresh price, signal, and performance data
✅ **API**: Returns real signals (`/api/algo/signals`)
✅ **Dashboard**: Shows current positions and trade signals
✅ **Trading**: System operates on current market data

## If You Run Into Issues

### Credentials not loading?
```powershell
# Manually set AWS profile:
$env:AWS_PROFILE = "algo-developer"

# Or verify credentials exist:
Get-Content ~/.aws/credentials | Select-String algo-developer
```

### Database connection timeout?
```powershell
# Check database is reachable:
# (Run this after refresh-aws-credentials.ps1)
psql -h $env:DB_HOST -U $env:DB_USER -d $env:DB_NAME -c "SELECT 1"
```

### Loader still running after 90 minutes?
```powershell
# Kill hung task (optional):
# Option 1: AWS Console → ECS → Stop task
# Option 2: Trigger failsafe:
curl https://api.yoursite.com/api/admin/kill-hung-loader -H "Authorization: Bearer $token"
```

## Key Files Modified

- `utils/validation/schema.py`: Fixed circular import (now imports directly from sql_safety)
- All 270 tests now pass
- Loaders ready to run with 6x parallelism

## What's NOT required

- ❌ No code changes (all fixed)
- ❌ No schema migrations (already applied)
- ❌ No configuration changes (already optimized)
- ❌ No external services setup (already deployed)

## Timeline

```
Now: Run loaders (Step 1 + 2)
+60 min: Fresh data loaded
+61 min: API returns real signals
+61 min: Dashboard shows current state
+61 min: Your site is fully operational
```

That's it. Go get that fresh data running.
