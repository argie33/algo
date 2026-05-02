# Remaining Optimization Opportunities

## Critical Issues Found

### 1. Repeated MAX(date) Queries (HIGH IMPACT)
- **Location**: market.js (11 occurrences), portfolio.js (2 occurrences)
- **Problem**: Each endpoint execution queries MAX(date) multiple times
- **Solution**: Cache with 5-minute TTL via market-cache.js utility
- **Expected gain**: 13 fewer queries per request, 10-50ms improvement per endpoint
- **Status**: Created market-cache.js utility (ready for integration)

### 2. Unfiltered DISTINCT Queries
- **Location**: market.js - `SELECT DISTINCT sector FROM company_profile`
- **Problem**: No LIMIT, returns all sectors (could be hundreds)
- **Solution**: Add `LIMIT 100` or use materialized view
- **Expected gain**: Faster response for market data endpoints

### 3. ILIKE Search Without Full-Text Index
- **Location**: stocks.js - search by symbol/name
- **Problem**: ILIKE on unindexed columns requires full table scan
- **Solution**: Add trigram index or full-text search index
- **Expected gain**: 10-100x faster search for large datasets

### 4. Missing LIMIT Clauses
- **Pattern**: Various queries return potentially large result sets
- **Solution**: Add explicit LIMIT to prevent memory bloat
- **Expected gain**: Reduced memory usage in Lambda

## Implementation Priority

1. **Immediate** (Ready to deploy):
   - Integrate market-cache.js to eliminate 13 repeated MAX(date) queries
   - Add LIMIT to DISTINCT sector queries

2. **Short-term** (Next iteration):
   - Create trigram index on symbol/security_name for faster search
   - Add full-text search support for securities

3. **Long-term** (Optional enhancements):
   - Consider using PostgreSQL functions for market date lookups
   - Implement query result caching at API level
   - Add query monitoring/profiling to identify new bottlenecks

## Expected Performance Gains

- Market endpoints: 50-100ms improvement (eliminate MAX date queries)
- Search endpoints: 100-500ms improvement (with full-text index)
- Overall: 10-20% reduction in database query time
