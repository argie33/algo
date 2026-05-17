# Production Incident Runbook

**Last Updated:** 2026-05-17  
**Scope:** All production systems (Lambda, RDS, CloudFront, API Gateway)

---

## Quick Reference

| Symptom | Likely Cause | First Step |
|---------|---|---|
| Frontend blank/404 | CloudFront cache issue | 1. Check CloudFront status 2. Check API Gateway logs |
| "No data available" | Loaders failed to run | Check RDS data freshness (data_status endpoint) |
| API endpoints timeout | Lambda cold-start or DB connection pool exhausted | Check Lambda CloudWatch logs; restart loaders |
| Charts/scores empty | API returns wrong columns | Check recent Lambda code changes; rollback if needed |
| Database slow | Query not optimized or table scan | Check slow query log; add indexes |

---

## I. Frontend Shows Blank / 404 / Cannot Load

### Detection
- User sees blank dashboard
- Browser console shows 404 on `/api/*` calls
- Refresh doesn't help

### Diagnosis
```bash
# 1. Check CloudFront cache status
aws cloudfront get-distribution-config --id E{DISTRIBUTION_ID}

# 2. Check if API Gateway is up
curl -s https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/health

# 3. Check Lambda error logs
aws logs tail /aws/lambda/algo-api --follow
```

### Recovery Steps

**If API Gateway is down:**
1. SSH to bastion (or use AWS Systems Manager)
2. Check RDS connectivity: `nc -zv algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com 5432`
3. Check Lambda environment variables: `aws lambda get-function-configuration --function-name algo-api`
4. Redeploy Lambda: Push to main branch → GitHub Actions triggers auto-deploy

**If CloudFront is stale:**
1. Invalidate CloudFront cache: `aws cloudfront create-invalidation --distribution-id E{ID} --paths '/*'`
2. Wait 2-5 minutes for invalidation
3. Hard refresh browser (Ctrl+Shift+R)

**If database unreachable:**
1. Check RDS instance status: `aws rds describe-db-instances --db-instance-identifier algo-db`
2. Check security group: `aws ec2 describe-security-groups --filters Name=group-id,Values=sg-{ID}`
3. If instance is "stopped", start it: `aws rds start-db-instance --db-instance-identifier algo-db`

---

## II. "No Data Available" / Empty Dashboards

### Detection
- Scores dashboard shows "Scores loading..." forever
- Deep-value list is empty
- Portfolio shows no positions

### Diagnosis
```bash
# 1. Check if data was actually loaded
curl -s https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/data-status

# 2. Check last successful loader run
aws logs tail /aws/lambda/run-loaders --follow --since 2h

# 3. Count records in key tables
psql -h algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com -U stocks -d stocks \
  -c "SELECT COUNT(*) FROM swing_trader_scores; SELECT MAX(date) FROM price_daily;"
```

### Recovery Steps

**If loaders haven't run in >24 hours:**
1. Manually trigger loader Lambda:
   ```bash
   aws lambda invoke --function-name run-loaders /tmp/response.json && cat /tmp/response.json
   ```
2. Monitor: `aws logs tail /aws/lambda/run-loaders --follow`
3. Wait 15-20 minutes for completion
4. Check record counts again (should increase)

**If specific loader is stuck:**
1. Check which loader failed: `aws logs tail /aws/lambda/run-loaders | grep ERROR`
2. Check loader-specific logs in CloudWatch
3. Common causes:
   - **Data source API down:** Check Alpaca/SEC status page
   - **Database constraints:** `psql ... -c "SELECT constraint_name FROM information_schema.constraint_column_usage"`
   - **Out of disk space:** `df -h /data` (if using EBS)

**If loaders are erroring consistently:**
1. Roll back most recent loader code change
2. Check environment variables are set (AWS Secrets Manager)
3. Run diagnostic query:
   ```sql
   SELECT * FROM algo_audit_log WHERE status = 'error' ORDER BY timestamp DESC LIMIT 5;
   ```

---

## III. API Endpoints Timeout (504 Gateway Timeout)

### Detection
- User sees "The request could not be completed. Please try again."
- API request takes >30 seconds
- Happens after heavy traffic / many concurrent users

### Diagnosis
```bash
# 1. Check Lambda duration and cold-start times
aws logs insights query --log-group-name /aws/lambda/algo-api \
  --query-string 'fields @duration, @initDuration | stats max(@duration), max(@initDuration)'

# 2. Check database connection pool status
psql -h algo-db... -U stocks -d stocks \
  -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"

# 3. Check for slow queries
psql -h algo-db... -U stocks -d stocks \
  -c "SELECT query, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 5;"
```

### Recovery Steps

**If Lambda cold-start is >3s:**
1. Increase Lambda memory (improves CPU, reduces cold-start):
   ```bash
   aws lambda update-function-configuration --function-name algo-api --memory-size 1024
   ```
2. Enable Lambda provisioned concurrency (keeps warm instances running):
   ```bash
   aws lambda put-provisioned-concurrency-config \
     --function-name algo-api --provisioned-concurrent-executions 5
   ```
3. Redeploy to trigger warm-up

**If database connections are exhausted (50+ active):**
1. Check which queries are holding connections:
   ```sql
   SELECT pid, query FROM pg_stat_activity WHERE state != 'idle';
   ```
2. Kill idle connections:
   ```sql
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity 
   WHERE state = 'idle' AND query_start < now() - interval '5 minutes';
   ```
3. Consider enabling RDS Proxy (front-load connection pooling):
   ```bash
   aws rds create-db-proxy --db-proxy-name algo-proxy --engine-family POSTGRESQL ...
   ```

**If specific query is slow:**
1. Add index to frequently-filtered columns:
   ```sql
   CREATE INDEX idx_swing_scores_symbol ON swing_trader_scores(symbol);
   ```
2. Rewrite query to use index (check EXPLAIN PLAN):
   ```bash
   psql -h algo-db... -c "EXPLAIN ANALYZE SELECT ..."
   ```

---

## IV. Charts / Scores Show Wrong Data or "Undefined"

### Detection
- Dashboard loads but columns show "undefined" or "-"
- Grade shows as blank, score shows as 0 across the board
- Price charts won't render

### Diagnosis
```bash
# 1. Check latest API response (browser DevTools → Network → click failing endpoint)
# 2. Verify API returned expected columns
curl -s 'https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/scores/stockscores?limit=1' | jq '.data[0]'

# 3. Check recent Lambda code changes
git log --oneline webapp/lambda/routes/*.js | head -5

# 4. Compare against API_CONTRACT.md for required columns
```

### Recovery Steps

**If API response is missing columns:**
1. Check Lambda route code matches API_CONTRACT.md:
   ```bash
   grep -A20 "router.get.*stockscores" webapp/lambda/routes/scores.js
   ```
2. If columns are missing, fix query:
   ```javascript
   // WRONG: SELECT symbol, grade FROM swing_trader_scores
   // RIGHT: SELECT symbol, grade, swing_score, trend_score, ... FROM swing_trader_scores LEFT JOIN ...
   ```
3. Redeploy: `git push origin main` → GitHub Actions auto-deploys

**If data values are all zeros/null:**
1. Check if loaders actually populated data:
   ```sql
   SELECT COUNT(*), MIN(date), MAX(date) FROM swing_trader_scores;
   ```
2. If counts are low, re-run loaders (see Section II)
3. If counts are high but values null, check loader logic (may have skipped computation)

**If database values seem stale:**
1. Check last successful load:
   ```sql
   SELECT table_name, MAX(date) as last_update FROM ( 
     SELECT 'swing_scores' as table_name, MAX(date) FROM swing_trader_scores
     UNION ALL
     SELECT 'prices', MAX(date) FROM price_daily
   ) t GROUP BY table_name;
   ```
2. If >12h old, manually trigger loaders

---

## V. Database Connection Errors

### Detection
- Lambda logs show "could not connect to server"
- Error: `FATAL: password authentication failed`
- Error: `timeout expired`

### Diagnosis
```bash
# 1. Test RDS connectivity from Lambda
aws lambda invoke --function-name test-db-connection /tmp/result.json
cat /tmp/result.json

# 2. Check Lambda has correct credentials
aws lambda get-function-configuration --function-name algo-api | grep -A10 Environment

# 3. Test credentials directly
psql -h algo-db.cojggi2mkthi.us-east-1.amazonaws.com -U stocks -d stocks -c "SELECT 1"
# (will prompt for password - check AWS Secrets Manager)
```

### Recovery Steps

**If password is wrong:**
1. Reset RDS master password:
   ```bash
   aws rds modify-db-instance --db-instance-identifier algo-db \
     --master-user-password new_secure_password --apply-immediately
   ```
2. Update AWS Secrets Manager:
   ```bash
   aws secretsmanager update-secret --secret-id algo/db/postgres \
     --secret-string '{"password":"new_password",...}'
   ```
3. Restart Lambda functions (new invocations pick up new secrets)

**If RDS is unreachable:**
1. Check RDS status: `aws rds describe-db-instances --db-instance-identifier algo-db`
2. If "stopped", start it: `aws rds start-db-instance --db-instance-identifier algo-db`
3. If "failed", create snapshot and restore:
   ```bash
   aws rds restore-db-instance-from-db-snapshot \
     --db-instance-identifier algo-db-restored \
     --db-snapshot-identifier <latest-snapshot>
   ```

**If security group is blocking traffic:**
1. Check inbound rules:
   ```bash
   aws ec2 describe-security-groups --group-ids sg-{RDS-SG} \
     | jq '.SecurityGroups[0].IpPermissions'
   ```
2. Ensure Lambda subnet has access to RDS:
   ```bash
   aws ec2 authorize-security-group-ingress --group-id sg-{RDS-SG} \
     --protocol tcp --port 5432 --source-security-group-id sg-{LAMBDA-SG}
   ```

---

## VI. Memory Leak / Lambda Performance Degradation

### Detection
- Lambda requests that normally take 1s now take 5s+
- Memory usage creeping up (CloudWatch metric shows 512MB → 900MB)
- Intermittent timeout errors

### Diagnosis
```bash
# 1. Check Lambda memory metrics
aws cloudwatch get-metric-statistics --namespace AWS/Lambda \
  --metric-name Duration --dimensions Name=FunctionName,Value=algo-api \
  --start-time 2026-05-15T00:00:00Z --end-time 2026-05-17T00:00:00Z --period 3600

# 2. Check for large response payloads (check API responses)
curl -s '.../api/scores/stockscores?limit=10000' | wc -c

# 3. Check Node.js memory (in CloudWatch logs)
aws logs tail /aws/lambda/algo-api | grep -i memory
```

### Recovery Steps

1. Increase Lambda memory allocation (improves CPU + memory):
   ```bash
   aws lambda update-function-configuration --function-name algo-api --memory-size 1024
   ```

2. Optimize response payload (paginate large result sets):
   ```bash
   # BEFORE: /api/scores/stockscores?limit=10000 (returns 10K records)
   # AFTER: /api/scores/stockscores?limit=100&offset=0 (paginate)
   ```

3. Add query timeout to prevent hung requests:
   ```javascript
   const query = db.query(sql, { timeout: 10000 }); // 10s timeout
   ```

4. Clear Lambda environment caches on redeploy

---

## VII. Escalation & Who to Contact

| Issue | Team | Contact |
|-------|------|---------|
| AWS Infrastructure | DevOps | Deploy via GitHub Actions (auto-escalates) |
| Data Pipeline (loaders) | Data Eng | Check logs; manually trigger if needed |
| API/Lambda code | Backend | Roll back last commit; run tests first |
| Frontend | Frontend | Invalidate CloudFront cache |
| Database tuning | DBA/DevOps | Query optimization; index creation |
| On-Call Emergency | Engineering | PagerDuty integration (if configured) |

---

## VIII. Testing Your Response (Dry-run)

Before an actual incident, verify your recovery steps:

```bash
# 1. Test database connectivity
python3 -c "from utils.db_connection import get_db_connection; get_db_connection(); print('OK')"

# 2. Test one loader
python3 loaders/loadstocksymbols.py

# 3. Test API locally
python3 -m pytest tests/integration/test_api_endpoints.py -v

# 4. Test Lambda deployment (on test branch)
git checkout -b test-deployment
git push origin test-deployment
# → GitHub Actions triggers on test branch; verify it succeeds
git checkout main
git branch -D test-deployment
```

---

## IX. Post-Incident

After resolving any incident:

1. **Document what happened:**
   - What failed
   - Root cause
   - How you fixed it
   - How to prevent next time

2. **Add to monitoring:**
   - Add CloudWatch alarm if this can be detected early
   - Add log pattern if error wasn't visible

3. **Update runbook:**
   - Add specific scenario if not covered
   - Update if recovery steps changed

4. **Create GitHub issue:**
   - Link to incident date/time
   - Propose permanent fix (not just workaround)
   - Assign to relevant team member
