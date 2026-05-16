# Local Setup Guide (Windows PostgreSQL)

**This is the ONLY guide you need. Ignore Docker/WSL references elsewhere.**

## Prerequisites
- Python 3.9+
- PostgreSQL 14+ running on Windows

## Setup (3 Steps - 30 minutes)

### 1. Verify PostgreSQL is working
```bash
# Test connection
psql -h localhost -U postgres -d postgres -c "SELECT version();"

# If that fails:
# - Install PostgreSQL: https://www.postgresql.org/download/windows/
# - Use the default user `postgres`
# - Remember the password you set
```

### 2. Create .env.local (if not already set)
```bash
# Copy from template
cp .env.example .env.local

# Edit .env.local with your PostgreSQL password:
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=<your_postgres_password>
DB_NAME=stocks
```

### 3. Initialize database + load data
```bash
# Create schema (132 tables)
python3 init_database.py

# Load all data (5 tiers, ~20 minutes)
python3 run-all-loaders.py
```

## Verify Everything Works
```bash
# Check data was loaded
python3 -c "
import psycopg2, os
from dotenv import load_dotenv

load_dotenv('.env.local')
conn = psycopg2.connect(
    host=os.getenv('DB_HOST'), port=int(os.getenv('DB_PORT')),
    user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM stock_symbols')
print(f'Symbols loaded: {cur.fetchone()[0]}')
cur.execute('SELECT COUNT(*) FROM price_daily')
print(f'Price records: {cur.fetchone()[0]}')
conn.close()
"

# Run orchestrator test
python3 algo_orchestrator.py --mode paper --dry-run
```

## Troubleshooting

**"password authentication failed"**
- Fix: Update DB_PASSWORD in .env.local with your actual PostgreSQL password

**"stocks database does not exist"**
- Run: `python3 init_database.py` again

**"FATAL: remaining connection slots are reserved"**
- PostgreSQL is out of connections
- Fix: Close other Python scripts, restart PostgreSQL

**Loaders timing out**
- Reduce parallelism: Edit `run-all-loaders.py`, change `max_workers=4` to `max_workers=2`

## Next Steps
1. Load data: `python3 run-all-loaders.py`
2. Test orchestrator: `python3 algo_orchestrator.py --mode paper --dry-run`
3. For AWS: Push to main, watch GitHub Actions deploy

## Questions?
- Check STATUS.md for current issues
- Check CLAUDE.md for architecture overview
- Check troubleshooting-guide.md for detailed issues
