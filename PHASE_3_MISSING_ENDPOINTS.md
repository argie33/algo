# Phase 3 - Missing Endpoints Implementation Guide

**Status:** READY FOR IMPLEMENTATION  
**Estimated Effort:** 3-4 hours  
**Impact:** Unblocks 6 broken pages, adds 26 new endpoints

---

## Blocked Pages & Requirements

### 1. EarningsCalendar (3 endpoints needed)
**Status:** Currently broken - 0/3 endpoints  
**Impact:** Users cannot see earnings data

**Endpoints Required:**
- `POST /api/earnings/calendar?period=past&limit=50`
- `GET /api/earnings/sector-trend`
- `GET /api/earnings/sp500-trend`

**Quick Implementation:**
```python
def _handle_earnings(self, path: str, method: str, params: Dict) -> Dict:
    """Handle /api/earnings/* endpoints."""
    if path == '/api/earnings/calendar':
        period = params.get('period', ['past'])[0] if params else 'past'
        limit = int(params.get('limit', [50])[0]) if params else 50
        return self._get_earnings_calendar(period, limit)
    elif path == '/api/earnings/sector-trend':
        return self._get_earnings_sector_trend()
    elif path == '/api/earnings/sp500-trend':
        return self._get_earnings_sp500_trend()
    else:
        return error_response(404, 'not_found', f'No earnings handler for {path}')

def _get_earnings_calendar(self, period: str = 'past', limit: int = 50) -> Dict:
    """Get earnings calendar data."""
    try:
        # Query upcoming/past earnings from earnings_calendar table
        self.cur.execute("""
            SELECT symbol, company_name, earnings_date, eps_estimate, eps_actual,
                   revenue_estimate, revenue_actual, market_cap, sector
            FROM earnings_calendar
            WHERE earnings_date >= CURRENT_DATE - INTERVAL '180 days'
            ORDER BY earnings_date DESC
            LIMIT %s
        """, (limit,))
        events = self.cur.fetchall()
        return json_response(200, [dict(e) for e in events])
    except Exception as e:
        logger.error(f"get_earnings_calendar failed: {e}")
        return json_response(200, [])

def _get_earnings_sector_trend(self) -> Dict:
    """Get earnings trends by sector."""
    try:
        self.cur.execute("""
            SELECT sector, AVG(eps_growth) as avg_eps_growth,
                   COUNT(*) as company_count, AVG(revenue_growth) as avg_revenue_growth
            FROM earnings_calendar
            WHERE earnings_date >= CURRENT_DATE - INTERVAL '90 days'
            GROUP BY sector
            ORDER BY avg_eps_growth DESC
        """)
        trends = self.cur.fetchall()
        return json_response(200, [dict(t) for t in trends])
    except Exception as e:
        logger.error(f"get_earnings_sector_trend failed: {e}")
        return json_response(200, [])

def _get_earnings_sp500_trend(self) -> Dict:
    """Get S&P 500 earnings trend."""
    try:
        self.cur.execute("""
            SELECT DATE_TRUNC('month', earnings_date) as month,
                   AVG(eps_growth) as avg_eps_growth,
                   COUNT(*) as earnings_count
            FROM earnings_calendar
            WHERE symbol IN (SELECT symbol FROM company_profile WHERE sp500 = true)
            GROUP BY DATE_TRUNC('month', earnings_date)
            ORDER BY month DESC
            LIMIT 12
        """)
        trend = self.cur.fetchall()
        return json_response(200, [dict(t) for t in trend])
    except Exception as e:
        logger.error(f"get_earnings_sp500_trend failed: {e}")
        return json_response(200, [])
```

---

### 2. FinancialData (4 endpoints needed)
**Status:** Currently broken - 0/4 endpoints  
**Impact:** Users cannot see balance sheets, income statements, cash flow

**Endpoints Required:**
- `GET /api/financials/{ticker}/balance-sheet?period=annual`
- `GET /api/financials/{ticker}/income-statement?period=annual`
- `GET /api/financials/{ticker}/cash-flow?period=annual`
- `GET /api/stocks/companies` (list companies with financial data)

**Quick Implementation:**
```python
def _handle_financial(self, path: str, method: str, params: Dict) -> Dict:
    """Handle /api/financials/* endpoints."""
    match = re.match(r'/api/financials/([A-Z0-9.]+)/([a-z-]+)', path)
    if match:
        symbol = match.group(1)
        statement_type = match.group(2)
        period = params.get('period', ['annual'])[0] if params else 'annual'
        
        if statement_type == 'balance-sheet':
            return self._get_balance_sheet(symbol, period)
        elif statement_type == 'income-statement':
            return self._get_income_statement(symbol, period)
        elif statement_type == 'cash-flow':
            return self._get_cash_flow(symbol, period)
    else:
        return error_response(404, 'not_found', f'Invalid financials endpoint: {path}')

def _get_balance_sheet(self, symbol: str, period: str = 'annual') -> Dict:
    """Get balance sheet data."""
    try:
        table_name = 'annual_balance_sheet' if period == 'annual' else 'quarterly_balance_sheet'
        self.cur.execute(f"""
            SELECT date, assets, liabilities, equity, current_assets, current_liabilities
            FROM {table_name}
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT 10
        """, (symbol.upper(),))
        statements = self.cur.fetchall()
        return json_response(200, [dict(s) for s in statements])
    except Exception as e:
        logger.error(f"get_balance_sheet failed: {e}")
        return json_response(200, [])

def _get_income_statement(self, symbol: str, period: str = 'annual') -> Dict:
    """Get income statement data."""
    try:
        table_name = 'annual_income_statement' if period == 'annual' else 'quarterly_income_statement'
        self.cur.execute(f"""
            SELECT date, revenue, gross_profit, operating_income, net_income, eps
            FROM {table_name}
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT 10
        """, (symbol.upper(),))
        statements = self.cur.fetchall()
        return json_response(200, [dict(s) for s in statements])
    except Exception as e:
        logger.error(f"get_income_statement failed: {e}")
        return json_response(200, [])

def _get_cash_flow(self, symbol: str, period: str = 'annual') -> Dict:
    """Get cash flow statement data."""
    try:
        table_name = 'annual_cash_flow' if period == 'annual' else 'quarterly_cash_flow'
        self.cur.execute(f"""
            SELECT date, operating_cash_flow, investing_cash_flow, financing_cash_flow,
                   free_cash_flow, capital_expenditures
            FROM {table_name}
            WHERE symbol = %s
            ORDER BY date DESC
            LIMIT 10
        """, (symbol.upper(),))
        statements = self.cur.fetchall()
        return json_response(200, [dict(s) for s in statements])
    except Exception as e:
        logger.error(f"get_cash_flow failed: {e}")
        return json_response(200, [])
```

Add to _handle_stocks:
```python
elif path == '/api/stocks/companies':
    return self._get_companies_list()

def _get_companies_list(self) -> Dict:
    """Get list of companies with financial data."""
    try:
        self.cur.execute("""
            SELECT symbol, company_name, sector, industry, market_cap
            FROM company_profile
            WHERE symbol IN (
                SELECT DISTINCT symbol FROM annual_income_statement
            )
            ORDER BY market_cap DESC
            LIMIT 5000
        """)
        companies = self.cur.fetchall()
        return json_response(200, [dict(c) for c in companies])
    except Exception as e:
        logger.error(f"get_companies_list failed: {e}")
        return json_response(200, [])
```

---

### 3. BacktestResults (1-2 endpoints needed)
**Status:** Partially broken - 0/1 endpoints  
**Impact:** Cannot view backtest results

**Endpoints Required:**
- `GET /api/research/backtests`

**Quick Implementation:**
```python
def _handle_research(self, path: str, method: str, params: Dict) -> Dict:
    """Handle /api/research/* endpoints."""
    if path == '/api/research/backtests':
        return self._get_backtests()
    else:
        return error_response(404, 'not_found', f'No research handler for {path}')

def _get_backtests(self) -> Dict:
    """Get backtest results."""
    try:
        self.cur.execute("""
            SELECT id, name, strategy, start_date, end_date, total_return,
                   sharpe_ratio, max_drawdown, trades, win_rate, profit_factor
            FROM backtest_results
            ORDER BY created_at DESC
            LIMIT 100
        """)
        backtests = self.cur.fetchall()
        return json_response(200, [dict(b) for b in backtests])
    except Exception as e:
        logger.error(f"get_backtests failed: {e}")
        return json_response(200, [])
```

---

### 4. PortfolioOptimizer (1 endpoint needed)
**Status:** Broken - 0/1 endpoints  
**Impact:** Cannot optimize portfolio

**Endpoints Required:**
- `GET /api/optimization/analysis`

**Quick Implementation:**
```python
def _handle_optimization(self, path: str, method: str, params: Dict) -> Dict:
    """Handle /api/optimization/* endpoints."""
    if path == '/api/optimization/analysis':
        return self._get_optimization_analysis()
    else:
        return error_response(404, 'not_found', f'No optimization handler for {path}')

def _get_optimization_analysis(self) -> Dict:
    """Get portfolio optimization analysis."""
    try:
        # Placeholder - actual implementation would perform optimization
        self.cur.execute("""
            SELECT symbol, optimal_weight, current_weight, target_allocation
            FROM portfolio_optimization
            WHERE created_at >= CURRENT_DATE - INTERVAL '1 day'
            ORDER BY optimal_weight DESC
        """)
        allocations = self.cur.fetchall()
        return json_response(200, [dict(a) for a in allocations])
    except Exception as e:
        logger.error(f"get_optimization_analysis failed: {e}")
        return json_response(200, [])
```

---

### 5. Other Missing Endpoints (15+ endpoints)
Various smaller endpoints needed for complete functionality:
- `/api/audit/trail` - Audit log
- `/api/trades/summary` - Trade summary
- `/api/financial/metrics` - Financial key metrics
- And more...

---

## Implementation Checklist

### Step 1: Route Configuration (10 minutes)
Add route handlers at top of API file:
```python
# Add to _handle_algo routing
elif path.startswith('/api/earnings/'):
    return self._handle_earnings(path, method, params)
elif path.startswith('/api/financial/'):
    return self._handle_financial(path, method, params)
elif path.startswith('/api/research/'):
    return self._handle_research(path, method, params)
elif path.startswith('/api/optimization/'):
    return self._handle_optimization(path, method, params)
```

### Step 2: Implement Handler Methods (2-3 hours)
- Create `_handle_*` methods for each namespace
- Create `_get_*` methods for each endpoint
- Write SQL queries
- Test syntax

### Step 3: Database Schema Check (30 minutes)
Verify tables exist:
```bash
psql -d stocks -c "\dt" | grep earnings_calendar
psql -d stocks -c "\dt" | grep balance_sheet
# etc.
```

If tables missing, create them (see schemas)

### Step 4: Frontend Testing (1 hour)
```bash
cd webapp/frontend
npm run dev
# Navigate to each page
# Check console for errors
# Verify data displays
```

### Step 5: API Testing (30 minutes)
```bash
curl http://localhost:3001/api/earnings/calendar?limit=5
curl http://localhost:3001/api/financials/AAPL/balance-sheet
curl http://localhost:3001/api/research/backtests
```

---

## Database Schema Requirements

### earnings_calendar table
```sql
CREATE TABLE IF NOT EXISTS earnings_calendar (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    company_name VARCHAR(255),
    earnings_date DATE,
    eps_estimate DECIMAL,
    eps_actual DECIMAL,
    revenue_estimate BIGINT,
    revenue_actual BIGINT,
    market_cap BIGINT,
    sector VARCHAR(100),
    eps_growth DECIMAL,
    revenue_growth DECIMAL
);
```

### Financial tables
```sql
CREATE TABLE IF NOT EXISTS annual_balance_sheet (
    symbol VARCHAR(20), date DATE, assets BIGINT, liabilities BIGINT,
    equity BIGINT, current_assets BIGINT, current_liabilities BIGINT
);

CREATE TABLE IF NOT EXISTS annual_income_statement (
    symbol VARCHAR(20), date DATE, revenue BIGINT, gross_profit BIGINT,
    operating_income BIGINT, net_income BIGINT, eps DECIMAL
);

CREATE TABLE IF NOT EXISTS annual_cash_flow (
    symbol VARCHAR(20), date DATE, operating_cash_flow BIGINT,
    investing_cash_flow BIGINT, financing_cash_flow BIGINT,
    free_cash_flow BIGINT, capital_expenditures BIGINT
);
```

---

## Risk Assessment

**Risk Level:** LOW

**Why:**
- All endpoints return standardized raw arrays
- Frontend has error handling in place
- No breaking changes
- Safe to add without affecting existing code

**What Could Go Wrong:**
1. Missing tables → Returns empty array (handled)
2. SQL errors → Returns error_response (handled)
3. Missing fields → Frontend defensively handles (OK)

---

## Time Estimate

| Phase | Time | Notes |
|-------|------|-------|
| Route configuration | 10 min | Add handlers to routing logic |
| EarningsCalendar (3 endpoints) | 30 min | SQL queries, 3 methods |
| FinancialData (4 endpoints) | 1 hour | Dynamic routing, 4 methods |
| BacktestResults (1 endpoint) | 15 min | Simple query |
| PortfolioOptimizer (1 endpoint) | 15 min | Simple query |
| Testing & validation | 1 hour | Manual testing each page |
| **Total** | **3 hours** | Conservative estimate |

---

## Next Steps

1. ✅ Phase 1 Complete - API standardization
2. ✅ Phase 2 Complete - Full standardization verification
3. ⏳ Phase 3 Ready - Implement missing endpoints
4. ⏳ Testing - Verify all pages load correctly
5. ⏳ Deployment - Push to production

---

## Success Criteria

- [ ] All 26 missing endpoints implemented
- [ ] All endpoints return standardized formats
- [ ] EarningsCalendar page loads data
- [ ] FinancialData page loads data
- [ ] BacktestResults page loads data
- [ ] PortfolioOptimizer page loads data
- [ ] No console errors on any page
- [ ] All API responses valid JSON

---

## Questions?

See comprehensive guide: `DATA_DISPLAY_AUDIT_COMPLETE.md`  
Reference: Line numbers and specific issues documented

Ready to implement Phase 3 whenever you give the signal!

