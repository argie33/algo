# Local Development Credential Setup

This guide explains how to set up credentials for running the system locally (loaders, orchestrator, tests).

## Prerequisites

- PostgreSQL running on `localhost:5432`
- Alpaca API account (for live trading features)
- AWS account with Secrets Manager access (optional)

## Option 1: Environment Variables (Simplest)

Set these in your terminal **before** running code:

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=stocks
export DB_NAME=stocks
export DB_PASSWORD=your_postgres_password

# Optional - for paper trading
export ALPACA_API_KEY=your_alpaca_key
export ALPACA_API_SECRET=your_alpaca_secret
export ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

Then run:
```bash
python3 init_database.py
python3 run-all-loaders.py
python3 algo/algo_orchestrator.py --mode paper --dry-run
```

## Option 2: AWS Secrets Manager (Recommended for Teams)

### 1. Store credentials in AWS

```bash
aws secretsmanager create-secret \
  --name algo/db/postgres \
  --secret-string '{"host":"localhost","port":5432,"user":"stocks","password":"your_password","database":"stocks"}'
```

### 2. Configure AWS on your machine

```bash
aws configure
# Enter Access Key ID, Secret Access Key, region
```

### 3. Run code

System automatically fetches from Secrets Manager:

```bash
python3 run-all-loaders.py
```

## Testing Credentials

```bash
# Test DB connection
python3 -c "from utils.db_connection import get_db_connection; get_db_connection(); print('OK')"

# Test one loader
python3 loaders/loadstocksymbols.py
```

## Troubleshooting

**"Database password not available":**
- Set `DB_PASSWORD` environment variable
- Or configure AWS Secrets Manager + `aws configure`

**"Connection refused":**
- Check PostgreSQL is running
- Verify DB_HOST, DB_PORT, DB_USER

See `troubleshooting-guide.md` for more help.
