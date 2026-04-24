# Fix Roadmap - Concrete Action Plan

## Phase 1: API Standardization (Week 1-2)
This is the foundation. Nothing else matters until responses are consistent.

### 1.1 Create API Response Standard
**File:** `/webapp/lambda/utils/standardResponse.js`
```javascript
// Standard response wrapper ALL routes must use
function successResponse(data, pagination = null) {
  return {
    success: true,
    data,
    pagination: pagination || null,
    timestamp: new Date().toISOString()
  };
}

function errorResponse(message, statusCode = 500, details = null) {
  return {
    success: false,
    error: message,
    details: process.env.NODE_ENV !== 'production' ? details : undefined,
    timestamp: new Date().toISOString()
  };
}

module.exports = { successResponse, errorResponse };
```

### 1.2 Refactor ALL 26 Route Files
**Task: Replace all `res.json({ ... })` with `successResponse(...)`**

Before (analysts.js):
```javascript
return res.json({
  data: result.rows || [],
  pagination: { page, limit, total, totalPages, hasNext, hasPrev },
  success: true
});
```

After:
```javascript
const { successResponse } = require("../utils/standardResponse");
return res.json(successResponse(
  result.rows || [],
  { page, limit, total, totalPages, hasNext, hasPrev }
));
```

**Affected files (26 total):**
- analysts.js, auth.js, commodities.js, community.js, contact.js
- earnings.js, economic.js, financials.js, health.js, industries.js
- manual-trades.js, market.js, metrics.js, options.js, optimization.js
- portfolio.js, price.js, scores.js, sectors.js, sentiment.js
- signals.js, stocks.js, strategies.js, technicals.js, trades.js, user.js

**Effort:** ~2 hours (mechanical refactor)

---

## Phase 2: API Layer Abstraction (Week 2)
Single, consistent way to call all APIs from frontend.

### 2.1 Create Single API Service
**File:** `/webapp/frontend-admin/src/services/apiClient.js`

```javascript
import axios from 'axios';
import { getApiUrl } from '../config/apiConfig';

const apiClient = axios.create({
  baseURL: getApiUrl(),
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
});

// Request interceptor for auth
apiClient.interceptors.request.use(async (config) => {
  const token = await getAuthToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor for standardized error handling
apiClient.interceptors.response.use(
  (response) => response.data,  // Always return data property
  (error) => {
    // Standardized error format
    if (error.response?.data?.success === false) {
      throw {
        message: error.response.data.error,
        details: error.response.data.details,
        status: error.response.status
      };
    }
    throw error;
  }
);

export default apiClient;
```

### 2.2 Delete Old Services
- Remove the duplicative fetching from raw `fetch()` in pages
- Keep `/src/services/api.js` only for axios config
- Replace DataService with React Query (unified, proven)
- Remove window.__CONFIG__.API_URL complexity

### 2.3 Create API Routes Facade
**File:** `/webapp/frontend-admin/src/services/routes.js`

```javascript
import apiClient from './apiClient';

export const routes = {
  // Analysts
  getAnalystUpgrades: (params) => 
    apiClient.get('/api/analysts/upgrades', { params }),
  
  // Signals
  getSignals: (timeframe, params) => 
    apiClient.get(`/api/signals/stocks?timeframe=${timeframe}`, { params }),
  
  // Stocks
  getDeepValueStocks: (params) => 
    apiClient.get('/api/stocks/deep-value', { params }),
  
  // ... etc for all endpoints
};
```

**Usage in components:**
```javascript
import { routes } from '../services/routes';
import { useQuery } from '@tanstack/react-query';

const { data, isLoading } = useQuery({
  queryKey: ['deepValueStocks', filters],
  queryFn: () => routes.getDeepValueStocks(filters)
});
```

**Effort:** ~4 hours

---

## Phase 3: Move Filtering to Backend (Week 3)
This is where real performance gains come from.

### 3.1 Add Query Parameter Support to ALL Data Routes

**Before (signals.js):**
```javascript
router.get("/stocks", async (req, res) => {
  // Only supports: timeframe, symbol, limit, page, days, signal_type
  // Frontend has to download all, then filter client-side
});
```

**After:**
```javascript
router.get("/stocks", async (req, res) => {
  const {
    timeframe = 'daily',
    symbol,
    signal_type,
    minScore,       // ← NEW
    maxScore,       // ← NEW
    minStrength,    // ← NEW
    sortBy = 'date', // ← NEW
    sortOrder = 'desc', // ← NEW
    limit = 50,
    page = 1
  } = req.query;

  // Build WHERE clause dynamically
  let whereClause = `WHERE bsd.date >= '2019-01-01' AND bsd.signal IN ('Buy', 'Sell')`;
  let params = [];
  let paramIndex = 1;

  if (symbol) {
    whereClause += ` AND bsd.symbol = $${paramIndex++}`;
    params.push(symbol.toUpperCase());
  }

  if (minScore !== undefined) {
    whereClause += ` AND ss_scores.composite_score >= $${paramIndex++}`;
    params.push(parseFloat(minScore));
  }

  if (maxScore !== undefined) {
    whereClause += ` AND ss_scores.composite_score <= $${paramIndex++}`;
    params.push(parseFloat(maxScore));
  }

  if (minStrength !== undefined) {
    whereClause += ` AND bsd.strength >= $${paramIndex++}`;
    params.push(parseFloat(minStrength));
  }

  // ... execute query with WHERE clause
});
```

### 3.2 Add Sorting to All Paginated Routes

Every paginated endpoint should support:
```javascript
/api/signals/stocks?sortBy=date&sortOrder=desc&limit=25&page=1
/api/signals/stocks?sortBy=strength&sortOrder=asc&limit=25&page=1
/api/signals/stocks?sortBy=composite_score&sortOrder=desc&limit=25&page=1
```

**Implementation pattern:**
```javascript
const validSortFields = ['date', 'symbol', 'strength', 'composite_score'];
const sortBy = validSortFields.includes(req.query.sortBy) ? req.query.sortBy : 'date';
const sortOrder = req.query.sortOrder === 'asc' ? 'ASC' : 'DESC';

const orderClause = `ORDER BY ${sortBy} ${sortOrder}`;
```

**Effort:** ~6 hours (design + implement across 10 routes)

---

## Phase 4: Fix Database Schema (Week 4)

### 4.1 Identify Redundant Tables
**Task: Determine which tables are authoritative**

Questions to answer:
- `buy_sell_*` vs `signal_*` - are they the same? If yes, consolidate.
- `company_profile` vs `stock_symbols` - which has correct company names?
- `stock_scores` - is this calculated fresh each time or materialized? If fresh, create materialized view.

```javascript
// Run these queries to understand the schema:
SELECT COUNT(*) FROM buy_sell_daily;
SELECT COUNT(*) FROM signal_daily;
SELECT * FROM stock_symbols LIMIT 5;
SELECT * FROM company_profile LIMIT 5;
```

### 4.2 Create Composite Indexes
**For signals query (currently 28 seconds):**
```sql
CREATE INDEX idx_buy_sell_daily_symbol_date ON buy_sell_daily(symbol, date DESC);
CREATE INDEX idx_stock_scores_composite ON stock_scores(composite_score DESC);
CREATE INDEX idx_earnings_history_symbol_date ON earnings_history(symbol, quarter DESC);
CREATE INDEX idx_company_profile_ticker ON company_profile(ticker);
```

Test signal query performance:
```javascript
// Before: 28 seconds
// Target: <500ms
console.time("signals");
const result = await query(`SELECT ... FROM buy_sell_daily ...`);
console.timeEnd("signals");
```

### 4.3 Create Views for Complex Joins
**Instead of LEFT JOIN on every request:**

```sql
-- Create materialized view combining all signal data
CREATE MATERIALIZED VIEW v_signals_enriched AS
SELECT
  bsd.id, bsd.symbol, bsd.timeframe, bsd.date, bsd.signal,
  bsd.strength, bsd.signal_triggered_date, bsd.created_at,
  COALESCE(cp.short_name, ss.security_name) as company_name,
  ss_scores.composite_score,
  eh.quarter as next_earnings_date,
  (eh.quarter - CURRENT_DATE)::INTEGER as days_to_earnings
FROM buy_sell_daily bsd
LEFT JOIN company_profile cp ON bsd.symbol = cp.ticker
LEFT JOIN stock_symbols ss ON bsd.symbol = ss.symbol
LEFT JOIN stock_scores ss_scores ON bsd.symbol = ss_scores.symbol
LEFT JOIN (
  SELECT DISTINCT ON (symbol) symbol, quarter
  FROM earnings_history
  WHERE quarter >= CURRENT_DATE
  ORDER BY symbol, quarter ASC
) eh ON bsd.symbol = eh.symbol;

CREATE INDEX idx_v_signals_symbol_date ON v_signals_enriched(symbol, date DESC);
```

**New route:**
```javascript
router.get("/stocks", async (req, res) => {
  // Query materialized view instead
  const result = await query(`
    SELECT * FROM v_signals_enriched
    WHERE ${whereClause}
    ORDER BY ${sortBy} ${sortOrder}
    LIMIT $${paramCount} OFFSET $${paramCount+1}
  `, params);
});
```

**Effort:** ~4 hours

---

## Phase 5: Centralize State Management (Week 4-5)

### 5.1 Move to React Query Only
**Delete:** All DataService references, all useState pagination/sorting duplicates
**Keep:** React Query for data fetching + caching

```javascript
// New standard pattern for all pages:
import { useQuery } from '@tanstack/react-query';
import { routes } from '../services/routes';

const MyPage = () => {
  const [filters, setFilters] = useState({ limit: 25, page: 1 });
  
  const { data, isLoading, error } = useQuery({
    queryKey: ['myData', filters],  // Key includes filters
    queryFn: () => routes.getMyData(filters),
    staleTime: 5 * 60 * 1000,  // 5 minutes
  });

  // No more custom caching, loading, error state!
};
```

### 5.2 Create Reusable Hooks
**File:** `/webapp/frontend-admin/src/hooks/usePaginatedData.js`

```javascript
export function usePaginatedData(queryKey, queryFn, options = {}) {
  const [pagination, setPagination] = useState({
    page: 1,
    limit: options.defaultLimit || 25,
    sortBy: options.defaultSort || 'date',
    sortOrder: 'desc',
    filters: {}
  });

  const { data, isLoading, error } = useQuery({
    queryKey: [queryKey, pagination],
    queryFn: () => queryFn(pagination),
    staleTime: 5 * 60 * 1000
  });

  const handlePageChange = (newPage) => {
    setPagination(p => ({ ...p, page: newPage }));
  };

  const handleSort = (field) => {
    setPagination(p => ({
      ...p,
      sortBy: field,
      sortOrder: p.sortBy === field && p.sortOrder === 'desc' ? 'asc' : 'desc'
    }));
  };

  const handleFilterChange = (newFilters) => {
    setPagination(p => ({ ...p, filters: newFilters, page: 1 }));
  };

  return {
    data: data?.data || [],
    pagination: data?.pagination,
    isLoading,
    error,
    handlePageChange,
    handleSort,
    handleFilterChange
  };
}
```

**Usage in all pages:**
```javascript
const DeepValueStocks = () => {
  const {
    data: stocks,
    pagination,
    isLoading,
    error,
    handlePageChange,
    handleSort,
    handleFilterChange
  } = usePaginatedData(
    'deepValueStocks',
    (params) => routes.getDeepValueStocks(params),
    { defaultLimit: 25 }
  );

  // Page logic is now unified and reusable
};
```

**Effort:** ~3 hours

---

## Phase 6: Configuration Single Source of Truth (Week 5)

### 6.1 Create Central Config File
**File:** `/webapp/frontend-admin/src/config/apiConfig.js`

```javascript
// ONE place to configure API URL
export function getApiUrl() {
  // Tier 1: Explicit production deployments
  if (import.meta.env.VITE_API_URL) {
    console.log('[API] Using VITE_API_URL:', import.meta.env.VITE_API_URL);
    return import.meta.env.VITE_API_URL;
  }

  // Tier 2: Development (relative path, Vite proxy)
  if (import.meta.env.DEV) {
    console.log('[API] Using relative path for dev (Vite proxy)');
    return '/api';  // Vite proxies this to :3001/api
  }

  // Tier 3: Production - infer from hostname
  if (typeof window !== 'undefined') {
    const isLocalhost = window.location.hostname === 'localhost' || 
                        window.location.hostname === '127.0.0.1';
    if (isLocalhost) {
      const url = 'http://localhost:3001';
      console.log('[API] Using localhost:', url);
      return url;
    }
    
    // AWS production - same host, port 3001
    const url = window.location.origin.replace(/:\d+$/, '') + ':3001';
    console.log('[API] Using AWS production:', url);
    return url;
  }

  throw new Error('[API] Unable to determine API URL');
}

export const API_CONFIG = {
  BASE_URL: getApiUrl(),
  TIMEOUT: 30000,
  RETRY_ATTEMPTS: 3,
  CACHE_TIME: 5 * 60 * 1000,  // 5 minutes
};
```

**Remove:** All other API URL discovery code

**Effort:** ~1 hour

---

## Phase 7: Add API Contract (Week 5-6)

### 7.1 Create OpenAPI/Swagger Spec
**File:** `/webapp/openapi.yaml`

```yaml
openapi: 3.0.0
info:
  title: Financial Dashboard API
  version: 2.0.0
paths:
  /api/signals/stocks:
    get:
      summary: Get trading signals
      parameters:
        - name: timeframe
          in: query
          schema:
            type: string
            enum: [daily, weekly, monthly]
        - name: symbol
          in: query
          schema: { type: string }
        - name: minScore
          in: query
          schema: { type: number, minimum: 0, maximum: 100 }
        - name: limit
          in: query
          schema: { type: integer, minimum: 1, maximum: 500 }
        - name: page
          in: query
          schema: { type: integer, minimum: 1 }
      responses:
        '200':
          description: Success
          content:
            application/json:
              schema:
                type: object
                properties:
                  success: { type: boolean }
                  data:
                    type: array
                    items: { $ref: '#/components/schemas/Signal' }
                  pagination: { $ref: '#/components/schemas/Pagination' }
components:
  schemas:
    Signal:
      type: object
      properties:
        id: { type: integer }
        symbol: { type: string }
        signal: { type: string, enum: [Buy, Sell] }
        strength: { type: number, nullable: true }
        composite_score: { type: number, nullable: true }
        created_at: { type: string, format: date-time }
      required: [id, symbol, signal]
    Pagination:
      type: object
      properties:
        page: { type: integer }
        limit: { type: integer }
        total: { type: integer }
        hasMore: { type: boolean }
```

**Generate TS types:**
```bash
npm install -g openapi-generator-cli
openapi-generator-cli generate -i openapi.yaml -g typescript-axios -o ./src/generated
```

**Effort:** ~2 hours

---

## Summary: Total Effort Estimate

| Phase | Task | Effort | Priority |
|-------|------|--------|----------|
| 1 | API Response Standardization | 2 hrs | **CRITICAL** |
| 2 | Frontend API Layer | 4 hrs | **CRITICAL** |
| 3 | Server-Side Filtering | 6 hrs | **HIGH** |
| 4 | Database Optimization | 4 hrs | **HIGH** |
| 5 | State Management | 3 hrs | **MEDIUM** |
| 6 | Config Centralization | 1 hr | **MEDIUM** |
| 7 | API Contract | 2 hrs | **LOW** |
| **Total** | | **22 hrs** | |

**Timeline:** ~3 weeks for one developer, working part-time alongside other tasks.

---

## Impact After Each Phase

- **After Phase 1:** Response formats consistent, frontend code simpler
- **After Phase 2:** 40% reduction in frontend code, single API layer
- **After Phase 3:** Pages load 100x faster (5000 rows → 25 rows)
- **After Phase 4:** Signal queries <500ms (was 28 seconds), reliable performance
- **After Phase 5:** Code duplication eliminated, state management clear
- **After Phase 6:** No more "which API URL?" confusion
- **After Phase 7:** Frontend/backend contract is explicit, type-safe

---

## Why This Matters

Right now, onboarding a new dev means:
1. "Where do I call the API?" (3 ways)
2. "What format is the response?" (4 formats)
3. "How do I add pagination?" (Reimplement in each component)
4. "Why is this so slow?" (Downloading 5000 records)

After these fixes:
1. "Use the apiClient"
2. "Standard response format"
3. "Use usePaginatedData hook"
4. "It loads in milliseconds"
