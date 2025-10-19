const request = require("supertest");
const express = require("express");

// Mock database BEFORE importing routes
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  initializeDatabase: jest.fn().mockResolvedValue(undefined),
  closeDatabase: jest.fn().mockResolvedValue(undefined),
  getPool: jest.fn(),
  transaction: jest.fn(),
  healthCheck: jest.fn(),
}));

// Import the mocked database
const { query, initializeDatabase} = require("../../../utils/database");

// Mock auth middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    if (!req.headers.authorization) {
      return res.status(401).json({ error: "No authorization header" });
    }
    req.user = { sub: "test-user-123", role: "user" };
    next();
  }),
  authorizeAdmin: jest.fn((req, res, next) => next()),
  checkApiKey: jest.fn((req, res, next) => next()),
}));

// Import app AFTER mocking all dependencies
const app = require("../../../server");

// Import the mocked database

const sectorRouter = require("../../../routes/sectors");


describe("Sectors Routes", () => {
  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/api/sectors", sectorRouter);
  });

  afterAll(() => {
    // Cleanup if needed
  });

  beforeEach(() => {
    jest.clearAllMocks();

    // Mock database query responses based on SQL patterns
    query.mockImplementation((sql, params) => {
      // Handle COUNT queries
      if (sql.includes("COUNT(*)") || sql.includes("count(*)")) {
        return Promise.resolve({ rows: [{ count: 243, total: 243 }], rowCount: 1 });
      }

      // Schema validation queries
      if (sql.includes("information_schema.tables")) {
        return Promise.resolve({ rows: [{ exists: true }], rowCount: 1 });
      }

      // Sector analysis queries with market data
      if (sql.includes("SELECT") && sql.includes("sector") && (sql.includes("performance") || sql.includes("return"))) {
        return Promise.resolve({
          rows: [
            { sector: "Technology", performance: 12.5, return_1d: 1.2, return_1m: 5.3, stocks_count: 40 },
            { sector: "Healthcare", performance: 8.3, return_1d: 0.8, return_1m: 3.2, stocks_count: 35 },
            { sector: "Financials", performance: 6.2, return_1d: 0.5, return_1m: 2.1, stocks_count: 30 },
            { sector: "Energy", performance: -2.1, return_1d: -0.3, return_1m: -1.2, stocks_count: 15 },
            { sector: "Consumer", performance: 4.5, return_1d: 0.3, return_1m: 1.8, stocks_count: 25 }
          ],
          rowCount: 5
        });
      }

      // Stock symbols table queries
      if (sql.includes("stock_symbols")) {
        return Promise.resolve({
          rows: [
            { symbol: "AAPL", name: "Apple Inc." },
            { symbol: "MSFT", name: "Microsoft Corp" },
            { symbol: "GOOGL", name: "Alphabet Inc." },
          ],
          rowCount: 3
        });
      }

      // Price data queries
      if (sql.includes("price_daily")) {
        return Promise.resolve({
          rows: [
            { symbol: "AAPL", date: "2025-10-18", close: 230.5, volume: 50000000 },
            { symbol: "MSFT", date: "2025-10-18", close: 430.0, volume: 30000000 },
            { symbol: "GOOGL", date: "2025-10-18", close: 155.0, volume: 25000000 },
          ],
          rowCount: 3
        });
      }

      // Company profile queries
      if (sql.includes("company_profile")) {
        return Promise.resolve({
          rows: [
            {
              symbol: "AAPL",
              name: "Apple Inc.",
              sector: "Technology",
              industry: "Consumer Electronics",
            },
            {
              symbol: "MSFT",
              name: "Microsoft Corp",
              sector: "Technology",
              industry: "Software",
            },
          ],
          rowCount: 2
        });
      }

      // Stock scores queries
      if (sql.includes("stock_scores")) {
        return Promise.resolve({
          rows: [
            {
              symbol: "AAPL",
              quality_score: 75,
              momentum_score: 80,
              value_score: 65,
              growth_score: 72,
              composite_score: 73,
            },
            {
              symbol: "MSFT",
              quality_score: 72,
              momentum_score: 75,
              value_score: 60,
              growth_score: 70,
              composite_score: 69,
            }
          ],
          rowCount: 2
        });
      }

      // Default case - return empty rows
      return Promise.resolve({ rows: [], rowCount: 0 });
    });
  });

  describe("GET /api/sectors", () => {
    test("should return sector performance data", async () => {
      const response = await request(app).get("/api/sectors");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);

      if (response.body.data.length > 0) {
        const sector = response.body.data[0];
        expect(sector).toHaveProperty("sector");
        expect(sector).toHaveProperty("performance");
      }
    });
  });

  describe("GET /api/sectors/performance", () => {
    test("should return detailed sector performance", async () => {
      const response = await request(app).get("/api/sectors/performance");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test("should handle period parameter", async () => {
      const response = await request(app).get(
        "/api/sectors/performance?period=1m"
      );

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
    });
  });

  describe("GET /api/sectors/leaders", () => {
    test("should return sector leaders", async () => {
      const response = await request(app).get("/api/sectors/leaders");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("top_performing_sectors");
      expect(response.body.data).toHaveProperty("sector_breadth");
    });
  });

  describe("GET /api/sectors/rotation", () => {
    test("should return sector rotation analysis", async () => {
      const response = await request(app).get("/api/sectors/rotation");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("sector_rankings");
      expect(response.body.data).toHaveProperty("market_cycle");
    });
  });

  describe("GET /api/sectors/:sector/details", () => {
    test("should return specific sector data", async () => {
      const response = await request(app)
        .get("/api/sectors/Technology/details")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("sector");
      expect(response.body.data).toHaveProperty("stocks");
    });
  });

  describe("GET /api/sectors/:sector/stocks", () => {
    test("should return stocks in sector", async () => {
      const response = await request(app).get("/api/sectors/Technology/stocks");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test("should handle limit parameter", async () => {
      const response = await request(app).get(
        "/api/sectors/Technology/stocks?limit=10"
      );

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data.length).toBeLessThanOrEqual(10);
    });
  });

  describe("GET /api/sectors/allocation", () => {
    test("should return sector allocation data", async () => {
      const response = await request(app)
        .get("/api/sectors/allocation")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("allocation");
      expect(Array.isArray(response.body.data.allocation)).toBe(true);
    });
  });
});
