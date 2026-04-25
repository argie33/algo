# Debugging Guide - Stock Analytics Platform

## Quick Diagnostics

### 1. Check API Health
```bash
# Terminal command to test the API
curl http://localhost:3001/api/health
curl http://localhost:3001/api/diagnostics
```

Visit in browser:
- `http://localhost:3001/api/status` — Quick status check
- `http://localhost:3001/api/health` — Full health check with database info
- `http://localhost:3001/api/diagnostics` — Detailed table status and recommendations

### 2. Check Frontend Network Calls
Open browser DevTools (F12):
1. Go to **Network** tab
2. Try to load a page (e.g., Deep Value Stocks)
3. Look for failed API calls (red status codes)
4. Click on the failed request → **Response** tab to see error details

## Common Error Messages & Fixes

### "Stock scores data not yet available"
**Problem:** The `stock_scores` table is empty or doesn't exist

**Check:**
```bash
# In your database terminal
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM stock_scores"
```

**Fixes:**
1. If table doesn't exist: Run database setup script
2. If table is empty: Run data population script to populate stock scores
3. Check `/api/diagnostics` to see which tables are populated

---

### "Failed to fetch stocks: relation ... does not exist"
**Problem:** A required database table is missing

**The error shows which table is missing.** Common missing tables:
- `stock_symbols` — Master list of stocks
- `stock_scores` — Score calculations (value, quality, growth, etc.)
- `company_profile` — Company information
- `price_daily` — Daily price data

**Fix:**
1. Run database initialization/migration scripts
2. Verify `.env.local` has correct `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`
3. Check PostgreSQL is running: `psql -h localhost -U stocks -d stocks -c "SELECT 1"`

---

### "Network connection failed. Please check your internet connection."
**Problem:** Frontend can't reach the API server

**Check:**
1. Is API server running? 
   ```bash
   node webapp/lambda/index.js
   ```
   Should show: `✅ Financial Dashboard API running on port 3001`

2. Is frontend running?
   ```bash
   cd webapp/frontend-admin && npm run dev
   ```
   Should show: `VITE v[X.X.X]`

3. Check frontend API configuration:
   - Open browser DevTools Console
   - Type: `window.__CONFIG__` and `window.location.origin`
   - It should match the API URL being used

---

### Blank Page With No Data & No Error
**Most Common Cause:** API call succeeds but returns empty results

**Troubleshooting:**
1. Open DevTools **Network** tab
2. Look for API calls (e.g., `/api/stocks/deep-value`)
3. Click the request → **Response** tab
4. Check if response shows:
   - `"success": true, "items": []` — Data endpoint is working but table is empty
   - `"success": false, "error": "..."` — Actual error (see error list above)
   - No response at all — Server not responding

**If items array is empty:**
- Run `/api/diagnostics` to check which tables have data
- If the required table is empty, run data population scripts
- Check if table name is correct (see CLAUDE.md for exact table names)

---

### Database Connection Errors
**Error: "Database connection failed"**

**Check connection:**
```bash
# Test if database is reachable
psql -h localhost -U stocks -d stocks -c "SELECT 1"

# Or from Node.js
node -e "
const pg = require('pg');
new pg.Client({
  host: 'localhost',
  user: 'stocks',
  password: 'YOUR_PASSWORD',
  database: 'stocks'
}).connect(console.log)
"
```

**Common fixes:**
- Verify `.env.local` has correct credentials
- Ensure PostgreSQL is running: `brew services list` (Mac) or check Services (Windows)
- Check firewall isn't blocking port 5432
- Verify user `stocks` exists: `psql -h localhost -U postgres -c "\du"`

---

## Checking API Logs

### See API Server Logs
The API server logs all requests and errors to console:
```
📨 [request-id] GET /api/stocks/deep-value
🔴 SERVER ERROR [500]: {...error details...}
⏱️ SLOW RESPONSE [200]: Duration exceeded 5 seconds
```

### Search for Your Specific Error
When API server is running, look for lines with:
- 🔴 (server errors)
- 🟡 (client errors) 
- ❌ (detailed error info)

## How to Report Issues

When asking for help, provide:

1. **What page/endpoint are you trying to access?**
   - Example: "Deep Value Stocks page"

2. **What error message do you see (if any)?**
   - Check browser console (F12)
   - Check /api/diagnostics response

3. **API diagnostic results**
   - Visit `http://localhost:3001/api/diagnostics`
   - Copy the full JSON response

4. **Recent API logs**
   - Run API server and try to reproduce issue
   - Copy the console output

## Table Reference

| Table | Purpose | Critical? |
|-------|---------|-----------|
| `stock_symbols` | Master stock list | ✅ YES |
| `stock_scores` | Value/quality/growth scores | ✅ YES |
| `company_profile` | Company info (sector, industry) | ✅ YES |
| `price_daily` | Daily OHLCV data | ✅ YES |
| `buy_sell_daily` | Trading signals | ❌ Optional |
| `technical_data_daily` | Technical indicators | ❌ Optional |
| `earnings_history` | Past earnings data | ❌ Optional |

If any of the ✅ tables are missing or empty, frontend features won't work.

## Development Tips

### Enable Extra Debugging
In browser console:
```javascript
window.__DEBUG_API__ = true;
localStorage.setItem('debug', '*');
```

Then reload page. You'll see detailed API logs.

### Check Response Format
The API response format must be:
```json
{
  "success": true,
  "data": {...} or "items": [...],
  "timestamp": "2026-04-25T...",
  "pagination": {...}  // Only for list endpoints
}
```

If you see a different format, it might be coming from the wrong endpoint.

### Clear Browser Cache
Sometimes old data is cached:
```javascript
// In browser console
localStorage.clear();
sessionStorage.clear();
// Then reload
```

---

## Still Stuck?

1. **Check /api/diagnostics** — This shows exactly which tables have data
2. **Check browser DevTools Network tab** — See actual API responses
3. **Check API server logs** — See what errors the server encountered
4. **Search this file** — For your specific error message
