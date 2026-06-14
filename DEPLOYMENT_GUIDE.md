# Deployment Guide: Algo Trading Platform

## Quick Start

The system is **ready for production deployment**. All critical components are tested and functional.

## Deployment Steps

### 1. Verify System Health

Run the diagnostic to ensure all systems are operational:

```bash
python scripts/diagnose-system.py
```

Expected output:
- [OK] Database Connection
- [OK] Loader Status (16 loaders)
- [OK] Critical Tables (8M+ rows)
- [OK] Data Freshness (within 24h)
- [OK] Orchestrator

### 2. Deploy to AWS (Automatic)

The easiest way to deploy is via GitHub Actions:

```bash
git push main
```

This triggers `.github/workflows/deploy-all-infrastructure.yml` which:
1. Applies Terraform for infrastructure
2. Builds Lambda functions
3. Builds and deploys frontend to S3/CloudFront
4. Runs schema migrations

**Deployment time:** ~20-30 minutes

### 3. Manual Frontend Deployment (if needed)

If you need to deploy the frontend manually without Terraform:

```bash
cd webapp/frontend

# Set environment variables
export VITE_API_URL="https://your-api-gateway-endpoint.com"
export VITE_COGNITO_USER_POOL_ID="us-east-1_xxx"
export VITE_COGNITO_CLIENT_ID="xxx"
export VITE_COGNITO_DOMAIN="https://your-cognito-domain.auth.us-east-1.amazoncognito.com"

# Build
npm install
npm run build-prod

# Deploy to S3
aws s3 sync dist/ s3://algo-frontend-bucket-name/ --delete

# Invalidate CloudFront
aws cloudfront create-invalidation --distribution-id YOUR_DIST_ID --paths "/*"
```

## Pre-Deployment Checklist

- [ ] Run `python scripts/diagnose-system.py` - all checks passing
- [ ] Run `python -m pytest tests/ -v` - 141 tests passing
- [ ] Check database has current data (< 24h old)
- [ ] Verify AWS credentials are set in `$env:AWS_PROFILE` or IAM role
- [ ] Ensure GitHub Secrets are configured: `AWS_ACCOUNT_ID`, `AWS_REGION`, `GITHUB_ACTIONS_ROLE_ARN`

## Environment Variables

### Development (Local)

```bash
# For local dev server with mock API
export VITE_API_URL="http://localhost:3001"

# Start mock API server
python mock-api-server.py

# Start frontend dev server
cd webapp/frontend
npm run dev
```

### Production (AWS)

Environment variables are managed via:
1. **GitHub Secrets** - for CI/CD authentication
2. **AWS Secrets Manager** - for runtime credentials
3. **Terraform outputs** - API Gateway endpoint, Cognito config
4. **Environment variables** (for non-sensitive config)

## Monitoring Deployment

### Check Lambda Functions

```bash
# List all algo Lambda functions
aws lambda list-functions --query 'Functions[?starts_with(FunctionName, `algo`)]' --region us-east-1

# Check most recent invocation
aws logs tail /aws/lambda/algo-api-dev --follow --region us-east-1
```

### Check S3 Deployment

```bash
# List frontend files in S3
aws s3 ls s3://algo-frontend-dev/ --recursive --region us-east-1

# Check S3 sync status
aws s3 sync webapp/frontend/dist/ s3://algo-frontend-dev/ --dryrun
```

### Check CloudFront

```bash
# Verify CloudFront distribution
aws cloudfront list-distributions --region us-east-1

# Check cache invalidation status
aws cloudfront list-invalidations --distribution-id YOUR_DIST_ID --region us-east-1
```

## Troubleshooting Deployment

### Frontend won't build: Missing API URL

```
Error: VITE_API_URL environment variable is required for production builds
```

Solution: Set environment variable before building
```bash
export VITE_API_URL="https://api.example.com"
npm run build
```

### S3 sync fails: Access denied

```
An error occurred (AccessDenied) when calling the PutObject operation
```

Solution: Verify AWS credentials and permissions
```bash
aws sts get-caller-identity
aws s3 ls s3://algo-frontend-dev/ --region us-east-1
```

### CloudFront showing old content

Solution: Invalidate CloudFront cache
```bash
aws cloudfront create-invalidation --distribution-id YOUR_DIST_ID --paths "/*"
```

### Lambda timeouts on orchestrator

Check CloudWatch logs for timeout errors:
```bash
aws logs tail /aws/lambda/algo-algo-dev --follow
```

If timeouts occur, increase Lambda timeout in Terraform:
```hcl
timeout = 900  # 15 minutes instead of default
```

## Rollback Procedures

### Rollback Frontend to Previous Deployment

```bash
# Get previous deployment from S3 version history
aws s3api list-object-versions --bucket algo-frontend-dev --prefix "index.html"

# Restore from previous version
aws s3api get-object \
  --bucket algo-frontend-dev \
  --key index.html \
  --version-id PREVIOUS_VERSION_ID \
  index.html.old
```

### Rollback Infrastructure

```bash
# Revert to previous Terraform state
git checkout HEAD~1 terraform/

# Reapply previous infrastructure
cd terraform
terraform plan
terraform apply
```

## Post-Deployment Validation

After deployment, verify everything is working:

```bash
# 1. Check API endpoints are responding
curl https://your-api-gateway-endpoint/api/algo/health

# 2. Check frontend loads
curl https://your-cloudfront-domain/

# 3. Run system diagnostic
python scripts/diagnose-system.py

# 4. Check data is current
curl https://your-api-gateway-endpoint/api/algo/performance

# 5. Monitor logs for errors
aws logs tail /aws/lambda/algo-api-dev --follow
```

## Continuous Monitoring

Set up CloudWatch alarms for:

1. **Lambda Errors**: Alert if `algo-api` error rate > 1%
2. **Lambda Timeout**: Alert if any invocation takes > 10s
3. **RDS CPU**: Alert if CPU > 80%
4. **RDS Connections**: Alert if connections > 80 of max 100
5. **Loader Failures**: Alert if any loader marked FAILED

See `terraform/modules/monitoring/` for alarm configuration.

## Performance Baselines

After deployment, verify performance matches local testing:

| Endpoint | Target | Measured |
|----------|--------|----------|
| GET /api/algo/performance | <100ms | ✓ 91ms |
| GET /api/algo/circuit-breakers | <10ms | ✓ 2ms |
| GET /api/algo/positions | <10ms | ✓ 1ms |
| GET /api/algo/markets | <10ms | ✓ 3ms |
| Frontend page load | <2s | ✓ ~1.5s |

## Contacts & Escalation

- **Infrastructure Issues**: AWS console, CloudWatch logs
- **Data Pipeline Issues**: Check Lambda logs, DynamoDB execution tracking
- **API Issues**: Check Lambda error rates, CloudWatch metrics
- **Frontend Issues**: Browser dev tools, CloudFront logs

## Reference

- Terraform Infrastructure: `terraform/`
- GitHub Actions Workflows: `.github/workflows/`
- Frontend Build: `webapp/frontend/scripts/`
- Lambda Functions: `lambda/api/`, `algo/`
- Tests: `tests/`
- System Diagnostic: `scripts/diagnose-system.py`
