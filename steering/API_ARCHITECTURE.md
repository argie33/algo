# API Architecture & Error Handling

REST API: Lambda `algo-api-dev` → Error boundary middleware → Route handlers → PostgreSQL. All errors return JSON with consistent status codes and reason codes.

---

## Exception Hierarchy

**All exceptions in `lambda/api/exceptions.py`:**

```
APIException (base, status=500)
├── ValidationError (400) — Invalid input, missing fields, type mismatch
├── AuthenticationError (401) — Invalid token, expired session, missing API key
├── AuthorizationError (403) — Valid token but insufficient permissions
├── NotFoundError (404) — Resource doesn't exist
├── ConflictError (409) — Resource already exists, state conflict
├── RateLimitError (429) — Too many requests within time window
├── DataUnavailableError (503) — Database unavailable, stale data
├── ExternalServiceError (502) — yfinance, Alpaca, SEC API failed
└── InternalServerError (500) — Unexpected error, logs full traceback
```

**Example:**
```python
# Endpoint tries to fetch stock that doesn't exist
raise NotFoundError("stock_id=9999 not found in portfolio")
# → Returns: HTTP 404 { "error": "not_found", "message": "...", "request_id": "..." }

# Database connection pool exhausted during high load
raise DataUnavailableError("connection pool saturated, try again in 10 seconds")
# → Returns: HTTP 503 { "error": "service_unavailable", "message": "...", "retry_after": 10 }

# Caller passes invalid JSON
raise ValidationError("field 'amount' must be a number, got string")
# → Returns: HTTP 400 { "error": "validation_failed", "message": "...", "field": "amount" }
```

---

## Error Boundary Middleware

**Every request flows through `lambda/api/middleware.py`:**

1. **Request validation:** Extract headers (auth token, content-type)
2. **Route lookup:** Match URL path to handler function
3. **Execute handler** in try-catch block
4. **Response formatting:**
   - **Success (handler returns dict):** HTTP 200 + JSON body
   - **Exception raised:** Catch exception, format as error response
   - **Unexpected error:** Log full traceback, return HTTP 500

**Error Response Format (all errors):**
```json
{
  "error": "error_code",
  "message": "Human-readable reason",
  "request_id": "uuid-for-logs",
  "timestamp": "2026-06-29T14:30:45Z",
  "status": 400,
  "details": {}
}
```

**Example Flow:**
```python
# Handler code
@app.route('/api/positions/{stock_id}', methods=['GET'])
def get_position(stock_id: str):
    if not stock_id:
        raise ValidationError("stock_id required")
    
    position = db.query(Position).filter(Position.stock_id == stock_id).first()
    if not position:
        raise NotFoundError(f"stock_id={stock_id} not found")
    
    return {
        "stock_id": position.stock_id,
        "quantity": position.quantity,
        "entry_price": position.entry_price
    }

# Middleware catches any exception:
try:
    response = get_position("AAPL")  # Success → HTTP 200
except NotFoundError as e:
    response = {
        "error": "not_found",
        "message": str(e),
        "status": 404
    }
    http_status = 404
```

---

## When to Raise vs Return Errors

**RAISE exception** (middleware formats as HTTP error):
- Input validation fails (ValidationError)
- User lacks permission (AuthorizationError)
- Resource doesn't exist (NotFoundError)
- External service unavailable (ExternalServiceError)
- Database error (DataUnavailableError)
- Rate limit exceeded (RateLimitError)

**RETURN error dict** (middleware wraps as HTTP 200 with error flag):
- Optional data unavailable (e.g., sentiment missing) → return `{"data_unavailable": True, "reason": "no_sentiment_data"}`
- Partial data available → return `{"positions": [...], "incomplete": True, "missing": ["sentiment", "technicals"]}`
- Trade request accepted but pending → return `{"status": "pending", "trade_id": "..."}`

**Example: Distinguish exceptions from optional data:**
```python
# This RAISES (caller's fault)
def buy(self, stock_id: str, quantity: int):
    if not stock_id:
        raise ValidationError("stock_id required")
    # ...

# This RETURNS error dict (data fault, not caller's fault)
def get_stock_sentiment(stock_id: str):
    sentiment = load_sentiment(stock_id)
    if not sentiment:
        return {
            "symbol": stock_id,
            "data_unavailable": True,
            "reason": "no_sentiment_coverage"
        }
    return {"symbol": stock_id, "sentiment_score": sentiment}
```

---

## Data Validation Helpers

**Safe extraction functions in `utils/validation.py`:**

```python
def safe_float(value: Any) -> float | None:
    """Convert to float, return None if invalid."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None

def safe_int(value: Any) -> int | None:
    """Convert to int, return None if invalid."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None

def safe_extract(obj: dict, key: str, type_fn: Callable) -> Any:
    """Extract from dict with type validation, raise ValidationError if invalid."""
    value = obj.get(key)
    if value is None:
        raise ValidationError(f"field '{key}' required")
    converted = type_fn(value)
    if converted is None:
        raise ValidationError(f"field '{key}' has invalid type (expected {type_fn.__name__})")
    return converted
```

**Usage:**
```python
# Unsafe (mypy passes but fails at runtime if data is dict)
if data.get("price") >= 0:  # price could be dict!
    trade = True

# Safe (explicit type validation)
price = safe_float(data.get("price"))
if price is not None and price >= 0:
    trade = True

# Safe with required fields
amount = safe_extract(trade_request, "amount", float)  # Raises ValidationError if missing/invalid
quantity = safe_extract(trade_request, "quantity", int)
```

---

## Frontend Error Handling

**Frontend sends errors to:** `POST /api/log-error` endpoint.

**Example error logged from UI:**
```javascript
// frontend/src/api.ts
fetch('/api/log-error', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    error: "ReferenceError: portfolioData is not defined",
    stack: "at Dashboard.render (Dashboard.tsx:42)",
    url: window.location.href,
    timestamp: new Date().toISOString()
  })
});
```

**Backend logs to:** CloudWatch `/aws/lambda/algo-api` + Slack #errors channel (if critical).

---

## Common Errors & Responses

| Scenario | Exception | HTTP | Body |
|----------|-----------|------|------|
| Missing `amount` field | ValidationError | 400 | `{"error": "validation_failed", "field": "amount"}` |
| Token expired | AuthenticationError | 401 | `{"error": "auth_failed", "message": "token expired"}` |
| User not trader | AuthorizationError | 403 | `{"error": "forbidden", "message": "requires trader role"}` |
| Stock not in portfolio | NotFoundError | 404 | `{"error": "not_found", "message": "..."}` |
| Too many requests | RateLimitError | 429 | `{"error": "rate_limited", "retry_after": 60}` |
| DB connection pool full | DataUnavailableError | 503 | `{"error": "service_unavailable"}` |
| yfinance timeout | ExternalServiceError | 502 | `{"error": "upstream_error", "service": "yfinance"}` |
| Unexpected Python error | InternalServerError | 500 | `{"error": "internal_error", "request_id": "..."}` |

---

## Transient vs Permanent Errors

**Transient (retry recommended):**
- HTTP 429 (rate limit) → Wait + retry
- HTTP 503 (service unavailable) → Exponential backoff
- HTTP 502 (upstream service timeout) → Retry once, then fail
- Database connection timeout → Retry with backoff

**Permanent (don't retry):**
- HTTP 400 (validation) → Fix input
- HTTP 401 (auth) → Refresh token or re-auth
- HTTP 403 (permission) → Not allowed
- HTTP 404 (not found) → Resource doesn't exist

**Frontend implements retry logic:**
```typescript
// api.ts
async function fetchWithRetry(url, options, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    const response = await fetch(url, options);
    if (response.ok) return response;
    
    if ([429, 503, 502].includes(response.status)) {
      // Transient error, backoff
      await new Promise(r => setTimeout(r, 1000 * Math.pow(2, i)));
      continue;
    } else {
      // Permanent error, stop
      return response;
    }
  }
}
```

---

## For Detailed Reference

See:
- `lambda/api/exceptions.py` — Full exception definitions
- `lambda/api/middleware.py` — Error boundary implementation
- `utils/validation.py` — Type-safe extraction helpers
- `steering/GOVERNANCE.md` — Fail-fast principles, data contracts
