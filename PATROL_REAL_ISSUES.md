# Data Patrol - Real Issues (Not False Alarms)

**Status:** Operational issues that need fixing

---

## ✅ Issue #1: "5 Patrol Runs" - Actually False Alarm

**What we thought:** Patrol running 5 times/day  
**What's actually happening:** ONE patrol run with 50+ individual log entries (findings)

**Why:** Each `patrol.log()` call in algo_data_patrol.py does a separate database INSERT + COMMIT. So 50 findings = 50 separate INSERT statements, each timestamped milliseconds apart.

**Is this a problem?** 
- ✓ Not really - patrol still runs once daily as scheduled
- ⚠️ Slightly inefficient - 50 database roundtrips instead of 1
- ⚠️ Makes logs harder to read

**Quick fix (if you care):**
Batch the INSERTs into a single transaction in `check_loader_contracts()`:
```python
# Instead of self.log() for each check
# Collect them all, then:
cur.executemany("INSERT INTO data_patrol_log VALUES (%s,...)", all_findings)
conn.commit()  # Once, not 50 times
```

**Verdict:** Low priority - system works fine as-is

---

## 🔴 Issue #2: CRITICAL - Data Loaders Not Running

**Evidence:**
```
Patrol CRITICAL findings (last 7 days):
  - May 3: buy_sell_daily stale 9 days (threshold: 7 days)
  - May 3: trend_template_data stale 9 days
  - May 3: technical_data_daily stale 9 days
```

**What this means:**
```
May 1: Last data update for these tables
May 3: Patrol runs, sees data is 2+ days old
May 4: Still no new data (3+ days old now)
```

**Root cause:** Data loaders are NOT successfully running.

### Why This Matters
- Patrol correctly identified stale data (working as designed!)
- But loaders should have refreshed data by now
- **Trading decisions being made on 3+ day old data** ⚠️

### What to Check

**1. Loader Task Scheduler Status:**
```powershell
# Check if loader tasks exist
Get-ScheduledTask | Where-Object {$_.TaskName -like "*load*"} | Select-Object TaskName, State

# Check for errors
$task = Get-ScheduledTask -TaskName "AlgoLoader*" -ErrorAction SilentlyContinue
if ($task) {
    Get-ScheduledTaskInfo -TaskName $task.TaskName | Select-Object LastRunTime, LastTaskResult, NextRunTime
}
```

**2. Loader Execution Logs:**
```bash
# Check for loader activity
ls -la ~/.local/share/algo/logs/load*.log 2>/dev/null | tail -10

# Check for errors
grep -i "error\|fail\|timeout\|rate" ~/.local/share/algo/logs/load*.log 2>/dev/null | tail -20
```

**3. Database Loader Status:**
```sql
-- Check when loaders last ran successfully
SELECT table_name, latest_date, age_days, status, error_message
FROM data_loader_status
WHERE table_name IN ('buy_sell_daily', 'trend_template_data', 'technical_data_daily')
ORDER BY latest_date DESC;

-- Expected: latest_date should be TODAY or YESTERDAY
-- If it's 3 days old, loader didn't run
```

**4. Test Loaders Manually:**
```bash
# Try running one loader directly
cd /path/to/algo
python3 loadbuyselldaily.py

# Does it complete? Any errors? Does data get updated?
```

### How to Fix

1. **Verify loaders are scheduled:**
   - Windows Task Scheduler should have daily loader tasks
   - Check they're set to run (enabled, not paused)

2. **Check for API credential failures:**
   - yfinance, Alpaca, etc. might be rate-limited or expired
   - Test: `python3 -c "import yfinance; yf.download('SPY', start='2026-05-04', end='2026-05-05')"`

3. **Check for network/connectivity issues:**
   - Can the loaders reach external APIs?
   - Any firewall/proxy issues?

4. **Restart loaders:**
   - If they're stuck/hung, may need manual restart
   - Enable task notifications to catch failures

---

## 🟡 Issue #3: Weak Orchestrator Scheduling

**Finding:** Orchestrator phase_1 runs rarely (1 time in last 24h, expected daily)

**Why it matters:**
- Orchestrator should run daily to evaluate trading conditions
- If not running, patrol results aren't being checked before trades
- Pattern: patrol runs daily @ 9:25am, but orchestrator not running daily

**Check:**
```powershell
# Look for AlgoOrchestrator task
Get-ScheduledTask | Where-Object {$_.TaskName -like "*orchestrator*"}

# Expected: Daily schedule at 8:00am ET (after patrol @ 7:25am)
```

**If missing:**
Need to create orchestrator Task Scheduler entry to run daily at 8:00am ET.

---

## Summary of Real Issues

| Issue | Severity | Status | Action |
|-------|----------|--------|--------|
| Multiple log entries per run | Low | Benign | Optional cleanup |
| **Data loaders not running** | **HIGH** | **Blocking** | **Urgent investigation** |
| Weak orchestrator scheduling | Medium | Blocking | Verify schedule exists |

---

## IMMEDIATE ACTION REQUIRED

### Priority 1: Fix Data Loaders (TODAY)
```
1. Check if loader tasks exist in Task Scheduler
2. Check if they ran in last 24 hours
3. If yes but data didn't update → API/network issue
4. If no → Task disabled or never created
5. Test one loader manually
```

**Impact:** Patrol WILL block trading if data stays stale >7 days (correct behavior but needs loader fix)

### Priority 2: Verify Orchestrator Scheduled (TODAY)
```
1. Check if orchestrator task exists in Task Scheduler  
2. Should run daily at 8:00am ET (after patrol)
3. If missing, create it
```

**Impact:** Without daily orchestrator runs, patrol results aren't checked before trading

---

## Next Steps

1. **Right now:** Check Windows Task Scheduler for all Algo* tasks
2. **This hour:** Run a loader manually to test connectivity
3. **Today:** Fix scheduling if tasks are missing or disabled
4. **Tomorrow:** Verify data loaders succeeded overnight

Then your system will be fully operational!
