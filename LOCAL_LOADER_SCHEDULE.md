# Local Loader Schedule Setup ✅

**Status:** READY FOR MONDAY (2026-07-21)  
**Today:** Saturday 2026-07-19 (no loaders run on weekends)  
**Schedule:** MON-FRI 2:00 AM & 4:05 PM ET (matches AWS EventBridge)

---

## What's Set Up

Your local Windows machine now has **2 automatic scheduled tasks** that run the data loaders:

| Task | Schedule | What It Does |
|------|----------|--------------|
| **morning-pipeline** | 2:00 AM MON-FRI | Load prices, technical indicators, market status |
| **afternoon-pipeline** | 4:05 PM MON-FRI | Load quality/growth/value scores, signals, risk metrics |

This exactly mirrors your AWS production setup (EventBridge Scheduler).

---

## When They'll Run

**This Week:**
- 🚫 Sunday 7/20 — No run (weekend)
- ✅ **Monday 7/21 — 2:00 AM** ← First run (morning pipeline)
- ✅ **Monday 7/21 — 4:05 PM** ← Scores loaded (afternoon pipeline)
- ✅ **Tuesday-Friday** — Both times each day

---

## Verify The Setup

### Option 1: Open Task Scheduler (GUI)
```
Win + R  →  taskschd.msc  →  Task Scheduler Library → algo folder
```

You'll see:
- `morning-pipeline` - Status: Ready
- `afternoon-pipeline` - Status: Ready

### Option 2: Command Line
```bash
# List all algo tasks
schtasks /query /tn "algo"

# Show detailed info
schtasks /query /tn "algo" /v
```

Expected output:
```
HostName:                 YOUR_PC
TaskName:                 \algo\morning-pipeline
Next Run Time:            2026-07-21 02:00:00 AM
Status:                   Ready

HostName:                 YOUR_PC
TaskName:                 \algo\afternoon-pipeline
Next Run Time:            2026-07-21 04:05:00 PM
Status:                   Ready
```

---

## What Happens When They Run

When the task executes:
1. Runs: `python scripts/run_local_orchestrator.py --morning` (or `--afternoon`)
2. Connects to local PostgreSQL database
3. Executes 9-phase orchestrator pipeline
4. Loads fresh data into tables
5. Logs output to Windows Event Viewer (Applications & Services Logs)

---

## Logs & Troubleshooting

### View Task Execution Logs

**Windows Event Viewer:**
```
Event Viewer (eventvwr)
  → Windows Logs
    → Application
      → Look for "Python" or "python.exe" entries
```

### Manual Test (To Verify Setup)

Run the morning pipeline manually:
```bash
python scripts/run_local_orchestrator.py --morning
```

Expected output:
```
[ORCHESTRATOR] Acquiring distributed lock...
[PHASE 1] Metric loaders validation: PASS - All metric loaders ready
-> Phase 1 success: All critical tables fresh
[PHASE 2] Circuit breakers: all clear
-> Phase 2 ok
...
[PHASE 9] Reconciliation complete
```

### Check Data Freshness

After a scheduled run completes, verify data loaded:
```bash
python scripts/monitor_data_staleness.py
```

You should see:
- ✅ price_daily: today (0d)
- ✅ stock_scores: <30m
- ✅ algo_signals: <5m

---

## If You Need To Disable/Modify

### Temporarily Disable a Task
```bash
schtasks /change /tn "algo\morning-pipeline" /disable
```

### Re-enable
```bash
schtasks /change /tn "algo\morning-pipeline" /enable
```

### Delete a Task (if needed)
```bash
schtasks /delete /tn "algo\morning-pipeline" /f
```

### Recreate All Tasks
```bash
scripts\setup_windows_schedule.bat
```

---

## Automatic Runs vs Manual Runs

The setup allows both:

| Method | Command | When |
|--------|---------|------|
| **Automatic** | Task Scheduler | MON-FRI 2 AM & 4:05 PM |
| **Manual** | `python scripts/run_local_orchestrator.py --morning` | Anytime |
| **Dashboard Auto** | `python start_dashboard_dev.py` | When you start the dashboard |

You can run `--morning` manually any time (weekends, evenings, etc.) to refresh data immediately.

---

## System Status Summary

**✅ READY FOR MONDAY TRADING:**

- Database: PostgreSQL running, 8.6M+ prices loaded
- Dev Server: Available (localhost:3001)
- Orchestrator: Tested ✅ (ran successfully at 15:03)
- Scheduled Tasks: Created ✅ (morning-pipeline, afternoon-pipeline)
- Permissions: Configured ✅

**Data Freshness (Saturday evening):**
- prices: 2d old (expected, no trading weekend)
- scores: 2h old (last run at 14:00)
- signals: fresh (just computed)
- trades/positions: fresh

**Monday morning (after 2 AM run):**
- prices will refresh to today
- all technical data will update
- scores will re-compute
- dashboard will show live market data

---

## Next Steps

1. **Monday 7/21 morning:** Check that loaders ran automatically
   ```bash
   python scripts/monitor_data_staleness.py
   # Should show price_daily, technical_data_daily as today (0d)
   ```

2. **During the week:** Dashboard will have fresh data (no manual refresh needed)

3. **Anytime:** Run manual refresh with `python scripts/run_local_orchestrator.py --morning`

---

## FAQ

**Q: Will the tasks run if my computer is off?**
A: No. Windows Task Scheduler only runs when the computer is awake. If it's off at 2 AM, the task won't execute. Solution: Keep computer on, or use `Wake-on-LAN` to wake it at 2 AM.

**Q: Can I change the times?**
A: Yes:
```bash
schtasks /change /tn "algo\morning-pipeline" /st 06:00
```

**Q: What if I manually run --morning at 9 AM? Will it conflict?**
A: No. The orchestrator uses a distributed lock, so only one run executes at a time. If both trigger, one waits for the other to finish.

**Q: How do I know if the scheduled task failed?**
A: Check Windows Event Viewer (eventvwr → Application). Look for Task Scheduler errors or Python exit codes.

---

## AWS Equivalents (For Reference)

| Local Setup | AWS Equivalent |
|-------------|-----------------|
| Task Scheduler morning-pipeline | EventBridge Rule: `morning-pipeline` |
| Task Scheduler afternoon-pipeline | EventBridge Rule: `afternoon-pipeline` |
| Python orchestrator script | Lambda function: `algo-orchestrator` |
| Local PostgreSQL | RDS database (stocks) |
| Dev Server (localhost:3001) | API Gateway + Lambda |

Your local setup is functionally identical to AWS — no EventBridge Scheduler needed locally (Windows Task Scheduler replaces it).

---

**Created:** 2026-07-19 (Session 279)  
**Last Updated:** 2026-07-19 15:05 ET  
**Verified:** ✅ Orchestrator tested, tasks created, ready for Monday

