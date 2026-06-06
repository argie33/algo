# AWS Deployment & Verification Guide

## ✅ DEPLOYMENT READINESS

All critical code fixes have been implemented and committed:
- `97acbe4e3`: fix: Add QueryCanceled error handling to data_coverage route (504 timeout response)
- Previous commits: Database timeout fixes, frontend config build scripts, error boundaries

**Status: READY FOR AWS DEPLOYMENT**

---

## 🚀 DEPLOYMENT PROCEDURE

### 1. GitHub Actions Deploy
```bash
git push origin main
```
This triggers `.github/workflows/deploy-all-infrastructure.yml` which:
1. Runs Terraform to create/update AWS resources
2. Builds frontend with `scripts/build-prod.js` passing API_URL from Terraform
3. Deploys Lambda functions with timeout error handling
4. Uploads frontend to S3 with CloudFront caching

### 2. Key Environment Variables Passed During Build
- `VITE_API_URL` - CloudFront domain URL (from Terraform `website_url` output)
- `COGNITO_USER_POOL_ID` - From Terraform cognito_user_pool_id output
- `COGNITO_CLIENT_ID` - From Terraform cognito_user_pool_client_id output
- `COGNITO_DOMAIN` - Cognito domain URL

---

## 📊 VERIFICATION CHECKLIST

### Phase 1: Infrastructure Deployment (CloudWatch Logs)

#### 1.1 Frontend Build Validation
- ✅ GitHub Actions: Verify `setup-prod.js` outputs show API_URL being set
- ✅ Check S3 sync completes without errors
- ✅ Verify `dist/config.js` contains correct `API_URL` (not hardcoded localhost)
  
**Log location:** GitHub Actions → deploy-all-infrastructure.yml → deploy-frontend job

**Expected output:**
```
[OK] Using Terraform website_url: https://d123456.cloudfront.net
[setup-prod] ✓ Generated config.js with API_URL=https://d123456.cloudfront.net
```

#### 1.2 Lambda Deployment
- ✅ API Lambda deployed successfully
- ✅ Algo Lambda deployed successfully

**Log location:** GitHub Actions → deploy-all-infrastructure.yml → deploy-api, deploy-algo jobs

### Phase 2: Runtime Verification (Browser & AWS Logs)

#### 2.1 Database Timeout Error Handling
**Test:** Trigger a slow query by loading a heavy endpoint
1. Open browser DevTools → Network tab
2. Load a data endpoint (e.g., `/api/market/breadth`)
3. If query times out, verify response has:
   - HTTP Status: `504` (Gateway Timeout)
   - Response body: `{"statusCode": 504, "errorType": "timeout", "message": "..."}`

**Log location:** CloudWatch → `/aws/lambda/algo-api-dev` → Lambda logs
**Expected:** `ERROR: [route_name] query timeout: ...` + `error_response(504, 'timeout', ...)`

#### 2.2 Frontend API Connectivity
**Test:** Verify frontend can reach API
1. Open browser console (F12)
2. Go to `/app/markets` (Markets Health page)
3. Check Network tab for API calls
4. Verify no CORS errors, requests succeed

**Expected:** GET `/api/market` returns 200 with data

#### 2.3 Circuit Breaker State
**Test:** Simulate API failures
1. Trigger 8+ failures (can simulate with DevTools offline mode)
2. Watch circuit breaker transition to OPEN state
3. Verify browser console shows: `[Circuit Breaker] Too many failures (8). Opening circuit.`
4. Wait 60+ seconds, verify circuit attempts recovery (HALF_OPEN state)

**Expected logs in console:**
```
[Circuit Breaker] Too many failures (8). Opening circuit.
[Circuit Breaker] Attempting recovery (HALF_OPEN state)
[Circuit Breaker] Circuit breaker closed. Resuming normal operation.
```

#### 2.4 Error Boundary Triggers
**Test:** Force a component error
1. Open React DevTools (Chrome/Firefox extension)
2. Force a rendering error by modifying component state to cause null reference
3. Verify error boundary catches it and shows error UI with error ID

**Expected:** Error screen with "Something went wrong" message, error ID, and "Try Again" button

#### 2.5 Config Loading & Timeout
**Test:** Verify config.js loads within 10s
1. DevTools → Network tab
2. Reload page
3. Check `config.js` request completes within 10 seconds
4. Verify it contains: `API_URL`, `USER_POOL_ID`, `ENVIRONMENT`

**Expected:** `public/config.js?v=TIMESTAMP` loads and contains window.__CONFIG__

### Phase 3: CloudWatch Logs Analysis

#### 3.1 API Lambda Logs
```bash
aws logs tail /aws/lambda/algo-api-dev --follow --format short
```

**Look for:**
- ✅ "timeout" messages → returns 504 status
- ✅ "Connection pool" messages → no "too many connections" errors
- ✅ "circuit breaker" messages → proper state transitions
- ❌ NOT: Silent failures or empty list returns on timeout

#### 3.2 Algo Lambda Logs  
```bash
aws logs tail /aws/lambda/algo-algo-dev --follow --format short
```

**Look for:**
- ✅ Phase 1 data freshness checks with proper HALT/PROCEED decisions
- ✅ Orchestrator runs successfully without halting on false positives
- ❌ NOT: "cache_invalidation_failure_flag" without proper error response

#### 3.3 API Gateway CloudWatch Metrics
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApiGateway \
  --metric-name 5XXError \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum
```

**Expected:** No 5xx errors from client misconfiguration (only from legitimate server errors)

---

## 🔧 TROUBLESHOOTING

### Problem: Frontend shows "API calls to localhost"
**Check:**
1. CloudFront domain: `aws cloudfront list-distributions`
2. S3 bucket config.js: `aws s3 cp s3://algo-frontend-bucket/config.js -`
3. GitHub Actions output: Verify `website_url` parameter passed to build-prod.js

**Fix:** Re-run GitHub Actions deployment with `skip_terraform=false`

### Problem: "Unable to fetch Cognito keys" (401/403 errors)
**Check:**
1. Lambda security group has NAT Gateway for outbound HTTPS
2. Cognito service endpoint is reachable: `curl https://cognito-idp.us-east-1.amazonaws.com/...`
3. Lambda timeout: Currently 3 seconds, may need increase for slow networks

**Fix:** Ensure VPC has NAT Gateway, or add VPC endpoint for Cognito

### Problem: Database timeout returns 200 with empty list
**Check:**
1. Route imports `QueryCanceled` from psycopg2.errors
2. Route has try/except for `QueryCanceled`
3. Route returns `error_response(504, 'timeout', ...)`

**Verify with:** `grep -r "QueryCanceled" lambda/api/routes/*.py`

### Problem: Config loading timeout error
**Check:**
1. config.js is deployed to S3: `aws s3 ls s3://algo-frontend-bucket/config.js`
2. CloudFront cache is invalidated: `aws cloudfront list-invalidations`
3. Browser DevTools shows 404 or 5xx for config.js

**Fix:** Manually invalidate CloudFront cache: `aws cloudfront create-invalidation --distribution-id <ID> --paths '/*'`

---

## 📈 MONITORING AFTER DEPLOYMENT

### Critical CloudWatch Dashboards to Monitor
1. **API Response Times** - Should be <500ms for most queries
2. **Database Connection Pool** - Should stay <80% capacity
3. **Lambda Errors** - Should be 0 except for legitimate client errors
4. **Circuit Breaker State** - Monitor for excessive OPEN/HALF_OPEN transitions

### Performance Baselines
- Config loading: <1s (P50), <3s (P99)
- API response: <200ms (P50), <1000ms (P99)
- Frontend page load: <3s (P50), <8s (P99)
- Database query timeout: <10-15s (should rarely trigger)

---

## ✅ SUCCESS CRITERIA

Deployment is successful when:
1. ✅ Frontend loads with correct API_URL (not localhost)
2. ✅ Database timeouts return 504 status (verified in logs)
3. ✅ Circuit breaker opens/closes properly on failures
4. ✅ Error boundaries catch and display component errors
5. ✅ Config.js loads within 10 seconds consistently
6. ✅ CloudWatch logs show no 500+ errors from application code
7. ✅ Cognito authentication works (frontend can reach JWKS if NAT Gateway configured)

---

## 🎯 CRITICAL PATH (Next Steps)

1. **Immediate:** Push `main` to trigger GitHub Actions deployment
2. **Monitor:** Watch CloudWatch logs for errors during deployment
3. **Verify:** Open production frontend and test basic flows
4. **Validate:** Check CloudWatch dashboards for error rates
5. **Investigate:** If any issues, check logs with queries above

---

## 📞 CONTACT SUPPORT

If deployment fails:
1. Check GitHub Actions logs first (most information)
2. Check CloudWatch logs for Lambda errors
3. Check S3 and CloudFront for deployment artifacts
4. Review this guide's Troubleshooting section

All critical code fixes are in place. Deployment readiness: **100%**
