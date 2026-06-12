# Algo Ops Dashboard

Single-pane-of-glass terminal dashboard for morning briefing and monitoring.

## Two Versions

### Production: `dashboard.py` (AWS RDS Direct)

Connects directly to AWS RDS via AWS Secrets Manager. Use this for production deployments.

```bash
# Requires: AWS credentials (AWS_PROFILE env var)
python tools/dashboard/dashboard.py
python tools/dashboard/dashboard.py -w         # watch mode (30s refresh)
python tools/dashboard/dashboard.py --compact  # narrow positions table
```

**Data sources:** AWS RDS (direct database queries — no API calls)

### Development: `dashboard-dev.py` (Local API)

Connects to localhost API (port 3001) for rapid iteration and testing.

```bash
# Requires: Local API running at http://localhost:3001
python tools/dashboard/dashboard-dev.py
python tools/dashboard/dashboard-dev.py -w    # watch mode
```

**Data sources:** HTTP API at `http://localhost:3001`

## Usage

```bash
# Live view (q or Ctrl+C to exit)
python tools/dashboard/dashboard.py

# Watch mode with auto-refresh
python tools/dashboard/dashboard.py -w         # refresh every 30s (default)
python tools/dashboard/dashboard.py -w 60      # refresh every 60s

# Compact view (narrow positions table)
python tools/dashboard/dashboard.py --compact
```

## Features

- Real-time database connection count and RDS pool health
- Active portfolio positions with P&L
- Trade history summary
- Morning prep data freshness status
- Circuit breaker health
- Orchestrator execution history
- Sector rotation data

## Dependencies

```bash
pip install psycopg2-binary rich boto3
```

## Environment

### For Production (dashboard.py)
- `AWS_PROFILE`: AWS profile with access to Secrets Manager
- Database credentials are loaded from AWS Secrets Manager (`algo/database`)

### For Development (dashboard-dev.py)
- `DASHBOARD_API_URL`: API base URL (default: `http://localhost:3001`)
- Requires local API service running on port 3001

## Architecture

| File | Data Source | Use Case |
|------|-------------|----------|
| `dashboard.py` | AWS RDS (direct) | Production - AWS credentials required |
| `dashboard-dev.py` | Local API (localhost:3001) | Development - rapid iteration |

Both files share the same dashboard UI and display logic. The only difference is how they fetch data.
