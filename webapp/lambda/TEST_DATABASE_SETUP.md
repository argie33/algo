# Test Database Configuration

## Overview

All tests use the **same database** (`stocks`) as the data loaders. This ensures:
- ✅ No confusion about which database tests access
- ✅ Tests have access to all loaded data
- ✅ Real integration testing with production data
- ✅ Tests validate both schema AND data

## Setup

### 1. Test Database Configuration
- Database: `stocks` (localhost:5432)
- Schema: Same as production (107 tables)
- Data: Populated by Python loaders
- Status: ✅ Ready for testing

### 2. Test Configuration
- **File**: `jest.setup.js`
- **Key Setting**: `DB_NAME` is set to `stocks` for all test runs
- **Important**: Tests use the SAME database as data loaders - NO separate test database

### 3. Environment Variables for Tests
```bash
DB_HOST=localhost        # Database host
DB_PORT=5432             # Database port
DB_USER=postgres         # PostgreSQL user
DB_PASSWORD=password     # PostgreSQL password
DB_NAME=stocks           # STOCKS database (same as loaders)
DB_SSL=false             # No SSL for local testing
```

## Data Loading

Python loaders populate `stocks` database with real data:
- `loaddailycompanydata.py` - Company profiles and stock symbols
- `loadstockscores.py` - Stock scoring data
- `loadpricedaily.py` - Historical price data
- `loadnews.py` - News and sentiment data
- `loadinfo.py` - Additional info data
- `loadlatesttechnicalsdaily.py` - Technical indicators

All tests access this same data.

## Benefits

✅ **Single Source of Truth**
- One database for both loaders and tests
- No data synchronization required
- No confusion about test database location

✅ **Real Integration Testing**
- Tests query real PostgreSQL with actual data
- Validates schema correctness
- Tests real query performance

✅ **Complete Test Coverage**
- Tests have access to all loaded data
- Can validate against real data patterns
- Catches data quality issues immediately

## Test Data Expectations

Tests expect the `stocks` database to contain:
- **price_daily**: 7.5M+ historical price records
- **company_profile**: 5,000+ company records
- **stock_symbols**: 5,000+ stock symbol records
- **stock_scores**: 2,000+ scoring records
- **technical_indicators**: 80+ indicator records
- Plus other tables loaded by loaders

## Important Notes

⚠️ **Single Database**
- Tests use `stocks` database (same as loaders)
- Jest setup enforces `DB_NAME=stocks`
- No separate test database

⚠️ **Data Persistence**
- Test data persists between runs
- Tests query real data from loaders
- Clean data for specific tests if needed

⚠️ **Debugging**
- If tests fail, check `stocks` database directly:
  ```bash
  psql -h localhost -U postgres -d stocks
  ```
- View test data: `SELECT * FROM stock_scores LIMIT 10;`
- Check loader status: `SELECT COUNT(*) FROM price_daily;`

## Troubleshooting

### Tests running against wrong database
- Verify `jest.setup.js` has `DB_NAME=stocks`
- Check `process.env.DB_NAME` in running tests
- Ensure no `.env` file overrides `DB_NAME`

### Tests report "No data found"
- Run data loaders to populate `stocks` database:
  ```bash
  cd /home/stocks/algo
  python3 loaddailycompanydata.py
  python3 loadstockscores.py
  ```
- Verify data was loaded: `SELECT COUNT(*) FROM stock_symbols;`

### Unexpected test failures
- May indicate real data quality issues
- Check data in database directly
- Validate loader output

## References

- Jest Setup: `jest.setup.js`
- Database Utils: `utils/database.js`
- Data Loaders: `/home/stocks/algo/*.py`
