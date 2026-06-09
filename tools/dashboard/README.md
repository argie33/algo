# Algo Ops Dashboard

Single-pane-of-glass terminal dashboard for morning briefing and monitoring.

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
pip install psycopg2-binary rich colorama
```

## Environment

Requires database credentials via `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`.
