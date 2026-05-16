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

### 3. Initialize database
```bash
# On Windows, set UTF-8 encoding to avoid character issues
set PYTHONIOENCODING=utf-8

# Create schema (116+ tables, takes ~1 minute)
python3 init_database.py
```

### 4. Load data
```bash
# Load all data through 5-tier dependency pipeline (~20 minutes)
python3 run-all-loaders.py
```

### 5. Verify everything works
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

**"character encoding" or "UnicodeEncodeError"**
- Windows encoding issue with init_database.py
- Fix: Set UTF-8 before running: `set PYTHONIOENCODING=utf-8` then `python3 init_database.py`

**"stocks database does not exist"**
- Run: `python3 init_database.py` again (with UTF-8 encoding set)

**"FATAL: remaining connection slots are reserved"**
- PostgreSQL is out of connections
- Fix: Close other Python scripts, restart PostgreSQL

**Loaders timing out**
- Reduce parallelism: Edit `run-all-loaders.py`, change `max_workers=4` to `max_workers=2`

## Next Steps (After Setup Complete)
1. ✅ Schema initialized
2. ✅ Data loaded via loaders
3. Test orchestrator: `python3 algo_orchestrator.py --mode paper --dry-run`
4. Check data quality: Verify record counts match expectations
5. For AWS deployment: Push to main branch, watch GitHub Actions at https://github.com/argie33/algo/actions

## Questions?
- Check STATUS.md for current issues
- Check CLAUDE.md for architecture overview
- Check troubleshooting-guide.md for detailed issues
