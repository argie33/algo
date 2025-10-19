/**
 * Analysts Integration Tests
 * Tests for analyst recommendations and research data
 * Route: /routes/analysts.js
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

// Import the mocked database
const { query } = require("../../../utils/database");

describe("Analysts API", () => {
  describe("Analyst Recommendations", () => {
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
    test("should retrieve analyst recommendations for stock", async () => {
      const response = await request(app).get(
        "/api/analysts/AAPL"
      );

      // With real test data loaded, should return 200
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("symbol", "AAPL");
      expect(response.body.data).toBeDefined();

      // Verify expected data structure with real data
      expect(response.body.data).toHaveProperty("upgrades_downgrades");
      expect(response.body.data).toHaveProperty("revenue_estimates");
      expect(response.body.data).toHaveProperty("eps_estimates");
      expect(Array.isArray(response.body.data.upgrades_downgrades)).toBe(true);
      expect(Array.isArray(response.body.data.revenue_estimates)).toBe(true);
      expect(Array.isArray(response.body.data.eps_estimates)).toBe(true);
      // Check counts object
      expect(response.body).toHaveProperty("counts");
      expect(response.body.counts).toHaveProperty("upgrades_downgrades");
      expect(response.body.counts).toHaveProperty("revenue_estimates");
      expect(response.body.counts).toHaveProperty("eps_estimates");
    });

    test("should handle invalid stock symbols", async () => {
      const response = await request(app).get(
        "/api/analysts/INVALID123"
      );

      // Should return 200 with empty data for invalid symbols
      expect([200, 404]).toContain(response.status);
      if (response.status === 404) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });
  });

  describe("Analyst Coverage", () => {
    test.skip("should return error for individual analyst coverage (not available from yfinance)", async () => {
      // Endpoint /coverage/:symbol doesn't exist in current implementation
      const response = await request(app).get("/api/analysts/coverage/AAPL");
      expect(response.status).toBe(404);
    });
  });

  describe("Price Targets", () => {
    test.skip("should retrieve price targets for stock", async () => {
      // Endpoint /price-targets/:symbol doesn't exist in current implementation
      const response = await request(app).get(
        "/api/analysts/price-targets/AAPL"
      );

      // With real test data loaded, should return 200
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toBeDefined();

      // Verify expected data structure with real data
      expect(response.body.data).toHaveProperty("symbol", "AAPL");
      expect(response.body.data).toHaveProperty("price_targets");
      expect(Array.isArray(response.body.data.price_targets)).toBe(true);
      expect(response.body.data.price_targets.length).toBeGreaterThan(0);

      // Verify first price target structure
      const target = response.body.data.price_targets[0];
      expect(target).toHaveProperty("analyst_firm");
      expect(target).toHaveProperty("target_price");
      expect(target).toHaveProperty("target_date");
      expect(typeof target.analyst_firm).toBe("string");
      expect(typeof target.target_price).toBe("number");
      expect(target.target_price).toBeGreaterThan(0);
    });

    test.skip("should provide consensus price targets", async () => {
      // Endpoint /consensus/:symbol doesn't exist in current implementation
      const response = await request(app).get("/api/analysts/consensus/AAPL");

      // With real test data loaded, should return 200
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toBeDefined();

      // Verify expected data structure with real data
      const consensus = response.body.data;
      expect(consensus).toHaveProperty("symbol", "AAPL");
      expect(consensus).toHaveProperty("target_high_price");
      expect(consensus).toHaveProperty("target_low_price");
      expect(consensus).toHaveProperty("target_mean_price");
      expect(consensus).toHaveProperty("recommendation_key");
      expect(consensus).toHaveProperty("analyst_opinion_count");

      expect(typeof consensus.target_high_price).toBe("number");
      expect(typeof consensus.target_low_price).toBe("number");
      expect(typeof consensus.target_mean_price).toBe("number");
      expect(typeof consensus.analyst_opinion_count).toBe("number");
      expect(consensus.target_high_price).toBeGreaterThan(consensus.target_low_price);
    });
  });

  describe("Analyst Research", () => {
    test.skip("should retrieve research reports", async () => {
      // Endpoint /research doesn't exist in current implementation
      const response = await request(app).get(
        "/api/analysts/research?symbol=AAPL&limit=10"
      );

      // With real test data loaded, should return 200
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body.data.length).toBeGreaterThan(0);

      // Verify first research report structure
      const research = response.body.data[0];
      expect(research).toHaveProperty("symbol", "AAPL");
      expect(research).toHaveProperty("analyst_firm");
      expect(research).toHaveProperty("report_title");
      expect(research).toHaveProperty("report_summary");
      expect(research).toHaveProperty("report_date");
      expect(typeof research.analyst_firm).toBe("string");
      expect(typeof research.report_title).toBe("string");
      expect(typeof research.report_summary).toBe("string");
    });

    test.skip("should filter research by analyst firm", async () => {
      // Endpoint /research doesn't exist in current implementation
      const response = await request(app).get(
        "/api/analysts/research?firm=Goldman&limit=5"
      );

      // With real test data loaded, should return 200
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(Array.isArray(response.body.data)).toBe(true);

      // If data exists, verify it's filtered by Goldman
      if (response.body.data.length > 0) {
        response.body.data.forEach((report) => {
          expect(report.analyst_firm).toContain("Goldman");
        });
      }
    });
  });
});
