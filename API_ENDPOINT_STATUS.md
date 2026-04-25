# API Endpoint Status Report

## BASE ENDPOINTS

### GET /api
✓ Working - Returns list of all available API endpoints
```
Endpoints:
- /api/auth
- /api/commodities  
- /api/earnings
- /api/economic
- /api/financials
- /api/health
- /api/market
- /api/portfolio
- /api/price
- /api/scores
- /api/sectors
- /api/sentiment
- /api/signals
- /api/user
- /api/trades
```

## STOCKS ENDPOINTS

### GET /api/stocks
✓ Working - Lists all stocks with pagination
- Returns: symbol, name, category, exchange
- Pagination: limit, offset, total, page

### GET /api/stocks/search?q=...
✓ Working - Search stocks by symbol or name
- Parameters: q (query), limit, offset
- Case-insensitive LIKE search

### GET /api/stocks/:symbol
✓ Working - Get details for a specific stock
- Returns: symbol, name, category, exchange

### GET /api/stocks/deep-value?limit=...
✗ BROKEN - Returns empty results
- Issue: No stocks have non-NULL value_score in stock_scores table
- Requires: loadstockscores.py must populate value_score field

## SCORES ENDPOINTS

### GET /api/scores/stockscores?...
✓ Working - Get stock scores with sorting/filtering
- Returns: symbol, composite_score, momentum_score, and metric inputs
- Pagination: page, limit, total, totalPages
- Note: value_score and quality_score are NULL

## MARKET ENDPOINTS

### GET /api/market/overview
✓ Working - Market overview with top stocks and sentiment
- Returns: market_status, quality counts, top 10 stocks, breadth, volatility, AAII sentiment
- Note: value_score is NULL in top_stocks

### GET /api/market/breadth
✓ Working - Market breadth data
- Returns: total_stocks, advancing, declining, unchanged, ratios, averages

### GET /api/market/indices
Status: Unknown - Not tested

## SECTORS ENDPOINTS

### GET /api/sectors
✓ Working - Returns sectors API index and available routes
- Shows: /sectors, /trend/:name, /:sector/stocks, /:sector/details

### GET /api/sectors/trend/:sectorName
✗ BROKEN - Returns "No trend data found"
- Issue: Sector trend data not populating correctly
- Root cause: Unknown (needs investigation)

## FINANCIALS ENDPOINTS

### GET /api/financials
✓ Working - Returns financials API index with available endpoints

### GET /api/financials/:symbol/balance-sheet
✗ BROKEN - Returns "Failed to fetch balance sheet"
- Issue: annual_balance_sheet table doesn't exist or has no data
- Requires: loadannualbalancesheet.py must run successfully

### GET /api/financials/:symbol/income-statement
Status: Unknown - Likely broken (requires annual_income_statement table)

### GET /api/financials/:symbol/cash-flow
Status: Unknown - Likely broken (requires annual_cash_flow table)

## KNOWN ISSUES & BLOCKERS

1. **value_score, quality_score, stability_score are NULL in stock_scores**
   - Blocks: /stocks/deep-value, full market analysis
   - Requires: loadstockscores.py to populate these fields
   - Severity: HIGH

2. **Financial statement tables missing data**
   - Blocks: /financials endpoints
   - Missing tables: annual_income_statement, annual_balance_sheet, annual_cash_flow
   - Requires: Corresponding loaders to run successfully
   - Severity: MEDIUM (non-critical features)

3. **Sector trend data not available**
   - Blocks: /sectors/trend endpoint
   - Root cause: Unknown - needs debugging
   - Severity: MEDIUM

## RECOMMENDATIONS

1. **IMMEDIATE**: Run loadstockscores.py to populate quality_score and value_score in stock_scores table
2. **NEXT**: Run remaining loaders for financial data and complete sector data
3. **DEBUG**: Investigate why sector trends aren't loading
4. **TEST**: Re-test all endpoints once data is fully populated
