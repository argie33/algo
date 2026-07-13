# Quick Start: Running Algo System Locally

**TL;DR:**
```bash
# Terminal 1: Start API dev server
python3 lambda/api/dev_server.py

# Terminal 2: Start dashboard (watch mode, auto-refreshes every 30s)
python3 -m dashboard --local -w 30
```

Press `Ctrl+C` to stop either one.

---

## Prerequisites

- Python 3.9+
- PostgreSQL running locally (on localhost:5432)
- Default DB credentials: `stocks/stocks` (or set via environment variables)

Check: `python scripts/diagnose_system.py` (tells you if everything is set up)

---

## Running Everything

### Option 1: Two Terminals (Recommended for Development)

**Terminal 1 - Start the API dev server:**
```bash
python3 lambda/api/dev_server.py
```

You'll see:
```
[DEV_SERVER] AUTO: Setting LOCAL_MODE=true for local development
[DEV_SERVER] [OK] Using localhost postgres (LOCAL_MODE=true)
2026-07-10 20:59:04 - INFO - Starting API dev server on http://localhost:3001
```

**Terminal 2 - Start the dashboard:**
```bash
# Watch mode (auto-refresh every 30 seconds)
python3 -m dashboard --local -w 30

# OR single view (doesn't auto-refresh)
python3 -m dashboard --local
```

Dashboard keys (once it's running):
- `p` - Positions panel
- `s` - Signals panel  
- `t` - Trades panel
- `f` - Portfolio (full screen)
- `q` - Quit

---

### Option 2: One Command (Automated)

**Linux/macOS:**
```bash
bash scripts/start_dev_environment.sh
```

**Windows (PowerShell):**
```powershell
.\scripts\start_dev_environment.ps1
```

This script:
1. Checks if dev_server is already running
2. Starts dev_server if needed
3. Waits for it to be ready
4. Launches the dashboard with `--local` flag
5. Cleans up when you exit

Press `Ctrl+C` to stop everything.

---

## Dashboard Shows "Data not Available"

**Problem:** You ran `python -m dashboard` without `--local` flag.

**Solution:** Always use the `--local` flag when developing locally:
```bash
python3 -m dashboard --local
```

**Why?** Without `--local`, the dashboard tries to connect to AWS API Gateway, which requires:
- Valid `COGNITO_USER_POOL_ID` env var
- Valid `COGNITO_CLIENT_ID` env var
- Valid AWS credentials for token refresh

For local development, use `--local` to connect to `http://localhost:3001` instead.

---

## Troubleshooting

### "Connection refused" when starting dashboard

**Cause:** Dev server isn't running on port 3001.

**Fix:** Make sure you started the dev server in another terminal:
```bash
python3 lambda/api/dev_server.py
```

### Dashboard shows blank panels or errors

Run diagnostics to check data:
```bash
python scripts/diagnose_system.py
```

If diagnostics pass but dashboard shows errors:
1. Kill all python processes: `pkill -9 python`
2. Start fresh: 
   - Terminal 1: `python3 lambda/api/dev_server.py`
   - Terminal 2: `python3 -m dashboard --local`

### "PostgreSQL connection refused"

**Cause:** Database isn't running or credentials are wrong.

**Fix:**
1. Check DB is running: `psql -U stocks stocks -c "SELECT 1"`
2. Check env vars:
   ```bash
   echo $DB_USER $DB_HOST
   # Should show: stocks localhost
   ```
3. If wrong, set them:
   ```bash
   export DB_USER=stocks
   export DB_PASSWORD=stocks
   export DB_HOST=localhost
   export DB_PORT=5432
   ```

---

## API Development

The dev server exposes the same API as Lambda (on `localhost:3001`):

```bash
# Get portfolio
curl -H "Authorization: Bearer dev-admin" \
  http://localhost:3001/api/algo/portfolio | python -m json.tool

# Get positions
curl -H "Authorization: Bearer dev-admin" \
  http://localhost:3001/api/algo/positions | python -m json.tool

# Get scores
curl -H "Authorization: Bearer dev-admin" \
  http://localhost:3001/api/algo/scores?limit=5 | python -m json.tool
```

**Dev tokens available:**
- `dev-admin` - Full access
- `dev-user` - User-level access
- `dev-trader` - Trading access

---

## Next Steps

- **View code:** See `lambda/api/routes/` for API handlers
- **Run tests:** `make test`
- **Check types:** `make type-check`
- **Deploy to AWS:** Push to main, GitHub Actions handles deployment automatically

---

## Important Notes

- **Local database:** Dev server connects to your local PostgreSQL (not AWS RDS)
- **Demo data:** Uses whatever data is currently in your local `stocks` database
- **No mock data:** This is a REAL data flow - trades executed here are LIVE (if using paper mode)
- **Dev tokens:** Only work on localhost:3001; AWS Lambda uses Cognito auth

---

## For AWS/Production Deployment

See `steering/OPERATIONS.md` for:
- Setting up AWS environment
- Deploying via GitHub Actions
- Configuring Cognito authentication
- Running in production mode
