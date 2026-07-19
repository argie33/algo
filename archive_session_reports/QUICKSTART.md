# Quickstart - Get Running in 5 Minutes

## Prerequisites

- Docker + Docker Compose (for local PostgreSQL)
- Python 3.12+
- Git

## 1. Clone & Setup (2 min)

```bash
git clone <your-repo>
cd algo
cp .env.example .env
# Edit .env with your Alpaca API keys
```

## 2. Start Local Database (1 min)

```bash
docker-compose up -d postgres
# Wait for "healthy" status
docker-compose ps
```

Verify connection:
```bash
psql -h localhost -U stocks -d stocks -c "SELECT 1"
# Expected: (1 row)
```

## 3. Initialize Database Schema

```bash
# Create tables (if not already done)
python scripts/init_db.py
# Expected: [INFO] Database schema initialized
```

## 4. Run Local Orchestrator (5 min)

```bash
# Run full pipeline (data load + algo)
python scripts/run_local_orchestrator.py --run-all

# Expected output:
# [INFO] Loading prices...
# [INFO] Loading technical indicators...
# [INFO] Running algo...
# [SUCCESS] All pipelines completed
```

Verify data loaded:
```bash
psql -h localhost -U stocks -d stocks << 'SQL'
SELECT COUNT(*) as prices_count FROM prices;
SELECT COUNT(*) as portfolios_count FROM portfolios;
SQL
```

## 5. Start Dashboard (1 min)

```bash
python dashboard.py
# Opens browser to http://localhost:5173
```

Verify:
- ✅ Dashboard loads without errors
- ✅ Prices panel shows latest data
- ✅ Portfolio positions visible
- ✅ Algo signals displayed

## You're Done!

Your local system is running. Next steps:

### Option A: Deploy to AWS
```bash
# See DEPLOYMENT_GUIDE.md
cd terraform
terraform apply -var-file=terraform.tfvars
```

### Option B: Automate Local Runs (Cron)
```bash
# See CRON_SETUP.md
crontab -e
# Add: 0 9 * * MON-FRI /usr/bin/python3 /path/to/scripts/run_local_orchestrator.py --morning
```

---

## Troubleshooting

### "psql: could not connect to server"
```bash
docker-compose ps
# If postgres not running:
docker-compose up -d postgres
# Wait 10 seconds for health check
```

### "ModuleNotFoundError: No module named 'psycopg2'"
```bash
pip install -r requirements.txt
```

### "Dashboard shows 'Data not available'"
```bash
# 1. Check database has data
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM prices"
# Should be > 0

# 2. Restart dashboard
python dashboard.py
```

### "Algo error: Connection pool exhausted"
```bash
# Too many concurrent connections
# For local: single instance is fine, but check for hung connections
psql -h localhost -U stocks -d stocks -c \
  "SELECT usename, application_name, state FROM pg_stat_activity"
```

---

## Next: Automation

Once local setup works, automate 2x daily runs:

```bash
# See CRON_SETUP.md for detailed instructions
# Quick: Add to crontab
0 9 * * MON-FRI python /path/to/scripts/run_local_orchestrator.py --morning
0 16 * * MON-FRI python /path/to/scripts/run_local_orchestrator.py --evening
```

---

## Environment Variables

All configurable via `.env`:

| Variable | Default | Purpose |
|----------|---------|---------|
| DB_HOST | localhost | PostgreSQL host |
| DB_PORT | 5432 | PostgreSQL port |
| DB_NAME | stocks | Database name |
| DB_USER | stocks | DB username |
| DB_PASSWORD | stocks_dev_password | DB password |
| ALPACA_API_KEY_ID | (required) | Alpaca paper trading key |
| ALPACA_API_SECRET_KEY | (required) | Alpaca paper trading secret |
| ALPACA_PAPER_TRADING | true | Use paper trading (not real $) |
| AWS_REGION | us-east-1 | AWS region for cloud deployment |

---

## Architecture

```
Your Machine
├── PostgreSQL (docker-compose)
├── Python orchestrator (2x daily via cron)
│   ├── Load prices
│   ├── Calculate indicators
│   └── Run algo
├── Python dashboard (on-demand)
│   └── Display results from DB
└── (Future: AWS RDS instead of local PostgreSQL)

AWS (when deployed)
├── RDS PostgreSQL
└── Lambda API (if needed for remote access)
```

---

For production deployment, see `DEPLOYMENT_GUIDE.md`.
For operations runbook, see `RUNBOOK.md`.
