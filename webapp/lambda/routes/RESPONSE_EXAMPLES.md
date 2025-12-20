# Response Format Examples - Before & After

## Example 1: Error Response (stocks.js)

### Before
```javascript
return res.error("Request failed", 400, {
  data: [],
  message: "Stocks data not yet loaded",
  count: 0,
  limit: limit,
  offset: offset
});
```

### After
```javascript
return res.status(400).json({
  success: false,
  error: "Stocks data not yet loaded"
});
```

## Example 2: Success with Data (stocks.js)

### Before
```javascript
res.json({
  stocks: result.rows || [],
  count: (result.rows || []).length,
  total: totalCount,
  limit: limit,
  offset: offset,
  pagination: { ... }
});
```

### After
```javascript
res.status(200).json({
  success: true,
  items: result.rows || [],
  pagination: {
    total: totalCount,
    page: Math.floor(offset / limit) + 1,
    limit: limit,
    offset: offset
  }
});
```

## Example 3: Server Error (sectors.js)

### Before
```javascript
res.serverError(error.message || "Failed to fetch sector analysis", {
  details: error.message,
});
```

### After
```javascript
return res.status(500).json({
  success: false,
  error: "Failed to fetch sector analysis",
  details: error.message
});
```

## Example 4: Success with Object Data (market.js)

### Before
```javascript
res.success(responseData, 200, {});
```

### After
```javascript
res.status(200).json({ 
  success: true, 
  data: responseData
});
```

## Example 5: Not Found Error (price.js)

### Before
```javascript
return res.error("Price data not available", 404, {
  message: "Price data table not yet loaded",
  symbol: symbolUpper,
});
```

### After
```javascript
return res.status(404).json({ 
  success: false,
  error: "Price data not available"
});
```

## Frontend Integration Examples

### Checking Success
```javascript
// Old way
if (response.data) { ... }

// New way  
if (response.success) { ... }
```

### Handling Errors
```javascript
// Old way
if (response.error) {
  console.error(response.error.message);
}

// New way
if (!response.success) {
  console.error(response.error);
}
```

### Accessing Paginated Data
```javascript
// Old way
const stocks = response.stocks;
const total = response.total;

// New way
const stocks = response.items;
const total = response.pagination.total;
```

### Accessing Single Item Data
```javascript
// Old way (varies by endpoint)
const data = response;

// New way (consistent)
const data = response.data;
```
