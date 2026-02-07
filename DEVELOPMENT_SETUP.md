# Development Setup Guide

This guide covers setting up the Stocks algorithmic trading dashboard for local development with database configuration that works for both local and AWS deployments.

## Quick Start (With Data Caching)

If you just want to run the application without setting up a database:

```bash
# 1. Start the backend API
cd /home/stocks/algo/webapp/lambda
node index.js

# 2. In another terminal, start the frontend
cd /home/stocks/algo/webapp/frontend
npm run dev
```

The frontend will display cached data from previous loads. No database setup needed.

**Access:**
- Frontend: http://localhost:5173
- Backend API: http://localhost:3001/api
- API Docs: http://localhost:3001/api/market

## Full Setup (With Local Database)

### Option 1: Using Docker Compose (Recommended)

**Prerequisites:** Docker and docker-compose v2

```bash
# 1. Start PostgreSQL container
cd /home/stocks/algo
docker compose up -d

# 2. Wait for PostgreSQL to be ready
docker compose exec postgres pg_isready -U postgres

# 3. Verify database is set up
docker compose exec postgres psql -U stocks -d stocks -c "SELECT 1;"
```

### Option 2: Manual PostgreSQL Setup

**Prerequisites:** PostgreSQL 16+ installed and running

```bash
# 1. Connect to PostgreSQL as admin
psql -U postgres

# 2. Run these commands in PostgreSQL:
CREATE USER stocks WITH PASSWORD 'stocks';
CREATE DATABASE stocks OWNER stocks;
GRANT ALL PRIVILEGES ON DATABASE stocks TO stocks;
ALTER DATABASE stocks OWNER TO stocks;

# 3. Exit PostgreSQL
\q
```

### Option 3: Environment-Based Configuration

If PostgreSQL is already configured on your system, ensure these environment variables are set in `.env.local`:

```bash
DB_HOST=localhost
DB_PORT=5432
DB_USER=stocks
DB_PASSWORD=stocks
DB_NAME=stocks
```

## Running Data Loaders

Once the database is set up:

```bash
# Option A: Run all data loaders (all phases)
bash /tmp/refresh_all_data.sh

# Option B: Run specific loader
python3 loadmarketindices.py      # Market indices
python3 loadbenchmark.py           # Index P/E metrics
python3 loadaaiidata.py            # Sentiment data
python3 loadearningshistory.py     # Earnings data
```

## Data Loader Phases

The comprehensive data refresh script runs in 7 phases:

### Phase 1: Market Data
- Market Indices (S&P 500, NASDAQ, Dow, Russell 2000)
- Benchmark Data & Index P/E Metrics
- Latest Daily Prices

### Phase 2: Market Sentiment
- AAII Sentiment Data
- NAAIM Manager Exposure
- Fear & Greed Index
- General Sentiment Data

### Phase 3: Earnings Data
- Earnings History
- Earnings Revisions
- Earnings Surprises

### Phase 4: Economic Data
- Economic Data (S&P 500 EPS, Valuations)

### Phase 5: Sector & Industry Data
- Sector Rankings
- Sector Performance
- Industry Rankings

### Phase 6: Market Internals
- Daily Company Data (Breadth, Advances/Declines)
- Market Technicals & Internals

### Phase 7: Additional Data
- Market Seasonality
- Market Positioning

## Database Configuration Strategy

The system uses a fallback configuration approach:

1. **AWS Environment (Production)**
   - Uses AWS Secrets Manager
   - Requires: `AWS_REGION` and `DB_SECRET_ARN` environment variables
   - Credentials stored securely in AWS

2. **Local Development**
   - Falls back to environment variables if AWS not configured
   - Reads from: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
   - Can be stored in `.env.local` file

3. **Docker Environment**
   - Automatically configures PostgreSQL in container
   - Initializes with stocks user and database
   - Uses `docker-compose.yml` and `init-db.sql`

## Troubleshooting

### PostgreSQL Authentication Failed

```bash
# Check if PostgreSQL is running
systemctl status postgresql

# Or if using Docker
docker compose ps

# Try connecting manually
PGPASSWORD='stocks' psql -U stocks -h localhost -d stocks
```

### Data Loaders Failing

```bash
# Check database connectivity
python3 -c "from lib.db import get_db_config; print(get_db_config())"

# View error logs
tail -f /tmp/backend.log
tail -f /tmp/data_refresh_local.log
```

### Missing Tables

Database tables are created automatically by the data loaders when they first run:

- `price_daily` - Daily price data
- `index_metrics` - Index P/E and valuation metrics
- `earnings_data` - Earnings history
- `sentiment_data` - Market sentiment indicators
- `sector_performance` - Sector data
- And many more...

### API Endpoints Returning Errors

```bash
# Check backend is running
curl http://localhost:3001/api/market

# Check database connection from backend
curl http://localhost:3001/api/system/health
```

## File Structure

```
/home/stocks/algo/
├── lib/
│   └── db.py              # Centralized database configuration
├── load*.py               # Data loader scripts
├── webapp/
│   ├── lambda/            # Backend API
│   │   ├── index.js
│   │   └── routes/
│   └── frontend/          # React frontend
│       ├── src/
│       └── package.json
├── .env.local             # Local environment variables
├── docker-compose.yml     # Docker compose configuration
├── init-db.sql            # Database initialization script
└── DEVELOPMENT_SETUP.md   # This file
```

## Environment Variables Reference

### Local Development (.env.local)
```bash
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_USER=stocks
DB_PASSWORD=stocks
DB_NAME=stocks

# AWS Configuration (leave empty for local dev)
AWS_REGION=
DB_SECRET_ARN=
```

### AWS Production
```bash
AWS_REGION=us-east-1
DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123456789:secret:stocks-db
```

## Database Architecture

### Connection Pool
- Local connections use psycopg2 directly
- Connection pooling handled per loader
- Auto-commit disabled for safety
- Transactions managed explicitly

### Schema
- Public schema used
- Tables created on-demand by loaders
- Automatic timestamp tracking
- UTF-8 encoding for text data

## Performance Considerations

1. **Data Loading** - Each loader optimizes for the specific data type
2. **Memory Usage** - Loaders use gc and resource monitoring
3. **API Caching** - Frontend can cache data for 30+ minutes
4. **Database Indexing** - Key columns indexed for fast queries

## Next Steps

1. Choose setup method (Docker recommended)
2. Run data loaders for initial data population
3. Verify data in frontend pages
4. For production, configure AWS Secrets Manager
5. Set up CI/CD pipeline for regular data updates

## Support

For issues or questions:
1. Check `DEVELOPMENT_SETUP.md` (this file)
2. Review logs in `/tmp/`
3. Check backend logs: `curl http://localhost:3001/api/system/health`
4. Verify database: `PGPASSWORD='stocks' psql -U stocks -h localhost -d stocks`

---

**Last Updated:** 2026-02-07
**System:** Ubuntu 24.04 LTS with PostgreSQL 16
**Docker:** Docker Compose v2.34+
