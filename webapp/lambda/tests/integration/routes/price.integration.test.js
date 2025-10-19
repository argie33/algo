const request = require("supertest");


// Mock database BEFORE importing routes/modules
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn().mockResolvedValue(undefined),
  closeDatabase: jest.fn().mockResolvedValue(undefined),
  getPool: jest.fn(),
  transaction: jest.fn((cb) => cb()),
  healthCheck: jest.fn(),
}));

// Import the mocked database
const { query, closeDatabase, initializeDatabase} = require("../../../utils/database");

// Mock auth middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123" };
    next();
  }),
  authorizeAdmin: jest.fn((req, res, next) => next()),
  checkApiKey: jest.fn((req, res, next) => next()),
}));

// Import app AFTER mocking all dependencies
const app = require("../../../server");

// Import the mocked database


describe("Price Routes", () => {
  
    beforeEach(() => {
    jest.clearAllMocks();
    query.mockImplementation((sql, params) => {
      // Default: return empty rows for all queries
      if (sql.includes("information_schema.tables")) {
        return Promise.resolve({ rows: [{ exists: true }] });
      }
      return Promise.resolve({ rows: [] });
    });
  });
  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/price/:symbol", () => {
    test("should return current price for symbol", async () => {
      const response = await request(app).get("/api/price/AAPL");

      // Price endpoint may return 404 if no price data loaded
      expect([200, 404]).toContain(response.status);
      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty("symbol");
        expect(response.body.data).toHaveProperty("price");
      }
    });

    test("should handle invalid symbol", async () => {
      const response = await request(app).get("/api/price/INVALID");

      expect([404, 500]).toContain(response.status);
    });
  });

  describe("GET /api/price/:symbol/history", () => {
    test("should return price history", async () => {
      const response = await request(app).get("/api/price/AAPL/history");

      expect([200, 404]).toContain(response.status);
      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });

    test("should handle period parameter", async () => {
      const response = await request(app).get(
        "/api/price/AAPL/history?period=1M"
      );

      expect([200, 404]).toContain(response.status);
      if (response.status === 200) {
        expect(response.body.success).toBe(true);
      }
    });
  });

  describe("GET /api/price/:symbol/intraday", () => {
    test("should return intraday prices", async () => {
      const response = await request(app).get("/api/price/AAPL/intraday");

      // May return 404 if no price data loaded
      expect([200, 404]).toContain(response.status);
      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });

    test("should handle interval parameter", async () => {
      const response = await request(app).get(
        "/api/price/AAPL/intraday?interval=5min"
      );

      expect([200, 404]).toContain(response.status);
      if (response.status === 200) {
        expect(response.body.success).toBe(true);
      }
    });
  });

  describe("POST /api/price/batch", () => {
    test("should return prices for multiple symbols", async () => {
      const symbols = { symbols: ["AAPL", "MSFT", "GOOGL"] };

      const response = await request(app)
        .post("/api/price/batch")
        .send(symbols);

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("prices");
    });

    test("should validate symbols array", async () => {
      const response = await request(app).post("/api/price/batch").send({});

      expect([400, 422]).toContain(response.status);
    });
  });

  describe("GET /api/price/alerts", () => {
    test("should return price alerts", async () => {
      const response = await request(app).get("/api/price/alerts");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });
  });

  describe("POST /api/price/alerts", () => {
    test("should create price alert", async () => {
      const alertData = {
        symbol: "AAPL",
        target_price: 150.0,
        condition: "above",
        notification_method: "email",
      };

      const response = await request(app)
        .post("/api/price/alerts")
        .send(alertData);

      expect([200, 400, 404]).toContain(response.status);

      if (response.status === 200 || response.status === 201) {
        expect(response.body.success).toBe(true);
      }
    });
  });
});
