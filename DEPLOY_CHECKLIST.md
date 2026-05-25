# Deployment Checklist

**Before executing `git push main` to deploy:**

## Code Quality
- [ ] All tests passing: `python3 -m pytest tests/ -v`
- [ ] Linting clean: `black --check algo/ lambda/ loaders/ utils/ config/`
- [ ] No TODO/FIXME comments left in code (except documented technical debt)
- [ ] Pre-commit hook passing (no .env files, session docs, or invalid configs)

## Credential & Security
- [ ] No hardcoded credentials in any file
- [ ] `.env` files are NOT committed
- [ ] AWS Secrets Manager paths correct in Terraform
- [ ] SEC_USER_AGENT environment variable set (sec_edgar_client.py)
- [ ] API Lambda DB_SSL = "require" (not "prefer")

## Database
- [ ] RDS instance running and accessible from VPC
- [ ] All schema migrations applied: `terraform/modules/database/init.sql`
- [ ] Database user password rotated recently (Q rotation schedule)
- [ ] Backup snapshots exist

## Lambda Configuration
- [ ] Orchestrator Lambda: Python 3.12 runtime
- [ ] API Lambda: Python 3.12 runtime, reserved_concurrent_executions = 10
- [ ] Both Lambdas: psycopg2 layer attached
- [ ] Environment variables set correctly in Terraform

## Infrastructure
- [ ] VPC/subnet configuration correct
- [ ] Security groups allow RDS port 5432 from Lambda
- [ ] CloudFront distribution configured (if using frontend)
- [ ] Cognito User Pool configured (if auth enabled)
- [ ] ECS cluster exists for data loaders

## Frontend
- [ ] Build successful: `npm run build`
- [ ] API_URL configuration correct (no double /api prefix)
- [ ] CORS headers properly configured
- [ ] Environment variables set in `config.js`

## EventBridge Schedules
- [ ] Data loader schedule enabled: 4AM ET daily
- [ ] Morning orchestrator schedule enabled: 9:30AM ET daily
- [ ] Evening orchestrator schedule enabled: 5:30PM ET daily (if trading)

## Manual Test (Local)
- [ ] Orchestrator test passes: `python3 -m pytest tests/backtest/test_backtest_regression.py::test_orchestrator_initialization`
- [ ] API responds to health check: `curl http://localhost:3001/api/health`
- [ ] Frontend loads without 404s
- [ ] Signal generation works with test data

## Production Readiness
- [ ] Backup RDS snapshot created
- [ ] CloudWatch log groups have retention policy set
- [ ] Alarms configured for critical errors (Lambda errors, DB connectivity)
- [ ] On-call rotation knows about deployment
- [ ] Rollback plan documented (if not automatic)

## Post-Deployment Verification (After Deploy)
- [ ] Check GitHub Actions workflow succeeded
- [ ] API Lambda test skipped or passed (no AWS creds required)
- [ ] CloudWatch logs show no errors in first 5 minutes
- [ ] Data loaders triggered and running (check ECS tasks)
- [ ] Health check endpoint returning 200 OK
- [ ] Frontend accessible at CloudFront URL
- [ ] Live trading mode still disabled (if not ready)

**DO NOT deploy if any checklist items are unchecked.**
