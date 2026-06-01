/**
 * Analyst Routes Unit Tests - Real YFinance Data Only
 * Tests the analyst routes that use actual data from YFinance loaders
 */
const express = require("express");
const request = require("supertest");
// Mock database for unit tests
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
}));

const { query, closeDatabase, initializeDatabase, getPool, transaction, healthCheck } = require('../../../utils/database');

describe("Analyst Routes Unit Tests - Real YFinance Data", () => {
  let app;
  beforeAll(() => {
    process.env.NODE_ENV = "test";
    app = express();
    app.use(express.json());
    // Load analyst routes
    const analystRouter = require("../../../routes/analysts");
    app.use("/api/analysts", analystRouter);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });
  describe("GET /api/analysts/", () => {
    test("should return API overview with real YFinance endpoints", async () => {
      const response = await request(app)
        .get("/api/analysts/")
        .expect(200);
      expect(response.body).toHaveProperty("message", "Analysts API - Real YFinance Data Only");
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("endpoints");
      expect(response.body).toHaveProperty("data_sources");
      expect(response.body.endpoints).toContain("/upgrades - Get analyst upgrades/downgrades from YFinance");
      expect(response.body.endpoints).toContain("/revenue-estimates - Get revenue estimates with analyst counts");
      expect(response.body.data_sources).toHaveProperty("upgrades");
      expect(response.body.data_sources).toHaveProperty("revenue_estimates");
    });
  });
  describe("GET /api/analysts/upgrades", () => {
    test("should return analyst upgrades from real YFinance data", async () => {
      const mockUpgrades = [
        {
          id: 1,
          symbol: "AAPL",
          firm: "Goldman Sachs",
          action: "upgrade",
          from_grade: "Hold",
          to_grade: "Buy",
          date: "2024-01-15",
          details: "Strong iPhone sales outlook",
          fetched_at: "2025-09-21T16:19:44.467Z"
        }
      ];
      query
        .mockResolvedValueOnce({ rows: mockUpgrades }) // main query
        .mockResolvedValueOnce({ rows: [{ total: "1" }] }); // count query
      const response = await request(app)
        .get("/api/analysts/upgrades")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("source", "YFinance via loadanalystupgradedowngrade.py");
      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0]).toHaveProperty("symbol", "AAPL");
      expect(response.body.data[0]).toHaveProperty("firm", "Goldman Sachs");
      expect(response.body.data[0]).toHaveProperty("action", "upgrade");
      expect(response.body.data[0]).toHaveProperty("from_grade", "Hold");
      expect(response.body.data[0]).toHaveProperty("to_grade", "Buy");
      expect(response.body).toHaveProperty("pagination");
    });
    test("should handle pagination parameters", async () => {
      query
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [{ total: "0" }] });
      const response = await request(app)
        .get("/api/analysts/upgrades?page=2&limit=10")
        .expect(200);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("LIMIT $1 OFFSET $2"),
        [10, 10]
      );
    });
  });
  describe("GET /api/analysts/revenue-estimates", () => {
    test("should return revenue estimates from real YFinance data", async () => {
      const mockEstimates = [
        {
          symbol: "AAPL",
          period: "0q",
          avg_estimate: 85000000000,
          low_estimate: 83000000000,
          high_estimate: 87000000000,
          number_of_analysts: 12,
          year_ago_revenue: 81000000000,
          growth: 0.049,
          fetched_at: "2025-09-28T01:09:43.465Z"
        }
      ];
      query.mockResolvedValueOnce({ rows: mockEstimates });
      const response = await request(app)
        .get("/api/analysts/revenue-estimates")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("source", "YFinance via loadrevenueestimate.py");
      expect(response.body.data[0]).toHaveProperty("symbol", "AAPL");
      expect(response.body.data[0]).toHaveProperty("number_of_analysts", 12);
      expect(response.body.data[0]).toHaveProperty("avg_estimate");
      expect(response.body.data[0]).toHaveProperty("growth");
    });
  });
  describe("GET /api/analysts/:symbol", () => {
    test("should return all analyst data for a symbol from real YFinance tables", async () => {
      const mockUpgrades = [
        {
          id: 1,
          symbol: "AAPL",
          firm: "Goldman Sachs",
          action: "upgrade",
          from_grade: "Hold",
          to_grade: "Buy",
          date: "2024-01-15",
          details: "iPhone sales growth",
          fetched_at: "2025-09-21T16:19:44.467Z"
        }
      ];
      const mockRevenueEstimates = [
        {
          symbol: "AAPL",
          period: "0q",
          avg_estimate: 85000000000,
          number_of_analysts: 12,
          growth: 0.049,
          fetched_at: "2025-09-28T01:09:43.465Z"
        }
      ];
      query
        .mockResolvedValueOnce({ rows: mockUpgrades })        // upgrades query
        .mockResolvedValueOnce({ rows: mockRevenueEstimates }); // revenue estimates query
      const response = await request(app)
        .get("/api/analysts/AAPL")
        .expect(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("symbol", "AAPL");
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("upgrades_downgrades");
      expect(response.body.data).toHaveProperty("revenue_estimates");
      expect(response.body).toHaveProperty("counts");
      expect(response.body.counts).toHaveProperty("upgrades_downgrades", 1);
      expect(response.body.counts).toHaveProperty("revenue_estimates", 1);
      expect(response.body.counts).toHaveProperty("total_analysts_covering", 12);
      expect(response.body).toHaveProperty("sources");
      expect(response.body.sources).toHaveProperty("upgrades_downgrades", "YFinance via loadanalystupgradedowngrade.py");
      expect(response.body.sources).toHaveProperty("revenue_estimates", "YFinance via loadrevenueestimate.py");
    });
  });
  describe("Error Handling", () => {
    test("should handle database query failures", async () => {
      query.mockRejectedValueOnce(new Error("Database connection failed"));
      const response = await request(app)
        .get("/api/analysts/upgrades")
        .expect(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error", "Failed to fetch analyst upgrades");
    });
    test("should handle null database results", async () => {
      query.mockResolvedValueOnce(null);
      const response = await request(app)
        .get("/api/analysts/upgrades")
        .expect(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error", "Database query failed");
    });
    test("should handle symbol-specific query failures", async () => {
      query.mockRejectedValueOnce(new Error("Symbol not found"));
      const response = await request(app)
        .get("/api/analysts/INVALID")
        .expect(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error", "Failed to fetch analyst data for symbol");
      expect(response.body).toHaveProperty("symbol", "INVALID");
    });
  });
});
