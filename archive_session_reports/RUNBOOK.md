# Operations Runbook

How to monitor, operate, and troubleshoot your algo system.

---

## Daily Operations

### Morning (Before Market Opens)

```bash
# 1. Check if orchestrator ran successfully
tail -50 logs/orchestrator.log | grep -E "SUCCESS|FAILED"

# 2. Verify data loaded
psql -h localhost -U stocks -d stocks -c \
  "SELECT MAX(date) as latest_price FROM prices"
# Should be today

# 3. Check algo executed
psql -h localhost -U stocks -d stocks -c \
  "SELECT COUNT(*) as signal_count FROM algo_signals WHERE created_at > NOW() - INTERVAL '24 hours'"
# Should be > 0
```

### Evening (After Orchestrator Runs)

```bash
# Check evening run completed
grep "evening pipeline completed" logs/orchestrator.log | tail -1

# Verify portfolio updated with day's trades
psql -h localhost -U stocks -d stocks -c \
  "SELECT * FROM trades WHERE created_at > NOW() - INTERVAL '24 hours'"
```

---

## Monitoring

### Health Check

```bash
# Database health
psql -h localhost -U stocks -d stocks -c "SELECT 1"
echo "✅ Database connected"

# Latest data
psql -h localhost -U stocks -d stocks -c \
  "SELECT MAX(date) as latest_date FROM prices"
echo "✅ Data is current"

# Cron status
crontab -l | grep algo-orchestrator
echo "✅ Cron jobs scheduled"
```

### Metrics to Watch

```bash
# Data freshness
psql -h localhost -U stocks -d stocks -c \
  "SELECT MAX(date) FROM prices"

# Algo signal generation
psql -h localhost -U stocks -d stocks -c \
  "SELECT COUNT(*) FROM algo_signals WHERE created_at > NOW() - INTERVAL '1 day'"

# Trade execution
psql -h localhost -U stocks -d stocks -c \
  "SELECT COUNT(*) as trades FROM trades WHERE created_at > NOW() - INTERVAL '1 day'"
```

---

## Common Issues & Fixes

### Issue: Cron Job Not Running

**Symptoms:**
- Logs haven't updated since yesterday
- Data is stale (no new prices)

**Fix:**
```bash
# Check cron
crontab -l

# Restart cron
sudo systemctl restart cron

# Verify it runs manually
/usr/local/bin/algo-orchestrator --morning
```

### Issue: Database Connection Failed

**Symptoms:**
```
psycopg2.OperationalError: could not connect to server
```

**Fix:**
```bash
# Restart PostgreSQL
docker-compose restart postgres
sleep 10
psql -h localhost -U stocks -d stocks -c "SELECT 1"
```

### Issue: "Data not available" in Dashboard

**Symptoms:**
- Dashboard loads but shows no data

**Fix:**
```bash
# Load data
python scripts/run_local_orchestrator.py --run-all

# Restart dashboard
python dashboard.py
```

### Issue: High AWS Bill

**Diagnosis:**
- Check terraform.tfvars for unnecessary features
- See IaC_IMPROVEMENTS.md for known cost issues

**Fix:**
- Remove VPC from Lambda
- Disable provisioned concurrency
- Reduce reserved concurrency

---

## Scheduled Maintenance

### Weekly
```bash
# Review logs for errors
grep ERROR logs/orchestrator.log
```

### Monthly
```bash
# Clean up old logs
find logs/ -name "*.log" -mtime +28 -delete

# Check AWS bill
aws ce get-cost-and-usage --time-period Start=$(date +%Y-%m-01),End=$(date +%Y-%m-28)
```

### Database Backup
```bash
# Create backup
pg_dump -h localhost -U stocks stocks > backup.sql
gzip backup.sql

# Restore from backup
gunzip backup.sql.gz
psql -h localhost -U stocks stocks < backup.sql
```

---

## Status Page

- Database: Running (docker-compose)
- Cron Jobs: 2x daily (morning + evening)
- Dashboard: On-demand
- AWS Infrastructure: Deployed and healthy

---

Contact: argeropolos@gmail.com
