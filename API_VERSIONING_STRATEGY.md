# API Versioning Strategy

## Current Status
The API currently has **no explicit version prefix** (e.g., endpoints are `/api/stocks` not `/api/v1/stocks`).

## Problem with No Versioning
- Cannot maintain multiple versions simultaneously
- Breaking changes affect all clients immediately
- Cannot deprecate endpoints gradually
- Clients have no migration path for API updates

## Recommended Versioning Strategy

### Option 1: URI Path Versioning (Recommended)
```
/api/v1/stocks        → Version 1 (current)
/api/v2/stocks        → Version 2 (future)
/api/v3/stocks        → Version 3 (future)
```

**Pros:**
- Clear version visibility
- Easy to maintain multiple versions
- Explicit deprecation path

**Cons:**
- Code duplication between versions
- More complex routing

### Option 2: Header-Based Versioning
```
GET /api/stocks
Accept: application/vnd.example.v1+json
```

**Pros:**
- Cleaner URLs
- Easier for browsers to test

**Cons:**
- Less visible
- Harder to track which version clients use

### Option 3: Query Parameter Versioning
```
GET /api/stocks?api_version=v1
```

**Pros:**
- Easiest to implement

**Cons:**
- Clutters URLs
- Easy to forget or override

## Implementation Plan

### Phase 1: Planning (Now)
- Decide on versioning strategy (recommend URI path)
- Document all current endpoints in v1
- Identify breaking vs non-breaking changes

### Phase 2: Code Changes (Before next breaking change)
```javascript
// Current structure (root index.js):
app.use("/api/stocks", stocksRoutes);
app.use("/api/prices", pricesRoutes);

// Versioned structure:
app.use("/api/v1/stocks", stocksRoutes);
app.use("/api/v1/prices", pricesRoutes);

// With deprecation warning:
app.use("/api/stocks", (req, res, next) => {
  res.setHeader('Deprecation', 'true');
  res.setHeader('Sunset', 'Sun, 31 Dec 2024 23:59:59 GMT');
  res.setHeader('Warning', '299 - "API v1 is deprecated, migrate to /api/v2"');
  next();
});
app.use("/api/stocks", stocksRoutes); // Forward to v1
```

### Phase 3: Deprecation (6 months before removal)
- Return `Deprecation: true` header
- Return `Sunset` header (removal date)
- Document migration guide
- Notify clients via changelog

### Phase 4: Removal (After deprecation period)
- Remove old version
- Update all clients
- Close migration window

## Deprecation Headers (HTTP Specification)

```http
HTTP/1.1 200 OK
Deprecation: true
Sunset: Sun, 31 Dec 2024 23:59:59 GMT
Link: </api/v2/stocks>; rel="successor-version"
Content-Type: application/json

{
  "success": true,
  "data": [...],
  "_deprecation": {
    "message": "API v1 is deprecated. Migrate to v2 by Dec 31, 2024",
    "migration_guide": "https://docs.example.com/v2-migration"
  }
}
```

## Current Action Item
**No immediate action required** - current codebase has no breaking changes planned.

When implementing a breaking change:
1. Create new version directory: `routes/v2/`
2. Update `index.js` to mount both v1 and v2
3. Add deprecation headers to v1
4. Document migration path

## Example Deprecated Endpoint Response

```javascript
router.get('/api/v1/stocks', deprecationWarning(), (req, res) => {
  // Return data with deprecation headers
  res.json({
    data: [...],
    _deprecation: {
      status: 'deprecated',
      sunset_date: '2025-01-01',
      successor: '/api/v2/stocks',
      migration_guide_url: 'https://docs.example.com/migrate-v2'
    }
  });
});
```

## Monitoring Deprecated Endpoints

Track usage via logs:
```javascript
const deprecationWarning = () => {
  return (req, res, next) => {
    res.setHeader('Deprecation', 'true');
    console.warn(`DEPRECATED: ${req.method} ${req.path} (migrate to v2)`);
    next();
  };
};
```

## Recommended Reading
- [RFC 8594: The Sunset HTTP Header Field](https://datatracker.ietf.org/doc/html/rfc8594)
- [API Versioning Best Practices](https://restfulapi.net/versioning-rest-api/)
