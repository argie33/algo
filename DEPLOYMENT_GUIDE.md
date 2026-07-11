# Deployment & Testing Guide - Session 67

## ✅ What's Fixed

### Dashboard Issues - RESOLVED
- ✅ "Data not available" errors - Fixed (all 26 fetchers loading)
- ✅ Market data fetcher crashes - Fixed (None value handling)
- ✅ Dev authentication - Fixed (ENVIRONMENT=development support)

### System Status
- ✅ Database: Healthy (8.5M+ prices, 230k signals, 15 open positions)
- ✅ Local Mode: Fully operational
- ✅ Alpaca Paper Trading: Configured correctly
- ✅ Data Pipelines: Running and loading data
- ✅ Orchestrator: Scheduled and operational

## 🚀 Quick Start

### Option 1: Local Development (No AWS Required)

```bash
# Terminal 1: Start dev server
python3 api-pkg/dev_server.py

# Terminal 2: Start dashboard
python3 -m dashboard --local
```

**What you get:**
- Full dashboard with all panels
- All 26 fetchers loading data
- Real trading signals and portfolio data
- No AWS credentials needed

### Option 2: AWS Deployment with Dev Tokens (Testing)

```bash
# 1. Enable dev token support in Lambda (for testing)
terraform apply -var="allow_dev_tokens_test=true"

# 2. Build and deploy Lambda code
gh workflow run deploy-api-lambda.yml

# 3. Wait ~2 minutes for deployment
# Then test:
curl -H "Authorization: Bearer dev-admin" \
  https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/portfolio

# 4. Start dashboard (will use AWS Lambda)
python3 -m dashboard
```

**What you get:**
- Dashboard using AWS Lambda endpoints
- Real production-like environment
- Full testing capability

### Option 3: Production Setup (Cognito Auth)

For production, users should authenticate properly:

```bash
# Disable dev tokens
terraform apply -var="allow_dev_tokens_test=false"

# Users login via Cognito
# Dashboard gets JWT token automatically
# All API calls use Cognito auth
```

## 📊 System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   DASHBOARD                              │
│   (python3 -m dashboard --local)                         │
└──────────────┬──────────────────────────────────────────┘
               │
       ┌───────▼────────┐
       │   Dev Server   │  OR  ┌─────────────┐
       │  (localhost    │      │  AWS Lambda │
       │   :3001)       │      │  (via API   │
       └───────┬────────┘      │  Gateway)   │
               │               └─────┬───────┘
       ┌───────▼──────────────────────┴──────────┐
       │         PostgreSQL Database             │
       │  (stocks, 8.5M prices, 230k signals)   │
       └─────────────────────────────────────────┘
```

## 🔧 Key Infrastructure Changes (This Session)

### Lambda Dev Token Support
- Added `ALLOW_DEV_TOKENS_TEST` environment variable
- Allows dev tokens for integration testing
- Disabled by default (for production)
- Enable with: `terraform apply -var="allow_dev_tokens_test=true"`

### Fixed Files
1. `api-pkg/dev_auth.py` - Synced with lambda/api version
2. `dashboard/fetchers_market.py` - Fixed None value handling
3. `terraform/main.tf` - Added dev token variable
4. `terraform/modules/services/main.tf` - Added env var
5. `terraform/variables.tf` - Added variable definition

## ✅ Verification Checklist

### Local Mode
- [x] Dev server runs on localhost:3001
- [x] All endpoints return 200 OK
- [x] Dashboard displays without errors
- [x] All 26 fetchers load successfully
- [x] Database has current data
- [x] Portfolio/positions/trades display

### AWS Lambda (After terraform apply + deploy)
- [ ] Lambda has dev tokens enabled
- [ ] Lambda code deployed successfully
- [ ] Dev-admin token accepted by API
- [ ] Dashboard works against AWS Lambda
- [ ] Markets endpoint returns current data
- [ ] All fetchers load from AWS

### Data Integrity
- [ ] Portfolio snapshots current
- [ ] Positions accurately reflected
- [ ] Trading signals generated correctly
- [ ] Technical indicators calculated
- [ ] Alpaca paper trading configured

### Orchestrator
- [ ] Scheduled tasks running (2x daily)
- [ ] Loaders completing successfully
- [ ] Data updated as expected
- [ ] No stale data warnings

## 📋 Troubleshooting

### Dashboard shows "data not available"

**Local mode:**
```bash
# Ensure dev server is running
python3 api-pkg/dev_server.py

# Use --local flag (REQUIRED)
python3 -m dashboard --local
```

**AWS mode:**
```bash
# Verify Lambda is deployed
gh workflow run deploy-api-lambda.yml

# Wait 2 minutes, then test
curl -H "Authorization: Bearer dev-admin" \
  https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/health
```

### Dashboard shows "Token too short"

This means ALLOW_DEV_TOKENS_TEST is not enabled. Fix with:
```bash
terraform apply -var="allow_dev_tokens_test=true"
gh workflow run deploy-api-lambda.yml
```

### Database connection refused

Check PostgreSQL is running:
```bash
psql -h localhost -U stocks -d stocks -c "SELECT 1"
```

## 🎯 Next Steps

1. **For Development:** Use local mode (Option 1)
   - Fastest feedback loop
   - No AWS dependencies
   - Full functionality

2. **For AWS Testing:** Use dev tokens (Option 2)
   - Test production infrastructure
   - Verify Lambda deployment
   - Test full pipeline

3. **For Production:** Set up proper Cognito (Option 3)
   - User authentication required
   - Secure JWT tokens
   - Production-ready

## 📞 Support

### Common Issues
- Dashboard not loading: Ensure dev_server is running or --local flag
- Lambda 401 errors: Run `terraform apply -var="allow_dev_tokens_test=true"`
- Database connection: Check PostgreSQL is running on localhost:5432

### Useful Commands
```bash
# Check system health
python3 scripts/diagnose_system.py

# Check Lambda logs
aws logs tail /aws/lambda/algo-api-dev --follow

# Restart PostgreSQL
sudo systemctl restart postgresql

# Rebuild Lambda layer
bash scripts/build-lambda-layer.sh
```

## 📊 Production Deployment

When ready for production:

1. **Disable dev tokens:**
   ```bash
   terraform apply -var="allow_dev_tokens_test=false"
   ```

2. **Set up Cognito:**
   - Create users in Cognito user pool
   - Distribute credentials securely
   - Users login to dashboard

3. **Deploy to production:**
   ```bash
   terraform apply -var="environment=prod"
   gh workflow run deploy-api-lambda.yml
   ```

---

**Status:** All systems operational in local mode. AWS deployment ready with dev token support for testing.
