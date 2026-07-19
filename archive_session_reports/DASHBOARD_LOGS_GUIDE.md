# Dashboard Logs Guide

The dashboard writes detailed logs to `~/.algo/logs/dashboard.log` at DEBUG level. These logs are NOT shown in the terminal to keep the UI clean, but they contain important diagnostic information about what's happening behind the scenes.

## Quick Start

### View logs in real-time while dashboard runs:
```bash
# Terminal 1: Start dashboard as normal
python dashboard.py --local -w 30

# Terminal 2: Watch the logs
python watch_dashboard_logs.py

# Or filter by level:
python watch_dashboard_logs.py --grep ERROR
python watch_dashboard_logs.py --grep WARNING
```

### Or just tail the raw log file:
```bash
# Linux/Mac
tail -f ~/.algo/logs/dashboard.log

# PowerShell (Windows)
Get-Content ~/.algo/logs/dashboard.log -Wait

# CMD (Windows)
type %USERPROFILE%\.algo\logs\dashboard.log
```

## Log File Location

- **File:** `~/.algo/logs/dashboard.log`
- **Rotation:** 10MB max per file, keeps 3 backups (dashboard.log, dashboard.log.1, dashboard.log.2, etc.)
- **Format:** `TIMESTAMP - MODULE - LEVEL - MESSAGE`

## Common Log Messages & What They Mean

### 🔴 ERROR Level (Critical Issues)

| Log Message | Meaning | What To Do |
|---|---|---|
| `[BOOTSTRAP] Database bootstrap failed: ...` | Cannot connect to database | Check `DB_HOST`, `DB_PASSWORD` environment variables |
| `safe_get: Data contains error marker: ...` | API returned error response | Check dashboard dev_server or AWS Lambda connectivity |
| `safe_list: Cannot extract list from ...` | API response format unexpected | Indicates API change or data corruption |
| `error_summary_panel: _error marker in X but no message extracted` | Malformed error response | Indicates data structure bug in API |
| `Pipeline fetch timed out after 20 seconds` | Dashboard data load took too long | Dev server or AWS Lambda is slow/overloaded |

### 🟡 WARNING Level (Degraded Operation)

| Log Message | Meaning | What To Do |
|---|---|---|
| `[DATA_UNAVAILABLE] Data is not a dict ...` | Unexpected data type from API | Normal fallback, dashboard shows "Data not available" |
| `[ERROR_BOUNDARY] error_summary_panel: no errors found` | Data loaded but may be incomplete | Check optional endpoints (optional errors don't block dashboard) |
| `compute_sector_agg: skipping position X (missing sector enrichment)` | Position data missing sector field | Sector panel may show incomplete data, but safe to continue |
| `Invalid view_mode '...', falling back to 'normal'` | User requested invalid dashboard view mode | Harmless, dashboard switches to normal view |

### 🟢 INFO Level (Operational Status)

| Log Message | Meaning | What To Do |
|---|---|---|
| `[DASHBOARD_STARTUP] LOCAL MODE DETECTED/ENABLED` | Dashboard auto-detected dev_server on localhost:3001 | Expected for local development |
| `[BOOTSTRAP] Database bootstrap complete. Connected to ...` | Successfully connected to database | Dashboard is ready |
| `Panel registry initialization completed` | All dashboard panels loaded successfully | Expected on startup |

### 🔵 DEBUG Level (Detailed Tracing)

| Log Message | Meaning | What To Do |
|---|---|---|
| `[BOOTSTRAP] Environment: AWS` or `Local` | Running mode detected | Indicates whether using AWS Lambda or local dev_server |
| `[BOOTSTRAP] Using DB_SECRET_ARN: ...` or `DB_SECRET_NAME: ...` | Database credentials source | Shows how credentials were loaded |
| `Found existing environment variables: DB_HOST=...` | Database already initialized | Expected, credentials set in environment |

## Troubleshooting Examples

### "Data not available" on all panels

Check logs for:
```bash
python watch_dashboard_logs.py --grep ERROR
```

Look for patterns like:
- `Pipeline fetch timed out` → dev_server/API too slow
- `Database bootstrap failed` → DB connection issue
- `safe_get: Data contains error` → API returning errors

### Dashboard shows [STALE Xh old] tags

Check logs for:
```bash
python watch_dashboard_logs.py --grep "STALE\|staleness"
```

This indicates circuit breaker detected old data — check if orchestrator is running.

### Flickering/flashing errors that disappear

The logs capture ALL of these. Run:
```bash
python watch_dashboard_logs.py
```

While dashboard is running and watch — you'll see transient errors that were too fast to read in the UI.

## Log Rotation

The dashboard uses rotating file handler (10MB max). When dashboard.log hits 10MB:
1. Current file → dashboard.log.1
2. .1 → .2
3. .2 → .3 (deleted if exists)

Old logs are preserved up to 3 backup files.

## Searching Logs

### Find all errors in current session:
```bash
grep ERROR ~/.algo/logs/dashboard.log | tail -20
```

### Find errors in last backup:
```bash
grep ERROR ~/.algo/logs/dashboard.log.1 | tail -20
```

### Count error types:
```bash
grep ERROR ~/.algo/logs/dashboard.log | cut -d' ' -f4- | sort | uniq -c | sort -rn
```

### Timeline of what happened:
```bash
# Show last 100 lines with timestamps
tail -100 ~/.algo/logs/dashboard.log
```

## What NOT to See

✅ Safe to ignore:
- `DEBUG` level messages (just tracing)
- `[DATA_UNAVAILABLE]` without `ERROR` (fallback behavior)
- Circuit breaker messages about STALE data (expected when orchestrator doesn't run)

❌ Problematic (take action):
- Any `ERROR` level message (something is broken)
- Multiple `Pipeline fetch timed out` in a row (API is stuck)
- Database connection errors when dashboard starts
