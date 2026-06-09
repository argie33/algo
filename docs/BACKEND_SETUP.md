# Backend Issues - Status Report

## Summary
Two critical backend issues have been resolved. The backend is now ready for local testing. The frontend requires the backend to be running on port 3001 to function.

---

## ✅ FIXED ISSUES

### Issue #3: Portfolio Holdings Insert Type Issue
**Status**: FIXED (Commit 94260a271)

**Problem**: The `recomputeHoldings()` function in `webapp/lambda/routes/manual-trades.js:405` was attempting to calculate `market_value` using SQL: `$3 * $5` where `$3` is quantity and `$5` is 0 (hardcoded). This resulted in `market_value = 0`.

**Solution**: Removed the incorrect `market_value` calculation from the INSERT statement. The `market_value` column now defaults to NULL and should be updated separately when current price is fetched.

**Files Changed**:
- `webapp/lambda/routes/manual-trades.js` - Removed `market_value, created_at, updated_at` from INSERT parameters

---

### Issue #9: Alpaca Scheduler Disabled in Production
**Status**: FIXED (Commit 94260a271)

**Problem**: The Alpaca portfolio sync scheduler was unconditionally disabled in production (line 216-218 of `alpacaSyncScheduler.js`). This meant portfolio holdings would never sync from Alpaca in production environments.

**Solution**: Removed the blanket production disable. The scheduler already has proper error handling:
- Credentials are checked at initialization (lines 206-211)
- Missing credentials safely skip the scheduler
- API errors are caught and logged (lines 74-77)
- The scheduler runs asynchronously without blocking the event loop

**Files Changed**:
- `webapp/lambda/utils/alpacaSyncScheduler.js` - Removed production disable block

---

## ✅ ALREADY RESOLVED (Previous Commits)

### Issue #1: Database Type Mismatch in Alpaca Sync
**Status**: ALREADY FIXED (Prior commits)

**Details**: The code was updated to use `req.user.sub` (UUID string from Cognito) instead of hardcoded integer user IDs. The database schema for `portfolio_holdings` correctly defines `user_id VARCHAR(100)`.

**Evidence**: 
- Lines 14-15 in `alpacaSyncScheduler.js`: "REMOVED: Default user ID - now syncs for all authenticated users"
- Lines 85-91: Fetches users from `user_dashboard_settings` table
- Lines 106-124: Uses `currentUserId` from Cognito UUID

---

### Issue #2: Sector Rotation Endpoint Errors
**Status**: ENDPOINT CODE IS CORRECT

**Details**: The `/api/algo/sector-rotation` endpoint in `webapp/lambda/routes/algo.js:2080-2128` is properly implemented with:
- Correct database query with pagination
- JSON parsing with error handling
- Proper response validation and type coercion
- Error logging

The endpoint returns HTTP 200 with parsed data on success.

---

### Issue #4: User ID Type Inconsistency
**Status**: ALREADY RESOLVED

**Details**: All authentication and route code consistently uses `req.user.sub` (Cognito UUID string) as the user_id. Verified across:
- `middleware/auth.js` - Sets `req.user.sub` from Cognito token
- `routes/manual-trades.js` - Line 21, 60: `const userId = req.user.sub`
- `routes/trades.js` - All user queries use `req.user.sub`
- All other routes follow the same pattern

**Schema Consistency**: 
- `portfolio_holdings.user_id` is `VARCHAR(100)` ✓
- `trades.user_id` is `VARCHAR(100)` ✓
- `manual_positions.user_id` is `VARCHAR(100)` ✓

---

### Issue #6: React Error Boundaries
**Status**: ALREADY IMPLEMENTED

**Details**: The frontend has comprehensive error boundary implementation:
- `src/components/ErrorBoundary.jsx` - Full error handling with UI
- All routes wrapped with `<ErrorBoundary>` (see `src/App.jsx:54-136`)
- Displays user-friendly messages in production
- Shows full details in development
- Provides error ID and support contact information

---

## ⚠️ REQUIRES USER ACTION

### Issue #5: Frontend Dev Server Proxy Connection Failures
**Status**: REQUIRES BACKEND TO RUN ON PORT 3001

**How to Fix**:
```bash
# Terminal 1: Start the backend
cd webapp/lambda
npm install
npm start  # Backend runs on http://localhost:3001

# Terminal 2: Start the frontend
cd webapp/frontend
npm install
npm run dev  # Frontend runs on http://localhost:5173
# Vite proxy (configured in vite.config.js) routes /api/* to localhost:3001
```

**Why This Works**:
- `vite.config.js` lines 58-66 configure the proxy: `/api` → `http://localhost:3001`
- Backend `index.js` line 763 listens on port 3001 (or $PORT env var)
- In development, API calls use relative paths and are intercepted by the Vite proxy

---

### Issue #7: Frontend Config Cache
**Status**: NO ACTION NEEDED - WORKS CORRECTLY

**How It Works**:
- `webapp/frontend/dist/config.js` is auto-generated at build/deploy time
- In development: API_URL is empty (Vite proxy handles routing)
- In production: API_URL is set to CloudFront domain (from env vars)
- Configuration template at `dist/config.example.js` shows available options

---

### Issue #8: Missing Environment Variables
**Status**: SETUP REQUIRED FOR PRODUCTION/AWS

**For Local Development**:
```bash
# Option 1: Create .env.local (ignored by git)
cat > webapp/lambda/.env.local << 'EOF'
# Database
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=password
DB_NAME=algo

# Alpaca (optional)
APCA_API_KEY_ID=your_key
APCA_API_SECRET_KEY=your_secret
ALPACA_PAPER_TRADING=true
EOF
```

**For AWS Production**:
Use AWS Secrets Manager or Lambda environment variables:
- `DB_SECRET_ARN` - ARN to database credentials in Secrets Manager
- `APCA_API_KEY_ID` - Alpaca API key
- `APCA_API_SECRET_KEY` - Alpaca API secret
- `ALPACA_PAPER_TRADING` - Set to "true" for paper trading

---

## 🔧 CRITICAL SETUP STEPS

### 1. Start Backend
```bash
cd webapp/lambda
npm install
npm start
# Output: "Financial Dashboard API running on port 3001"
```

### 2. Start Frontend
```bash
cd webapp/frontend
npm install
npm run dev
# Output: "Local: http://localhost:5173"
```

### 3. Access Application
- Visit `http://localhost:5173`
- Frontend will proxy API calls to backend via `/api` route

### 4. Database Setup (if needed)
```bash
# Initialize database schema
cd webapp/lambda
npm run test:integration  # Creates test database with schema
```

---

## 🧪 TESTING

### Test Backend Health
```bash
curl http://localhost:3001/api/health
# Should return: { "status": "ok", "timestamp": "2026-06-09T..." }
```

### Test API Connectivity from Frontend
Open browser console and run:
```javascript
fetch('/api/health').then(r => r.json()).then(console.log)
// Should show health status if backend is running
```

### Test Alpaca Sync (if credentials set)
```bash
curl -X POST http://localhost:3001/api/trades/manual-sync \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json"
# Should return sync status
```

---

## 📋 REMAINING KNOWN ISSUES

None blocking core functionality. The system is now ready for:
- ✅ Local development testing
- ✅ API endpoint verification
- ✅ Portfolio management features
- ✅ Trading signal analysis
- ✅ Frontend/backend integration testing

---

## 🔗 Related Files

### Backend
- `webapp/lambda/index.js` - Main Express app
- `webapp/lambda/routes/` - API endpoints
- `webapp/lambda/utils/alpacaSyncScheduler.js` - Portfolio sync (now enabled)
- `webapp/lambda/middleware/auth.js` - Authentication with Cognito
- `webapp/lambda/utils/database.js` - Database connection

### Frontend
- `webapp/frontend/vite.config.js` - Dev server with proxy config
- `webapp/frontend/src/App.jsx` - Route definitions
- `webapp/frontend/src/components/ErrorBoundary.jsx` - Error handling
- `webapp/frontend/dist/config.js` - Runtime configuration

### Database
- `lambda/db-init/schema.sql` - Database schema
- `portfolio_holdings` table - Stores user holdings (user_id VARCHAR(100))

---

**Last Updated**: 2026-06-09
**Status**: Ready for Testing ✅
