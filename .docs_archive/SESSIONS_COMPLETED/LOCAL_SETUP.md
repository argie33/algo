# Local Development Setup

## Prerequisites

- **Node.js 20+** (check: `node --version`)
- **PostgreSQL 14+** (local or remote)
- **Python 3.11+** (for data loaders)
- `.env.local` file with database credentials

## Install Dependencies

```bash
# Backend
npm install

# Frontend
cd webapp/frontend
npm install
cd ../..
```

## Configure Database

### Option 1: Local PostgreSQL

```bash
# Create database and user
psql -U postgres -c "CREATE DATABASE stocks;"
psql -U postgres -c "CREATE USER stocks WITH PASSWORD 'password';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;"

# Create .env.local
cat > .env.local << 'EOF'
DB_HOST=localhost
DB_PORT=5432
DB_USER=stocks
DB_PASSWORD=password
DB_NAME=stocks
VITE_API_URL=http://localhost:3001
EOF
```

### Option 2: Remote Database (AWS RDS)

```bash
cat > .env.local << 'EOF'
DB_HOST=your-rds-endpoint.rds.amazonaws.com
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=your-password
DB_NAME=stocks
VITE_API_URL=http://localhost:3001
EOF
```

## Start Development Stack

```bash
# Terminal 1: Start API server (port 3001)
node webapp/lambda/index.js

# Terminal 2: Start frontend dev server (port 5174)
cd webapp/frontend
npm run dev

# Terminal 3: (Optional) Load data locally
cd ..
python3 loadpricedaily.py --backfill_days 30
python3 loadbuyselldaily.py
python3 loadtechnicalsdaily.py
```

## Verify Setup

Open browser: `http://localhost:5174`

Check API health:
```bash
curl http://localhost:3001/api/health
# Should return: { "success": true, "database": "connected" }
```

## Common Issues

### Port 3001 already in use
```bash
lsof -i :3001 | grep LISTEN | awk '{print $2}' | xargs kill -9
```

### Database connection refused
```bash
# Check credentials in .env.local
psql -h localhost -U stocks -d stocks -c "SELECT 1"
```

### Node modules not installed
```bash
rm -rf node_modules package-lock.json
npm install
cd webapp/frontend && npm install && cd ../..
```

### Database schema doesn't exist

The schema is created automatically on first API start. If tables are missing:
```bash
# Restart the API server
node webapp/lambda/index.js
# It will create tables on startup
```

## Environment Variables Reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_HOST` | localhost | Database hostname |
| `DB_PORT` | 5432 | Database port |
| `DB_USER` | stocks | Database user |
| `DB_PASSWORD` | - | Database password |
| `DB_NAME` | stocks | Database name |
| `VITE_API_URL` | http://localhost:3001 | API endpoint URL |
| `FRED_API_KEY` | (optional) | Federal Reserve API key |
| `ALPACA_API_KEY` | (optional) | Alpaca trading API key |
| `ALPACA_API_SECRET` | (optional) | Alpaca API secret |
| `ALPACA_PAPER_TRADING` | true | Use paper trading account |

## Loading Data Locally

```bash
# Load price data (all stocks)
python3 loadpricedaily.py --backfill_days 30

# Load technical indicators
python3 loadtechnicalsdaily.py

# Load buy/sell signals
python3 loadbuyselldaily.py

# Load fundamental data
python3 loadannualincomestatement.py
python3 loadannualbalancesheet.py

# See DATA_LOADING.md for complete loader list and schedule
```

## Next Steps

- See `API_REFERENCE.md` for available API endpoints
- See `DATA_LOADING.md` for all 39 data loaders
- See `TROUBLESHOOTING.md` for common issues
