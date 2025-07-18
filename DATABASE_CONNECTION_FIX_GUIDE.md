# DATABASE CONNECTION CRISIS FIX - DEPLOYMENT GUIDE

## CRITICAL ISSUE
Circuit breaker is OPEN, blocking all database access. This fix provides:
1. Enhanced circuit breaker with Lambda-optimized thresholds
2. Database connection manager with integrated circuit breaker
3. Emergency recovery endpoints

## FILES CREATED
1. webapp/lambda/utils/databaseCircuitBreaker.js
2. webapp/lambda/utils/databaseConnectionManager.js
3. webapp/lambda/routes/emergency.js

## DEPLOYMENT STEPS

### Step 1: Update Main Database Utility
Edit webapp/lambda/utils/database.js:

```javascript
// Add at the top
const databaseManager = require('./databaseConnectionManager');

// Replace existing query function with:
async function query(text, params = []) {
  return databaseManager.query(text, params);
}

// Add health check function:
async function healthCheck() {
  try {
    await databaseManager.query('SELECT 1');
    return { status: 'healthy' };
  } catch (error) {
    return { status: 'unhealthy', error: error.message };
  }
}

module.exports = { query, healthCheck };
```

### Step 2: Add Emergency Routes
Edit webapp/lambda/index.js (or main router):

```javascript
// Add emergency routes
const emergencyRoutes = require('./routes/emergency');
app.use('/api/health', emergencyRoutes);
```

### Step 3: Deploy to Lambda
```bash
cd webapp/lambda
npm run package
npm run deploy-package
```

## IMMEDIATE RECOVERY

### Check Circuit Breaker Status
```bash
curl https://your-api-url/api/health/circuit-breaker-status
```

### Emergency Reset (if needed)
```bash
curl -X POST https://your-api-url/api/health/emergency/reset-circuit-breaker
```

### Test Database
```bash
curl https://your-api-url/api/health
```

## KEY IMPROVEMENTS
- Failure threshold: 5 → 10 (more forgiving)
- Recovery timeout: 60s → 30s (faster recovery)
- Half-open calls: 3 → 5 (better testing)
- Enhanced SSL/JSON error handling
- Emergency manual recovery

## SUCCESS INDICATORS
✅ Circuit breaker state: closed
✅ Database queries succeed
✅ Health endpoint returns 200
✅ No "Circuit breaker is OPEN" errors

The circuit breaker will automatically attempt recovery every 30 seconds.
If automatic recovery fails, use the emergency reset endpoint.
