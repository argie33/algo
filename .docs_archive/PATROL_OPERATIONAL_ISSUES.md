# Data Patrol - Operational Issues Still Causing Grief

**Date:** 2026-05-04  
**Severity:** Medium (system works but not optimally)

---

## 🔴 Issue #1: Patrol Running 5 Times at 3pm Instead of Once at 7:25am

### Current Behavior
```
07:00 - 1 run (expected)
15:00 - 5 runs (⚠️ UNEXPECTED!)
```

### Why This Is a Problem
- **Resource waste:** Running patrol 5x wastes DB and compute
- **Log noise:** 142 rows/day in patrol_log (5x more than needed)
- **Timing uncertainty:** Tasks running unpredictably
- **Harder to debug:** Multiple concurrent runs could cause issues

### Root Cause
Unknown - likely:
1. Windows Task Scheduler has multiple triggers
2. Manual re-runs happening (someone testing patrol)
3. Orchestrator calling patrol multiple times
4. Background job running on interval

### Immediate Fix Needed
**Check Task Scheduler configuration:**
```powershell
# In Windows PowerShell as Administrator:
Get-ScheduledTask -TaskName "AlgoPatrolMorning" | Get-ScheduledTaskInfo

# Look for: Multiple triggers, incorrect schedule
# Edit: Control Panel > Task Scheduler > AlgoPatrolMorning > Triggers
```

**Expected configuration:**
- Single trigger: Daily at 7:25 AM ET
- Action: Run `run_patrol.cmd`
- No other triggers

### Workaround (Temporary)
Until Task Scheduler is fixed, manually set:
```batch
REM In run_patrol.cmd, only allow one run per day
set LAST_RUN_FILE=%USERPROFILE%\algo_logs\patrol_last_run.txt
if exist %LAST_RUN_FILE% (
    for /f %%A in (%LAST_RUN_FILE%) do set LAST=%%A
    REM Only run if last run was >12 hours ago
)
```

---

## 🔴 Issue #2: Stale Data Errors Still Being Generated (26 CRITICAL in 7 days)

### Current Behavior
```
Staleness CRITICAL: 26 occurrences (last 7 days)
Loader_contract ERROR: 10 occurrences
Zero_data ERROR: 4 occurrences
```

### Why This Is a Problem
- **Blocking trading unnecessarily:** CRITICAL findings should be rare
- **Indicates data loading issues:** Not patrol tuning issues
- **Pattern suggests root cause:** Same tables failing repeatedly
  - buy_sell_daily stale
  - trend_template_data stale
  - technical_data_daily stale

### Root Cause (Data Loading Problem)
The stale data errors suggest:
1. **Data loaders not running successfully** 
   - May 3: "buy_sell_daily stale 9d > 7d threshold" = no new data loaded
2. **Loaders failing silently** 
   - Returning success code but not updating tables
3. **API rate limiting or timeout**
   - Loaders hitting limits during high-volume loads

### Immediate Investigation Needed

**Check loader status for past 7 days:**
```sql
SELECT table_name, frequency, latest_date, status, error_message
FROM data_loader_status
WHERE table_name IN ('buy_sell_daily', 'trend_template_data', 'technical_data_daily')
ORDER BY table_name, last_audit_at DESC
LIMIT 10;
```

**Check for loader errors in logs:**
```bash
# Check if loaders are running
grep -r "buy_sell_daily\|trend_template" ~/.local/share/algo/logs/ 2>/dev/null | tail -20

# Check for API errors
grep -i "timeout\|rate\|limit\|error" ~/.local/share/algo/logs/loader*.log 2>/dev/null | tail -20
```

**Check if loaders are even scheduled:**
```powershell
# Windows Task Scheduler
Get-ScheduledTask -TaskPath "\Algo\" | Where TaskName -like "*loader*"

# Should show daily/weekly loader schedules
```

### Fix Approach
1. **Verify loaders are running** - Check Task Scheduler
2. **Check loader logs** - See if they're completing successfully
3. **Validate API credentials** - Alpaca, yfinance, etc. still working
4. **Monitor next 3 days** - See if new data loads successfully

**Until fixed:**
- Patrol will continue showing CRITICAL staleness errors
- Orchestrator will block trading on these findings
- This is **correct behavior** (don't want to trade on stale data)

---

## 🟡 Issue #3: Weak Orchestrator Integration (Only 1 Patrol Check/Day)

### Current Behavior
```
Phase 1 patrol checks: 1 in last 24 hours
Expected: 1 per orchestrator run (ideally daily/near-daily)
```

### Why This Is a Problem
- **Orchestrator may not be running daily** - Should execute once per day (or more)
- **If orchestrator doesn't run, patrol results ignored** - Data issues go undetected
- **Patrol and trading workflow disconnected**

### Root Cause (Likely)
Orchestrator is NOT scheduled to run, or:
1. Only runs on-demand manually
2. Scheduled but failing silently
3. Scheduled but conditions prevent execution

### Investigation Needed

**Check if orchestrator is scheduled:**
```powershell
# Windows Task Scheduler
Get-ScheduledTask -TaskName "*orchestrator*"

# Should show: Daily at 8:00am ET (after patrol at 7:25am)
```

**Check orchestrator execution logs:**
```bash
# Look for Phase 1 execution records
sqlite3 algo_audit_log.db "SELECT COUNT(*) FROM algo_audit_log WHERE action_type LIKE 'phase_1_%' AND created_at > datetime('now', '-7 days')"

# Should show 1-2+ per day if running daily
```

**Check if orchestrator errors are occurring:**
```bash
grep -i "error\|exception\|fail" ~/.local/share/algo/logs/orchestrator*.log 2>/dev/null | tail -20
```

### Fix Approach
1. **Verify orchestrator is scheduled** in Windows Task Scheduler
2. **Confirm schedule:** Daily at 8:00am ET (after patrol)
3. **Check for blocking conditions:**
   - Market hours check failing
   - DB connectivity issues
   - Permission issues

---

## 📋 Operational Issues Summary

| Issue | Severity | Symptom | Root Cause | Fix Effort |
|-------|----------|---------|-----------|-----------|
| **#1: Patrol 5x/day** | Medium | 5 runs at 3pm | Task Scheduler mis-config | 30 min |
| **#2: Stale data errors** | High | 26 CRITICAL findings | Loaders not running | 1-2 hours |
| **#3: Weak orchestrator** | Medium | Only 1 patrol check/day | Orchestrator not scheduled | 30 min |

---

## 🛠️ Recommended Action Plan

### TODAY (Immediate)
1. **Fix Task Scheduler** (30 min)
   - Check patrol trigger (should be 1x daily at 7:25am)
   - Check orchestrator trigger (should be 1x daily at 8:00am)
   - Remove any duplicate/manual triggers

2. **Investigate loader failures** (1-2 hours)
   - Check data_loader_status table
   - Review loader logs for last 7 days
   - Test a single loader manually to verify API access

### THIS WEEK
3. **Verify daily execution** (ongoing)
   - Monitor patrol logs: ~/algo_logs/patrol-*.log
   - Monitor orchestrator phase 1: Check algo_audit_log daily
   - Expect: 1 patrol run/day at 7:25am, 1 orchestrator run/day at 8:00am+

4. **Fix stale data root cause**
   - Get loaders running consistently
   - Update thresholds if needed
   - Verify data freshness

---

## Files to Check

**Task Scheduler configuration:**
```
Control Panel > Administrative Tools > Task Scheduler
Look for: "AlgoPatrolMorning", "AlgoOrchestrator", etc.
```

**Logs to review:**
```
~/algo_logs/patrol-2026-05-04.log
~/algo_logs/patrol-2026-05-03.log
CloudWatch Logs (if configured)
SQL: SELECT * FROM algo_audit_log ORDER BY created_at DESC LIMIT 50
```

**Database queries to run:**
```sql
-- Loader status
SELECT * FROM data_loader_status ORDER BY last_audit_at DESC LIMIT 20;

-- Orchestrator phase 1
SELECT * FROM algo_audit_log WHERE action_type LIKE 'phase_1_%' ORDER BY created_at DESC LIMIT 20;

-- Patrol results
SELECT DATE(created_at), COUNT(*), MAX(severity) FROM data_patrol_log GROUP BY DATE(created_at) ORDER BY 1 DESC LIMIT 7;
```

---

## When These Are Fixed

✓ Patrol runs exactly once daily at 7:25am  
✓ Data loaders complete successfully  
✓ Patrol shows 0 stale data CRITICAL errors  
✓ Orchestrator runs daily at 8:00am  
✓ Phase 1 patrol integration logs appear daily

Then you're good to go!

---

**Next Step:** Check Windows Task Scheduler right now - that's the fastest fix (30 min).
