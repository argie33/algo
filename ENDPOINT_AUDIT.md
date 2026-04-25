# API Endpoint Audit - April 25, 2026

## Summary
Comprehensive test of all 29 API routes revealed **11 working routes**, **8 routes with 500 errors**, and **multiple broken/missing sub-endpoints**.

## ✅ FIXED (3 endpoints)
- ✅ `/api/scores/all` - Added as alias to /stockscores
- ✅ `/api/signals/daily` - Added as alias with timeframe=daily
- ✅ `/api/sentiment/summary` - New endpoint aggregating all sentiment sources

## 🔴 CRITICAL ISSUES (500 Server Errors - need DB fixes)
| Endpoint | Error | Status |
|----------|-------|--------|
| `/api/analysts/by-symbol/:symbol` | "Failed to fetch analyst data" | 500 |
| `/api/analysts/sentiment` | "Failed to fetch analyst data" | 500 |
| `/api/options/chains/:symbol` | "Failed to fetch options chain" | 500 |
| `/api/strategies/covered-calls` | "Failed to fetch strategies" | 500 |
| `/api/trades/history` | Column "type" does not exist | 500 |
| `/api/trades/manual` | Same as above | 500 |

**Root Cause:** Likely database schema mismatches or missing tables
- trades table might not have "type" column OR authentication is failing
- analyst_sentiment_analysis table issues
- options/chains tables might be empty or missing

## 🟡 MISSING ENDPOINTS (404 Not Found)
| Route | Missing | Has | Notes |
|-------|---------|-----|-------|
| `/api/analysts` | /list, /symbol/:symbol | /upgrades, /sentiment, /by-symbol/:symbol | Need /list alias |
| `/api/commodities` | /list | /categories, /prices, /market-summary, /cot/:symbol | Need /list alias |
| `/api/community` | * ROOT BROKEN | /stats | Root endpoint returns 404 |
| `/api/industries` | /list | /industries, /trend/industry/:industryName | Need /list alias |
| `/api/optimization` | /portfolio | /analysis | Need /portfolio alias |
| `/api/options` | /symbol/:symbol | /chains/:symbol | Actual path is /chains not /symbol |
| `/api/sectors` | /sector/:name | /sectors, /sector/:name | Endpoint exists! |
| `/api/strategies` | /list | /covered-calls | Need /list alias |

## 🟢 WORKING ROUTES (OK status)
- ✅ /api/stocks
- ✅ /api/price/history/:symbol
- ✅ /api/earnings/info
- ✅ /api/financials/:symbol/balance-sheet
- ✅ /api/market/overview
- ✅ /api/portfolio/metrics
- ✅ /api/health
- ✅ /api/diagnostics
- ✅ /api/technicals/:symbol
- ✅ /api/technicals/daily
- ✅ /api/commodities/categories
- ✅ /api/commodities/prices
- ✅ /api/industries/industries

## Action Plan

### Phase 1: Fix 500 Errors (Critical)
1. **Trades table issue** - Check table schema, verify "type" column exists
2. **Analysts endpoints** - Check analyst_sentiment_analysis table, verify columns
3. **Options endpoints** - Check if options tables exist and have data
4. **Strategies endpoint** - Check if strategies table/data exists

### Phase 2: Add Missing Aliases (Quick Wins)
1. Add `/api/analysts/list` as alias to `/upgrades`
2. Add `/api/commodities/list` as alias to `/categories`
3. Add `/api/industries/list` as alias to `/industries`
4. Add `/api/strategies/list` as alias to `/covered-calls`
5. Add `/api/optimization/portfolio` as alias to `/analysis`

### Phase 3: Fix Community Route
- Community root endpoint broken - likely needs root handler added

## Testing Commands
```bash
# Test specific endpoint
curl -s "http://localhost:3001/api/analysts/by-symbol/AAPL"

# Check server logs
tail -50 /tmp/server.log

# Restart server with fresh code
pkill -f "node.*index.js"
sleep 2
node webapp/lambda/index.js
```
