# Algo Ops Dashboard

Single-pane-of-glass terminal dashboard for morning briefing and monitoring.

## Usage

### AWS Mode (Default)

Connects directly to AWS RDS via AWS Secrets Manager.

```bash
# Requires: AWS credentials (AWS_PROFILE env var)
python -m tools.dashboard.dashboard
python -m tools.dashboard.dashboard -w         # watch mode (30s refresh)
python -m tools.dashboard.dashboard --compact  # narrow positions table
```

### Local Mode

Connects to local API endpoint (localhost:3001).

```bash
# Requires: Local API service running on http://localhost:3001
python -m tools.dashboard.dashboard --local
python -m tools.dashboard.dashboard -w 60 --local
```

The data source mode (AWS or LOCAL) is displayed in the header while loading and in the top-right of the dashboard.

## Options

```bash
# Live view (q or Ctrl+C to exit)
python -m tools.dashboard.dashboard

# Watch mode with auto-refresh
python -m tools.dashboard.dashboard -w         # refresh every 30s (default)
python -m tools.dashboard.dashboard -w 60      # refresh every 60s

# Compact view (narrow positions table)
python -m tools.dashboard.dashboard --compact

# Print legend (all panel definitions)
python -m tools.dashboard.dashboard --legend
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

- `AWS_PROFILE`: AWS profile with access to Secrets Manager
- Database credentials are loaded from AWS Secrets Manager (`algo/database`)

## Data Source

`dashboard.py` queries AWS RDS directly via AWS Secrets Manager credentials.
