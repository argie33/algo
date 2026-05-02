# Quick API Test - Core Endpoints

## Commands to Test (run in browser or curl)

```bash
# Health checks
curl http://localhost:3001/api/health
curl http://localhost:3001/api/health/database

# Core data endpoints
curl http://localhost:3001/api/stocks
curl http://localhost:3001/api/sectors
curl http://localhost:3001/api/signals/daily
curl http://localhost:3001/api/market/overview
curl http://localhost:3001/api/portfolio/positions
curl http://localhost:3001/api/economic/indicators
```

## Expected Outcomes

- Health endpoints should return 200 with status info
- Data endpoints should return 200 with data or empty array if no data
- Should NOT return 404 or undefined errors
- Frontend pages should be able to display results

## Issues to Fix

1. 404 errors - endpoint doesn't exist or is named wrong
2. Empty data - database tables are empty (need loaders to run)
3. Database connection errors - DB not running or wrong credentials

## Next Steps

After verifying these work:
1. Update frontend to use these endpoints only
2. Remove frontend code calling deleted endpoints
3. Run full test suite
