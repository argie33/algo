# AWS Lambda Scores Data Bug - Root Cause & Fix

**Session 138 - 2026-07-14 14:50 UTC**

## Problem Identified

**Dashboard Issue**: Growth Score shows "--" and RS shows "0" for all symbols in AWS mode

**Root Cause**: AWS Lambda API returns corrupted/stale data
```
Database actual values:     growth_score=0.39,  rs_percentile=53.27
Local dev_server returns:   growth_score=0.39,  rs_percentile=53.27  ✅
AWS Lambda API returns:     growth_score=None,  rs_percentile=0.0    ❌
```

## Evidence

**Test Results**:
1. Database query (local): ✅ Returns correct values (0.39, 53.27)
2. Local dev_server (`localhost:3001`): ✅ Returns correct values (0.39, 53.27)
3. AWS Lambda (`api-dev`): ❌ Returns corrupted values (None, 0.0)

## Why This Happens

**Hypothesis**: AWS Lambda is either:
1. Running old/stale code version that doesn't include the correct SELECT statement
2. Or RDS database connection is returning cached/filtered results
3. Or response serialization is corrupting values during JSON transformation

**Evidence Against Serialization Bug**: 
- Local dev_server uses same conversion functions but returns correct data
- Therefore the issue is in Lambda query execution or RDS connection

## Solution

### Immediate Fix (DEPLOYED):
1. **Trigger Lambda redeployment**: `gh workflow run deploy-api-lambda.yml`
   - This forces Lambda to rebuild from current git code
   - Should pick up correct scores query

### If Redeployment Doesn't Fix:

**Step 1**: Verify RDS vs Local Database
```bash
# Check if AWS RDS has different data than local
aws rds describe-db-instances --db-instance-identifier algo-postgres \
  --query 'DBInstances[0].[Endpoint.Address]'
```

**Step 2**: Run Query Directly on RDS
```python
import psycopg2
# Connect to RDS endpoint instead of localhost
conn = psycopg2.connect("dbname=stocks user=stocks host=<RDS_ENDPOINT>")
# Run the exact scores query to verify data
```

**Step 3**: Check Lambda Layers
```bash
# Lambda might be using a stale layer with old code
aws lambda get-function --function-name algo-api-dev \
  --query 'Configuration.Layers'
```

**Step 4**: Force Full Rebuild
```bash
# Option A: Run full infrastructure deployment
gh workflow run deploy-all-infrastructure.yml

# Option B: Manually rebuild Lambda layer and redeploy
aws lambda update-function-code \
  --function-name algo-api-dev \
  --s3-bucket <bucket> \
  --s3-key <lambda-zip-key>
```

## Prevention

**To prevent this in future**:

1. **Add data validation to Lambda response**:
   ```python
   # In _get_dashboard_scores() after building response
   for score in response['top']:
       assert score['growth_score'] is not None or score['composite_score'] < 50, \
           f"Growth score NULL but composite high: {score['symbol']}"
       assert score['rs_percentile'] > 0 or score['rs_percentile'] is None, \
           f"RS percentile is 0: {score['symbol']}"
   ```

2. **Add data quality checks to Lambda health endpoint**:
   ```python
   @app.route('/api/lambda/health')
   def health():
       # Verify at least 50% of scores have growth_score > 0
       # Return degraded status if data quality low
   ```

3. **Monitor response quality in CloudWatch**:
   - Alert if >10% of scores have NULL growth_score
   - Alert if >10% of scores have rs_percentile == 0

4. **Cache busting on deployment**:
   - Add cache-control headers to force fresh data after Lambda update
   - Or increment query version/schema on changes

## Testing After Fix

Run these to verify AWS Lambda now returns correct data:

```bash
# 1. Check current Lambda modification time (after deployment)
aws lambda get-function --function-name algo-api-dev \
  --query 'Configuration.LastModified'

# 2. Test API directly
curl -s 'https://<api-gateway-endpoint>/api/algo/scores?limit=1' | jq '.top[0] | {symbol, growth_score, rs_percentile}'

# 3. Test via dashboard
python3 scripts/verify_dashboard_data_quality.py | grep -A3 "Growth Score"

# 4. Start dashboard and verify visual display
python dashboard.py
# Look for Scores panel - should show numeric values, not "--"
```

## Expected Result

After redeployment, you should see:
- Growth column: Numeric values (e.g., 0.39, 25.5, 42.0)
- RS column: Percentile values (0-100, not all 0s)
- Scores panel loads without "Data not available" warnings

## Files Affected

- `lambda/api/routes/algo_handlers/dashboard.py` - `_get_dashboard_scores()` function (line 1527+)
- `lambda/api/routes/algo_handlers/metrics.py` - Response transformation functions
- `lambda/api/routes/utils.py` - `safe_json_serialize()`, `safe_dict_convert()`

## Related Issues

- **Growth Score NULL** (Session 138): Different issue - some symbols legitimately missing growth data
- **Breadth Momentum 50.0** (Session 138): Working correctly, not related
- **Positions Cache TTL** (Session 138): Fixed separately in same commit
