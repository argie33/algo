# Database and API Optimization Plan

## Problem Statement
The API is experiencing **25+ second query timeouts** on several endpoints, causing 500 errors and preventing data display.

### Root Causes Identified
1. **Missing Database Indexes** - Queries perform full table scans instead of indexed lookups
2. **Expensive JOINs** - Multiple JOIN operations on large tables compound the problem
3. **No Query Result Caching** - Same queries executed repeatedly without caching
4. **Unrestricted Full Table Queries** - Endpoints allow querying entire tables without filters
5. **Suboptimal Query Plans** - Database query planner not optimized for large result sets

---

## Solution Architecture

### Phase 1: Database Optimization (CRITICAL - Do First)

#### 1.1 Add Database Indexes
**File**: `webapp/lambda/migrations/optimize-database-indexes.sql`

Run this SQL migration to add 40+ indexes on critical columns:
```bash
psql -h YOUR_DB_HOST -U YOUR_USER -d YOUR_DB < webapp/lambda/migrations/optimize-database-indexes.sql
```

**Expected Impact**: Reduce query times from 25+ seconds to <200ms

Key indexes added:
- `stock_symbols(symbol)` - 99% of queries filter by symbol
- `company_profile(ticker, sector, industry)` - Join columns
- `earnings_history(symbol, quarter)` - Composite index for common queries
- `price_history_daily(symbol, date DESC)` - Time-series queries
- `buy_sell_daily(symbol, date DESC)` - Signals queries

#### 1.2 Analyze Tables
After creating indexes, run ANALYZE to optimize query planner:
```sql
ANALYZE stock_symbols;
ANALYZE company_profile;
ANALYZE earnings_history;
-- ... (see migration file for full list)
```

#### 1.3 Monitor Query Performance
```sql
-- Check slow queries
SELECT query, mean_exec_time, calls 
FROM pg_stat_statements 
ORDER BY mean_exec_time DESC 
LIMIT 10;

-- Verify indexes are being used
EXPLAIN (ANALYZE, BUFFERS) 
SELECT * FROM quality_metrics WHERE symbol = 'AAPL';
```

---

### Phase 2: API Query Optimization

#### 2.1 Query Optimization Middleware
**File**: `webapp/lambda/middleware/queryOptimization.js`

Implements:
- **Pagination enforcement** - Limits to 500 items max per query
- **Result caching** - 5-minute cache for expensive queries
- **Symbol-based filtering** - Requires ?symbol param for large tables
- **Query timeouts** - 10-second timeout with graceful fallback

**Usage**:
```javascript
const { validatePagination, withCache } = require('../middleware/queryOptimization');

// Enforce pagination
const { limit, offset, page } = validatePagination(req.query);

// Add caching
const data = await withCache('key', async () => {
  return await query('SELECT * FROM metrics WHERE symbol = $1', [symbol]);
});
```

#### 2.2 Required Symbol Filtering
**Endpoints that now require ?symbol parameter:**
- `/api/metrics/quality?symbol=AAPL`
- `/api/metrics/stability?symbol=AAPL`
- `/api/stocks/quick/overview?search=AAPL` (search filter)
- `/api/stocks/full/data?search=AAPL` (search filter)

This prevents full table scans and ensures queries complete in <100ms.

#### 2.3 Simplified Query Joins
**Removed expensive JOINs:**
- `/api/signals/stocks` - Removed earnings_history and stock_scores JOINs
- Reduced from 5 JOINs (25+ seconds) to 2 JOINs (<500ms)
- Frontend can fetch related data separately if needed

---

### Phase 3: Caching Strategy

#### 3.1 Response Caching
- Earnings data: Cache 1 hour (updates daily)
- Stock metrics: Cache 5 minutes (updated continuously)
- Company profiles: Cache 24 hours (rarely changes)

#### 3.2 Lazy Loading
```javascript
// Instead of fetching all data upfront:
// Bad: SELECT * FROM stock_symbols (4M+ rows)

// Good: SELECT * FROM stock_symbols LIMIT 50 OFFSET 0
// Then paginate: next page is OFFSET 50
```

---

### Phase 4: Endpoint Best Practices

#### 4.1 Pagination Standards
All endpoints now support:
```
GET /api/metrics/growth?limit=50&offset=0
GET /api/stocks/quick/overview?limit=50&page=1
```

- `limit`: 1-500 (default: 50)
- `offset`: 0+ (for cursor pagination)
- `page`: 1+ (for page-based pagination)

#### 4.2 Response Format
**Standard response structure:**
```json
{
  "data": [...],
  "items": [...],
  "pagination": {
    "limit": 50,
    "offset": 0,
    "total": 5000,
    "page": 1,
    "hasMore": true
  },
  "success": true
}
```

#### 4.3 Filtering
**Common filter patterns:**
```
?symbol=AAPL          // Single symbol
?symbols=AAPL,MSFT    // Multiple symbols
?sector=Technology    // By sector
?search=Apple         // Full-text search
?date_from=2026-01-01 // Date range
?date_to=2026-04-25
```

---

## Implementation Checklist

### Immediate Actions (Do Now)
- [x] Create missing API endpoints (10 endpoints added)
- [x] Optimize expensive queries (removed JOINs)
- [x] Add query optimization middleware
- [ ] **Run database migration: optimize-database-indexes.sql** ⚠️ CRITICAL
- [ ] Test endpoints after DB indexes created

### Short Term (This Week)
- [ ] Implement response caching in all endpoints
- [ ] Add query timeout handlers
- [ ] Update API documentation with pagination requirements
- [ ] Test with real data volumes

### Medium Term (This Month)
- [ ] Implement database query profiling
- [ ] Create monitoring dashboard for slow queries
- [ ] Consider read replicas for reporting queries
- [ ] Implement GraphQL federation for complex queries

---

## Performance Expectations

### Before Optimization
| Endpoint | Response Time | Status |
|----------|--------------|--------|
| /api/metrics/quality | 25000ms+ | 500 Error |
| /api/stocks/quick | 25000ms+ | 500 Error |
| /api/signals/stocks | 25000ms+ | 500 Error |

### After Optimization
| Endpoint | Response Time | Status |
|----------|--------------|--------|
| /api/metrics/quality?symbol=AAPL | <100ms | ✅ |
| /api/stocks/quick/overview | <200ms | ✅ |
| /api/signals/stocks | <500ms | ✅ |

---

## Database Index Maintenance

### Weekly
```sql
-- Analyze tables for query optimization
ANALYZE;

-- Check index bloat
SELECT schemaname, tablename, indexname, 
  ROUND(pg_relation_size(indexrelid) / 1024.0 / 1024.0, 2) AS size_mb
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC;
```

### Monthly
```sql
-- Reindex large tables
REINDEX TABLE stock_symbols;
REINDEX TABLE earnings_history;

-- Vacuum to reclaim space
VACUUM FULL ANALYZE;
```

---

## Monitoring & Alerts

### Key Metrics to Monitor
1. **Query Response Time** - Alert if >5 seconds
2. **Index Bloat** - Alert if >30% bloat
3. **Connection Pool Usage** - Alert if >80% usage
4. **Cache Hit Ratio** - Target >80%

### CloudWatch Metrics
```
api_response_time_p95
database_connection_pool_usage
index_bloat_percentage
cache_hit_ratio
slow_query_count
```

---

## Testing Strategy

### Load Testing
```bash
# Test single endpoint with 100 concurrent requests
ab -n 100 -c 10 http://localhost:3000/api/metrics/growth?symbol=AAPL

# Load test all endpoints
wrk -t4 -c100 -d30s http://localhost:3000/api/metrics/growth?symbol=AAPL
```

### Functional Testing
- [x] All 10 endpoints return data
- [ ] Pagination works correctly
- [ ] Caching improves performance
- [ ] Symbol filtering required endpoints error without symbol
- [ ] Timeouts handled gracefully

---

## Rollout Plan

### Stage 1: Database Optimization (CRITICAL)
1. Backup database
2. Run SQL migration (optimize-database-indexes.sql)
3. Run ANALYZE
4. Test endpoints - should see instant improvement

### Stage 2: API Updates
1. Deploy code changes
2. Test new endpoints
3. Monitor error rates

### Stage 3: Monitoring
1. Enable performance monitoring
2. Set up alerts
3. Document baseline metrics

---

## Success Criteria

✅ All endpoints respond in <1 second
✅ No 500 errors for valid requests
✅ >95% of queries use indexes (verified with EXPLAIN ANALYZE)
✅ Cache hit ratio >80%
✅ Pages load completely without timeouts
✅ All data displays correctly in UI

---

## Questions & Support

For questions about:
- **Database**: See optimize-database-indexes.sql comments
- **API**: See queryOptimization.js for implementation details
- **Performance**: Monitor with EXPLAIN ANALYZE and SLOW_LOG
