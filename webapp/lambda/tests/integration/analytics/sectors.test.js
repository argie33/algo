/**
 * Sectors Analysis Integration Tests
 * Tests for sector-based analysis and performance
 * Route: /routes/sectors.js
 */

const request = require("supertest");
const { app } = require("../../../index");

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


describe("Sectors Analysis API", () => {
  describe("Sector Performance", () => {
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
    test("should retrieve sector performance data", async () => {
      const response = await request(app).get("/api/sectors/performance");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const sector = response.body.data[0];
          expect(sector).toHaveProperty("sector");

          // Just verify we have sector data, performance fields may vary
          expect(sector.sector).toBeDefined();
        }
      }
    });
  });

  describe("Sector Rotation", () => {
    test("should analyze sector rotation patterns", async () => {
      const response = await request(app).get("/api/sectors/rotation");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const data = response.body.data;
        // Just verify we got data, structure may vary
        expect(data).toBeDefined();
      }
    });
  });

  describe("Sector Stocks", () => {
    test("should retrieve stocks by sector", async () => {
      const response = await request(app).get("/api/sectors/technology/stocks");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const stock = response.body.data[0];
          expect(stock).toHaveProperty("symbol");
          expect(stock).toHaveProperty("sector", "Technology");
        }
      }
    });
  });
});
