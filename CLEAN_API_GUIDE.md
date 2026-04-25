# Clean API Architecture - Developer Guide

## Overview
We've implemented a **unified API response format** that eliminates messy `.data?.data` checks and makes the codebase maintainable.

---

## For Backend Developers

### Always Use These Helpers
Never use raw `res.json()`. Always use the response helpers:

```javascript
const { sendSuccess, sendError, sendPaginated, sendNotFound, sendBadRequest } = require('../utils/apiResponse');

// Single object response
router.get('/api/user/:id', async (req, res) => {
  try {
    const user = await getUser(req.params.id);
    if (!user) {
      return sendNotFound(res, 'User not found');
    }
    sendSuccess(res, user);
  } catch (error) {
    sendError(res, error.message);
  }
});

// List/paginated response
router.get('/api/users', async (req, res) => {
  const { limit = 10, offset = 0 } = req.query;
  const users = await getUsers(limit, offset);
  const total = await getUserCount();
  
  sendPaginated(res, users, {
    limit,
    offset,
    total,
    page: Math.floor(offset / limit) + 1
  });
});

// Error responses
router.post('/api/data', async (req, res) => {
  try {
    validateInput(req.body);
  } catch (error) {
    return sendBadRequest(res, error.message);
  }
  
  // ... process
  sendSuccess(res, result, 201); // Can pass custom status code
});
```

### Response Format Reference
All responses include:
- `success` (boolean) - Always present
- `timestamp` (ISO string) - Always present
- `data` (any) - For single-object responses
- `items` (array) - For lists
- `pagination` (object) - For paginated lists
  - `limit`, `offset`, `total`, `page`, `totalPages`, `hasNext`, `hasPrev`
- `error` (string) - Only on errors

---

## For Frontend Developers

### Use the Clean API Client
Import from `services/apiClient.js`:

```javascript
import apiClient from '../services/apiClient';

// GET request
const response = await apiClient.get('/api/endpoint', { param: 'value' });
const { success, data, items, pagination, error } = response;

// POST request
const response = await apiClient.post('/api/endpoint', { field: 'value' });
const { success, data, error } = response;

// PUT, DELETE, PATCH
await apiClient.put('/api/resource/123', updateData);
await apiClient.delete('/api/resource/123');
await apiClient.patch('/api/resource/123', partialUpdate);
```

Response is ALWAYS normalized:
```javascript
{
  success: true,
  data: null,         // Single object responses
  items: [],          // List responses
  pagination: {...},  // Paginated list metadata
  error: null,        // Error message (only on failures)
  timestamp: "2026-04-24T...",
  _raw: response      // Raw Axios response for debugging
}
```

### Use Clean React Query Hooks
Import from `hooks/useCleanAPI.js`:

```javascript
import { useStocks, useStockScores, useMarketOverview, useSectorSearch } from '../hooks/useCleanAPI';

// Getting a list
function StocksList() {
  const { data, isLoading, error } = useStocks({ limit: 50, offset: 0 });
  
  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error: {error.message}</div>;
  
  // data = { items: [...], pagination: {...} }
  return (
    <div>
      {data.items.map(stock => (
        <div key={stock.symbol}>{stock.symbol}</div>
      ))}
    </div>
  );
}

// Getting market data
function MarketDashboard() {
  const { data } = useMarketOverview();
  
  // data = { ...market data }
  return <div>{data.market_status}</div>;
}

// Searching
function SearchStocks() {
  const query = 'AAPL';
  const { data } = useStockSearch(query);
  
  return data.items.map(stock => <div>{stock.symbol}</div>);
}
```

### Creating/Updating/Deleting with Mutations

```javascript
import { useCreateResource, useUpdateResource, useDeleteResource } from '../hooks/useCleanAPI';

function CreateForm() {
  const mutation = useCreateResource('/api/endpoint');
  
  const handleSubmit = async (formData) => {
    const { data, error } = await mutation.mutateAsync(formData);
    if (error) {
      alert(`Error: ${error}`);
    } else {
      alert('Created successfully!');
    }
  };
  
  return <form onSubmit={handleSubmit}>...</form>;
}
```

### No More Response Format Workarounds!

```javascript
// ❌ OLD (BAD)
const { data } = response;
const items = data?.data?.items || data?.items || response.items || [];

// ✅ NEW (CLEAN)
const { items } = response;
```

---

## Migration Checklist for Components

### Step 1: Update Imports
```javascript
// OLD
import useAPI from '../hooks/useAPI';
const { data } = useAPI.useSectors();

// NEW
import { useSectors } from '../hooks/useCleanAPI';
const { data } = useSectors();
```

### Step 2: Remove Workarounds
```javascript
// OLD
const data = response.data?.data || response.data;

// NEW
const { data } = response;
// OR for lists
const { items, pagination } = response;
```

### Step 3: Update Assumptions
```javascript
// OLD
const items = data.items || [];

// NEW
const items = data.items; // Always present for list endpoints
```

---

## Testing the New Format

### Test an endpoint
```bash
curl http://localhost:3001/api/stocks?limit=5 | jq .

# Response format:
{
  "success": true,
  "items": [...],
  "pagination": {...},
  "timestamp": "2026-04-24T..."
}
```

### Test error handling
```bash
curl http://localhost:3001/api/stocks/not-found

# Response format:
{
  "success": false,
  "error": "Stock not found",
  "timestamp": "2026-04-24T..."
}
```

---

## Key Files

| File | Purpose |
|------|---------|
| `utils/apiResponse.js` | Response helpers (backend) |
| `middleware/responseNormalizer.js` | Safety net normalizer (backend) |
| `services/apiClient.js` | Clean API client (frontend) |
| `hooks/useCleanAPI.js` | React Query hooks (frontend) |

---

## Benefits You Get

1. **Type Safety** - Consistent response shape means better TypeScript support
2. **Simplicity** - No more `.data?.data` or format detection
3. **Debugging** - Always know what shape you'll get
4. **Scalability** - New endpoints automatically follow the pattern
5. **Documentation** - One format to document
6. **Testing** - Easier to write tests with consistent contracts

---

## Questions?

If an endpoint returns something unexpected:
1. Check if it's using the response helpers (it should be)
2. Check the responseNormalizer middleware (it's a safety net)
3. Debug using `response._raw` to see the raw Axios response
4. Report the endpoint and we'll fix it

---

## Status

- ✅ Backend helpers: Complete
- ✅ Response normalizer: Complete
- ✅ Frontend apiClient: Complete
- ✅ React Query hooks: Complete
- 🔄 Component migration: In progress
- 🔄 Testing: In progress

Start using `useCleanAPI` for new code. Migrate old components as you touch them.
