# Economic Data & Forecasting Infrastructure - Codebase Exploration Summary

## Project Context
- **Current Date**: October 21, 2025
- **Codebase**: Stock trading algorithm with React frontend, Node.js/Express backend, Python data loaders
- **Database**: PostgreSQL with economic data tables
- **Key Service**: AWS Lambda functions with ECS containerization

---

## 1. CURRENT ECONOMIC PAGE IMPLEMENTATION

### Frontend Page: EconomicModeling.jsx
**Location**: `/home/stocks/algo/webapp/frontend/src/pages/EconomicModeling.jsx`

**Current Features**:
- Recession probability forecasting (composite model)
- Economic stress index calculation
- Yield curve analysis and inversion detection
- Leading economic indicators tracking
- Scenario planning (Base, Bull, Bear cases)
- Upcoming economic events display

**Displayed Metrics**:
1. **Recession Probability** (Composite Model)
   - Sources: NY Fed Model (35%), Goldman Sachs (25%), JP Morgan (25%), AI Ensemble (15%)
   - Range: 0-100%
   - Color-coded risk levels: Green (<20%), Yellow (20-40%), Red (>40%)

2. **Economic Stress Index** (0-100)
   - Calculated from leading indicators
   - Combines negative/positive/neutral signals

3. **GDP Growth** (Annualized Q/Q)
   - Current rate displayed with trend indicator
   - Shows vs previous quarter comparison

4. **Unemployment Rate**
   - Current rate with Sahm Rule calculation

5. **Yield Curve Analysis**
   - 2Y-10Y Spread (basis points)
   - 3M-10Y Spread (basis points)
   - Inversion status with historical accuracy (87.5% accuracy since 1970)
   - Average lead time to recession (6-24 months)

6. **Leading Economic Indicators**
   - 8+ indicators with signal strength ratings
   - Trend indicators: improving/deteriorating/stable

### Three Main Tabs:
1. **Leading Indicators Tab**
   - Individual indicator cards with signal strengths
   - Signal summary (positive/negative/neutral counts)
   - Upcoming economic events (next 30 days)

2. **Yield Curve Tab**
   - Line chart of treasury yield curve
   - Inversion analysis with historical context
   - Historical accuracy and lead time metrics

3. **Scenario Planning Tab**
   - Base Case, Bull Case, Bear Case cards
   - Probability assignments
   - Key metrics: GDP Growth, Unemployment, Fed Funds Rate

---

## 2. DATA LOADING INFRASTRUCTURE

### Python Data Loader: loadecondata.py
**Location**: `/home/stocks/algo/loadecondata.py`
**Trigger**: Part of deploy-app-stocks workflow (ECS VALIDATION FIX - DEPLOY NOW)

**Core Functionality**:
- Fetches FRED (Federal Reserve Economic Data) series
- Loads economic calendar events
- Stores data in PostgreSQL

**Supported FRED Series (56 total)**:

#### U.S. Output & Demand
- `GDPC1` - Real GDP
- `PCECC96` - Real Personal Consumption Expenditures
- `GPDI` - Gross Private Domestic Investment
- `GCEC1` - Real Government Consumption
- `EXPGSC1` - Real Exports
- `IMPGSC1` - Real Imports

#### U.S. Labor Market
- `UNRATE` - Unemployment Rate
- `PAYEMS` - Nonfarm Payrolls
- `CIVPART` - Civilian Labor Force Participation Rate
- `CES0500000003` - Average Hourly Earnings
- `AWHAE` - Average Weekly Hours
- `JTSJOL` - Job Openings
- `ICSA` - Initial Unemployment Claims
- `OPHNFB` - Labor Productivity
- `U6RATE` - U-6 Unemployment Rate

#### U.S. Inflation & Prices
- `CPIAUCSL` - Consumer Price Index
- `CPILFESL` - Core CPI (excluding food & energy)
- `PCEPI` - Personal Consumption Expenditures Price Index
- `PCEPILFE` - Core PCE
- `PPIACO` - Producer Price Index
- `MICH` - University of Michigan Consumer Sentiment
- `T5YIFR` - 5-Year Forward Inflation Expectation Rate

#### U.S. Financial & Monetary
- `FEDFUNDS` - Federal Funds Rate
- `DGS2` - 2-Year Treasury Yield
- `DGS10` - 10-Year Treasury Yield
- `T10Y2Y` - 10Y-2Y Treasury Spread
- `MORTGAGE30US` - 30-Year Fixed Mortgage Rate
- `BAA` - Moody's Baa Corporate Bond Yield
- `AAA` - Moody's Aaa Corporate Bond Yield
- `SP500` - S&P 500 Index
- `VIXCLS` - VIX Volatility Index
- `M2SL` - M2 Money Supply
- `WALCL` - Federal Reserve Balance Sheet
- `IOER` - Interest on Excess Reserves
- `IORB` - Interest on Reserve Balances

#### U.S. Housing & Construction
- `HOUST` - Housing Starts
- `PERMIT` - Building Permits
- `CSUSHPISA` - Case-Shiller Home Price Index
- `RHORUSQ156N` - Homeowner Vacancy Rate
- `RRVRUSQ156N` - Rental Vacancy Rate
- `USHVAC` - Housing Vacancies

**Database Tables Created**:

1. **economic_data**
   ```sql
   series_id TEXT NOT NULL
   date DATE NOT NULL
   value DOUBLE PRECISION
   PRIMARY KEY (series_id, date)
   ```

2. **economic_calendar**
   ```sql
   event_id VARCHAR(50) UNIQUE
   event_name VARCHAR(255) NOT NULL
   country VARCHAR(10) DEFAULT 'US'
   category VARCHAR(100)
   importance VARCHAR(20)
   currency VARCHAR(3) DEFAULT 'USD'
   event_date DATE NOT NULL
   event_time TIME
   timezone VARCHAR(50) DEFAULT 'America/New_York'
   actual_value VARCHAR(100)
   forecast_value VARCHAR(100)
   previous_value VARCHAR(100)
   unit VARCHAR(50)
   frequency VARCHAR(20)
   source VARCHAR(100)
   description TEXT
   impact_analysis TEXT
   is_revised BOOLEAN DEFAULT FALSE
   created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   ```

**Economic Calendar Data Sources** (Free/Open):
1. **FRED Releases API** - Primary source
2. **Scheduled Events Generator**:
   - FOMC meetings (8 per year, roughly every 6-7 weeks)
   - Nonfarm Payrolls (first Friday of month)
   - CPI releases (around 13th of month)
3. **Fallback**: Mock calendar data for testing

**Calendar Event Categories**:
- `monetary_policy` - Fed decisions, interest rates
- `employment` - Payroll, unemployment reports
- `inflation` - CPI, PPI releases
- `gdp` - Economic growth data
- `housing` - Housing starts, permits
- `manufacturing` - Factory output, industrial production
- `consumer` - Retail sales, consumer spending

---

## 3. BACKEND API ENDPOINTS

### Economic Routes: `/api/economic/*`
**Location**: `/home/stocks/algo/webapp/lambda/routes/economic.js`

#### Endpoints Implemented:

1. **GET /api/economic/** (Root)
   - Returns list of available routes
   - Pagination support: `?page=1&limit=25`
   - Series filtering: `?series=GDP`

2. **GET /api/economic/data**
   - Returns paginated economic data
   - Parameters: `?limit=50`
   - Returns: `series_id, date, value`

3. **GET /api/economic/indicators**
   - Category filtering: `?category=growth|inflation|employment|monetary`
   - Returns: Series with metadata
   - Simulated categories from series patterns

4. **GET /api/economic/calendar**
   - Date range filtering: `?start_date=2025-01-01&end_date=2025-12-31`
   - Importance filtering: `?importance=high|medium|low`
   - Country filtering: `?country=US`
   - Returns: Upcoming economic events

5. **GET /api/economic/series/:seriesId**
   - Get historical data for specific series
   - Parameters: `?timeframe=&frequency=&limit=100`
   - Returns: Series data with change percentages

6. **GET /api/economic/forecast**
   - Forecast series values
   - Parameters: `?series=GDP&horizon=1Q|1Y&confidence=0.95`
   - Method: Trend-adjusted moving average

7. **GET /api/economic/correlations**
   - Correlation analysis between series
   - Parameters: `?series=GDP&timeframe=2Y|5Y`
   - Returns: Correlations with other series

8. **GET /api/economic/compare**
   - Compare multiple series
   - Parameters: `?series=GDP,CPI,UNEMPLOYMENT&normalize=true|false`
   - Returns: Series data, correlation matrix

**Series Mapping** (50+ mappings):
```javascript
Examples:
'GDP' → 'GDP'
'CPI' → 'CPI'
'UNEMPLOYMENT' → 'UNRATE'
'INFLATION' → 'CPI'
'PAYROLL' → 'PAYEMS'
'FEDERAL_FUNDS' → 'FEDFUNDS'
'YIELD_CURVE' → 'T10Y2Y'
'CORE_PCE' → 'PCEPILFE'
...and 40+ more
```

### Market Routes for Economic Analysis: `/api/market/*`
**Location**: `/home/stocks/algo/webapp/lambda/routes/market.js` (6,390 lines)

#### Economic Analysis Endpoints:

1. **GET /api/market/recession-forecast**
   - Returns: Composite recession probability
   - Models: NY Fed, Goldman Sachs, JP Morgan, AI Ensemble
   - Calculation: Weighted probability from key indicators
   - Indicators used:
     - Yield spread (T10Y2Y) - Weight: 40%
     - Unemployment rate (UNRATE) - Weight: 25%
     - VIX volatility - Weight: 20%
     - Federal funds rate - Weight: 15%

2. **GET /api/market/leading-indicators**
   - Returns: Full yield curve (2Y, 5Y, 10Y, 30Y maturities)
   - Stress index calculation
   - Risk level assessment
   - Upcoming events
   - Yield curve inversion status

3. **GET /api/market/sectoral-analysis**
   - Sector performance from company profile data
   - Economic context:
     - GDP growth (GDPC1)
     - Unemployment (UNRATE)
     - Industrial production (INDPRO)
   - Sector counts and pricing

4. **GET /api/market/economic-scenarios**
   - Dynamic scenarios based on current indicators:
     - **Bull Case**: Soft landing
     - **Base Case**: Mild slowdown
     - **Bear Case**: Economic contraction
   - Calculates: Probability, GDP growth, unemployment, Fed rate
   - Returns: Weighted summary metrics

---

## 4. CURRENT DATABASE STRUCTURE

### Tables in Use:

1. **economic_data** (main)
   - 56+ FRED series
   - Historical daily/monthly data
   - Latest data from loadecondata.py

2. **economic_calendar**
   - Upcoming economic events
   - FOMC meetings, employment reports, CPI releases
   - Impact levels (High/Medium/Low)

3. **Related Tables** (from market routes):
   - `company_profile` - Sector information
   - `price_daily` - Stock prices
   - `market_data` - Market cap, market data

---

## 5. MISSING DATA & GAPS

### API Data Gaps in Frontend:

**In EconomicModeling.jsx, the following errors are shown**:

1. **"Upcoming events data not available from API endpoint"**
   - Frontend expects: `leadingData.upcomingEvents`
   - Current issue: Economic calendar not properly returned

2. **"Yield curve data not available from API endpoint"**
   - Frontend expects: `leadingData.yieldCurveData`
   - Should be: Array of `{maturity, yield}` objects
   - Currently hardcoded in market.js (lines 3597-3663)

### Missing Economic Indicators:

**Not yet loaded but potentially valuable**:
- Trailing P/E ratios
- Forward P/E ratios
- Dividend yield
- Credit spreads (detailed)
- Term structure of interest rates
- Real yields (inflation-adjusted)
- Leading Economic Index (LEI)
- Coincident Economic Index (CEI)
- Conference Board sentiment indices

### Missing Analysis Features:

1. **Predictive Models**:
   - Machine learning recession prediction
   - Time series forecasting (ARIMA, Prophet)
   - Vector autoregression (VAR)

2. **Cross-Market Analysis**:
   - Macro-financial correlations
   - Factor models
   - Risk decomposition

3. **Fundamental Analysis**:
   - Earnings forecasts
   - Valuation metrics
   - Sector rotation analysis

---

## 6. FRED DATA LOADING STATUS

### Last Update:
- **Loader**: `loadecondata.py`
- **Frequency**: Triggered by ECS workflow deployment
- **Data Freshness**: Depends on deployment schedule

### Upsert Strategy:
```sql
INSERT INTO economic_data (series_id, date, value)
VALUES %s
ON CONFLICT (series_id, date) DO UPDATE
  SET value = EXCLUDED.value;
```
- All data is upserted (replaced if exists)
- Maintains historical data integrity

---

## 7. FRONTEND-BACKEND INTEGRATION

### API Calls from EconomicModeling.jsx:
```javascript
Promise.all([
  api.get("/api/market/recession-forecast"),
  api.get("/api/market/leading-indicators"),
  api.get("/api/market/sectoral-analysis"),
  api.get("/api/market/economic-scenarios")
])
```

### Data Flow:
1. Frontend requests 4 endpoints simultaneously
2. Backend queries PostgreSQL economic_data table
3. Calculates indicators and probabilities
4. Returns structured JSON responses
5. Frontend displays in tabs and cards

### Error Handling:
- Fallback to mock data if API returns null
- User warnings for missing data sources
- Error alerts for connection failures

---

## 8. TECHNOLOGY STACK

### Backend:
- **Framework**: Express.js (Node.js)
- **Database**: PostgreSQL
- **Data Source**: FRED API (Federal Reserve)
- **Python Loader**: 
  - `fredapi` (0.5.1)
  - `psycopg2-binary` (2.9.9)
  - `pandas` (2.1.4)
  - `boto3` (1.34.69) for AWS Secrets Manager

### Frontend:
- **Framework**: React
- **UI Library**: Material-UI (MUI)
- **Charts**: Recharts
- **HTTP Client**: Axios (via api service)

### Deployment:
- **Container**: Docker/ECS
- **Secrets**: AWS Secrets Manager
- **Lambda Compatibility**: API runs on Lambda with 3-second timeouts

---

## 9. ARCHITECTURE SUMMARY

```
┌─────────────────────────────────────────────────────────┐
│                   React Frontend                         │
│          (EconomicModeling.jsx Component)               │
└────────────────┬────────────────────────────────────────┘
                 │ HTTP API Calls
                 │ /api/market/recession-forecast
                 │ /api/market/leading-indicators
                 │ /api/market/sectoral-analysis
                 │ /api/market/economic-scenarios
                 │
┌────────────────▼────────────────────────────────────────┐
│        Express.js Backend (market.js routes)            │
│    - Queries PostgreSQL economic_data table             │
│    - Calculates indicators, probabilities, scenarios    │
│    - Returns JSON responses                             │
└────────────────┬────────────────────────────────────────┘
                 │ SQL Queries
                 │
┌────────────────▼────────────────────────────────────────┐
│              PostgreSQL Database                        │
│  - economic_data (56+ FRED series)                      │
│  - economic_calendar (upcoming events)                  │
└────────────────┬────────────────────────────────────────┘
                 │ Data Refresh
                 │
┌────────────────▼────────────────────────────────────────┐
│        Python Data Loader (loadecondata.py)             │
│  - Fetches from FRED API                               │
│  - Loads calendar events                                │
│  - Upserts to economic_data table                       │
└─────────────────────────────────────────────────────────┘
```

---

## 10. KEY FINDINGS & RECOMMENDATIONS

### What's Working Well:
✅ FRED data loading infrastructure is solid
✅ 56+ economic indicators being tracked
✅ Clean database schema with proper relationships
✅ Multiple API endpoints for economic data
✅ Recession forecasting model with weighted ensemble
✅ Yield curve analysis with historical accuracy metrics
✅ Scenario planning with probabilistic models

### Critical Gaps:
❌ Yield curve data not properly returned to frontend
❌ Upcoming economic calendar events not integrated
❌ Missing real-time event tracking
❌ Hardcoded scenario data instead of dynamic calculation
❌ No cross-market correlation analysis
❌ Limited predictive modeling (basic moving average only)

### Recommendations for Comprehensive Dashboard:

**Phase 1 - Fix Integration Issues**:
1. Fix yield curve data endpoint to return chart data
2. Integrate economic calendar events properly
3. Standardize API response formats

**Phase 2 - Enhance Analysis**:
1. Add real-time price-to-earnings tracking
2. Implement factor model analysis
3. Add sector rotation signals

**Phase 3 - Advanced Modeling**:
1. Machine learning recession prediction
2. Dynamic factor models
3. Volatility forecasting
4. Portfolio stress testing

**Phase 4 - User Experience**:
1. Custom indicator selection
2. Alert configuration
3. Historical backtesting
4. Export capabilities

