# Test Database Configuration

## Overview

Integration tests now use a **separate test database** (`stocks_test`) instead of mocking database queries. This ensures tests catch real data quality issues and integration bugs.

## Setup

### 1. Test Database Created
- Database: `stocks_test` (localhost:5432)
- Schema: Copied from production `stocks` database (106 tables)
- Status: ✅ Ready for testing

### 2. Test Configuration
- **File**: `jest.setup.js`
- **Key Change**: `DB_NAME` is set to `stocks_test` for all test runs
- **Important**: Tests NEVER use production `stocks` database

### 3. Environment Variables for Tests
```bash
DB_HOST=localhost        # Test database host
DB_PORT=5432             # Test database port
DB_USER=postgres         # PostgreSQL user
DB_PASSWORD=password     # PostgreSQL password
DB_NAME=stocks_test      # TEST database (not production!)
DB_SSL=false             # No SSL for local testing
```

## Benefits

✅ **Real Integration Testing**
- Tests query real PostgreSQL, not mocks
- Catches schema mismatches immediately
- Prevents data quality issues

✅ **Isolated from Production**
- Test database is completely separate
- Tests can safely truncate/modify data
- No risk to production data

✅ **Reproducible Results**
- Same schema as production
- Real query execution paths
- Accurate performance characteristics

## Test Data

Test database starts empty. Individual tests can:
1. Insert specific test data
2. Use the `db-test-helper.js` to set up fixtures
3. Clear data between tests for isolation

Example:
```javascript
const { resetTestDatabase } = require('../helpers/db-test-helper');

beforeEach(async () => {
  await resetTestDatabase(); // Clean state for each test
});
```

## Important Notes

⚠️ **Production Safety**
- Tests ONLY use `stocks_test` database
- Jest setup enforces `DB_NAME=stocks_test`
- No test can ever modify production data

⚠️ **Test Isolation**
- Each test should clean up after itself
- Use `resetTestDatabase()` for clean state
- Avoid test interdependencies

⚠️ **Debugging**
- If tests fail, check `stocks_test` database directly:
  ```bash
  psql -h localhost -U postgres -d stocks_test
  ```
- View test data: `SELECT * FROM stock_scores;`
- Clear data: Queries are auto-rolled back or use truncate

## Migration from Mocks

### Before (Mock-based)
```javascript
// ❌ Mock database doesn't match reality
jest.mock('../utils/database', () => ({
  query: jest.fn().mockResolvedValue({
    rows: [{ indicator: 'test' }] // Wrong field name!
  })
}));
```

### After (Real database)
```javascript
// ✅ Real database ensures correctness
const { query } = require('../utils/database');
const result = await query('SELECT * FROM economic_indicators');
// Actual schema with correct field names
```

## Troubleshooting

### Test fails with "stocks_test database not found"
```bash
# Recreate test database
PGPASSWORD=password psql -h localhost -U postgres << EOF
DROP DATABASE IF EXISTS stocks_test;
CREATE DATABASE stocks_test;
GRANT ALL PRIVILEGES ON DATABASE stocks_test TO postgres;
EOF

# Copy schema from production
PGPASSWORD=password pg_dump -h localhost -U postgres --schema-only stocks | \
  PGPASSWORD=password psql -h localhost -U postgres -d stocks_test
```

### Tests running against production instead of test database
- Verify `jest.setup.js` has `DB_NAME=stocks_test`
- Check `process.env.DB_NAME` in running tests
- Ensure no `.env` file overrides `DB_NAME`

### Test data persists between test runs
- Add `afterEach(() => resetTestDatabase())` to test suites
- Or use `beforeEach` to start with clean state
- This ensures test isolation

## References

- Test Helper: `tests/helpers/db-test-helper.js`
- Jest Setup: `jest.setup.js`
- Database Utils: `utils/database.js`
