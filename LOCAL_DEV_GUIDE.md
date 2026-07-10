# Local Development Guide

## Quick Start (Recommended)

### Windows PowerShell
```powershell
.\start_local_dev.ps1
```

### macOS / Linux
```bash
./start_local_dev.sh
```

This script will:
1. Start the API dev_server on http://localhost:3001
2. Wait for the server to be ready
3. Launch the dashboard in local mode (TUI) with auto-refresh

**Press `q` to quit the dashboard** - the dev_server will be automatically cleaned up.

---

## Manual Setup (If You Prefer)

### Terminal 1: Start dev_server
```bash
python api-pkg/dev_server.py
# or
python lambda/api/dev_server.py
```

Expected output:
```
[DEV_SERVER] AUTO: Setting LOCAL_MODE=true for local development
[DEV_SERVER] Using localhost postgres (LOCAL_MODE=true)
2026-07-10 16:09:35,877 - INFO - Starting API dev server on http://localhost:3001
```

### Terminal 2: Start dashboard
```bash
python -m dashboard --local
```

**IMPORTANT:** The `--local` flag is required when running locally. Without it, the dashboard tries to connect to AWS API Gateway and will fail with authentication errors.

---

## Available Dashboard Commands

**While dashboard is running:**
- `p` - Portfolio panel
- `pos` - Positions panel
- `s` - Signals panel
- `h` - Health status
- `r` - Sector ranking
- `t` - Trades
- `e` - Economic data
- `d` - Data quality issues
- `q` - Quit

---

## Troubleshooting

### "Data Unavailable" Messages

**Cause:** Using wrong API endpoint or missing --local flag  
**Solution:** Make sure you're running with the `--local` flag

```bash
# WRONG - will try to hit AWS API and fail auth
python -m dashboard

# CORRECT - will use localhost:3001
python -m dashboard --local
```

### "Connection refused" on localhost:3001

**Cause:** dev_server not running or not ready  
**Solution:** Start dev_server in another terminal

```bash
python api-pkg/dev_server.py
# Wait for: "Starting API dev server on http://localhost:3001"
```

### Database Connection Errors

**Cause:** PostgreSQL not running on localhost:5432  
**Solution:** Start PostgreSQL

```bash
# macOS
brew services start postgresql

# Ubuntu/Debian
sudo systemctl start postgresql

# Docker
docker run -d \
  -e POSTGRES_USER=stocks \
  -e POSTGRES_PASSWORD=stocks \
  -e POSTGRES_DB=stocks \
  -p 5432:5432 \
  postgres:15
```

### API Returns "Stale" Data

**Expected:** Initial runs return data from database (no fresh snapshots yet)  
**This is normal** - the orchestrator isn't running in dev mode, so portfolio snapshots come from existing data  
**No action needed** - system will function correctly; dashboard shows best available data

---

## Architecture

```
User → Dashboard TUI (python -m dashboard --local)
        ↓
    API Layer (api-pkg/dev_server.py on localhost:3001)
        ↓
    PostgreSQL (localhost:5432)
```

The dev_server mimics the AWS Lambda API but runs locally, connecting to your local PostgreSQL database.

---

## Environment Variables

Set these if you need to customize:

```bash
# API server
export API_PORT=3001  # Default: 3001

# Database (dev_server auto-detects from env)
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_PASSWORD=stocks
export DB_NAME=stocks

# Dashboard
export DASHBOARD_API_URL=http://localhost:3001  # Auto-set when using --local flag
export LOCAL_MODE=true  # Auto-set when using --local flag
```

---

## Stopping Services

When using helper scripts:
- **Dashboard**: Press `q` (dev_server auto-stops)
- **Manual mode**: 
  - `Ctrl+C` on dev_server
  - `Ctrl+C` on dashboard

---

## Next Steps

Once local development is working:

1. **For AWS Deployment**: See CLAUDE.md "Instant Fixes" section for `terraform apply` command
2. **For Live Trading**: See steering/OPERATIONS.md for orchestrator scheduling
3. **For Data Loading**: Run orchestrator manually with `python3 scripts/trigger_orchestrator.py`

