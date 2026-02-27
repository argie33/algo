# How to Check All System Logs

## 🔍 LOCAL SYSTEM LOGS

### Check Data Loader Logs
```bash
# Main buy/sell signal loader
tail -f /tmp/loadbuyselldaily.log

# All loader logs
ls -lah /tmp/load*.log
tail -f /tmp/load*.log
```

### Check Running Processes
```bash
# See all active loaders
pgrep -af 'python.*load'

# Monitor in real-time
watch -n 5 'pgrep -af python.*load | wc -l'
```

### Check Memory & CPU Usage
```bash
# Overall system stats
free -h
top -b -n 1 | head -20

# Check Python memory usage
ps aux | grep python | grep -v grep
```

### Check Database Connectivity
```bash
# Test connection
export PGPASSWORD="bed0elAn"
psql -h localhost -U stocks -d stocks -c "SELECT 1"

# Check table row counts
psql -h localhost -U stocks -d stocks << 'SQL'
SELECT tablename, (SELECT COUNT(*) FROM pg_tables WHERE tablename=pg_tables.tablename) as rows
FROM pg_tables WHERE schemaname='public' ORDER BY tablename;
SQL
```

---

## 🌐 GITHUB ACTIONS LOGS

### View in Web Browser
1. Go to: https://github.com/argie33/algo/actions
2. Click on the latest workflow run
3. Click on the failed job to see detailed logs
4. Look for error messages, stack traces, timeout errors

### What to Look For
- **Build errors:** Docker build failures
- **Deployment errors:** CloudFormation stack errors
- **Authentication errors:** AWS credential issues
- **Timeout errors:** Lambda/ECS task timeouts
- **Data loading errors:** Loader script failures

### Common Error Patterns
```
ERROR: Docker build failed
STDERR: AWS credentials not found
TIMEOUT: Task timed out after 300 seconds
FATAL: Database connection refused
```

---

## ☁️ AWS LOGS (If Deployed)

### CloudWatch Logs
1. Go to AWS CloudWatch console
2. Navigate to: Logs → Log groups
3. Look for log groups:
   - `/aws/lambda/StockPlatformAPI`
   - `/aws/ecs/stock-loader-tasks`
   - `/aws/rds/database-errors`

### Lambda Logs
```
[Timestamp] START RequestId: xxx
[Timestamp] ... log message ...
[Timestamp] END RequestId: xxx
[Timestamp] REPORT Duration: XXXms
```

### ECS Task Logs
- Shows output from data loader scripts
- Contains progress updates
- Shows errors and exceptions
- Check for rate limiting or API errors

### RDS Performance Insights
1. Go to RDS console
2. Click on your DB instance
3. Go to Performance Insights
4. Look for slow queries or connection issues

---

## 🔍 FRONTEND LOGS

### Browser Console (When Frontend is Running)
1. Start frontend: `cd webapp/frontend && npm run dev`
2. Open browser DevTools: F12
3. Check Console tab for:
   - JavaScript errors (red)
   - Warnings (yellow)
   - Network errors (API calls failing)

### Check API Responses
1. Go to DevTools → Network tab
2. Filter by "api" or "xhr"
3. Click on each request
4. Check:
   - Status code (should be 200-299)
   - Response body (check for errors)
   - Headers (auth tokens, etc.)

### API Health Check
```bash
# Test API locally
curl -v http://localhost:3001/health

# Should return:
{
  "status": "healthy",
  "timestamp": "2026-02-26T20:35:00Z",
  "database": {
    "stocks": 4988,
    "signals": 73,  # This should increase
    ...
  }
}
```

---

## 📊 MONITORING SCRIPT

Create a real-time monitoring script:

```bash
#!/bin/bash
# monitor_all.sh

while true; do
  clear
  echo "╔══════════════════════════════════════════════════════╗"
  echo "║    SYSTEM MONITORING - $(date '+%Y-%m-%d %H:%M:%S')             ║"
  echo "╚══════════════════════════════════════════════════════╝"
  
  echo ""
  echo "📊 DATABASE STATUS:"
  export PGPASSWORD="bed0elAn"
  psql -h localhost -U stocks -d stocks -t << 'SQL'
  SELECT 'Symbols: ' || COUNT(*) FROM stock_symbols
  UNION ALL
  SELECT 'Signals: ' || COUNT(DISTINCT symbol) FROM buy_sell_daily;
SQL
  
  echo ""
  echo "⚙️  ACTIVE LOADERS:"
  pgrep -af 'python.*load' | wc -l | xargs echo "Count:"
  
  echo ""
  echo "💾 MEMORY:"
  free -h | grep Mem | awk '{print "Used: " $3 " / Total: " $2}'
  
  echo ""
  echo "🔄 LAST LOGS:"
  tail -3 /tmp/loadbuyselldaily.log 2>/dev/null || echo "No logs yet"
  
  sleep 10
done
```

Save as `monitor_all.sh` and run:
```bash
chmod +x monitor_all.sh
./monitor_all.sh
```

---

## 🚨 ERROR DIAGNOSIS FLOWCHART

### Is the frontend loading?
- YES → Check browser console for errors
- NO → Check if `npm run dev` is running

### Does the API respond?
- YES → Check API response data
- NO → Check Lambda logs or API gateway logs

### Is data loading?
- YES → Check progress in database
- NO → Check loader logs for errors

### Is GitHub Actions working?
- SUCCESS → Check if data arrived in AWS
- FAILURE → Check job logs for error message

---

## 📝 Key Log Files

### Local Machine
- Loader output: `/tmp/loadbuyselldaily.log`
- All loaders: `/tmp/load*.log`
- Docker logs: `docker logs <container-id>`

### AWS CloudWatch
- Lambda: `/aws/lambda/StockPlatformAPI`
- ECS: `/aws/ecs/stock-loader-tasks`
- RDS: Event logs in RDS console

### GitHub Actions
- Workflow logs: https://github.com/argie33/algo/actions
- Artifact logs: Check workflow artifact downloads

---

## ✅ SUCCESS INDICATORS

### Database
✅ All 4,988 symbols present
✅ 4,988+ signals in buy_sell_daily (1+ per symbol)
✅ No error messages in loader logs

### GitHub Actions
✅ Green checkmarks on all jobs
✅ No FAILED status
✅ Build completed in <10 minutes

### AWS
✅ Lambda logs show no errors
✅ RDS has all data tables
✅ API health endpoint returns 4,988 symbols

### Frontend
✅ No red errors in browser console
✅ API calls return 200 status
✅ Stock list displays all 4,988 stocks

---

## 🔧 TROUBLESHOOTING COMMANDS

```bash
# Emergency stop all loaders
pkill -f python

# Check if database is accessible
psql -h localhost -U stocks -d stocks -c "\dt"

# See what's consuming memory
ps aux --sort=-%mem | head -10

# Check if API is responding
curl -s http://localhost:3001/health | jq .

# See recent git changes
git log --oneline -10

# Check untracked files
git status --short
```

---

**Last Updated:** 2026-02-26
**Purpose:** Comprehensive debugging guide for stock platform
