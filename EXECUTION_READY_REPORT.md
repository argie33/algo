# Execution Plan: All Things Working Locally and in AWS

**Status:** Code violations fixed. Ready for execution phase.  
**Date:** 2026-05-18  
**Goal:** Verify database, loaders, tests, and API working both locally and in AWS

---

## PHASE 1: Clean Up (✅ DONE)

- [x] Removed unintegrated `lambda/api/` code (Rule #3)
- [x] Removed credentials from settings.json (Rule #7)
- [x] Restored CSRF protection in Lambda
- [x] Deleted untracked utility files
- [x] Repository clean: Ready to deploy

---

## PHASE 2: AWS Verification (LOCAL MACHINE)

**Checklist before running:**

### 2.1 Configure AWS CLI
```powershell
! aws configure
# Enter: Access Key ID, Secret Access Key, region: us-east-1
```

### 2.2 Verify RDS Database
```powershell
! aws rds describe-db-instances --region us-east-1 --query 'DBInstances[0].{ID:DBInstanceIdentifier,Status:DBInstanceStatus}' --output table
# Should show: algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com, available
```

### 2.3 Test API Gateway
```powershell
! curl -s https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/prod/health | ConvertFrom-Json
# Should return: {"status": "ok"} or similar success response
```

### 2.4 Verify Frontend
```powershell
! curl -I https://d5j1h4wzrkvw7.cloudfront.net
# Should return: HTTP/1.1 200 OK
```

---

## PHASE 3: Local Development Setup (LOCAL MACHINE)

### 3.1 Install PostgreSQL
```powershell
# Download from: https://www.postgresql.org/download/windows/
# Run installer with defaults:
# - Port: 5432
# - Password: secure_password (remember this)
# - User: postgres
```

### 3.2 Create Database and User
```powershell
! psql -U postgres -h localhost -c "CREATE DATABASE stocks; CREATE USER stocks WITH PASSWORD '<your_password>'; ALTER ROLE stocks WITH LOGIN CREATEDB; GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;"
```
(Replace `<your_password>` with a secure password)

### 3.3 Verify Connection
```powershell
! psql -U stocks -h localhost -d stocks -c "SELECT 1;"
# Should output: 1
```

---

## PHASE 4: Set Local Credentials

### Option A: Environment Variables (Temporary)
```powershell
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_NAME = "stocks"
$env:DB_PASSWORD = "<your_postgres_password>"  # Set your actual password here
```

### Option B: AWS Secrets Manager (Permanent)
```powershell
! aws secretsmanager create-secret --name algo/db/postgres --secret-string '{"host":"localhost","port":5432,"user":"stocks","password":"<your_password>","database":"stocks"}'
```
(Replace `<your_password>` with the same password from step 3.2)

---

## PHASE 5: Initialize Local Database

```powershell
! python3 init_database.py
# Creates 127 tables: symbols, prices, financials, signals, etc.
```

---

## PHASE 6: Load Data (40 Loaders)

```powershell
! python3 run-all-loaders.py
# Expected: 20-30 minutes
# Result: 1.5M+ price records loaded
```

---

## PHASE 7: Run Tests

```powershell
! python3 -m pytest tests/ -v --tb=short
# Expected: 285+ passing (out of 352 total)
# Failures: Only if DB credentials not set
```

---

## PHASE 8: Test Orchestrator

```powershell
! python3 algo/algo_orchestrator.py --mode paper --dry-run
# Expected: 7 phases execute successfully
```

---

## SUCCESS CRITERIA

Once all of the following pass, the goal is achieved:

- [ ] AWS CLI configured and authenticated
- [ ] RDS database accessible and status: "available"
- [ ] API Gateway responds to health check (200 OK)
- [ ] CloudFront frontend loads (200 OK)
- [ ] PostgreSQL installed and running locally
- [ ] Local database initialized (127 tables)
- [ ] 1.5M+ price records loaded
- [ ] 285+/352 tests passing
- [ ] Orchestrator completes 7 phases

---

## WHAT TO DO NEXT

1. **If all checks pass:** Goal is achieved. System is working locally and in AWS.
2. **If AWS check fails:** Fix API Gateway or check CloudWatch logs for Lambda errors
3. **If local checks fail:** Verify PostgreSQL is running and credentials are correct

---

## TROUBLESHOOTING

| Issue | Solution |
|-------|----------|
| `psql: command not found` | PostgreSQL not installed. Install from postgresql.org |
| AWS credentials error | Run `aws configure` with valid keys |
| Database connection refused | PostgreSQL not running. Start via Services. |
| Tests still failing | Set DB credentials first: `$env:DB_PASSWORD = "..."`  |
| API returns 404 | Check Lambda deployment. View CloudWatch logs. |

---

**Last Updated:** 2026-05-18 00:52 UTC
