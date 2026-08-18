# Algo Ops Dashboard

Single-pane-of-glass terminal dashboard for morning briefing and monitoring.

## Usage

### AWS Mode (Default)

Connects directly to AWS RDS via AWS Secrets Manager.

```bash
# Requires: AWS credentials (AWS_PROFILE env var)
python -m dashboard
python -m dashboard -w         # watch mode (30s refresh)
python -m dashboard --compact  # narrow positions table
```

### Local Mode

Connects to the local dev API server (`lambda/api/dev_server.py`) on localhost:3001.

```bash
# Requires: python lambda/api/dev_server.py running in another terminal
python -m dashboard --local
python -m dashboard -w 60 --local
```

The data source mode (AWS or LOCAL) is displayed in the header while loading and in the top-right of the dashboard.

## Options

```bash
# Live view (q or Ctrl+C to exit)
python -m dashboard

# Watch mode with auto-refresh
python -m dashboard -w         # refresh every 30s (default)
python -m dashboard -w 60      # refresh every 60s (min 10s, max 600s)

# Compact view (narrow positions table)
python -m dashboard --compact

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

- **AWS mode (default):** queries AWS RDS directly via AWS Secrets Manager credentials.
- **Local mode (`--local`):** queries the local dev API server (`lambda/api/dev_server.py`,
  port 3001) instead - no AWS credentials required, but the dev server must be running first.
