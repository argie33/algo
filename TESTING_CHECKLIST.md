# Complete Testing Checklist for All Pages

## Prerequisites
- PostgreSQL running on localhost:5432 with data loaded
- Database credentials configured in environment variables
- Backend running on port 4000: `cd webapp/lambda && node index.js`
- Frontend running on port 5173: `cd webapp/frontend && npm run dev`

## Backend Verification

### API Endpoints That Were Fixed
- [ ] `GET /api/scores/stockscores?limit=10&sortBy=composite_score` - Returns stock scores
- [ ] `GET /api/scores/stockscores?offset=0&limit=50` - Offset-based pagination works
- [ ] `GET /api/scores/stockscores?sp500Only=true` - sp500Only parameter accepted

### Critical API Endpoints All Pages Depend On
- [ ] `GET /api/sentiment/data?limit=100&page=1` - Sentiment stocks
- [ ] `GET /api/sentiment/summary` - Sentiment summary
- [ ] `GET /api/sentiment/divergence` - Sentiment divergence
- [ ] `GET /api/sentiment/analyst/insights/{symbol}` - Analyst insights
- [ ] `GET /api/scores/stockscores?limit=100` - Stock scores (FIXED ENDPOINT)
- [ ] `GET /api/algo/status` - Algo status
- [ ] `GET /api/algo/positions` - Positions
- [ ] `GET /api/algo/markets` - Markets data
- [ ] `GET /api/economic/leading-indicators` - Economic data
- [ ] `GET /api/economic/yield-curve-full` - Yield curve
- [ ] `GET /api/market/sentiment?range=30d` - Market sentiment
- [ ] `GET /api/market/fear-greed?range=30d` - Fear & Greed index

## Frontend Page Testing

### Sentiment Page (`/app/sentiment`)
- [ ] Page loads without 404 or permission errors
- [ ] Sentiment data table displays with stock symbols
- [ ] Sentiment gauge renders composite score
- [ ] Rating funnel chart shows analyst distribution
- [ ] Change leaders (gainers/decliners) display properly
- [ ] Contrarian setups section shows correctly
- [ ] Analyst tab works when selecting a stock
- [ ] No console errors in browser dev tools

### Scores Dashboard (`/app/scores`)
- [ ] Page loads and displays stock scores
- [ ] Scores table sorts by composite_score correctly
- [ ] Pagination works (next/prev buttons)
- [ ] Search by symbol filters results
- [ ] Factor breakdown shows (momentum, value, growth, etc.)
- [ ] Top gainers/losers display
- [ ] No console errors

### Sector Analysis (`/app/sectors`)
- [ ] Sector rankings display
- [ ] Daily strength scores chart renders
- [ ] Mansfield RS rotation chart shows
- [ ] Breadth indicators display
- [ ] Industry drill-down works
- [ ] No console errors

### Economic Dashboard (`/app/economic`)
- [ ] Page loads with economic indicators
- [ ] Recession probability gauge renders
- [ ] Yield curve chart displays
- [ ] Leading indicators show with values
- [ ] Credit spreads panel renders
- [ ] No console errors

### Markets Health (`/app/market`)
- [ ] Page loads with market overview
- [ ] Regime banner displays current market state
- [ ] Index strip shows major indices
- [ ] Breadth indicators display correctly
- [ ] VIX card shows volatility
- [ ] Market internals display
- [ ] Top movers section renders
- [ ] No console errors

### Algo Trading Dashboard (`/app/algo`)
- [ ] Page loads (may require admin auth)
- [ ] Strategy status displays
- [ ] Position data shows
- [ ] Trade history displays
- [ ] Circuit breaker status shows
- [ ] Performance metrics display
- [ ] Patrol log displays
- [ ] No console errors

### Other Pages to Test
- [ ] Trading Signals (`/app/signals`) - displays and searches signals
- [ ] Deep Value Stocks (`/app/deep-value`) - shows value candidates
- [ ] Stock Detail (`/app/stocks/{symbol}`) - shows individual stock data
- [ ] Portfolio Dashboard (`/app/portfolio`) - displays portfolio data
- [ ] Trade Tracker (`/app/trades`) - shows trade history
- [ ] Service Health (`/app/health`) - shows service status
- [ ] Settings (`/app/settings`) - loads settings page

## Error Handling Tests

### Test 404 Handling
- [ ] Access invalid route (e.g., `/app/nonexistent`) - shows "Not Found" page
- [ ] No 500 errors thrown

### Test API Error Handling
- [ ] When backend is down - pages show error message (not blank page)
- [ ] When API returns empty data - pages show "No data available"
- [ ] When pagination limit exceeded - gracefully handles

### Test Loading States
- [ ] Pages show loading spinner while fetching data
- [ ] Spinner disappears when data loads
- [ ] Buttons disabled during API calls

## Network/Performance Tests

### Browser Console (DevTools)
- [ ] No JavaScript errors logged
- [ ] No 404 errors in Network tab (all API calls return valid status)
- [ ] No CORS errors
- [ ] No undefined variable errors

### Page Load Performance
- [ ] Homepage loads in under 5 seconds
- [ ] Data-heavy pages (Sentiment, Scores) load in under 8 seconds
- [ ] No memory leaks (DevTools > Memory tab)

## Responsive Design

- [ ] Pages render on desktop (1920x1080)
- [ ] Pages render on tablet (768x1024)
- [ ] Pages render on mobile (375x667)
- [ ] No horizontal scroll on mobile
- [ ] Touch interactions work on mobile

## AWS Deployment Verification

### After deploying to AWS:
- [ ] Frontend loads from CloudFront/S3
- [ ] Backend API responds on correct domain
- [ ] All endpoints return 200 status codes
- [ ] Data loads and displays correctly
- [ ] No CORS errors when accessing cross-origin
- [ ] SSL/HTTPS working correctly
- [ ] All pages accessible without errors

## Sign-Off

Once all checks pass:
- [ ] All pages render properly
- [ ] No errors in console
- [ ] All API calls work
- [ ] Site runs fully locally
- [ ] Site runs fully in AWS
- [ ] No regressions from other pages

Date Tested: _______________
Tested By: _______________
Status: ✅ All Tests Passing / ⚠️ Issues Found
