# Implementation Guide - THEN Phase
## Fixing Blocking Issues & Major Integration Failures

**Status:** Diagnostic phase complete. Ready to implement fixes.

---

## BLOCK-006: Data Loaders Hanging (CRITICAL - START HERE)

### Quick Fix (30 minutes)
The loaders are hanging likely due to yfinance API being slow or rate-limited. The code already has timeout protection (180s for batch), but ECS task might need timeout adjustment.

**Fix Steps:**

1. **Enable enhanced logging in ECS task:**
   ```bash
   # Update task definition to enable DEBUG logging
   aws ecs register-task-definition \
     --family algo-stock_prices_daily-loader \
     --container-definitions '[{
       "name": "algo-stock_prices_daily-loader",
       "environment": [
         {"name": "LOG_LEVEL", "value": "DEBUG"},
         {"name": "LOADER_TIMEOUT_SEC", "value": "600"}
       ]
     }]'
   ```

2. **Trigger manual loader test:**
   ```bash
   # Run smallest loader first (stock_symbols)
   aws ecs run-task \
     --cluster algo-cluster-dev \
     --task-definition algo-stock_symbols-loader:latest \
     --launch-type FARGATE \
     --network-configuration "awsvpcConfiguration={subnets=[SUBNET_ID],securityGroups=[SG_ID],assignPublicIp=ENABLED}"
   
   # Watch logs
   aws logs tail /ecs/algo-stock_symbols-loader --follow
   ```

3. **If logs show timeout errors:**
   - Check if timeout_sec in `utils/data/source_router.py` line 372 needs increasing
   - Current: 180s for batch → Try increasing to 300s if yfinance is slow

4. **If logs show success:**
   - Trigger next loader: `algo-market_health_daily-loader`
   - Then trigger full morning pipeline manually
   - Monitor all Step Function executions

### Code Fix (If Needed)

**File:** `utils/data/source_router.py`

```python
# Line 372: If batch downloads timeout frequently, increase timeout
# FROM:
hist = _call_with_timeout(do_download, timeout_sec=180, retries=3)

# TO:
hist = _call_with_timeout(do_download, timeout_sec=300, retries=3)  # 5 min timeout for batch
```

---

## MAJOR-001: API Returning Empty Data Instead of Errors

### Issue Pattern
Some endpoints catch exceptions and return `[]` or `{}` instead of proper error responses.

### Fix Steps

1. **Find problematic endpoints:**
   ```bash
   # Search for catch-all exceptions returning empty
   grep -rn "except.*:" lambda/api/routes/ | grep -A 2 "return \[\]\|return {}"
   ```

2. **Fix each endpoint using error_response helper:**

   **From:**
   ```python
   try:
       data = fetch_data()
       return {"data": data}
   except Exception as e:
       logger.error(f"Error: {e}")
       return {}  # WRONG - returns 200 OK with empty object
   ```

   **To:**
   ```python
   try:
       data = fetch_data()
       return {"statusCode": 200, "data": data}
   except Exception as e:
       logger.error(f"Error: {e}", exc_info=True)
       return error_response(503, 'data_unavailable', f'Failed to fetch data: {str(e)}')
   ```

3. **Use db_route_handler decorator for database operations:**
   ```python
   from lambda.api.routes.utils import db_route_handler, error_response
   
   @db_route_handler('get_positions')
   def _get_positions(cur):
       cur.execute("SELECT * FROM algo_positions")
       return cur.fetchall()
   
   # This automatically handles database errors and returns proper error responses
   ```

4. **Test the fix:**
   ```bash
   # Trigger an error condition (empty database or bad parameter)
   curl https://API_URL/api/algo/positions
   
   # Should return error with _error field, not empty object
   # Response should be: {"statusCode":503,"_error":"...","message":"..."}
   ```

---

## MAJOR-002: Data Freshness Thresholds Inconsistent

### Issue
Different endpoints have different freshness thresholds (300s-3600s), confusing traders.

### Fix

**File:** `tools/dashboard/fetchers.py`

Create centralized thresholds:
```python
# Add at top of file
FRESHNESS_THRESHOLDS = {
    'prices': 300,           # 5 minutes - most critical
    'performance': 3600,     # 1 hour - daily data
    'portfolio': 900,        # 15 minutes - intraday
    'market_health': 3600,   # 1 hour
    'signals': 300,          # 5 minutes
}

# Then use everywhere:
def fetch_prices(self):
    data = self._get_data()
    age = (datetime.now() - data.timestamp).total_seconds()
    
    if age > FRESHNESS_THRESHOLDS['prices']:
        return {'_error': f'Price data stale ({age/60:.0f} min old)'}
    
    return {'prices': data, 'age_seconds': age}
```

---

## MAJOR-003: Missing Input Validation

### Endpoints to Fix
- `/api/algo/preview` (POST)
- `/api/algo/pre-trade-impact` (POST)
- `/api/contact/submit` (POST)

### Fix Pattern

```python
# Add request body validation
from pydantic import BaseModel, Field, validator
from typing import Optional

class PreviewRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10)
    shares: int = Field(..., gt=0, lt=1000000)
    price: float = Field(..., gt=0)
    
    @validator('symbol')
    def symbol_uppercase(cls, v):
        return v.upper().strip()

# In route handler:
@app.post('/api/algo/preview')
def preview(body: dict):
    try:
        req = PreviewRequest(**body)
        # Process validated request
        return {'statusCode': 200, 'data': process_preview(req)}
    except ValidationError as e:
        return error_response(400, 'bad_request', f'Invalid request: {e}')
    except Exception as e:
        return error_response(500, 'internal_error', 'Preview failed')
```

---

## MAJOR-004: Transaction Rollback Issues

### Issue
Multi-statement database operations don't rollback on error, leaving inconsistent state.

### Fix Pattern

**From:**
```python
with DatabaseContext('write') as cur:
    cur.execute("INSERT INTO table1 ...")
    cur.execute("INSERT INTO table2 ...")  # Fails - but table1 committed!
```

**To:**
```python
from utils.db.context import DatabaseContext

def atomic_operation():
    with DatabaseContext('write') as cur:
        try:
            cur.execute("INSERT INTO table1 ...")
            cur.execute("INSERT INTO table2 ...")
            # Implicit commit on context exit
        except Exception as e:
            # Context manager automatically rolls back
            logger.error(f"Transaction failed, rolling back: {e}")
            raise  # Re-raise for caller to handle
```

---

## MAJOR-005: Async Operations Have No Timeout

### Issue
External API calls (`requests.get()`, yfinance, FRED) can hang indefinitely.

### Status
✅ Already fixed in most places. Check for any remaining instances:

```bash
grep -rn "requests.get\|requests.post" loaders/ | grep -v "timeout="
```

If found:
```python
# WRONG:
response = requests.get(url)

# CORRECT:
response = requests.get(url, timeout=30)  # 30 second timeout
```

---

## MAJOR-006: Frontend Error Logging Not Wired

### Status
✅ Already implemented in frontend. Verify:

1. Check that `/api/logs` endpoint exists:
   ```bash
   curl https://API_URL/api/logs -X POST -d '{"message":"test"}'
   ```

2. Verify logs appear in CloudWatch:
   ```bash
   aws logs tail /aws/frontend/algo-trading-dashboard --follow
   ```

---

## Recommended Fix Order

1. **TODAY** (Critical - blocks everything)
   - [ ] BLOCK-006: Debug and fix loader hanging
   - [ ] Verify loaders run successfully
   - [ ] Verify data freshness updates

2. **TODAY** (High - prevents traders from using system)
   - [ ] MAJOR-001: Fix empty data responses
   - [ ] Test API error handling

3. **TOMORROW** (High - traders need reliable data)
   - [ ] MAJOR-002: Standardize freshness thresholds
   - [ ] MAJOR-003: Add input validation
   - [ ] MAJOR-004: Add transaction rollback

4. **THIS WEEK** (Medium - improves reliability)
   - [ ] MAJOR-005: Verify all timeouts in place
   - [ ] MAJOR-006: Verify frontend logging
   - [ ] Add CloudWatch alarms for stale data

---

## Testing Each Fix

After implementing each fix:

```bash
# 1. Deploy changes
git add -A && git commit -m "Fix: MAJOR-001 error responses"

# 2. Push to trigger CI/CD (or deploy manually)
git push origin main

# 3. Verify fix
curl https://API_URL/api/health | jq '.data | {status, freshness}'

# 4. Check logs
aws logs tail /aws/lambda/algo-api-dev --follow

# 5. Monitor metrics
cloudwatch get-metric-statistics ...
```

---

## Success Criteria - Full System

- [ ] API health endpoint returns `"status": "healthy"`
- [ ] Signal age < 24 hours
- [ ] Data updated daily (price_daily has today's date)
- [ ] All endpoints return proper error responses (with `_error` field)
- [ ] No empty arrays/objects returned on errors
- [ ] Database transactions are atomic (all-or-nothing)
- [ ] External API calls have timeouts
- [ ] Frontend displays error alerts properly
- [ ] CloudWatch logs show normal operation

---

## Questions Before Proceeding?

1. **Loader hanging issue unclear?** → Check ECS logs with `DEBUG` logging enabled
2. **Don't know which endpoint has error?** → Search code for `return []` or `return {}`
3. **Unsure about error_response() helper?** → See `lambda/api/routes/utils.py` lines 1-50
4. **Need to understand the system better?** → See `steering/algo.md` (comprehensive)

---

## Next: AFTER THAT Phase

Once THEN phase (above) is complete, proceed to AFTER THAT:

See `COMPREHENSIVE_ISSUES_LIST.md` for:
- **ARCH issues** (1-5): Security, rate limiting, config management
- **DATA issues** (1-4): Portfolio staleness, validation, gaps
- **TEST issues** (1+): Add automated integration tests
- **MONITOR issues** (1+): Add CloudWatch alarms

---

## Key Files to Edit

**For BLOCK-006:**
- `utils/data/source_router.py` (line 372) - timeout adjustment
- `lambda/db-init/schema.sql` - if schema needs updating

**For MAJOR issues:**
- `lambda/api/routes/*.py` - all route handlers
- `tools/dashboard/fetchers.py` - freshness logic
- `config/thresholds.py` - centralized config (create if needed)

**For testing:**
- `tests/integration/test_loaders.py` - loader tests
- `tests/integration/test_api.py` - API error tests
