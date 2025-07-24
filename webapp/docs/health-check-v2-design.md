# Database Health Check System V2 - Design Specification

## Problem Statement

The current health check system has critical performance issues:
- Single massive query taking 15+ seconds
- Frontend timeouts and 504 errors
- No progressive data loading
- Poor user experience with long waiting times

## Solution Architecture

### Multi-Tier Health Check System

```
┌─────────────────────────────────────────────────────────┐
│                    Response Times                       │
├─────────────────────────────────────────────────────────┤
│ Tier 1: Connection Health      < 1 second              │
│ Tier 2: Critical Tables        < 3 seconds             │
│ Tier 3: Full System Health     Background/Cached       │
│ Tier 4: Historical Trends      Cached (1 hour TTL)     │
└─────────────────────────────────────────────────────────┘
```

## API Design

### New Health Endpoints

| Endpoint | Purpose | Response Time | Data |
|----------|---------|---------------|------|
| `GET /health/connection` | Database connectivity | < 1s | Connection status, table count |
| `GET /health/critical` | Critical tables only | < 3s | 7 most important tables |
| `GET /health/full` | Complete system health | Cached | All tables (background updated) |
| `GET /health/summary` | High-level overview | < 1s | Cached summary metrics |

### Response Format

```json
{
  "status": "healthy|degraded|error",
  "responseTime": 1250,
  "cached": false,
  "timestamp": "2025-01-24T01:55:00.000Z",
  "database": {
    "name": "stocks",
    "total_tables": 45,
    "critical_tables_present": 7
  },
  "summary": {
    "total_tables": 45,
    "healthy_tables": 38,
    "stale_tables": 5,
    "empty_tables": 2,
    "total_records": 2500000
  },
  "critical_tables": {
    "symbols": {
      "status": "healthy",
      "estimated_rows": 8500,
      "category": "symbols",
      "is_critical": true
    }
  }
}
```

## Frontend Integration Strategy

### Progressive Loading Pattern

```javascript
const HealthChecker = {
  // 1. Immediate: Show connection status
  async checkConnection() {
    const response = await fetch('/api/health/connection');
    updateUI('connection', response);
  },
  
  // 2. Fast: Load critical tables (3s)
  async checkCritical() {
    const response = await fetch('/api/health/critical');
    updateUI('critical', response);
  },
  
  // 3. Background: Full system health
  async checkFull() {
    const response = await fetch('/api/health/full');
    updateUI('full', response);
  }
};

// Load in sequence for better UX
HealthChecker.checkConnection()
  .then(() => HealthChecker.checkCritical())
  .then(() => HealthChecker.checkFull());
```

### UI Loading States

```
Loading Sequence:
1. [0-1s]   Show "Checking connection..." → Connection status
2. [1-4s]   Show "Loading critical tables..." → Critical tables grid
3. [4s+]    Show "Loading complete system..." → Full table list
4. [Background] Auto-refresh every 5 minutes
```

## Caching Strategy

### Multi-Level Cache

```javascript
const CacheStrategy = {
  connection: {
    ttl: 30000,      // 30 seconds
    reason: "Connection can change quickly"
  },
  critical: {
    ttl: 60000,      // 1 minute
    reason: "Critical tables need frequent monitoring"
  },
  full: {
    ttl: 300000,     // 5 minutes
    reason: "Full scan is expensive, cache longer"
  },
  trends: {
    ttl: 3600000,    // 1 hour
    reason: "Historical data changes slowly"
  }
};
```

### Cache Invalidation

- **Schema Changes**: Invalidate full + critical cache
- **Data Operations**: Invalidate critical cache only
- **Connection Issues**: Invalidate connection cache
- **Manual Refresh**: User can force refresh any layer

## Performance Optimizations

### Database Query Optimization

```sql
-- OLD: Single massive query (15+ seconds)
SELECT * FROM information_schema.tables t
LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
-- + complex processing

-- NEW: Targeted fast queries (< 3 seconds)
-- Connection check
SELECT current_database(), COUNT(*) FROM information_schema.tables;

-- Critical tables only
SELECT table_name, n_live_tup, status 
FROM pg_stat_user_tables 
WHERE relname = ANY($1);  -- Only 7 critical tables
```

### Background Processing

- **Background Worker**: Runs full scan every 5 minutes
- **Non-blocking**: Users never wait for full scan
- **Graceful Degradation**: Show cached data if background scan fails
- **Progressive Enhancement**: Load critical data first, enhance with full data

## Implementation Plan

### Phase 1: Core Infrastructure (Day 1)
- [x] Create health-v2.js with multi-tier endpoints
- [ ] Add route registration in main index.js
- [ ] Test connection and critical endpoints
- [ ] Verify cache functionality

### Phase 2: Frontend Integration (Day 2) 
- [ ] Update ServiceHealth.jsx for progressive loading
- [ ] Implement loading states and error handling
- [ ] Add real-time cache status indicators
- [ ] Test user experience with slow connections

### Phase 3: Background Processing (Day 3)
- [ ] Implement background health scanner
- [ ] Add health data persistence (optional)
- [ ] Setup monitoring and alerting
- [ ] Performance testing and optimization

### Phase 4: Advanced Features (Day 4+)
- [ ] Historical health trends
- [ ] Health score algorithms
- [ ] Automated health recommendations
- [ ] Integration with monitoring systems

## Migration Strategy

### Zero-Downtime Migration

1. **Deploy New Endpoints**: Add v2 endpoints alongside existing
2. **Frontend Flag**: Use feature flag to switch between v1/v2
3. **Gradual Rollout**: Test v2 with subset of users
4. **Full Migration**: Switch all users to v2
5. **Cleanup**: Remove v1 endpoints after verification

### Rollback Plan

- Keep v1 endpoints active during migration
- Feature flag allows instant rollback
- Database queries are read-only (safe)
- Cache failures fallback to direct queries

## Success Metrics

### Performance Targets

- **Connection Health**: < 1 second response time
- **Critical Tables**: < 3 seconds response time  
- **User Experience**: Data visible within 1 second
- **Cache Hit Rate**: > 80% for critical endpoints
- **Error Rate**: < 1% for health checks

### Monitoring

```javascript
const HealthMetrics = {
  responseTime: {
    connection: "< 1000ms",
    critical: "< 3000ms", 
    full: "background only"
  },
  cachePerformance: {
    hitRate: "> 80%",
    missRate: "< 20%",
    invalidationRate: "< 5% per hour"
  },
  reliability: {
    uptime: "> 99.9%",
    errorRate: "< 1%",
    backgroundScanSuccess: "> 95%"
  }
};
```

## Risk Assessment

### High Risk
- **Database Connection Issues**: Mitigated with graceful degradation
- **Cache Corruption**: Mitigated with TTL and validation
- **Background Scan Failures**: Mitigated with retry logic

### Medium Risk  
- **Memory Usage**: Monitor cache size, implement LRU eviction
- **Concurrent Access**: PostgreSQL handles well, add connection pooling

### Low Risk
- **Frontend Compatibility**: Progressive enhancement pattern
- **Migration Issues**: Feature flag allows safe rollback

## Conclusion

This new design provides:

1. **Fast Response Times**: < 3 seconds for all user-facing operations
2. **Better User Experience**: Progressive data loading
3. **Scalability**: Background processing handles expensive operations  
4. **Reliability**: Multiple fallback layers and caching
5. **Maintainability**: Clear separation of concerns and modular design

The system transforms from a blocking, slow health check to a responsive, scalable monitoring solution that provides immediate feedback while maintaining comprehensive health data.