# Rate Limiting Strategy

## Overview

Rate limiting is implemented in three layers:

1. **API Gateway Layer** (10,000 RPS steady-state) — Hard limit at AWS level
2. **Application Layer** (per-endpoint rules) — Protects against abuse and expensive operations
3. **External API Layer** (yfinance, FRED) — Prevents rate-limit cascades from upstream services

This doc defines the Application Layer. Infrastructure (API Gateway) and external APIs are documented separately.

## API Gateway Throttling

- **Steady-state:** 10,000 RPS (can handle 10,000 requests per second across all endpoints)
- **Burst capacity:** Configured by AWS (default account limits)
- **Implementation:** Terraform in `terraform/modules/services/main.tf` lines 344-347
- **Behavior:** Returns HTTP 429 "Too Many Requests" when exceeded

When API Gateway throttling is triggered, it affects ALL endpoints. This should rarely happen under normal load (<10,000 RPS across the entire system).

## Application-Layer Rate Limiting

All rate limits are defined in `utils/rate_limiting.py`. Each endpoint has a configuration with:

- **max_requests:** Maximum requests allowed in the time window
- **window_seconds:** Time window (typically 60 seconds)
- **description:** Why this limit exists

### Endpoint Categories

#### 1. Public Endpoints (No Authentication Required)
Used by anonymous users. Global per-endpoint limits to prevent DoS.

```
/api/algo/markets (100 req/min)
/api/algo/market (100 req/min)
/api/algo/market-factors (100 req/min)
/api/algo/swing-scores (100 req/min)
/api/algo/swing-scores-history (50 req/min)
/api/openapi.json (50 req/min)
/api/swagger (50 req/min)
/api/redoc (50 req/min)
```

Enforcement: `check_public_rate_limit(endpoint)` in `lambda/api/routes/algo.py`

#### 2. Authenticated User Endpoints
Accessible to users with valid JWT. Per-user limits to prevent abuse of authenticated APIs.

```
/api/algo/status (100 req/min) — Portfolio status
/api/algo/trades (100 req/min) — Trade history
/api/algo/positions (100 req/min) — Current positions
/api/algo/performance (100 req/min) — Performance metrics
/api/algo/circuit-breakers (100 req/min) — Circuit breaker status
/api/algo/equity-curve (100 req/min) — Equity chart data
/api/algo/data-status (100 req/min) — Data freshness info
```

Enforcement: Add to `/api/algo/*` route handlers to gate requests via `check_public_rate_limit()`.

#### 3. Admin Endpoints
Accessible only to users in the 'admin' Cognito group. Per-user, per-endpoint limits due to expensive operations.

**Health/Status Endpoints** (Can check frequently):
```
/api/admin/loader-status (30 req/min)
/api/admin/system-health (30 req/min)
```

**Expensive Query Endpoints** (Full scans, table walks):
```
/api/admin/database-stats (20 req/min)
/api/admin/data-quality (10 req/min)
```

**Trigger Operations** (Start async jobs, expensive computation):
```
/api/algo/patrol (5 req/5min) — Triggers data validation scan
```

**Dashboard Histogram Endpoints** (Aggregation queries):
```
/api/algo/daily-return-histogram (20 req/min)
/api/algo/trade-distribution (20 req/min)
/api/algo/holding-period-distribution (20 req/min)
/api/algo/stage-distribution (20 req/min)
```

Enforcement: `check_admin_rate_limit(user_id, endpoint)` in `lambda/api/routes/admin.py` and `lambda/api/routes/algo.py`

### Implementation Details

**Storage:** 
- In-memory tracking: Per-Lambda-instance (stateless, no persistence)
- DynamoDB tracking: Distributed across Lambda fleet (with TTL auto-cleanup)
- Control: Pass `use_dynamodb=True` to `check_admin_rate_limit()` to switch backends

**Behavior on Rate Limit Exceeded:**
- Returns HTTP 429 with `{"message": "Rate limit exceeded: max X requests per Y seconds"}`
- Logs warning with user_id and endpoint
- Admin endpoints: Audit log records the denial

**Clock Skew:**
- Per-instance tracking uses wall-clock time (no NTP required)
- DynamoDB tracking: Server-side timestamps with ±1s tolerance

## Endpoints WITHOUT Rate Limiting (By Design)

These endpoints are not rate-limited because they are either:
1. Low-cost (minimal database query)
2. Read-only (no state-changing side effects)
3. Not publicly exposed (require authentication)

Examples:
- `/api/openapi.json` — Serves static spec
- `/api/sentiment/*` — Read-only sentiment data
- `/api/economic/*` — Read-only economic indicators
- `/api/market/*` — Read-only market data
- `/api/stocks/*` — Read-only stock data
- Most other data fetches

These should be rate-limited if they are accessed at very high volume or become attack vectors. Add them to `ADMIN_RATE_LIMITS` or `PUBLIC_RATE_LIMITS` in `utils/rate_limiting.py` and add enforcement in the route handler.

## Configuration Changes

To add or modify rate limits:

1. Edit `utils/rate_limiting.py` (add endpoint to appropriate dict)
2. Add enforcement in the route handler (check limit before processing):
   ```python
   if path in ADMIN_RATE_LIMITS:
       limits = ADMIN_RATE_LIMITS[path]
       is_allowed, error_msg = check_admin_rate_limit(user_id, path, ...)
       if not is_allowed:
           return error_response(429, 'too_many_requests', error_msg)
   ```

## Monitoring & Alerts

Rate limit violations are logged:
- **Log level:** WARNING for every violation
- **Context:** user_id, endpoint, request count in window
- **Action:** Check CloudWatch Logs for patterns

Future: Add CloudWatch alarm if rate-limit violations exceed threshold (e.g., >100/hour on single endpoint).

## Testing

To test rate limiting locally:

```python
# Test admin rate limit
from utils.rate_limiting import check_admin_rate_limit, ADMIN_RATE_LIMITS

# Simulate 11 requests in 60 seconds (limit is 10)
for i in range(11):
    allowed, msg = check_admin_rate_limit('user123', '/api/admin/system-health')
    print(f"Request {i+1}: {allowed}") # Prints: True True ... True False

# Test public rate limit
from utils.rate_limiting import check_public_rate_limit, PUBLIC_RATE_LIMITS

# Simulate 101 requests in 60 seconds (limit is 100)
for i in range(101):
    allowed, msg = check_public_rate_limit('/api/algo/markets')
    print(f"Request {i+1}: {allowed}") # Prints: True True ... True False
```

## Future Improvements

- [ ] DynamoDB rate limit table provisioning (optional enhancement)
- [ ] Per-client-IP rate limiting for anonymous users (besides per-endpoint)
- [ ] Rate limit reset headers (Retry-After, X-RateLimit-*)
- [ ] Dashboard widget for rate limit metrics
- [ ] Automatic rate limit tuning based on load patterns
