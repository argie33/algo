# Local Development Setup & Testing Guide

## Overview
This guide helps you set up the entire financial trading platform locally with real data and working tests.

## Prerequisites

### Option 1: Using Real PostgreSQL (Recommended for Production-like Testing)
```bash
# Ubuntu/Debian
sudo apt-get install postgresql postgresql-contrib

# macOS (Homebrew)
brew install postgresql

# Docker
docker run -d --name postgres-stocks \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=stocks \
  -p 5432:5432 \
  postgres:15
```

### Option 2: Using In-Memory Database (Fastest for Unit Tests)
- Already included: `pg-mem` package in package.json
- No setup required, works immediately

---

## Setup Step 1: Install Dependencies

```bash
cd /home/stocks/algo/webapp/lambda
npm install
```

---

## Setup Step 2: Initialize Database

### Option A: PostgreSQL (Real Database)

```bash
# Create database and user (if using system PostgreSQL)
sudo -u postgres psql << SQL
CREATE DATABASE IF NOT EXISTS stocks;
ALTER USER postgres WITH PASSWORD 'password';
\c stocks
SQL

# Apply schema
psql -h localhost -U postgres -d stocks -f setup_test_database.sql

# Seed test data
psql -h localhost -U postgres -d stocks -f seed_comprehensive_local_data.sql
```

### Option B: Automatic Setup Script
```bash
bash scripts/setup-local-data.sh
```

---

## Setup Step 3: Verify Database Connection

```bash
# Test connection
psql -h localhost -U postgres -d stocks -c "SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema='public';"

# Should show: count
#        10-20 (or more, depending on schema)
```

---

## Setup Step 4: Configure Environment

### Backend Configuration
Verify `webapp/lambda/.env` has correct settings:

```bash
cat webapp/lambda/.env
```

Should contain:
```
DB_HOST=localhost
DB_USER=postgres
DB_PASSWORD=password
DB_NAME=stocks
DB_PORT=5432
NODE_ENV=development
LOCAL_DEV_MODE=true
```

### Frontend Configuration
Verify `webapp/frontend/.env` has correct API port:

```bash
cat webapp/frontend/.env | grep VITE_API_URL
```

Should show:
```
VITE_API_URL=http://localhost:5001
```

⚠️ **CRITICAL**: If it shows `http://localhost:3001`, update it to `http://localhost:5001`

```bash
sed -i 's|http://localhost:3001|http://localhost:5001|g' webapp/frontend/.env
```

---

## Setup Step 5: Run Tests

### Run All Tests
```bash
cd webapp/lambda
npm test
```

### Run Specific Test Suites
```bash
# Unit tests only
npm run test:unit

# Integration tests only
npm run test:integration

# Financial/Portfolio tests
npm run test:financial

# Security/Auth tests
npm run test:security

# API/Routes tests
npm run test:api

# Database tests
npm run test:database
```

### Run with Coverage
```bash
npm test -- --coverage
```

---

## Setup Step 6: Start Backend Server Locally

```bash
cd webapp/lambda
npm start
```

Server runs on: `http://localhost:5001`

---

## Setup Step 7: Start Frontend

```bash
cd webapp/frontend
npm install
npm run dev
```

Frontend runs on: `http://localhost:5173`

---

## Verification Checklist

### Database Setup
- [ ] PostgreSQL running on localhost:5432
- [ ] Database `stocks` exists
- [ ] Tables created (check via `psql ... -c "\dt"`)
- [ ] Test data populated (check via `psql ... -c "SELECT COUNT(*) FROM price_daily;"`)

### Backend
- [ ] Dependencies installed (`npm install` completed)
- [ ] Server starts without errors (`npm start`)
- [ ] Health endpoint responds: `curl http://localhost:5001/health`

### Frontend
- [ ] Dependencies installed
- [ ] Dev server starts (`npm run dev`)
- [ ] Pages load: `http://localhost:5173`

### Tests
- [ ] Unit tests pass: `npm run test:unit`
- [ ] Integration tests pass: `npm run test:integration`
- [ ] No database timeout errors

---

## Common Issues & Fixes

### PostgreSQL Connection Failed

**Problem**: `error: connection to server at "localhost" (127.0.0.1), port 5432 failed`

**Solution**:
```bash
# Check if PostgreSQL is running
sudo service postgresql status  # Linux
brew services list              # macOS

# Start PostgreSQL
sudo service postgresql start   # Linux
brew services start postgresql # macOS

# Or use Docker
docker start postgres-stocks
```

### Database Tables Not Found

**Problem**: `relation "stock_symbols" does not exist`

**Solution**:
```bash
# Recreate schema
psql -h localhost -U postgres -d stocks -f setup_test_database.sql

# Verify tables
psql -h localhost -U postgres -d stocks -c "\dt"
```

### Test Timeout Errors

**Problem**: `timeout exceeded when trying to connect`

**Solution**:
```bash
# Increase test timeout in jest.config.js
testTimeout: 60000  # Increase from 30000

# Or check database connection
npm run test:database -- --verbose
```

### Port Already in Use

**Problem**: `listen EADDRINUSE: address already in use :::5001`

**Solution**:
```bash
# Find process using port
lsof -i :5001

# Kill it
kill -9 <PID>

# Or use different port
PORT=5002 npm start
```

---

## Data Seeding

### Seed Comprehensive Test Data
```bash
psql -h localhost -U postgres -d stocks -f seed_comprehensive_local_data.sql
```

This creates:
- 20 test symbols (AAPL, MSFT, GOOGL, etc.)
- 90 days of price data per symbol
- Technical indicators
- Company profiles
- Market data

### Verify Data Is Loaded
```bash
psql -h localhost -U postgres -d stocks << SQL
SELECT COUNT(*) as total_symbols FROM stock_symbols;
SELECT COUNT(*) as total_prices FROM price_daily;
SELECT COUNT(*) as total_scores FROM stock_scores;
SQL
```

---

## API Testing

### Test Health Endpoint
```bash
curl http://localhost:5001/health
```

### Test Dashboard API
```bash
curl http://localhost:5001/api/dashboard/summary
```

### Test Sectors API
```bash
curl http://localhost:5001/api/sectors
```

### Test Portfolio API (Requires Auth)
```bash
curl -H "Authorization: Bearer <token>" http://localhost:5001/api/portfolio
```

---

## Frontend Testing

### Access Pages

**Dashboard**: http://localhost:5173/
- Shows market overview, gainers/losers, sector breakdown

**Sectors**: http://localhost:5173/sectors
- Shows sector analysis and rankings

**Portfolio**: http://localhost:5173/portfolio
- Shows user portfolio (requires login)

**Analytics**: http://localhost:5173/analytics
- Shows detailed analytics and backtesting

### Verify Real Data Loads
- Open browser developer console (F12)
- Check Network tab for API calls
- Verify API responses contain data from database
- Check Console for any errors

---

## Running Full Test Suite

```bash
# Backend comprehensive tests
cd webapp/lambda
npm run test:comprehensive

# Frontend component tests
cd webapp/frontend
npm run test

# E2E tests
npm run test:e2e
```

---

## Performance Testing

```bash
# Backend performance tests
npm run test:performance

# Frontend Lighthouse audit
npm run build && npx lighthouse http://localhost:5173
```

---

## Troubleshooting

### Get Database Logs
```bash
# PostgreSQL logs
sudo journalctl -u postgresql -n 100  # Linux
brew services log postgresql           # macOS
```

### Reset Everything
```bash
# Drop database
psql -h localhost -U postgres -c "DROP DATABASE IF EXISTS stocks;"

# Recreate and reseed
./scripts/setup-local-data.sh
```

### Check Node Version
```bash
node --version  # Should be >= 18.0.0
npm --version   # Should be >= 8.0.0
```

---

## Next Steps

1. Complete setup steps 1-7
2. Run verification checklist
3. Run tests and fix any failures
4. Access frontend at http://localhost:5173
5. Check API responses at http://localhost:5001/health

For issues, check:
- `/home/stocks/algo/webapp/lambda/.env` - Database config
- `/home/stocks/algo/INTEGRATION_TEST_MOCK_ANALYSIS.md` - Test details
- `/home/stocks/algo/FIX_PATTERNS.md` - Common fixes
