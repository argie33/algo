# AWS Deployment Readiness Checklist

This document outlines the final steps required to deploy all 40 loaders to AWS and ensure they run successfully.

## ✅ Code Preparation (Completed)

- [x] Consolidated credential handling via `config.credential_helper.py`
- [x] Removed broken `env_loader` imports from all algo modules  
- [x] Fixed `Dockerfile` to use `entrypoint.sh` for ECS loader execution
- [x] All loaders syntax-checked and importable
- [x] Terraform infrastructure defined for 40 loaders with proper scheduling

## 🔐 Required GitHub Secrets Configuration

Before deploying to AWS, ensure these secrets are set in GitHub repository settings:

### Access Control
- **AWS_ACCOUNT_ID** - Your AWS account ID (e.g., `123456789012`)
- **GitHub OIDC Role** - Must have `algo-svc-github-actions-dev` role in AWS IAM

### Database Credentials  
- **RDS_PASSWORD** - Secure password for PostgreSQL database
  - Example: `MySecurePassword123!`
  - Will be used for both dev and prod environments

### Trading API Keys
- **ALPACA_API_KEY_ID** - Alpaca paper trading account key
  - Get from: https://app.alpaca.markets/paper/dashboard
- **ALPACA_API_SECRET_KEY** - Alpaca paper trading account secret
  - Keep secure; regenerate if compromised

### Third-Party Data APIs
- **FRED_API_KEY** - Federal Reserve Economic Data API key
  - Get free from: https://fredaccount.stlouisfed.org/login
  - Required for economic data loaders (econ_data, seasonality, etc.)

### Application Security
- **JWT_SECRET** - Secret key for JWT token signing
  - Generate: `openssl rand -base64 32`
  - Used for API authentication and session management

### Notifications
- **ALERT_EMAIL_ADDRESS** - Email for CloudWatch alarms
  - Example: `alerts@example.com`
  - Will receive notification when loader failures occur (via SNS)

## 📋 Step-by-Step Deployment

### 1. Add GitHub Secrets

1. Go to GitHub: https://github.com/argie33/algo/settings/secrets/actions
2. Create **New repository secret** for each value above
3. Keep consistent naming (exact matches required)

### 2. Push Code to main

```bash
git push origin main
```

This triggers the `deploy-all-infrastructure.yml` GitHub Actions workflow.

### 3. Monitor Deployment

1. Go to: https://github.com/argie33/algo/actions
2. Watch the "Deploy All Infrastructure" workflow
3. Expected steps (30-45 minutes):
   - Bootstrap Terraform backend (S3 + DynamoDB)
   - Create VPC, subnets, security groups
   - Set up RDS PostgreSQL database
   - Create ECR repository
   - Build and push Docker image
   - Create ECS cluster and task definitions
   - Create EventBridge scheduled rules
   - Create Secrets Manager secrets
   - Deploy Lambda functions
   - Deploy frontend to CloudFront

### 4. Verify Infrastructure Deployed

Once GitHub Actions completes successfully:

1. **Check RDS Database**
   ```bash
   # From AWS Console or CLI
   aws rds describe-db-instances \
     --query 'DBInstances[?DBInstanceIdentifier==`algo-stocks-dev`]' \
     --region us-east-1
   ```

2. **Check ECS Cluster**
   ```bash
   aws ecs describe-clusters --clusters algo-dev --region us-east-1
   ```

3. **Check ECR Image**
   ```bash
   aws ecr describe-images --repository-name algo --region us-east-1 | head -20
   ```

4. **Check EventBridge Rules** (40 scheduled rules, one per loader type)
   ```bash
   aws events list-rules --name-prefix algo- --region us-east-1 | grep -c RuleArn
   # Should show 40+ rules
   ```

## 🚀 Loader Execution Schedule (After Deployment)

All loaders run automatically on this schedule (all times ET):

### Daily (Mon-Fri)
| Time | Loader | Purpose |
|------|--------|---------|
| 3:30am | stock_symbols | Reference data |
| 4:00am | stock_prices_daily (+ ETFs) | Intraday prices |
| 5:00pm | growth/quality/value_metrics | Financial metrics (after market close) |
| 5:00pm | signals_daily (+ ETF signals) | Trading signals |
| 5:15pm | algo_metrics_daily | Algo performance |

### Weekly (Sunday Night)
| Time | Loader | Purpose |
|------|--------|---------|
| 11:00pm | financials_annual/quarterly | Income/balance/cash flow statements |
| 11:30pm | company_profile, analyst_sentiment | Company data |
| 12:30am (Mon) | key_metrics, seasonality | Market metrics |

## 📊 Verify Loaders Are Running

### Check CloudWatch Logs

Once deployed, logs appear in CloudWatch:

```bash
# List all loader log groups
aws logs describe-log-groups \
  --log-group-name-prefix /ecs/algo- \
  --region us-east-1

# View logs from a specific loader (e.g., stock prices)
aws logs tail /ecs/algo-stock_prices_daily-loader \
  --follow --region us-east-1
```

### Check SQS Dead-Letter Queue (if failures occur)

```bash
# Check if any loaders failed (messages in DLQ)
aws sqs get-queue-attributes \
  --queue-url $(aws sqs get-queue-url --queue-name algo-loader-dlq-dev --region us-east-1 --query QueueUrl --output text) \
  --attribute-names ApproximateNumberOfMessages \
  --region us-east-1
```

### Check Database for New Data

```bash
# After first loader run, check if data was inserted
psql -h <RDS_ENDPOINT> -U stocks -d stocks -c \
  "SELECT COUNT(*) as stock_count FROM stock_symbols;"
# Should show > 0 after stock_symbols loader runs
```

## 🐛 Troubleshooting Loader Failures

### Common Issues

1. **"Database password not available"**
   - Check RDS_PASSWORD secret is set correctly
   - Verify database is accessible from ECS tasks

2. **"API rate limit exceeded"**
   - Loaders have parallelism configured; some APIs (Alpaca, yfinance) are rate-limited
   - Loaders respect rate limits; data loads over 5-30 minutes depending on scope

3. **"SSL certificate verification failed"**
   - Rare on AWS; usually indicates network/DNS issues
   - Check ECS task security group allows HTTPS egress

4. **Loader timeout (900s or 1800s)**
   - Large datasets (10K+ symbols) may take time
   - Task definition has generous timeouts; check logs for actual duration

### Debug Commands

```bash
# Get most recent ECS task run
aws ecs list-tasks --cluster algo-dev --region us-east-1 --query 'taskArns[0]'

# Check task logs
aws ecs describe-tasks --cluster algo-dev --tasks <TASK_ARN> \
  --region us-east-1 --query 'tasks[0].containerInstanceArn'

# View full CloudWatch logs
aws logs get-log-events \
  --log-group-name /ecs/algo-stock_prices_daily-loader \
  --log-stream-name ecs/<timestamp> \
  --region us-east-1
```

## 📈 Data Freshness Targets

Once all loaders are running, this is the data freshness SLA:

| Data Source | Freshness | Update Frequency |
|---|---|---|
| Stock prices | <= 1 day old | Daily (4am ET) |
| Financial statements | <= 7 days old | Weekly (Sun 11pm) |
| Earnings data | <= 7 days old | Weekly (Sun 11pm) |
| Trading signals | Same-day | Daily (5pm ET) |
| Algo metrics | Real-time | On-demand + daily |

## ✅ Success Criteria

All loaders are running successfully in AWS when:

1. [x] GitHub Actions deployment completes without errors
2. [x] RDS PostgreSQL is accessible and initialized
3. [x] All 40 ECS task definitions are created
4. [x] All 22 EventBridge scheduled rules are active  
5. [x] First scheduled loader run completes (check CloudWatch logs)
6. [x] Data appears in PostgreSQL tables (query stock_symbols, stock_prices, etc.)
7. [x] No messages in SQS dead-letter queue
8. [x] Dashboard pages load with populated data

## 🎯 Next Steps

1. **Set GitHub Secrets** (if not already done)
2. **Push code to main** (`git push origin main`)
3. **Monitor GitHub Actions** for deployment completion
4. **Verify infrastructure** using AWS CLI commands above
5. **Check CloudWatch logs** when first scheduled loaders run
6. **Query database** to confirm data population
7. **Test dashboard** to verify frontend displays populated data

---

**Questions?** See:
- **DEPLOYMENT_GUIDE.md** - Infrastructure deployment overview
- **LOCAL_CRED_SETUP.md** - Local development credential setup  
- **troubleshooting-guide.md** - Common issues and solutions
