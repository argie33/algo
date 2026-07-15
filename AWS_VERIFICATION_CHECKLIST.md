# AWS Verification Checklist - Session 151

## Status: Code Deployed to Main ✅

Latest commit: `28409bde3 fix: correct growth/quality metrics - fix income statement row parsing`

All related fixes committed:
- ✅ Growth metrics row parsing fix (28409bde3)
- ✅ reason_type column cleanup (54d95408f)
- ✅ EOD watermark handling (8ad00e511)
- ✅ Alpaca support (4b2df707e)

## Local Verification ✅

- ✅ API endpoint `/api/algo/scores` returns growth_score values
- ✅ Database: 3,965/4,711 stocks have growth_score (84%)
- ✅ Sample data: growth scores ranging from 0-100 (realistic values)
- ✅ Integration tests passing: test_dashboard_api_includes_growth_score
- ✅ Stock scores computed with real growth data

## AWS Verification Checklist (TODO)

### 1. GitHub Actions Deployment
- [ ] Navigate to: https://github.com/argie33/algo/actions
- [ ] Verify latest workflow run (should be after commit 28409bde3)
- [ ] Check build status: ✅ Passed or ⚠️ Failed?
- [ ] Check "Terraform Apply" step succeeded
- [ ] Check "Push Docker Image" step succeeded
- [ ] Look for any errors in CI/CD logs

### 2. AWS CloudWatch Logs
- [ ] Go to CloudWatch Logs in AWS Console
- [ ] Check log group: `/aws/lambda/algo-orchestrator` or similar
- [ ] Filter for recent logs (last 2-4 hours)
- [ ] Look for errors in orchestrator execution
- [ ] Verify Phase 1 (metrics loading) completed successfully
- [ ] Check for growth_metrics loader logs

### 3. AWS RDS Database
- [ ] Connect to RDS instance (use AWS Secrets Manager credentials)
- [ ] Run: `SELECT COUNT(*) FROM stock_scores WHERE growth_score IS NOT NULL`
- [ ] Should be >3000 (compare with local: 3,965)
- [ ] Run: `SELECT MAX(updated_at) FROM stock_scores`
- [ ] Should be recent (within last 2-4 hours)
- [ ] Run sample query:
  ```sql
  SELECT symbol, composite_score, growth_score 
  FROM stock_scores 
  WHERE composite_score > 70 
  ORDER BY growth_score DESC LIMIT 5
  ```
- [ ] Verify growth_score values are real numbers, not NULL

### 4. API Gateway / Lambda  
- [ ] Test endpoint in AWS: `https://<api-gateway-url>/api/algo/scores`
- [ ] Should return data with growth_score fields
- [ ] Check Lambda execution logs for any errors
- [ ] Monitor CloudWatch Metrics for invocation count/duration

### 5. Dashboard Testing (AWS Mode)
- [ ] Set environment: `export DASHBOARD_API_URL=https://<api-gateway-url>`
- [ ] Run: `python dashboard.py`
- [ ] Navigate to scores panel
- [ ] Verify growth scores display (should show values like 88.9, 100.0, etc.)
- [ ] Check for any authentication errors in console

## Expected Results

✅ If all checks pass:
- AWS should have fresh growth_metrics data (within 4 hours)
- stock_scores.growth_score populated for 80%+ of stocks
- Dashboard displays growth scores in AWS mode
- No errors in CloudWatch logs

## Troubleshooting

**If growth_score is NULL in AWS RDS:**
1. Check orchestrator logs for growth_metrics loader errors
2. Verify stock_scores was recomputed after metrics loaded
3. Check if deployment actually pushed the new code

**If API returns auth errors:**
1. Verify Lambda has correct IAM permissions
2. Check Cognito configuration in environment variables
3. Verify API Gateway has correct authorizer settings

**If dashboard shows "Data not available":**
1. Check dashboard logs for API call errors
2. Verify DASHBOARD_API_URL is set correctly
3. Try hitting API endpoint directly with curl
4. Check Lambda cold-start latency (may need provisioned concurrency)

## Success Metrics

- [ ] stock_scores.growth_score: 80%+ coverage (3000+/4000 stocks)
- [ ] Latest update timestamp: within 4 hours
- [ ] API response time: <2 seconds
- [ ] Dashboard: growth scores visible in scores panel
- [ ] No errors in CloudWatch logs
