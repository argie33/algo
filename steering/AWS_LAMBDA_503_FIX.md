# AWS Lambda 503 Errors: Root Cause & Fixes

## ROOT CAUSE FOUND & FIXED (2026-07-14)

Provisioned concurrency was warming the wrong target. Terraform's
`aws_lambda_provisioned_concurrency_config.api` pointed its `qualifier` at
`aws_lambda_function.api.version` — a raw version number frozen at whatever the *last
`terraform apply`* published. But `deploy-api-lambda.yml` (the frequent code-only deploy
path) publishes a NEW version on every push and repoints a `LIVE` alias to it — and API
Gateway's `integration_uri` invoked `aws_lambda_function.api.invoke_arn` (unqualified,
always `$LATEST`). Three different targets, only one of which (`$LATEST`) ever actually
served traffic, and it was never the one kept warm. Every real request cold-started
(~7s VPC init, confirmed in CloudWatch logs) and concurrent cold starts produced the
Throttles seen in `AWS/Lambda` metrics — the proximate cause of client-facing 503s.

Fixed in `terraform/modules/services/main.tf`: provisioned concurrency, the API Gateway
integration, and the Lambda invoke permission all now target the same `LIVE` alias that
`deploy-api-lambda.yml` maintains (`ignore_changes = [function_version]` so Terraform
doesn't fight the deploy workflow over which version the alias points to). A stray
lowercase `live` alias (pointing at version 1, never referenced by anything) was also
cleaned up — it was dead leftover from earlier manual troubleshooting.

## Root Causes of Lambda 503 Errors

Lambda returns HTTP 503 "Service Unavailable" when:

1. **VPC Cold Start Timeout** (15-40 seconds exceeds API Gateway timeout of 29 seconds)
2. **Lambda Cannot Reach Database** (VPC configuration missing or security groups misconfigured)
3. **Insufficient Provisioned Concurrency** (requests queue up, existing instances overwhelmed)
4. **Reserved Concurrency Exhausted** (parallel loaders exceed reserved limit)
5. **Lambda Function Errors** (code throws unhandled exception during initialization)
6. **Database Connection Pool Exhausted** (too many concurrent requests, not enough connections)

## Quick Diagnosis

```bash
# Check latest Lambda logs for errors
aws logs tail /aws/lambda/algo-api-dev --follow --region us-east-1

# Check if Lambda has VPC configuration
aws lambda get-function-configuration --function-name algo-api-dev \
  --region us-east-1 --query 'VpcConfig'

# Check provisioned concurrency
aws lambda get-provisioned-concurrency-config --function-name algo-api-dev \
  --qualifier LIVE --region us-east-1
```

## Fix #1: VPC Configuration (Most Common)

If Lambda has no VPC configuration and database is in a VPC:

```bash
# Run the automated fix script
bash scripts/fix-lambda-vpc.sh

# OR manually configure:
aws lambda update-function-configuration \
  --function-name algo-api-dev \
  --vpc-config SubnetIds=subnet-xxx,subnet-yyy \
                SecurityGroupIds=sg-zzz \
  --region us-east-1
```

**After running the fix:**
1. Wait 60 seconds for Lambda to update
2. Re-deploy Lambda code: `gh workflow run deploy-api-lambda.yml`
3. Test: `curl https://<api-url>/api/health`

## Fix #2: Enable Provisioned Concurrency

Keeps Lambda instances warm to eliminate VPC cold-start delays:

```bash
# Apply Terraform with provisioned concurrency
cd terraform
terraform apply -var="api_lambda_provisioned_concurrency=5"
```

Cost: ~$12/month per unit in us-east-1 (set to 0 to disable).

**Why this matters:**
- Without provisioned concurrency: VPC cold start takes 15-40 seconds
- API Gateway timeout: 29 seconds
- Result: First request times out and returns 503
- Fix: Pre-warmed instances are ready instantly

## Fix #3: Increase Lambda Timeout

If Lambda needs more time to initialize:

```bash
cd terraform
terraform apply -var="api_lambda_timeout=60"
```

Default is 30 seconds. Increase if database queries are slow.

## Fix #4: Increase Reserved Concurrency

If parallel loaders are overwhelming the API Lambda:

```bash
cd terraform
terraform apply -var="api_lambda_reserved_concurrency=100"
```

Default is 50. This reserves capacity for API while allowing loaders to queue.

## Fix #5: Database Connection Pool Issues

If you see "too many connections" errors:

1. Check RDS connection count: `SELECT count(*) FROM pg_stat_activity;`
2. Increase RDS connection limit (via Parameter Group)
3. Reduce concurrent loader parallelism in `steering/DATA_LOADERS.md`

## Verify All Fixes Are Applied

After applying fixes, test each endpoint:

```bash
# Test basic health check
curl https://<api-url>/api/health

# Test portfolio endpoint (requires auth)
curl -H "Authorization: Bearer <token>" https://<api-url>/api/algo/portfolio

# Test signals endpoint (known to be slow)
curl -H "Authorization: Bearer <token>" https://<api-url>/api/algo/dashboard-signals

# Monitor error rate (should be < 1%)
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=algo-api-dev \
  --start-time 2026-07-10T00:00:00Z \
  --end-time 2026-07-11T00:00:00Z \
  --period 3600 \
  --statistics Sum
```

## Recommended Production Configuration

```terraform
# Apply these settings for reliable production operation:
api_lambda_timeout = 60                      # 1 minute for slow queries
api_lambda_memory = 1024                     # 1 GB for better performance
api_lambda_provisioned_concurrency = 5       # Keep 5 instances warm
api_lambda_reserved_concurrency = 100        # Reserve capacity for API
```

## Dashboard Shows "Data Not Available"

If dashboard still shows errors after Lambda fixes:

1. **Check API is returning data:**
   ```bash
   curl -H "Authorization: Bearer dev-admin" http://localhost:3001/api/algo/portfolio
   # Should return JSON with portfolio data, not {"_error": "..."}
   ```

2. **If using AWS Lambda (not local dev):**
   - Ensure Lambda is deployed with latest code: `gh workflow run deploy-api-lambda.yml`
   - Wait 60 seconds after deployment
   - Ensure provisioned concurrency is allocated
   - Check CloudWatch logs for errors

3. **If using local dev server:**
   - Use `python3 -m dashboard --local` (must use --local flag)
   - Do NOT use dashboard without --local in local dev (tries to use AWS Lambda)

## Monitoring for Future Issues

Set up CloudWatch alarms:

```bash
# Alarm for 503 errors
aws cloudwatch put-metric-alarm \
  --alarm-name "api-lambda-503-errors" \
  --alarm-description "Alert when Lambda returns 503 errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions <SNS_TOPIC_ARN>

# Alarm for cold starts (Duration > 10 seconds)
aws cloudwatch put-metric-alarm \
  --alarm-name "api-lambda-cold-starts" \
  --alarm-description "Alert when Lambda has cold starts" \
  --metric-name Duration \
  --namespace AWS/Lambda \
  --statistic Average \
  --period 300 \
  --threshold 10000 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions <SNS_TOPIC_ARN>
```

## Debug Checklist

- [ ] Lambda has VPC configuration (subnets + security groups)
- [ ] Lambda security group allows egress to RDS port 5432
- [ ] RDS security group allows ingress from Lambda security group
- [ ] Provisioned concurrency is enabled (≥ 1 unit)
- [ ] Lambda timeout is sufficient (≥ 30 seconds)
- [ ] Reserved concurrency is not exhausted
- [ ] Database has no connection pool errors
- [ ] Latest Lambda code is deployed
- [ ] No unhandled exceptions in Lambda code
- [ ] API Gateway has < 1% error rate

## Getting Help

If 503 errors persist after all fixes:

1. Check Lambda CloudWatch logs: `aws logs tail /aws/lambda/algo-api-dev --follow`
2. Check API Gateway logs: `aws logs tail /aws/apigateway/algo-api-dev --follow`
3. Run diagnostic script: `python3 scripts/diagnose_aws_issues.py`
4. Open GitHub issue with error logs and diagnostic output
