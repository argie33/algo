# Windows EOD Loader Scheduler Setup

## Overview

This document describes how to set up automatic daily EOD (End-of-Day) loader runs on Windows using Task Scheduler.

**Target:** Daily loader execution at 5:30 PM ET (market close + 30 min for data availability)

---

## Prerequisites

1. **Git for Windows** installed (provides bash.exe)
   - Download from https://git-scm.com/download/win
   - Default install location: `C:\Program Files\Git\bin\bash.exe`
   - If installed elsewhere, edit `scripts/eod_loader_wrapper.bat` line 20

2. **PostgreSQL database access**
   - `.env.local` file with `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
   - Database must be accessible from this machine at scheduled time

3. **Python 3.9+** with all loader dependencies
   - All loaders must work locally first
   - Test with: `bash run_eod_loaders.sh` manually

4. **Admin rights** to register Task Scheduler job

---

## Installation (One-Time Setup)

### Step 1: Prepare batch scripts

Scripts already created:
- `scripts/schedule_eod_daily.bat` — Registers the scheduled task
- `scripts/eod_loader_wrapper.bat` — Wrapper that runs the actual pipeline
- `scripts/eod_manual_trigger.bat` — Manual trigger for testing

### Step 2: Create log directory

```cmd
mkdir C:\algo-logs
```

### Step 3: Register the scheduled task

**As Administrator**, run:

```cmd
cd C:\Users\arger\code\algo
scripts\schedule_eod_daily.bat
```

This will:
- Create a Windows Task Scheduler job named `algo-eod-daily`
- Set it to run daily at 5:30 PM (17:30)
- Execute `scripts/eod_loader_wrapper.bat`

You should see:
```
SUCCESS: Task scheduled.

Next steps:
  1. Verify in Task Scheduler (taskschd.msc)
  ...
```

### Step 4: Verify in Task Scheduler

Open Task Scheduler:
```cmd
taskschd.msc
```

Look for:
- **Task name:** `algo-eod-daily`
- **Schedule:** Daily, 5:30 PM
- **Action:** `C:\Users\arger\code\algo\scripts\eod_loader_wrapper.bat`
- **Status:** Enabled (green checkmark)

If not enabled, right-click → Enable.

---

## Testing

### Manual test (see output live):

```cmd
scripts\eod_manual_trigger.bat
```

This runs the full `run_eod_loaders.sh` pipeline with output visible. Useful for:
- First-time verification
- Debugging loader issues
- On-demand EOD runs (holidays, retries)

Expected output:
```
[2026-05-04 17:35:22] === EOD LOADER PIPELINE STARTED ===
[2026-05-04 17:35:22] 1. Pre-load patrol...
[2026-05-04 17:35:45] 2. Loading EOD data...
[2026-05-04 17:35:45]   1/6 load_eod_bulk.py (price_daily)
...
[2026-05-04 17:43:00] === EOD PIPELINE COMPLETE ===
```

### Scheduled task test (verify logs):

```cmd
REM Manually trigger the scheduled task
schtasks /run /tn "algo-eod-daily"

REM Check the log (most recent)
dir C:\algo-logs
type C:\algo-logs\eod-2026-05-04_17-30-45.log
```

Expected log location: `C:\algo-logs\eod-YYYY-MM-DD_HH-MM-SS.log`

---

## Log Monitoring

Logs are stored in: `C:\algo-logs\eod-*.log`

Each scheduled run creates a new log file with timestamp.

### View latest log:

```cmd
REM Windows
type C:\algo-logs\eod*.log | tail -50

REM Or open in PowerShell
Get-ChildItem C:\algo-logs -Filter "eod*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content
```

### Typical log structure:

```
[2026-05-04 17:30:00] === EOD LOADER PIPELINE STARTED ===
[2026-05-04 17:30:01] 1. Pre-load patrol...
[2026-05-04 17:30:30] PRE-LOAD PATROL OK
[2026-05-04 17:30:30] 2. Loading EOD data...
[2026-05-04 17:30:30]   1/6 load_eod_bulk.py (price_daily)
[2026-05-04 17:35:00]   2/6 loadtechnicalsdaily.py
...
[2026-05-04 17:42:30] === EOD PIPELINE COMPLETE ===
```

### Check for errors:

```cmd
REM Show last 30 lines
powershell -Command "Get-Content (Get-ChildItem C:\algo-logs -Filter 'eod*.log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName -Tail 30"

REM Search for ERROR/FAIL/WARN
findstr /r "ERROR FAIL WARN CRITICAL" C:\algo-logs\eod*.log | tail -20
```

---

## Troubleshooting

### Task doesn't run at scheduled time

**Check:**
1. Task Scheduler: right-click `algo-eod-daily` → Properties → General
   - Enabled? (should be checked)
   - Run with highest privileges? (might be needed)
   - Run only if user is logged in? (uncheck if needed for headless runs)

2. Task Scheduler History tab
   - Look for "Last Run Time" and "Result"
   - If Result = `0`, task succeeded
   - If Result ≠ `0`, double-click for error details

3. Log file created?
   - `ls C:\algo-logs` should show recent eod-*.log
   - If no log, task never ran

**Fix:**
```cmd
REM Re-register (deletes old, creates new)
schtasks /delete /tn "algo-eod-daily" /f
scripts\schedule_eod_daily.bat
```

### Log file shows errors

**Common issues:**

1. **"Git Bash not found"**
   - Install Git for Windows
   - Or edit `eod_loader_wrapper.bat` to point to correct bash path

2. **"psql: could not translate host name"**
   - `.env.local` has wrong `DB_HOST`
   - Test: `psql -h <DB_HOST> -U stocks -d stocks -c "SELECT 1"`

3. **"Module not found: optimal_loader"**
   - Missing Python dependencies
   - Run locally first: `python3 run_eod_loaders.sh`

4. **"Permission denied"**
   - Run as Administrator: `Run as administrator` in Task Scheduler

### Test database connection

```cmd
REM From algo directory
python3 -c "import psycopg2; import os; conn = psycopg2.connect(host=os.getenv('DB_HOST','localhost'), user='stocks', password=os.getenv('DB_PASSWORD',''), database='stocks'); print('OK')"
```

---

## Updating Schedule

### Change time (e.g., 6:00 PM instead of 5:30 PM):

```cmd
schtasks /change /tn "algo-eod-daily" /st 18:00
```

### Change frequency (e.g., twice daily):

```cmd
REM Delete and re-create with different schedule
schtasks /delete /tn "algo-eod-daily" /f
schtasks /create /tn "algo-eod-daily" ^
    /tr "C:\Users\arger\code\algo\scripts\eod_loader_wrapper.bat" ^
    /sc daily /mo 2 /st 10:00
```

### Disable temporarily:

```cmd
schtasks /change /tn "algo-eod-daily" /disable
schtasks /change /tn "algo-eod-daily" /enable
```

---

## Cleanup (Remove scheduled task)

```cmd
schtasks /delete /tn "algo-eod-daily" /f
```

---

## Next Steps

1. ✓ Scripts created (`eod_loader_wrapper.bat`, etc.)
2. ✓ Documentation complete (this file)
3. **→ Run setup:** `scripts\schedule_eod_daily.bat` (as Admin)
4. **→ Test:** `scripts\eod_manual_trigger.bat`
5. **→ Verify:** Check `C:\algo-logs` for logs
6. **→ Monitor:** Watch logs at 5:30 PM for first scheduled run

---

## Related Files

- `run_eod_loaders.sh` — The actual loader pipeline
- `.env.local` — Database configuration (must be present)
- `LOADER_SCHEDULE.md` — Details on which loaders run when
- `PENDING_OPTIMIZATIONS.md` — Why this is important (QW3 item)
