# Troubleshooting Guide

Common issues and solutions.

## Database Issues

### "connection to server at localhost failed"

**Cause:** PostgreSQL not running

**Solution:**
```bash
# macOS
brew services start postgresql

# Linux
sudo systemctl start postgresql

# Windows - use PostgreSQL app or Windows Services
```

### "password authentication failed for user stocks"

**Cause:** Missing database credentials

**Solution:**
Set environment variables:
```bash
export DB_PASSWORD=your_password
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_NAME=stocks
```

Or use AWS Secrets Manager - see `LOCAL_CRED_SETUP.md`

### "database stocks does not exist"

**Cause:** Database never initialized

**Solution:**
```bash
python3 init_database.py
```

## Loader Issues

### "ModuleNotFoundError: No module named utils"

**Cause:** Loader not run from correct directory

**Solution:**
```bash
cd loaders
python3 loadstocksymbols.py

# OR from root
cd /c/Users/arger/code/algo
python3 loaders/loadstocksymbols.py
```

### "No such file: load_*.py"

**Cause:** Loader file doesn't exist or was renamed

**Solution:**
List available loaders:
```bash
ls loaders/load*.py loaders/loadc*.py | head -20
```

### "ValueError: Database password not available"

**Cause:** DB_PASSWORD env var not set, AWS not configured

**Solution:**
1. Set environment variable: `export DB_PASSWORD=...`
2. OR configure AWS: `aws configure` (then AWS Secrets Manager used auto)

## Test Issues

### "FAILED test_position_sizer.py - psycopg2.OperationalError"

**Cause:** Tests need database connection

**Solution:**
```bash
# Set credentials first
export DB_PASSWORD=your_password

# Run tests
python3 -m pytest tests/ -v
```

### "ModuleNotFoundError in conftest.py"

**Cause:** Running from wrong directory

**Solution:**
```bash
cd /c/Users/arger/code/algo  # Go to project root
python3 -m pytest tests/ -v
```

## Orchestrator Issues

### "Cannot find required data tables"

**Cause:** Tables not created by init_database.py

**Solution:**
```bash
python3 init_database.py
python3 run-all-loaders.py --tier 0  # Load symbols first
```

### "Dry-run fails with empty data"

**Cause:** Loaders haven't run yet

**Solution:**
```bash
python3 run-all-loaders.py  # Full run takes ~20 min
python3 algo/algo_orchestrator.py --mode paper --dry-run
```

## GitHub Actions Deployment Issues

### "Terraform validation failed"

**Cause:** Infrastructure code has syntax error

**Solution:**
1. Check GitHub Actions log for error details
2. Fix .tf file syntax
3. Commit and push

### "Lambda function timeout"

**Cause:** Timeout set too low for loaders

**Solution:**
In `terraform/lambda.tf`, increase timeout:
```hcl
timeout = 300  # Increase from 60 seconds
```

## Performance Issues

### "Loaders running very slow"

**Cause:** Database connection pool exhausted or network latency

**Solution:**
```bash
# Check database connections
psql -U stocks -h localhost -d stocks -c "SELECT count(*) FROM pg_stat_activity;"

# Restart database if too many connections
```

## Development Tips

### Debug a specific loader

```bash
python3 -u loaders/loadpricedaily.py 2>&1 | head -100
```

### Watch database queries in real-time

```bash
psql -U stocks -h localhost -d stocks
stocks=# SELECT query, state FROM pg_stat_activity WHERE state = 'active';
```

### Clear all data and restart

```bash
python3 init_database.py --reset  # Drops and recreates
python3 run-all-loaders.py  # Reload from scratch
```

## Getting Help

1. Check this guide first (most issues covered)
2. Check `STATUS.md` for system state
3. Review recent commits: `git log --oneline -20`
4. Check GitHub Actions logs for deployment issues

For persistent issues, review logs:
```bash
# Local logs
tail -100 logs/*.log

# AWS CloudWatch (after deployment)
aws logs tail /aws/lambda/load-price-daily --follow
```
