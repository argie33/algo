# Test Schema Guide

## Database Schema Reference for Tests

Tests must use the ACTUAL database schema, not assumed schemas.

### ✅ Correct Table References

#### company_profile table
```javascript
// ✅ CORRECT
SELECT ticker, short_name, long_name, sector, industry
FROM company_profile
WHERE ticker = $1

// ❌ WRONG - no 'symbol' column
SELECT symbol FROM company_profile

// ❌ WRONG - no 'market_cap' column
SELECT market_cap FROM company_profile
```

#### market_data table
```javascript
// ✅ CORRECT
SELECT ticker, current_price, volume, market_cap
FROM market_data
WHERE ticker = $1

// ❌ WRONG - uses 'ticker' not 'symbol'
SELECT symbol FROM market_data

// ❌ WRONG - uses 'current_price' not 'price'
SELECT price FROM market_data
```

### ✅ Correct JOIN Patterns

```javascript
// ✅ CORRECT - ticker to ticker
FROM company_profile cp
LEFT JOIN market_data md ON cp.ticker = md.ticker

// ✅ CORRECT - ticker to symbol
FROM company_profile cp
LEFT JOIN price_daily pd ON cp.ticker = pd.symbol

// ❌ WRONG - no symbol column in company_profile
FROM company_profile cp
LEFT JOIN market_data md ON cp.symbol = md.ticker
```

### Schema Changes (Oct 2025)

**Commits that fixed schema issues:**
- c51e33d0e: Fixed market.js, sectors.js, backtest.js to use ticker columns
- f05857879: Replaced 'stocks' table with 'company_profile'
- 24ddfdfc6: Fixed market indices ticker column
- 6db2901bc: Fixed sectors company_profile reference

**Key Changes:**
1. `stocks` table → `company_profile` table
2. Column `symbol` → `ticker` in company_profile
3. Column `symbol` → `ticker` in market_data
4. Column `price` → `current_price` in market_data
5. `market_cap` moved from company_profile → market_data

### Test Validation

Before writing tests that query the database:
1. Check ACTUAL_DB_SCHEMA.md for correct column names
2. Use ticker for company_profile and market_data tables
3. Use symbol for price_daily, technical_data tables
4. JOIN on cp.ticker = md.ticker (not cp.symbol)

### Running Tests

```bash
# Run all tests
npm test

# Run specific test suites
npm run test:unit
npm run test:integration
npm run test:api
```

Tests should NOT assume table schemas - they should match the actual database structure created by the loaders.
