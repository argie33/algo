const request = require("supertest");
const express = require("express");

// Mock database BEFORE importing routes
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn().mockResolvedValue(undefined),
  closeDatabase: jest.fn().mockResolvedValue(undefined),
  getPool: jest.fn(),
  transaction: jest.fn(),
  healthCheck: jest.fn(),
}));

// Import the mocked database
const { query } = require("../../../utils/database");

// Mock auth middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123" };
    next();
  }),
  authorizeAdmin: jest.fn((req, res, next) => next()),
  checkApiKey: jest.fn((req, res, next) => next()),
}));

// Import the mocked database

const sectorRouter = require("../../../routes/sectors");

let app;

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
      // Schema validation queries
      if (sql.includes("information_schema.tables")) {
        return Promise.resolve({ rows: [{ exists: true }] });
      }

      // Stock symbols table queries
      if (sql.includes("stock_symbols")) {
        return Promise.resolve({
          rows: [
            { symbol: "AAPL", name: "Apple Inc." },
            { symbol: "MSFT", name: "Microsoft Corp" },
          ],
        });
      }

      // Price data queries
      if (sql.includes("price_daily")) {
        return Promise.resolve({
          rows: [
            { symbol: "AAPL", date: "2025-10-18", close: 230.5, volume: 50000000 },
            { symbol: "MSFT", date: "2025-10-18", close: 430.0, volume: 30000000 },
          ],
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
          ],
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
          ],
        });
      }

      // Default case - return empty rows
      return Promise.resolve({ rows: [] });
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
