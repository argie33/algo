# API Architecture Cleanup - Unified Response Format

## PROBLEM
The system has INCONSISTENT API responses:
- Some endpoints use `sendSuccess()`/`sendError()`/`sendPaginated()` helpers
- Others use raw `res.json()` with custom formats
- Frontend has to hack `.data?.data` checks to handle multiple response shapes
- Debugging is difficult - you never know what format you'll get

## SOLUTION
**ONE UNIFIED RESPONSE FORMAT** across ALL endpoints:

### Response Format (All Endpoints)
```javascript
{
  success: boolean,              // Always present
  data?: any,                    // For single-object responses
  items?: array,                 // For list responses
  pagination?: object,           // For paginated lists
  error?: string,                // Only on errors
  timestamp: "2026-04-24T..."    // ISO string, always present
}
```

### Backend Response Helpers (Use These Exclusively)
All in `webapp/lambda/utils/apiResponse.js`:

```javascript
sendSuccess(res, data, statusCode)   // Returns { success: true, data, timestamp }
sendError(res, error, statusCode)    // Returns { success: false, error, timestamp }
sendPaginated(res, items, pagination) // Returns { success, items, pagination, timestamp }
sendNotFound(res, message)           // Returns 404 { success: false, error, timestamp }
sendBadRequest(res, error)           // Returns 400 { success: false, error, timestamp }
sendUnauthorized(res, message)       // Returns 401 { success: false, error, timestamp }
```

### Frontend API Client (`apiClient.js`)
Single normalized client with automatic response normalization:

```javascript
const response = await apiClient.get('/api/endpoint', params);
// response always has shape: { success, data, items, pagination, error, timestamp }

// For lists:
const { items, pagination } = response;

// For single objects:
const { data } = response;

// For errors:
if (!response.success) {
  console.error(response.error);
}
```

### Frontend React Query Hooks (`useCleanAPI.js`)
Clean hooks that return normalized data:

```javascript
const { data, isLoading, error } = useStocks({ limit: 50 });
// data = { items: [...], pagination: {...} }

const { data } = useMarketOverview();
// data = { ...marketData }
```

**NO MORE** `.data?.data` or nested wrapping!

## Migration Checklist

### Phase 1: Setup (DONE)
- [x] Create unified `sendSuccess`, `sendError`, `sendPaginated` helpers
- [x] Create `apiClient.js` with normalized response interceptor
- [x] Create `useCleanAPI.js` with clean React Query hooks

### Phase 2: Backend (IN PROGRESS)
Fix all endpoints to use the response helpers:
- [ ] Audit all `res.json()` calls in routes/
- [ ] Replace raw `res.json()` with appropriate helpers
- [ ] Ensure all paginated responses use consistent pagination format
- [ ] Test all endpoints return correct format

### Phase 3: Frontend (TODO)
Update components to use clean hooks:
- [ ] Replace old `useAPI` imports with `useCleanAPI`
- [ ] Remove `.data?.data` workarounds
- [ ] Remove response format checks/guards
- [ ] Update all components consuming API data

### Phase 4: Testing (TODO)
- [ ] Unit tests for each endpoint's response format
- [ ] Integration tests for frontend-backend flow
- [ ] E2E tests with correct data shapes

## Key Benefits
1. **Single source of truth** - One response format everywhere
2. **Frontend simplicity** - No more format detection/workarounds
3. **Debugging** - Consistent structure makes debugging trivial
4. **Scalability** - New endpoints automatically follow the standard
5. **Type safety** - Can generate TypeScript types from one format
6. **API documentation** - Single format to document

## Breaking Changes
This requires updating:
- All backend endpoints (routes/*.js)
- All frontend API consumption (components, hooks, services)
- All tests expecting old response formats

But the benefit is CLEAN, MAINTAINABLE architecture.

## Example: Before vs After

### BEFORE (Messy)
```javascript
// Backend
router.get('/api/endpoint', (req, res) => {
  res.json({
    success: true,
    data: {
      items: [...],
      extra: "field"
    },
    // OR sometimes:
    // { items: [...], custom_pagination: {...} }
  });
});

// Frontend hack
const response = await api.get('/api/endpoint');
const items = response.data?.data?.items || response.data?.items || response.items;
const pagination = response.data?.pagination || response.pagination;
```

### AFTER (Clean)
```javascript
// Backend
router.get('/api/endpoint', (req, res) => {
  sendPaginated(res, items, pagination);
  // Always returns: { success, items, pagination, timestamp }
});

// Frontend
const response = await apiClient.get('/api/endpoint');
const { items, pagination } = response;
// Done. No guessing.
```

## Status
- Backend helpers: IMPLEMENTED
- Frontend client: IMPLEMENTED
- Frontend hooks: IMPLEMENTED
- Backend endpoint migration: TODO
- Frontend component migration: TODO
- Testing: TODO
