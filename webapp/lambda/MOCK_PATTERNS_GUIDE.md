# Jest Mock Patterns Guide

## Quick Comparison: Working vs Failing Tests

### WORKING PATTERN (health.test.js)

```javascript
// 1. Mock dependencies FIRST
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  initializeDatabase: jest.fn(),
  getPool: jest.fn(),
  healthCheck: jest.fn(),
}));

// 2. Import mocked functions
const { query, initializeDatabase, getPool, healthCheck } = require('../../../utils/database');

// 3. Import routes AFTER mocking
const healthRoutes = require("../../../routes/health");

// 4. Create app with routes
let app;
beforeAll(() => {
  app = express();
  app.use(express.json());
  app.use("/health", healthRoutes);
});

// 5. Use mocks in tests
beforeEach(() => {
  jest.clearAllMocks();
  initializeDatabase.mockResolvedValue();
  healthCheck.mockResolvedValue({ status: "connected" });
});

test("should work", async () => {
  const response = await request(app).get("/health");
  expect(response.status).toBe(200);
});
```

**Key Points**:
- Mock defined before any imports
- Route code receives mocked database
- No real database connection
- Tests run in ~100ms (fast!)

---

### FAILING PATTERN (signals.test.js - current)

```javascript
// ❌ Real DB connects from jest.setup.js FIRST
// jest.setup.js runs and initializes database

// ❌ Then mock is defined (too late!)
const mockQuery = jest.fn();
jest.mock("../../../utils/database", () => ({
  query: mockQuery
}))

// ❌ Route imports get REAL database, not mock
const signalsRoutes = require("../../../routes/signals");

// ❌ Mock queues are set up but never used
mockQuery.mockResolvedValueOnce({ rows: [...] });
mockQuery.mockResolvedValueOnce({ rows: [...] });

test("should work", async () => {
  // ❌ Real database connection attempted here
  // ✗ Test fails: "Cannot connect to localhost:5432"
});
```

**What Goes Wrong**:
1. jest.setup.js initializes REAL database
2. Database module is cached with REAL pool
3. jest.mock() is defined but module already cached
4. Mock is ignored
5. Route tries to use REAL database
6. Tests fail with DB connection errors

---

## Pattern 1: Simple Route Tests

Use this for routes that don't make complex queries

```javascript
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  initializeDatabase: jest.fn(),
  getPool: jest.fn(),
  transaction: jest.fn(),
  healthCheck: jest.fn(),
}));

const { query } = require("../../../utils/database");
const appRoutes = require("../../../routes/myapp");

describe("App Routes", () => {
  let app;
  
  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/app", appRoutes);
  });
  
  beforeEach(() => {
    jest.clearAllMocks();
  });
  
  test("should return data", async () => {
    query.mockResolvedValue({
      rows: [{ id: 1, name: "test" }]
    });
    
    const response = await request(app).get("/app/list");
    expect(response.body.data).toEqual([{ id: 1, name: "test" }]);
  });
});
```

**When to Use**: 
- Simple GET/POST routes
- Routes with 1-2 database queries
- No complex filtering or transaction logic

---

## Pattern 2: Query Pattern Matching

Use this for routes with multiple query types

```javascript
const mockQuery = jest.fn();
jest.mock("../../../utils/database", () => ({
  query: mockQuery
}));

// ✅ Better than sequential mocks!
mockQuery.mockImplementation((sql, params) => {
  // Schema queries
  if (sql.includes("information_schema.columns")) {
    return Promise.resolve({
      rows: [
        { column_name: "id" },
        { column_name: "symbol" },
        { column_name: "price" }
      ]
    });
  }
  
  // List queries
  if (sql.includes("SELECT") && sql.includes("FROM signals")) {
    return Promise.resolve({
      rows: [
        { id: 1, symbol: "AAPL", price: 150 }
      ]
    });
  }
  
  // Count queries
  if (sql.includes("COUNT(*)")) {
    return Promise.resolve({
      rows: [{ count: 1 }]
    });
  }
  
  // Default
  return Promise.resolve({ rows: [] });
});
```

**Advantages**:
- Works regardless of query order
- Real DB won't override with different queries
- Easier to extend with new query types
- Better for debugging (can see which query matched)

**When to Use**:
- Routes with 3+ database queries
- Routes with optional filtering
- Routes with schema introspection
- Complex business logic routes

---

## Pattern 3: Utility/Service Tests

Use this for testing utility functions and services

```javascript
jest.mock("../../../utils/database");
jest.mock("../../../utils/apiKeyService");
jest.mock("crypto");

const { query } = require("../../../utils/database");
const { storeApiKey } = require("../../../utils/apiKeyService");

describe("API Key Service", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // ✅ Clear module cache to reset singletons
    delete require.cache[require.resolve("../../../utils/apiKeyService")];
  });
  
  test("should store key", async () => {
    query.mockResolvedValue({ rows: [], rowCount: 1 });
    
    const result = await storeApiKey("token", "alpaca", { key: "x" });
    
    expect(result.success).toBe(true);
    expect(query).toHaveBeenCalledWith(
      expect.stringContaining("INSERT"),
      expect.any(Array)
    );
  });
});
```

**Key Points**:
- Clear require cache to reset singletons
- All dependencies must be mocked
- Test the function, not the database

---

## Pattern 4: Transaction Tests

Use this for tests involving transactions

```javascript
jest.mock("../../../utils/database");

const { transaction } = require("../../../utils/database");

describe("Transactions", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });
  
  test("should commit on success", async () => {
    const mockClient = {
      query: jest.fn()
        .mockResolvedValueOnce()  // BEGIN
        .mockResolvedValueOnce({ rows: [] })  // INSERT
        .mockResolvedValueOnce(),  // COMMIT
      release: jest.fn()
    };
    
    transaction.mockImplementation(async (callback) => {
      await mockClient.query("BEGIN");
      try {
        const result = await callback(mockClient);
        await mockClient.query("COMMIT");
        mockClient.release();
        return result;
      } catch (error) {
        await mockClient.query("ROLLBACK");
        mockClient.release();
        throw error;
      }
    });
    
    const result = await transaction(async (client) => {
      await client.query("INSERT ...");
      return "success";
    });
    
    expect(result).toBe("success");
  });
});
```

---

## Pattern 5: Error Handling Tests

Use this for testing error scenarios

```javascript
const mockQuery = jest.fn();
jest.mock("../../../utils/database", () => ({
  query: mockQuery
}));

describe("Error Handling", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });
  
  test("should handle DB connection error", async () => {
    mockQuery.mockRejectedValue(
      new Error("connect ECONNREFUSED 127.0.0.1:5432")
    );
    
    const response = await request(app).get("/api/data");
    
    expect(response.status).toBe(500);
    expect(response.body.error).toContain("connection");
  });
  
  test("should handle query timeout", async () => {
    mockQuery.mockRejectedValue(
      new Error("Query timeout after 5000ms")
    );
    
    const response = await request(app).get("/api/data");
    
    expect(response.status).toBe(500);
    expect(response.body.error).toContain("timeout");
  });
  
  test("should handle data validation error", async () => {
    mockQuery.mockRejectedValue(
      new Error('duplicate key value violates unique constraint')
    );
    
    const response = await request(app).post("/api/data");
    
    expect(response.status).toBe(400);
  });
});
```

---

## Pattern 6: Middleware Tests

Use this for testing middleware

```javascript
jest.mock("../../../utils/database");
jest.mock("jsonwebtoken");

const jwt = require("jsonwebtoken");
const { authenticateToken } = require("../../../middleware/auth");

describe("Auth Middleware", () => {
  let req, res, next;
  
  beforeEach(() => {
    req = { headers: {}, user: null };
    res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn().mockReturnThis()
    };
    next = jest.fn();
    jest.clearAllMocks();
  });
  
  test("should authenticate valid token", () => {
    req.headers.authorization = "Bearer valid-token";
    jwt.verify = jest.fn().mockReturnValue({
      id: "user123",
      email: "test@example.com"
    });
    
    authenticateToken(req, res, next);
    
    expect(req.user).toEqual({ id: "user123", email: "test@example.com" });
    expect(next).toHaveBeenCalled();
  });
  
  test("should reject missing token", () => {
    authenticateToken(req, res, next);
    
    expect(res.status).toHaveBeenCalledWith(401);
    expect(next).not.toHaveBeenCalled();
  });
});
```

---

## Common Mock Setup Mistakes

### ❌ Mistake 1: Mock after import

```javascript
// ❌ WRONG - mock defined after import
const database = require("../../../utils/database");
jest.mock("../../../utils/database", () => ({
  query: jest.fn()
}));
// Too late! database already cached
```

### ✅ Fix 1: Mock before import

```javascript
// ✅ CORRECT
jest.mock("../../../utils/database", () => ({
  query: jest.fn()
}));
const database = require("../../../utils/database");
```

---

### ❌ Mistake 2: Forgetting jest.clearAllMocks()

```javascript
// ❌ WRONG - mocks carry state between tests
test("first test", () => {
  query.mockResolvedValue({ rows: [1] });
  // ...
});

test("second test", () => {
  // ✗ First test's mock is still active!
  query.mockResolvedValue({ rows: [2] });
  // ...
});
```

### ✅ Fix 2: Clear mocks in beforeEach

```javascript
// ✅ CORRECT
beforeEach(() => {
  jest.clearAllMocks();  // Reset all mocks
});

test("first test", () => {
  query.mockResolvedValue({ rows: [1] });
  // ...
});

test("second test", () => {
  query.mockResolvedValue({ rows: [2] });
  // ✓ Clean mock state
});
```

---

### ❌ Mistake 3: Sequential mocks with unpredictable query order

```javascript
// ❌ WRONG - relies on exact query order
mockQuery.mockResolvedValueOnce({ rows: [...] });  // Query 1
mockQuery.mockResolvedValueOnce({ rows: [...] });  // Query 2
mockQuery.mockResolvedValueOnce({ rows: [...] });  // Query 3
// If real DB attempts different queries first, mocks are wrong
```

### ✅ Fix 3: Use pattern matching instead

```javascript
// ✅ CORRECT
mockQuery.mockImplementation((sql) => {
  if (sql.includes("SELECT id FROM users")) {
    return Promise.resolve({ rows: [...] });
  }
  if (sql.includes("UPDATE users")) {
    return Promise.resolve({ rowCount: 1 });
  }
  return Promise.resolve({ rows: [] });
});
```

---

## Test Configuration for Mocking

### jest.config.js for Unit Tests

```javascript
module.exports = {
  testEnvironment: "node",
  // ✅ Skip integration setup for unit tests
  setupFilesAfterEnv: process.env.TEST_ENV === 'integration' 
    ? ["<rootDir>/jest.setup.js"] 
    : [],
  
  testTimeout: process.env.TEST_ENV === 'integration' ? 60000 : 5000,
  maxWorkers: process.env.TEST_ENV === 'integration' ? 1 : 4,
  
  // ✅ Clear mocks for unit tests
  clearMocks: process.env.TEST_ENV !== 'integration',
  resetMocks: process.env.TEST_ENV !== 'integration',
  restoreMocks: process.env.TEST_ENV !== 'integration',
};
```

### Run Unit Tests

```bash
# Use mocked database
TEST_ENV=unit npm test -- signals.test.js

# Use real database
TEST_ENV=integration npm test -- signals.integration.test.js
```

---

## Verification Checklist

Before submitting tests, verify:

- [ ] All `jest.mock()` calls are at TOP of file
- [ ] Mocked modules imported AFTER jest.mock()
- [ ] Real modules imported AFTER jest.mock()
- [ ] jest.clearAllMocks() in beforeEach()
- [ ] Mock responses match actual database structure
- [ ] Error scenarios tested with mockRejectedValue()
- [ ] Query patterns are distinct and don't overlap
- [ ] Tests pass with TEST_ENV=unit
- [ ] Tests pass with TEST_ENV=integration (if integration test)
- [ ] No "Cannot connect to database" errors

---

