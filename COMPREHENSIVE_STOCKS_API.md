# Comprehensive Stocks API Endpoints

## Overview
The stocks API has been updated to provide comprehensive company, market, and financial data from all the tables populated by the `loadinfo.py` script. This gives you access to rich financial data, analyst estimates, governance scores, and executive information.

## Main Endpoints

### 1. GET `/api/stocks/` - Comprehensive Stock Data
**Returns comprehensive stock data with all available company information**

**Data Sources:**
- `stock_symbols` - Basic stock symbol information
- `company_profile` - Company details, sector, industry, business summary
- `market_data` - Current prices, volume, market cap, 52-week ranges
- `key_metrics` - Financial ratios, P/E, revenue, margins, cash flow
- `analyst_estimates` - Price targets and analyst recommendations  
- `governance_scores` - ESG and governance risk scores
- `leadership_team` - Executive count (details via separate endpoint)

**Query Parameters:**
- `page` (default: 1) - Page number for pagination
- `limit` (default: 50, max: 200) - Records per page
- `search` - Search by symbol or company name
- `exchange` - Filter by exchange
- `sortBy` - Sort column (symbol, name, exchange, etc.)
- `sortOrder` - asc/desc

**Response Structure:**
```json
{
  "success": true,
  "performance": "COMPREHENSIVE LOADINFO DATA - All company profiles, market data, financial metrics, analyst estimates, and governance scores from loadinfo tables",
  "data": [
    {
      "ticker": "AAPL",
      "symbol": "AAPL", 
      "name": "Apple Inc.",
      "fullName": "Apple Inc.",
      "shortName": "Apple",
      "displayName": "Apple Inc.",
      
      "exchange": "NASDAQ",
      "fullExchangeName": "NASDAQ Global Select",
      "marketCategory": "Q",
      "market": "us_market",
      
      "sector": "Technology",
      "sectorDisplay": "Technology",
      "industry": "Consumer Electronics",
      "industryDisplay": "Consumer Electronics",
      "businessSummary": "Company description...",
      "employeeCount": 164000,
      
      "website": "https://www.apple.com",
      "investorRelationsWebsite": "https://investor.apple.com",
      "address": {
        "street": "One Apple Park Way",
        "city": "Cupertino", 
        "state": "CA",
        "postalCode": "95014",
        "country": "United States"
      },
      "phoneNumber": "408-996-1010",
      
      "currency": "USD",
      "quoteType": "EQUITY",
      
      "price": {
        "current": 150.25,
        "previousClose": 149.50,
        "open": 150.00,
        "dayLow": 149.75,
        "dayHigh": 151.00,
        "fiftyTwoWeekLow": 124.17,
        "fiftyTwoWeekHigh": 199.62,
        "fiftyDayAverage": 145.50,
        "twoHundredDayAverage": 155.75,
        "bid": 150.20,
        "ask": 150.30,
        "marketState": "REGULAR"
      },
      
      "volume": 45000000,
      "averageVolume": 50000000,
      "marketCap": 2400000000000,
      
      "financialMetrics": {
        "trailingPE": 25.5,
        "forwardPE": 22.1,
        "priceToSales": 6.8,
        "priceToBook": 12.5,
        "pegRatio": 1.2,
        "bookValue": 12.25,
        "enterpriseValue": 2450000000000,
        "evToRevenue": 6.2,
        "evToEbitda": 18.5,
        "totalRevenue": 394000000000,
        "netIncome": 99000000000,
        "ebitda": 130000000000,
        "grossProfit": 170000000000,
        "epsTrailing": 6.15,
        "epsForward": 6.85,
        "epsCurrent": 6.50,
        "priceEpsCurrent": 23.1,
        "earningsGrowthQuarterly": 0.08,
        "revenueGrowth": 0.05,
        "earningsGrowth": 0.07,
        "totalCash": 165000000000,
        "cashPerShare": 10.50,
        "operatingCashflow": 104000000000,
        "freeCashflow": 92000000000,
        "totalDebt": 110000000000,
        "debtToEquity": 1.65,
        "quickRatio": 0.88,
        "currentRatio": 1.07,
        "profitMargin": 25.1,
        "grossMargin": 43.3,
        "ebitdaMargin": 33.0,
        "operatingMargin": 30.5,
        "returnOnAssets": 20.1,
        "returnOnEquity": 147.4,
        "dividendRate": 0.92,
        "dividendYield": 0.61,
        "fiveYearAvgDividendYield": 1.2,
        "payoutRatio": 14.9
      },
      
      "analystData": {
        "targetPrices": {
          "high": 200.0,
          "low": 140.0,
          "mean": 175.0,
          "median": 172.0
        },
        "recommendation": {
          "key": "BUY",
          "mean": 2.1,
          "rating": 2.0
        },
        "analystCount": 35
      },
      
      "governance": {
        "auditRisk": 2,
        "boardRisk": 1,
        "compensationRisk": 3,
        "shareholderRightsRisk": 2,
        "overallRisk": 2
      },
      
      "leadership": {
        "executiveCount": 8,
        "hasLeadershipData": true,
        "detailsAvailable": true
      },
      
      "hasCompanyProfile": true,
      "hasMarketData": true, 
      "hasFinancialMetrics": true,
      "hasAnalystData": true,
      "hasGovernanceData": true,
      "hasLeadershipData": true,
      
      "displayData": {
        "primaryExchange": "NASDAQ Global Select",
        "category": "Q",
        "type": "Stock",
        "tradeable": true,
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "keyMetrics": {
          "pe": 25.5,
          "marketCap": 2400000000000,
          "revenue": 394000000000,
          "profitMargin": 25.1,
          "dividendYield": 0.61,
          "analystRating": "BUY",
          "targetPrice": 175.0
        },
        "riskProfile": {
          "overall": 2,
          "hasHighRisk": false,
          "hasModerateRisk": false, 
          "hasLowRisk": true
        }
      }
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 50,
    "total": 8500,
    "totalPages": 170,
    "hasNext": true,
    "hasPrev": false
  },
  "metadata": {
    "totalStocks": 8500,
    "currentPage": 1,
    "showingRecords": 50,
    "dataSources": [
      "stock_symbols", "company_profile", "market_data", "key_metrics",
      "analyst_estimates", "governance_scores", "leadership_team"
    ],
    "comprehensiveData": {
      "includesCompanyProfiles": true,
      "includesMarketData": true,
      "includesFinancialMetrics": true,
      "includesAnalystEstimates": true,
      "includesGovernanceScores": true,
      "includesLeadershipTeam": true
    },
    "endpoints": {
      "leadershipDetails": "/api/stocks/leadership/:ticker",
      "leadershipSummary": "/api/stocks/leadership"
    }
  }
}
```

### 2. GET `/api/stocks/leadership/:ticker?` - Executive Leadership Data
**Returns detailed executive and leadership information**

**Parameters:**
- `:ticker` (optional) - Get leadership for specific company
- `limit` (default: 50, max: 200) - For summary endpoint only

**Examples:**
- `/api/stocks/leadership/AAPL` - Apple executives
- `/api/stocks/leadership?limit=20` - Top 20 highest-paid executives

**Response Structure:**
```json
{
  "success": true,
  "ticker": "AAPL",
  "data": [
    {
      "ticker": "AAPL",
      "companyName": "Apple",
      "executiveInfo": {
        "name": "Timothy D. Cook",
        "title": "Chief Executive Officer",
        "age": 62,
        "birthYear": 1960
      },
      "compensation": {
        "totalPay": 98734394,
        "exercisedValue": 0,
        "unexercisedValue": 0,
        "fiscalYear": 2023
      },
      "roleSource": "yahoo"
    }
  ],
  "count": 8,
  "endpoint": "leadership_by_ticker"
}
```

## Data Quality & Availability

The API indicates data availability for each stock with boolean flags:
- `hasCompanyProfile` - Company details available
- `hasMarketData` - Current market prices available  
- `hasFinancialMetrics` - Financial ratios and metrics available
- `hasAnalystData` - Analyst estimates and recommendations available
- `hasGovernanceData` - ESG/governance risk scores available
- `hasLeadershipData` - Executive information available

## Performance Features

- **Fast Queries:** Optimized LEFT JOINs across all loadinfo tables
- **Pagination:** Built-in pagination with configurable limits
- **Search & Filter:** Search by symbol/name, filter by exchange
- **Sorting:** Sortable by multiple columns
- **Rich Display Data:** Pre-formatted data for easy frontend display

## Integration Notes

1. **Frontend Integration:** The `displayData` object contains pre-formatted values perfect for UI display
2. **Risk Assessment:** The `riskProfile` object categorizes governance risk levels
3. **Data Completeness:** Use the `has*Data` flags to conditionally display sections
4. **Executive Details:** Use the leadership endpoint for detailed executive compensation data
5. **Performance:** The API returns comprehensive data in a single query for optimal performance

## Testing

Use the provided test script:
```bash
python test_comprehensive_stocks.py
```

This tests both the main stocks endpoint and the leadership endpoint to verify all data is being returned correctly.
