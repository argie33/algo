# System Testing Guide

## Quick Start - Local Testing

### 1. Start the API Server
```bash
python3 server.py
```
This starts Flask on `http://localhost:3001` serving all `/api/*` endpoints.

### 2. Start the Frontend Dev Server
```bash
cd webapp/frontend
npm run dev
```
This starts Vite on `http://localhost:5173` with hot reload.

### 3. Open Browser & Test
- Navigate to: `http://localhost:5173`
- Open F12 Console (DevTools)
- Test the following pages and verify no errors appear in the console:

#### Pages to Test
- [ ] Dashboard / Home (/)
- [ ] Stocks (/stocks)
- [ ] Signals (/signals)
- [ ] Portfolio (/portfolio)
- [ ] Analysis (/analysis)

#### API Endpoints Being Called
When viewing each page, these API calls should complete without errors:
- [ ] GET /api/stocks - list all stocks
- [ ] GET /api/stocks/{symbol} - individual stock details
- [ ] GET /api/prices/history/{symbol} - price history
- [ ] GET /api/market/technicals - market technicals
- [ ] GET /api/sectors - sector data

#### F12 Console Verification Checklist
In DevTools Console, verify:
- [ ] No red error messages (Error: ...)
- [ ] No yellow warnings about deprecated APIs
- [ ] No CORS errors
- [ ] No network 404/500 errors
- [ ] All API responses return 200 OK status
- [ ] API response times < 1000ms

## API Endpoints Reference

### Base URL (Local)
```
http://localhost:3001
```

### Endpoints
```
GET /api/stocks?limit=50                          # List stocks
GET /api/stocks/AAPL                               # Stock details
GET /api/stocks/AAPL?limit=5                       # Stock with details
GET /api/stocks?search=APPLE                       # Search stocks
GET /api/stocks?sector=Technology                  # Filter by sector

GET /api/prices/history/AAPL?limit=30              # Price history
GET /api/prices/history/AAPL?interval=weekly       # Weekly prices

GET /api/market/technicals                         # Market health
GET /api/sectors                                   # Sector list
GET /api/signals?limit=100                         # Trading signals

GET /health                                        # Health check
```

## Database Status
```
Stock Symbols:           10,153 records
Price Daily:             5,822,492 records
Buy/Sell Signals:        466,067 records
Technical Indicators:    5,000 records
Signal Quality Scores:   3 records
Market Health:           2 records
Trend Template:          3 records
```

## System Components Status
```
[OK] Database:        PostgreSQL 13+ on localhost:5432
[OK] API Handler:     Lambda function wrapper (server.py)
[OK] Frontend:        Vite dev server with React
[OK] Data Loaders:    All core loaders configured
[OK] Orchestrator:    Trading engine (dry-run verified)
```

## Troubleshooting

### API Returns 503
**Cause:** Database not connected
**Fix:** Ensure PostgreSQL is running and env vars are set:
```bash
export DB_HOST=localhost DB_PORT=5432 DB_NAME=stocks DB_USER=stocks DB_PASSWORD=password
python3 server.py
```

### CORS Errors
**Cause:** Flask server not configured correctly
**Fix:** Restart both servers and clear browser cache
```bash
# Terminal 1
python3 server.py

# Terminal 2
cd webapp/frontend && npm run dev
```

### Frontend Shows "No Data"
**Cause:** API not responding or data not loaded
**Fix:** Check F12 Network tab to verify API calls and responses

### Page Load Slow
**Cause:** Data fetching takes time
**Fix:** This is normal for first load. Wait 2-3 seconds for data to display.

## Next Steps
1. Run all tests: `python3 -m pytest tests/`
2. Run health check: `python3 run-all-loaders.py` (full refresh)
3. Deploy to AWS when ready (see ARCHITECTURE.md)
