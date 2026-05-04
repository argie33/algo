# Troubleshooting

## Local Development Issues

### API won't start on port 3001

**Error:** `EADDRINUSE: address already in use :::3001`

**Fix:**
```bash
# Kill the process on port 3001
lsof -i :3001 | grep LISTEN | awk '{print $2}' | xargs kill -9

# Or use a different port
PORT=3002 node webapp/lambda/index.js
```

### Database connection refused

**Error:** `Error: connect ECONNREFUSED 127.0.0.1:5432`

**Fix:**
```bash
# 1. Check PostgreSQL is running
psql -h localhost -U stocks -d stocks -c "SELECT 1"

# 2. Verify .env.local has correct credentials
cat .env.local

# 3. Test connection manually
psql -h localhost -U stocks -d stocks -c "SELECT current_database();"

# 4. If using RDS, check security group allows your IP
aws ec2 describe-security-groups --group-ids sg-xxxxx
```

### Frontend not loading

**Error:** Blank page or "Cannot GET /"

**Fix:**
```bash
# 1. Check frontend server is running
curl http://localhost:5174

# 2. Check API proxy is configured
grep "VITE_API_URL" webapp/frontend/.env

# 3. Rebuild frontend
cd webapp/frontend
npm run dev
```

### Database schema doesn't exist

**Error:** `relation "price_daily" does not exist`

**Fix:**
```bash
# The schema is created automatically on first API start
# Just restart the API:
node webapp/lambda/index.js

# If still missing, check logs for creation errors
# Tables should be in public schema, not another schema
psql -h localhost -U stocks -d stocks -c "\dt"
```

### Node modules missing

**Error:** `Cannot find module 'express'`

**Fix:**
```bash
# Reinstall dependencies
rm -rf node_modules package-lock.json
npm install

# Also reinstall frontend
cd webapp/frontend
rm -rf node_modules package-lock.json
npm install
```

---

## AWS Deployment Issues

### CloudFormation stack creation fails

**Error:** `CREATE_FAILED` in CloudFormation

**Fix:**
```bash
# 1. Check events for the actual error
aws cloudformation describe-stack-events \
  --stack-name your-stack-name \
  --query 'StackEvents[0]'

# 2. Common issues:
#    - Security group doesn't exist
#    - VPC/subnet not found
#    - IAM role lacks permissions

# 3. Delete and retry
aws cloudformation delete-stack --stack-name your-stack-name
```

### Lambda deployment fails

**Error:** `An error occurred (InvalidParameterValueException)`

**Fix:**
```bash
# 1. Verify S3 bucket exists and is accessible
aws s3 ls s3://your-bucket

# 2. Verify code zip is valid
unzip -t lambda-function.zip

# 3. Check Lambda execution role has needed permissions
aws iam get-role-policy --role-name your-role --policy-name your-policy
```

### RDS connection from Lambda fails

**Error:** `ECONNREFUSED` or `timeout`

**Fix:**
```bash
# 1. Verify security group allows Lambda → RDS
aws ec2 describe-security-groups --group-ids sg-xxxxx

# 2. Check RDS is in the same VPC as Lambda
aws rds describe-db-instances --query 'DBInstances[0].DBSubnetGroup'

# 3. Verify database credentials in Secrets Manager
aws secretsmanager get-secret-value --secret-id stocks-db-credentials

# 4. Test from Lambda logs
# Lambda should be able to reach RDS endpoint on port 5432
```

### EventBridge rule not triggering

**Error:** Lambda not executing on schedule

**Fix:**
```bash
# 1. Verify rule exists and is enabled
aws events describe-rule --name algo-eod-orchestrator

# 2. Check rule targets
aws events list-targets-by-rule --rule algo-eod-orchestrator

# 3. Enable rule if disabled
aws events enable-rule --name algo-eod-orchestrator

# 4. Check Lambda permissions
aws lambda list-policy --function-name algo-orchestrator

# 5. Manually invoke to test
aws lambda invoke \
  --function-name algo-orchestrator \
  --payload '{"test": true}' \
  /tmp/response.json
```

---

## Data & Loader Issues

### No data showing on frontend

**Steps to debug:**

1. Check database has data:
```bash
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM price_daily;"
```

2. Check API returns data:
```bash
curl http://localhost:3001/api/stocks
curl http://localhost:3001/api/price/history/AAPL
```

3. Check frontend API calls:
   - Open DevTools (F12) → Network
   - Look for `/api/stocks` request
   - Check response status (200 = OK, 500 = error)

4. Check API logs:
```bash
tail -f /var/log/api.log
```

### Loader fails but no error message

**Fix:**
```bash
# 1. Run loader locally with verbose output
python3 loadpricedaily.py --debug

# 2. Check database connection
python3 -c "from database_helper import DatabaseHelper; db = DatabaseHelper(); print(db.health_check())"

# 3. Check data source credentials
echo $FRED_API_KEY
echo $ALPACA_API_KEY

# 4. Check loader logs in AWS
aws logs tail /ecs/loaders --follow
```

### Data is stale (not updated)

**Fix:**
```bash
# 1. Check when loaders last ran
aws logs filter-log-events \
  --log-group-name /ecs/loaders \
  --start-time $(date -d '24 hours ago' +%s)000

# 2. Manually trigger a loader
python3 loadpricedaily.py --backfill_days 1

# 3. Check if EventBridge rules are enabled
aws events list-rules --query 'Rules[*].[Name,State]'
```

---

## Performance Issues

### API is slow (>1s response time)

**Fix:**
```bash
# 1. Check Lambda duration
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=api \
  --start-time 2026-05-04T00:00:00Z \
  --end-time 2026-05-04T23:59:59Z \
  --period 3600 \
  --statistics Average

# 2. Check database query performance
# Enable query logging in PostgreSQL:
sudo -u postgres psql -c "ALTER SYSTEM SET log_statement = 'all';"
sudo systemctl restart postgresql

# 3. Check for missing database indexes
# See DATA_LOADING.md for recommended indexes

# 4. Profile Lambda execution
# Enable X-Ray tracing in CloudFormation
```

### High database CPU

**Fix:**
```bash
# 1. Identify slow queries
psql -h localhost -U stocks -d stocks -c "\x on" -c "
SELECT query, mean_exec_time, calls 
FROM pg_stat_statements 
ORDER BY mean_exec_time DESC LIMIT 10;"

# 2. Add indexes
# Common: price_daily(symbol, date), buy_sell_daily(symbol, date)

# 3. Check for N+1 queries in API code
# Look for loops that query database inside

# 4. Enable connection pooling (RDS Proxy)
```

---

## Monitoring & Alerts

### Check system health

```bash
# API health
curl http://localhost:3001/api/health

# API diagnostics
curl http://localhost:3001/api/diagnostics

# Database status
psql -h localhost -U stocks -d stocks -c "SELECT version();"

# CloudWatch metrics
aws cloudwatch list-metrics --namespace AWS/Lambda
```

### View logs

```bash
# API logs (local)
tail -f api.log

# Lambda logs (AWS)
aws logs tail /aws/lambda/api --follow

# Loader logs (AWS)
aws logs tail /ecs/loaders --follow

# Algo logs (AWS)
aws logs tail /aws/lambda/algo-orchestrator --follow
```

### Subscribe to alerts

```bash
# SNS topic for critical alerts
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT:alerts \
  --protocol email \
  --notification-endpoint your@email.com
```

---

## See Also

- `LOCAL_SETUP.md` — Local development setup
- `AWS_DEPLOYMENT.md` — AWS infrastructure
- `API_REFERENCE.md` — API endpoints
- `DATA_LOADING.md` — Data loaders
