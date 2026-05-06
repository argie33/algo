# Local Development Setup — The RIGHT Way

**Last Updated**: 2026-05-06  
**Status**: Complete IaC-based setup for local development

---

## Overview

This guide sets up a local development environment that **mirrors your AWS CloudFormation infrastructure exactly**. The goal is consistent behavior between local and AWS deployments.

### Key Principles

1. **IaC Everything**: Infrastructure defined in code (docker-compose, env files, scripts)
2. **Environment Parity**: Local database matches AWS RDS configuration
3. **No Hardcoded Secrets**: All credentials in .env.local (which is .gitignored)
4. **Idempotent Setup**: Can run setup multiple times safely
5. **Single Source of Truth**: Same init_database.py schema runs everywhere

---

## Prerequisites

### Required Tools
- **Docker** and **Docker Compose** (to run PostgreSQL locally)
  - macOS/Linux: Install Docker Desktop
  - Windows: Install Docker Desktop with WSL2
  
- **Python 3.9+** (for orchestrator and database initialization)

- **Git** (version control)

### Optional Tools
- **pgAdmin** (web-based database browser, included in docker-compose)
- **psql** (PostgreSQL client, for direct database access)

---

## Step 1: Environment Configuration

### Copy Template to Local File
```bash
cp .env.local.example .env.local
```

### Edit .env.local
Set these values in your `.env.local`:

**For Local PostgreSQL (Development)**:
```env
DB_HOST=postgres                          # Docker service name
DB_PORT=5432
DB_NAME=stocks                             # Matches CloudFormation DBName
DB_USER=stocks                             # Matches CloudFormation MasterUsername
DB_PASSWORD=your-secure-local-password     # Your choice
DB_SSL=false                               # Local doesn't need SSL

ALPACA_API_KEY_ID=YOUR_PAPER_KEY
APCA_API_SECRET_KEY=YOUR_PAPER_SECRET
```

**For AWS RDS (if using RDS from local)**:
```env
DB_HOST=your-rds-endpoint.us-east-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=stocks                             # Same as CloudFormation
DB_USER=stocks                             # Same as CloudFormation
DB_PASSWORD=your-rds-master-password       # From CloudFormation deployment
DB_SSL=true                                # Required for internet access
```

**Trading Configuration**:
```env
EXECUTION_MODE=paper                       # NEVER use 'live' in development
ORCHESTRATOR_DRY_RUN=true                 # Run in dry-run mode initially
DATA_PATROL_ENABLED=true
```

---

## Step 2: Start Local PostgreSQL Database

### Start Docker Compose
```bash
docker-compose -f docker-compose.local.yml up -d
```

This starts:
- **PostgreSQL 15** (matches RDS version in CloudFormation)
- **pgAdmin** (optional, access at http://localhost:5050)

### Verify PostgreSQL is Ready
```bash
docker-compose -f docker-compose.local.yml logs postgres
```

Wait for: `"database system is ready to accept connections"`

### Check Connection Health
```bash
docker-compose -f docker-compose.local.yml exec postgres pg_isready -U stocks
```

Expected output: `accepting connections`

---

## Step 3: Initialize Database Schema

### Run init_database.py
```bash
python init_database.py
```

This:
1. Connects using .env.local credentials
2. Creates all algo tables (algo_tca, algo_performance_daily, etc.)
3. Creates indexes on critical columns
4. Initializes sequences for auto-incrementing IDs
5. Is idempotent — safe to run multiple times

### Verify Schema Creation
```bash
psql -h localhost -U stocks -d stocks -c "\dt algo_*"
```

Expected output: List of all algo_* tables with their rows count

---

## Step 4: Load Historical Data (Optional but Recommended)

For live performance metrics to work, you need historical price data:

```bash
# This assumes you have a data loader for historical data
python load_historical_prices.py --years 3 --symbols "SPY,QQQ,IWM"
```

Or use your existing data loaders from ECS to populate the database.

---

## Step 5: Verify End-to-End Setup

### Test Database Connection
```bash
python -c "
import psycopg2
from dotenv import load_dotenv
import os
from pathlib import Path

env_file = Path('.env.local')
load_dotenv(env_file)

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=int(os.getenv('DB_PORT', 5432)),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
print('✓ Database connection successful')
conn.close()
"
```

### Test All Module Imports
```bash
python -c "
modules = [
    'algo_tca', 'algo_performance', 'algo_pretrade_checks',
    'algo_market_events', 'algo_wfo', 'algo_var', 'algo_governance'
]
for mod in modules:
    __import__(mod)
    print(f'✓ {mod}')
"
```

### Run Orchestrator in Dry-Run Mode
```bash
python algo_orchestrator.py --dry-run
```

Expected behavior:
- Runs all 7 phases
- Does NOT create real orders
- Prints phase execution summaries
- Exits cleanly with no errors

---

## Step 6: Accessing the Database

### Via psql (Command Line)
```bash
psql -h localhost -U stocks -d stocks
```

Then run SQL queries:
```sql
SELECT COUNT(*) FROM algo_positions;
SELECT COUNT(*) FROM algo_trades;
SELECT * FROM algo_tca LIMIT 5;
```

### Via pgAdmin (Web UI)
1. Open http://localhost:5050
2. Login: admin@stocks.local / admin
3. Add server: host=postgres, user=stocks, password=<your_password>
4. Browse tables in Web UI

---

## Development Workflow

### Daily Development
```bash
# 1. Start services
docker-compose -f docker-compose.local.yml up -d

# 2. Make code changes
# (edit algo files, test, commit)

# 3. Test changes
python -m pytest tests/

# 4. Run orchestrator in dry-run
python algo_orchestrator.py --dry-run

# 5. Commit and push
git add .
git commit -m "description"
git push origin main
```

### Testing Specific Components
```bash
# Test position sizer
python -c "
from algo_position_sizer import PositionSizer
from algo_config import AlgoConfig
config = AlgoConfig()
sizer = PositionSizer(config)
result = sizer.calculate_position_size('AAPL', 150, 147, 100000)
print(result)
"

# Test pre-trade checks
python -c "
from algo_pretrade_checks import PreTradeChecks
checks = PreTradeChecks({}, '', '', '')
passed, reason = checks.check_fat_finger(150, 148, 5.0)
print(f'Fat finger check: {passed} ({reason})')
"
```

### Stopping Services
```bash
# Stop but keep data
docker-compose -f docker-compose.local.yml down

# Stop and delete all data (fresh start)
docker-compose -f docker-compose.local.yml down -v
```

---

## Troubleshooting

### PostgreSQL Won't Start
```bash
# Check logs
docker-compose -f docker-compose.local.yml logs postgres

# Potential issues:
# 1. Port 5432 in use: change docker-compose.local.yml port mapping
# 2. Data corruption: run `down -v` and restart
# 3. Docker not running: start Docker Desktop
```

### Can't Connect to Database
```bash
# Test connectivity
docker-compose -f docker-compose.local.yml exec postgres pg_isready

# Check credentials in .env.local match docker-compose
grep DB_ .env.local

# Verify database exists
docker-compose -f docker-compose.local.yml exec postgres psql -U stocks -l
```

### Module Import Errors
```bash
# Reinstall dependencies
pip install -r requirements.txt

# Check Python version
python --version  # Should be 3.9+

# Check imports one by one
python -c "import psycopg2; import dotenv; import alpaca_trade_api"
```

### Orchestrator Hangs
- Check that database is responding: `pg_isready`
- Check that data_patrol isn't stuck: add shorter timeout to DATA_PATROL_TIMEOUT_MS
- Check logs for blocking queries: `psql -c "SELECT * FROM pg_stat_activity;"`

---

## AWS Deployment Connection

### From Local to AWS RDS (for Testing)
If you have AWS RDS running and want to test against it locally:

```bash
# Update .env.local to point to AWS RDS
DB_HOST=your-rds-endpoint.us-east-1.rds.amazonaws.com
DB_PASSWORD=<your-rds-password>
DB_SSL=true

# Test connection
python -c "
import psycopg2
conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=5432,
    user='stocks',
    password=os.getenv('DB_PASSWORD'),
    database='stocks',
    sslmode='require'
)
print('Connected to AWS RDS')
"
```

### CloudFormation Stack Parameters
When deploying to AWS, these parameters must match your RDS configuration:

```bash
# In .github/workflows/deploy-data-infrastructure.yml
aws cloudformation deploy \
  --template-file template-data-infrastructure.yml \
  --parameter-overrides \
    RDSUsername=stocks \
    RDSPassword=your-secure-password \
  ...
```

The values must match what you used in local development (same database name, same username).

---

## IaC Best Practices Applied Here

✓ **Version Controlled**: docker-compose.local.yml in git  
✓ **Documented**: This guide explains every step  
✓ **Idempotent**: Safe to run setup multiple times  
✓ **Environment-Agnostic**: Same code works local and AWS  
✓ **No Secrets in Code**: All credentials in .env.local (.gitignored)  
✓ **Schema Consistency**: init_database.py used everywhere  
✓ **Health Checks**: PostgreSQL healthcheck ensures readiness  
✓ **Single Source of Truth**: docker-compose.local.yml = source of local setup  

---

## Next Steps

1. **Follow Steps 1-5 above** to set up local environment
2. **Run orchestrator**: `python algo_orchestrator.py --dry-run`
3. **Verify output**: Check that all 7 phases complete
4. **Load test data**: Run data loaders to populate database
5. **Run paper mode**: `EXECUTION_MODE=paper python algo_orchestrator.py`
6. **Monitor metrics**: Query algo_performance_daily, algo_tca tables

---

## Support

If setup fails:
1. Check this guide Step-by-Step
2. Review docker-compose logs: `docker-compose logs <service>`
3. Verify .env.local has correct values: `cat .env.local | grep DB_`
4. Test database directly: `docker-compose exec postgres psql -U stocks -c "SELECT 1"`

---

**Status**: Ready for Local Development Setup  
**Last Updated**: 2026-05-06
