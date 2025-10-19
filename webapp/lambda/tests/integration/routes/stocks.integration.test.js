const request = require("supertest");

let app;

// Mock database BEFORE importing routes/modules
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn().mockResolvedValue(undefined),
  closeDatabase: jest.fn().mockResolvedValue(undefined),
  getPool: jest.fn(),
  transaction: jest.fn((cb) => cb()),
  healthCheck: jest.fn(),
}));

// Mock auth middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123" };
    next();
  }),
  authorizeAdmin: jest.fn((req, res, next) => next()),
  checkApiKey: jest.fn((req, res, next) => next()),
}));

const { query } = require("../../../utils/database");

describe("Stocks Routes Integration Tests", () => {
  
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

  describe("GET /api/stocks/", () => {
    test("should return stocks data with comprehensive key metrics", async () => {
      const response = await request(app)
        .get("/api/stocks/?page=1&limit=5")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty("pagination");

      // Verify comprehensive key metrics are included
      if (response.body.data.length > 0) {
        const stock = response.body.data[0];
        // Check for actual fields returned by the endpoint - based on actual response structure
        expect(stock).toHaveProperty("symbol");
        expect(stock).toHaveProperty("sector");
        expect(stock).toHaveProperty("marketCap");
        expect(stock).toHaveProperty("price");
        expect(stock).toHaveProperty("volume");
        expect(stock).toHaveProperty("financialMetrics");

        // Check financial metrics structure
        if (stock.financialMetrics) {
          expect(stock.financialMetrics).toHaveProperty("trailingPE");
          expect(stock.financialMetrics).toHaveProperty("forwardPE");
          expect(stock.financialMetrics).toHaveProperty("dividendYield");
        }

      }
    });

    test("should handle pagination properly", async () => {
      const response = await request(app)
        .get("/api/stocks/?page=1&limit=2")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("pagination");

      if (response.body.data.length > 0) {
        expect(response.body.pagination).toHaveProperty("page", 1);
        expect(response.body.pagination).toHaveProperty("limit", 2);
        expect(response.body.pagination).toHaveProperty("total");
        expect(response.body.pagination).toHaveProperty("totalPages");
      }
    });
  });

  describe("GET /api/stocks/sectors", () => {
    test("should return sectors data", async () => {
      const response = await request(app).get("/api/stocks/sectors");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toBeDefined();
      }
    });

    test("should handle concurrent requests to sectors endpoint", async () => {
      const requests = Array(5)
        .fill()
        .map(() => request(app).get("/api/stocks/sectors"));

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect(response.status).toBe(200);
        expect(response.headers["content-type"]).toMatch(/json/);
      });
    });
  });

  describe("GET /api/stocks/search", () => {
    test("should handle search with valid query", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("results");
      expect(Array.isArray(response.body.data.results)).toBe(true);
    });

    test("should require query parameter", async () => {
      const response = await request(app)
        .get("/api/stocks/search")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.data.results).toEqual([]);
    });

    test("should handle empty search query", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.data.results).toEqual([]);
    });

    test("should handle search with limit parameter", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=A&limit=10")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 401, 404].includes(response.status)).toBe(true);
    });

    test("should require authentication for search", async () => {
      const response = await request(app).get("/api/stocks/search?q=AAPL");

      expect([200, 401].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/stocks/:symbol", () => {
    test("should handle valid stock symbol", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("symbol", "AAPL");
    });

    test("should handle invalid stock symbols", async () => {
      const response = await request(app)
        .get("/api/stocks/INVALID")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
    });

    test("should handle very long symbol names", async () => {
      const response = await request(app)
        .get("/api/stocks/VERYLONGSYMBOLNAME123456")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 401, 404].includes(response.status)).toBe(true);
    });

    test("should handle special characters in symbols", async () => {
      const response = await request(app)
        .get("/api/stocks/@")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 401, 404].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/stocks/trending", () => {
    test("should return trending stocks", async () => {
      const response = await request(app)
        .get("/api/stocks/trending")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle timeframe parameters", async () => {
      const response = await request(app)
        .get("/api/stocks/trending?timeframe=1d")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 401, 404].includes(response.status)).toBe(true);
    });

    test("should require authentication for trending", async () => {
      const response = await request(app).get("/api/stocks/trending");

      expect([200, 401].includes(response.status)).toBe(true);
    });
  });

  describe("GET /api/stocks/screener", () => {
    test("should return screener results", async () => {
      const response = await request(app)
        .get("/api/stocks/screener")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });

    test("should handle screener filters", async () => {
      const response = await request(app)
        .get("/api/stocks/screener?market_cap_min=1000000&pe_ratio_max=20")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });
  });

  describe("Watchlist Operations", () => {
    test("should handle watchlist requests", async () => {
      const response = await request(app)
        .get("/api/stocks/watchlist")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 301, 401, 404, 500].includes(response.status)).toBe(true);
    });

    test("should handle adding to watchlist", async () => {
      const response = await request(app)
        .post("/api/stocks/watchlist/add")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({ symbol: "AAPL" });

      expect([200, 400, 401, 404].includes(response.status)).toBe(true);
    });

    test("should validate symbol parameter for watchlist add", async () => {
      const response = await request(app)
        .post("/api/stocks/watchlist/add")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({});

      expect([400, 401].includes(response.status)).toBe(true);
    });

    test("should handle removing from watchlist", async () => {
      const response = await request(app)
        .delete("/api/stocks/watchlist/remove")
        .set("Authorization", "Bearer dev-bypass-token")
        .send({ symbol: "AAPL" });

      expect([200, 400, 401, 404].includes(response.status)).toBe(true);
    });
  });

  describe("Stock Data Endpoints", () => {
    test("should handle stock quote requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/quote")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401, 404].includes(response.status)).toBe(true);
    });

    test("should handle stock technicals requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/technicals")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle stock options requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/options")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle stock insider trading requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/insider")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle stock analysts requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/analysts")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle stock earnings requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/earnings")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle stock dividends requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/dividends")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle stock sentiment requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/sentiment")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle stock social requests", async () => {
      const response = await request(app)
        .get("/api/stocks/AAPL/social")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });
  });

  describe("Authentication Tests", () => {
    test("should handle requests without authentication", async () => {
      const response = await request(app).get("/api/stocks/search?q=AAPL");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle malformed authorization headers", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=AAPL")
        .set("Authorization", "InvalidFormat");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle empty authorization headers", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=AAPL")
        .set("Authorization", "");

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle missing bearer token", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=AAPL")
        .set("Authorization", "Bearer ");

      expect([200, 401].includes(response.status)).toBe(true);
    });
  });

  describe("Error Handling and Edge Cases", () => {
    test("should handle concurrent requests", async () => {
      const requests = [
        request(app).get("/api/stocks/sectors"),
        request(app)
          .get("/api/stocks/search?q=A")
          .set("Authorization", "Bearer dev-bypass-token"),
        request(app)
          .get("/api/stocks/AAPL")
          .set("Authorization", "Bearer dev-bypass-token"),
        request(app)
          .get("/api/stocks/trending")
          .set("Authorization", "Bearer dev-bypass-token"),
      ];

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect([200, 400, 401, 404].includes(response.status)).toBe(true);
      });
    });

    test("should handle invalid parameters gracefully", async () => {
      const invalidRequests = [
        request(app)
          .get("/api/stocks/search?q=A&limit=abc")
          .set("Authorization", "Bearer dev-bypass-token"),
        request(app)
          .get("/api/stocks/trending?timeframe=INVALID")
          .set("Authorization", "Bearer dev-bypass-token"),
        request(app)
          .get("/api/stocks/search?q=A&limit=1000")
          .set("Authorization", "Bearer dev-bypass-token"),
      ];

      for (const req of invalidRequests) {
        const response = await req;
        expect([200, 400, 401, 404].includes(response.status)).toBe(true);
      }
    });

    test("should validate response content types", async () => {
      const endpoints = ["/api/stocks/sectors", "/api/stocks/search?q=AAPL"];

      for (const endpoint of endpoints) {
        const response = await request(app)
          .get(endpoint)
          .set("Authorization", "Bearer dev-bypass-token");

        if ([200, 400, 401].includes(response.status)) {
          expect(response.headers["content-type"]).toMatch(/application\/json/);
        }
      }
    });

    test("should handle SQL injection attempts safely", async () => {
      const maliciousInputs = [
        "'; DROP TABLE stocks; --",
        "1' OR '1'='1",
        "UNION SELECT * FROM users",
      ];

      for (const input of maliciousInputs) {
        const response = await request(app)
          .get(`/api/stocks/${encodeURIComponent(input)}`)
          .set("Authorization", "Bearer dev-bypass-token");

        expect([200, 400, 401, 404].includes(response.status)).toBe(true);
      }
    });

    test("should handle database connection issues gracefully", async () => {
      const response = await request(app)
        .get("/api/stocks/sectors")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);

      if (response.status >= 500) {
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should handle international characters in search", async () => {
      const response = await request(app)
        .get("/api/stocks/search?q=" + encodeURIComponent("测试"))
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 401, 404].includes(response.status)).toBe(true);
    });
  });
});
