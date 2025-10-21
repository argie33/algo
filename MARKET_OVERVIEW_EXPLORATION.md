# MarketOverview Page - Comprehensive Analysis

## Current Page Structure & Display

### MarketOverview.jsx Components
The page displays market data in multiple sections:

1. **Major Indices Display** (Top of page)
   - S&P 500, NASDAQ, Dow Jones, Russell 2000, VIX
   - Shows: symbol, price, change %, change amount

2. **Sentiment Indicators Cards**
   - Fear & Greed Index (0-100 scale)
   - NAAIM Exposure (0-100 scale)
   - AAII Sentiment (Bullish/Neutral/Bearish %)

3. **Top Movers Section**
   - Top 5 Gainers with price & % change
   - Top 5 Losers with price & % change

4. **Market Breadth Section**
   - Advancing/Declining/Unchanged counts
   - Advance/Decline ratio
   - Average change percentage

5. **Market Statistics**
   - Total stocks
   - Total market cap
   - Large/Mid/Small cap distribution

6. **Distribution Days** (IBD Methodology)
   - SPY, QQQ, IWM distribution day counts
   - Signal status: NORMAL, ELEVATED, CAUTION, UNDER_PRESSURE

7. **Tabbed Sections**
   - Tab 0: Sentiment History (30-day charts for Fear/Greed, NAAIM, AAII)
   - Tab 1: Market Breadth Details (pie charts)
   - Tab 2: Seasonality Analysis

## API Endpoints Currently Used

### Frontend API Calls (api.js)
```
GET /api/market/overview           → getMarketOverview()
GET /api/market/sentiment/history  → getMarketSentimentHistory(days)
GET /api/market/breadth            → getMarketBreadth()
GET /api/market/distribution-days  → getDistributionDays()
GET /api/seasonality-data          → getSeasonalityData()
```

### Backend Routes (market.js)
```
GET /market/overview           - Main market overview data
GET /market/summary            - Market summary with indices & breadth
GET /market/sentiment/history  - Sentiment indicators history
GET /market/breadth           - Market breadth data
GET /market/distribution-days - Distribution days by index
GET /market/seasonality       - Seasonality analysis data
GET /market/indices           - Market indices
GET /market/data              - Generic market data endpoint
```

## Data Sources & Loaders

### 1. Market Data Loader (loadmarket.py)
**Purpose**: Collect comprehensive market data for indices and ETFs
**Data Collected**:
- Price, volume, market cap
- Returns: 1d, 5d, 1m, 3m, 6m, 1y
- Volatility: 30d, 90d, 1y
- Moving averages: 20, 50, 200 day
- Technical: 52-week high/low, distance metrics
- Beta calculation (vs SPY)
- Asset classification (index, broad_market_etf, sector_etf, etc.)
- Geographic region classification

**Symbols Tracked**:
- Major US Indices: ^GSPC, ^IXIC, ^DJI, ^RUT, ^VIX
- Broad Market ETFs: SPY, QQQ, DIA, IWM, VTI
- International: ^FTSE, ^N225, ^HSI, EEM, VEA, VWO
- Bonds: ^TNX, ^IRX, TLT, BND, HYG
- Commodities: GLD, SLV, USO, UNG, DBA
- Sector ETFs: XLF, XLK, XLE, XLV, XLI, XLC, XLY, XLP, XLB, XLRE, XLU
- Style ETFs: IVV, IVW, IVE, IJH, IJR, VBR, VUG, VTV

**Database Table**: market_data
- Symbol, name, date
- Price, volume, market cap
- Returns (6 columns)
- Volatility (3 columns)
- Moving averages & distances (6 columns)
- High/low metrics (4 columns)
- Volume & beta (3 columns)
- Asset classification (2 columns)

### 2. Fear & Greed Index Loader (loadfeargreed.py)
**Purpose**: Scrape CNN Fear & Greed Index daily
**Data**:
- Date
- Index value (0-100)
- Rating (classification)

**Source**: https://production.dataviz.cnn.io/index/fearandgreed/graphdata
**Database Table**: fear_greed_index

### 3. AAII Sentiment Data Loader (loadaaiidata.py)
**Purpose**: Download AAII investor sentiment survey data weekly
**Data**:
- Date
- Bullish %
- Neutral %
- Bearish %

**Source**: https://www.aaii.com/files/surveys/sentiment.xls
**Database Table**: aaii_sentiment_survey (implied)

### 4. NAAIM Exposure Loader (loadnaaim.py)
**Purpose**: Load NAAIM manager equity exposure data
**Data**:
- Date
- Mean exposure (0-100)
- Bearish exposure

**Source**: NAAIM website/API
**Database Table**: market_sentiment (implied)

### 5. Market Breadth Data
**Source**: Calculated from price_daily table
**Query Logic**: 
- Counts advancing/declining/unchanged from daily price changes
- Calculates advance/decline ratio
- Average change percentage across all stocks

### 6. Distribution Days (IBD Methodology)
**Definition**: Down 0.2%+ on higher volume over 25-day window
**Indices Tracked**: SPY, QQQ, IWM
**Signal Levels**: NORMAL, ELEVATED, CAUTION, UNDER_PRESSURE
**Database Table**: distribution_days (implied) or calculated

### 7. Seasonality Data
**Analysis Types**:
- Monthly seasonality (average returns by month)
- Quarterly patterns
- Presidential cycle (4-year pattern)
- Day of week effects
- Holiday effects
- Sector seasonality by month

## Database Schema Summary

### Key Tables
1. **market_data** - Market indices/ETF daily metrics
2. **price_daily** - Daily price data for all stocks
3. **fear_greed_index** - Daily Fear & Greed values
4. **aaii_sentiment_survey** - Weekly AAII sentiment
5. **market_sentiment** - NAAIM and other sentiment data
6. **distribution_days** - IBD-style distribution day tracking
7. **company_profile** - Stock/sector information
8. **sector_etf** - Sector performance data

## Data Duplication Issues to Avoid

### Already Displayed on Other Pages
1. **StockScreener.jsx** 
   - Shows individual stock scores
   - Do NOT duplicate stock-specific analysis

2. **SectorAnalysis.jsx**
   - Shows sector performance in detail
   - MarketOverview shows only top sectors briefly

3. **Dashboard/Dashboard.jsx**
   - May show summary market data
   - Keep consistency with summary level

### Duplication Prevention Strategy
- MarketOverview = HIGH-LEVEL market-wide metrics
- SectorAnalysis = DETAILED sector breakdown
- StockScreener = INDIVIDUAL stock analysis
- Dashboard = SUMMARY of all data

## Potential Market Data Enhancements

### Currently Missing but Available
1. **VIX Volatility Index**
   - Already loaded in loadmarket.py
   - Can add: Current VIX level, 1-month trend, historical range
   - Use case: Market volatility context

2. **Yield Curve Data**
   - Treasury yields (TNX, IRX already loaded)
   - Missing: Inverted yield curve detection, 2Y-10Y spread
   - Use case: Recession/economic health indicator

3. **Market Breadth Indicators**
   - Currently: Simple advancing/declining counts
   - Missing: McClellan Oscillator, McClellan Summation
   - Could calculate from price_daily

4. **Put/Call Ratio**
   - Currently: Not loaded
   - Data source: CBOE options data
   - Use case: Options market sentiment

5. **Market Momentum**
   - Currently: Not prominently displayed
   - Could calculate: RSI, MACD on indices
   - Use case: Trend confirmation

6. **Smart Money vs Retail Sentiment**
   - NAAIM (professional managers) - loaded
   - AAII (retail) - loaded
   - Divergence analysis - opportunity

7. **Technical Levels**
   - Support/Resistance on major indices
   - Currently: Calculated in price data
   - Could add: Key technical levels display

8. **Earnings Calendar Impact**
   - Earnings dates for major stocks
   - Could show upcoming high-impact earnings
   - Use case: Market catalyst awareness

9. **Economic Calendar Indicators**
   - FRED API integration opportunity
   - Interest rates, unemployment, inflation
   - CPI, Fed decisions, GDP

10. **Sector Momentum**
    - Currently: Static sector returns
    - Missing: Sector relative strength vs market

## Configuration for Data Sources

### Environment Variables / Secrets
- DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
- DB_SECRET_ARN (AWS Secrets Manager)
- yfinance API (free, integrated)
- AAII Excel file (public URL)
- CNN Fear & Greed (public API)

### Update Frequency Recommendations
- Market data: Daily after market close
- Fear & Greed: Daily
- AAII: Weekly (published Thursday)
- NAAIM: Weekly (published Friday)
- Distribution days: Daily
- Seasonality: Monthly

## API Response Structure

### Standard Response Format
```json
{
  "success": true,
  "data": {
    // endpoint-specific data
  },
  "metadata": {
    "source": "table_name",
    "count": 10,
    "timestamp": "ISO-8601"
  },
  "timestamp": "ISO-8601"
}
```

### Error Handling
- 503: Backend offline (expected)
- 502: Gateway error (infrastructure)
- 500: Server error
- 404: Endpoint not found
- 401: Authentication failed
