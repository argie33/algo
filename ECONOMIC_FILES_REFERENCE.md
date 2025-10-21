# Economic Data System - File Reference Guide

## Quick Navigation

### Core Implementation Files

#### Frontend Components
| File | Size | Purpose |
|------|------|---------|
| `/home/stocks/algo/webapp/frontend/src/pages/EconomicModeling.jsx` | ~43KB | Main economic forecasting UI component |
| `/home/stocks/algo/webapp/frontend/src/tests/unit/pages/EconomicModeling.test.jsx` | - | Unit tests |
| `/home/stocks/algo/webapp/frontend/src/tests/component/EconomicModeling.test.jsx` | - | Component tests |
| `/home/stocks/algo/webapp/frontend/src/tests/integration/EconomicModelingIntegration.test.jsx` | - | Integration tests |

#### Backend Routes & APIs
| File | Lines | Purpose |
|------|-------|---------|
| `/home/stocks/algo/webapp/lambda/routes/economic.js` | ~814 | Economic data endpoints |
| `/home/stocks/algo/webapp/lambda/routes/market.js` | 6,390 | Market & economic analysis endpoints |

**Key Market.js Endpoints (Economic)**:
- Line 3210: `/recession-forecast`
- Line 3356: `/leading-indicators`
- Line 3671: `/sectoral-analysis`
- Line 3764: `/economic-scenarios`

#### Python Data Loaders
| File | Size | Purpose |
|------|------|---------|
| `/home/stocks/algo/loadecondata.py` | 21.4KB | FRED data loader (56 series, calendar) |
| `/home/stocks/algo/requirements-loadecondata.txt` | - | Python dependencies |
| `/home/stocks/algo/Dockerfile.econdata` | - | Container for loader |

#### Database & Configuration
| File | Purpose |
|------|---------|
| `/home/stocks/algo/webapp/lambda/seed_economic_yield_curve.sql` | Sample economic data for testing |
| `/home/stocks/algo/webapp/lambda/check_economic_series.js` | Database validation utilities |

#### Test Files
| File | Purpose |
|------|---------|
| `/home/stocks/algo/webapp/lambda/test-economic-api.js` | API testing script |
| `/home/stocks/algo/webapp/lambda/debug-economic-test.js` | Debugging utilities |
| `/home/stocks/algo/webapp/lambda/tests/unit/routes/economic.test.js` | Unit tests |
| `/home/stocks/algo/webapp/lambda/tests/integration/routes/economic.integration.test.js` | Integration tests |

---

## Data Flow Diagram

```
1. DATA COLLECTION LAYER
   ↓
   loadecondata.py (Python)
   ├─ Fetches from FRED API (56 series)
   ├─ Loads economic calendar
   └─ Writes to PostgreSQL

2. DATABASE LAYER
   ↓
   PostgreSQL
   ├─ Table: economic_data
   │  └─ (series_id, date, value)
   └─ Table: economic_calendar
      └─ (event_id, event_name, date, importance, ...)

3. BACKEND API LAYER
   ↓
   Express.js Routes
   ├─ /api/economic/* (economic.js)
   │  └─ General economic data queries
   └─ /api/market/* (market.js)
      ├─ /recession-forecast
      ├─ /leading-indicators
      ├─ /sectoral-analysis
      └─ /economic-scenarios

4. FRONTEND LAYER
   ↓
   React Components (EconomicModeling.jsx)
   ├─ Recession Probability Card
   ├─ Economic Stress Index Card
   ├─ Leading Indicators Tab
   ├─ Yield Curve Tab
   └─ Scenario Planning Tab
```

---

## Key Data Structures

### Frontend State (EconomicModeling.jsx)
```javascript
economicData: {
  forecastModels: [],           // Recession probability models
  recessionProbability: 0,       // Composite probability %
  riskLevel: "Medium",           // Low/Medium/High
  
  leadingIndicators: [],         // Array of indicators
  gdpGrowth: 0,                  // GDP %
  unemployment: 0,               // Unemployment %
  inflation: 0,                  // Inflation %
  employment: {},                // Employment details
  
  yieldCurve: {
    spread2y10y: 0,              // 2Y-10Y spread (bps)
    spread3m10y: 0,              // 3M-10Y spread (bps)
    isInverted: false,           // Inversion status
    interpretation: "",          // Human-readable text
    historicalAccuracy: 87.5,    // % accuracy
    averageLeadTime: 12          // Months
  },
  yieldCurveData: [],            // Array for chart
  
  sectoralData: [],              // Sector performance
  scenarios: [],                 // Base/Bull/Bear cases
  upcomingEvents: []             // Next 30 days events
}
```

### Economic Data Table (PostgreSQL)
```sql
Series Categories:
├─ Output (GDP, PCE, Investment)
├─ Labor Market (UNRATE, PAYEMS, Job openings)
├─ Inflation (CPI, PCE, PPI, expectations)
├─ Monetary (FEDFUNDS, Treasury yields, Fed balance)
└─ Housing (Housing starts, permits, vacancies)

Sample Row:
series_id: 'UNRATE'
date: '2025-10-21'
value: 4.1
```

### API Response Format (Recession Forecast)
```json
{
  "data": {
    "compositeRecessionProbability": 45,
    "riskLevel": "Medium",
    "forecastModels": [
      {
        "name": "NY Fed Model",
        "probability": 42
      }
    ],
    "indicators": {
      "T10Y2Y": { "value": -0.05 },
      "UNRATE": { "value": 4.1 },
      "VIXCLS": { "value": 18.5 },
      "FEDFUNDS": { "value": 3.5 }
    }
  }
}
```

---

## API Endpoint Reference

### Economic Routes (`/api/economic/*`)
```
GET  /api/economic/
GET  /api/economic/data
GET  /api/economic/indicators
GET  /api/economic/calendar
GET  /api/economic/series/:seriesId
GET  /api/economic/forecast
GET  /api/economic/correlations
GET  /api/economic/compare
```

### Market Economic Routes (`/api/market/*`)
```
GET  /api/market/recession-forecast
GET  /api/market/leading-indicators
GET  /api/market/sectoral-analysis
GET  /api/market/economic-scenarios
GET  /api/market/ai-insights
```

---

## Series Mapping Reference

Complete FRED series list (56 total):

### Output (6)
- GDP, GDPC1, PCECC96, GPDI, GCEC1, EXPGSC1, IMPGSC1

### Labor (9)
- UNRATE, PAYEMS, CIVPART, CES0500000003, AWHAE, JTSJOL, ICSA, OPHNFB, U6RATE

### Inflation (7)
- CPIAUCSL, CPILFESL, PCEPI, PCEPILFE, PPIACO, MICH, T5YIFR

### Monetary (14)
- FEDFUNDS, DGS2, DGS10, T10Y2Y, MORTGAGE30US, BAA, AAA, SP500, VIXCLS, M2SL, WALCL, IOER, IORB

### Housing (6)
- HOUST, PERMIT, CSUSHPISA, RHORUSQ156N, RRVRUSQ156N, USHVAC

---

## Implementation Status

### ✅ Completed Features
- [x] FRED data loader (56 series)
- [x] Economic calendar infrastructure
- [x] Recession probability calculation
- [x] Yield curve analysis
- [x] Leading indicators tracking
- [x] Scenario planning
- [x] Economic data API endpoints
- [x] Frontend UI components

### ❌ Known Issues
- [ ] Yield curve chart data not returned to frontend
- [ ] Economic calendar events not properly integrated
- [ ] Hardcoded yield curve test data (lines 3597-3663 in market.js)
- [ ] Upcoming events show error in frontend

### 🔧 To Implement
- [ ] Real-time price/earnings tracking
- [ ] Macro factor models
- [ ] ML recession prediction
- [ ] Cross-market correlation analysis
- [ ] Advanced scenario modeling
- [ ] Alert configuration UI

---

## Debugging Commands

```bash
# Test economic data loading
python /home/stocks/algo/loadecondata.py

# Check FRED series in database
curl "http://localhost:3000/api/economic/indicators"

# Test recession forecast
curl "http://localhost:3000/api/market/recession-forecast"

# Test leading indicators
curl "http://localhost:3000/api/market/leading-indicators"

# Seed test data
psql -f /home/stocks/algo/webapp/lambda/seed_economic_yield_curve.sql
```

---

## Key Dependencies

### Python
- `fredapi` (0.5.1) - FRED API client
- `pandas` (2.1.4) - Data manipulation
- `psycopg2-binary` (2.9.9) - PostgreSQL driver
- `boto3` (1.34.69) - AWS integration

### Node.js
- `express` - API framework
- `recharts` - Charting library (frontend)
- `@mui/material` - UI components

---

## Environment Variables Required

```
# For loadecondata.py
DB_SECRET_ARN=arn:aws:secretsmanager:region:account:secret:...
FRED_API_KEY=your_fred_api_key

# Database connection (via Secrets Manager)
- username
- password
- host
- port
- dbname
```

---

## Performance Notes

### Database Optimization
- Primary key on (series_id, date) for fast lookups
- 56 series × ~600 monthly data points = ~33.6K base rows
- Full history loaded on data refresh

### API Performance
- 3-second timeout on Lambda functions
- Parallel Promise.all() for multiple endpoints
- Series caching at DB level via upsert strategy

### Frontend Performance
- React.useMemo() for indicator calculations
- Tab switching to reduce component renders
- Error fallbacks to prevent UI crashes

---

## Testing Strategy

### Unit Tests
- Individual indicator calculations
- API response parsing
- Database connection handling

### Integration Tests
- Full data flow from FRED → DB → API → Frontend
- Calendar event generation and loading
- Scenario probability calculations

### E2E Tests
- Complete user workflows
- Chart rendering
- Error state handling

