# Algo Ops Dashboard

Single-pane-of-glass terminal dashboard for morning briefing and monitoring.

## Usage

`dashboard.py` connects directly to AWS RDS via AWS Secrets Manager.

```bash
# Requires: AWS credentials (AWS_PROFILE env var)
python tools/dashboard/dashboard.py
python tools/dashboard/dashboard.py -w         # watch mode (30s refresh)
python tools/dashboard/dashboard.py --compact  # narrow positions table
```

**Data sources:** AWS RDS (direct database queries)

## Options

```bash
# Live view (q or Ctrl+C to exit)
python tools/dashboard/dashboard.py

# Watch mode with auto-refresh
python tools/dashboard/dashboard.py -w         # refresh every 30s (default)
python tools/dashboard/dashboard.py -w 60      # refresh every 60s

# Compact view (narrow positions table)
python tools/dashboard/dashboard.py --compact

# Print legend (all panel definitions)
python tools/dashboard/dashboard.py --legend
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
