/**
 * Analysts Route Tests
 * Tests analyst upgrades/downgrades, recommendations, and price targets
 */

const request = require("supertest");
const express = require("express");

const analystsRouter = require("../../../routes/analysts");

// Mock dependencies
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn().mockResolvedValue({}),
}));

jest.mock("../../../utils/logger", () => ({
  error: jest.fn(),
  info: jest.fn(),
  warn: jest.fn(),
  debug: jest.fn(),
}));

const { query } = require("../../../utils/database");

// Create test app
const app = express();
app.use(express.json());
app.use("/api/analysts", analystsRouter);

describe("Analysts Routes", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    console.log = jest.fn();
    console.error = jest.fn();
  });

  describe("GET /api/analysts/upgrades", () => {
    const mockUpgrades = [
      {
        symbol: "AAPL",
        company_name: "Apple Inc.",
        from_grade: "Hold",
        to_grade: "Buy",
        action: "Upgrade",
        firm: "Goldman Sachs",
        date: "2024-01-15",
        details: "Raised price target on strong iPhone sales",
      },
      {
        symbol: "MSFT",
        company_name: "Microsoft Corporation",
        from_grade: "Buy",
        to_grade: "Strong Buy",
        action: "Upgrade",
        firm: "Morgan Stanley",
        date: "2024-01-14",
        details: "Cloud growth exceeding expectations",
      },
    ];

    const mockCount = [{ total: "50" }];

    test("should return analyst upgrades with pagination", async () => {
      query
        .mockResolvedValueOnce({ rows: mockUpgrades, rowCount: 2 })
        .mockResolvedValueOnce({ rows: mockCount, rowCount: 1 });

      const response = await request(app).get("/api/analysts/upgrades");

      expect(response.status).toBe(200);
      expect(response.body).toEqual({
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            company_name: "Apple Inc.",
            company: "Apple Inc.", // Should map company_name to company
            from_grade: "Hold",
            to_grade: "Buy",
            action: "Upgrade",
            firm: "Goldman Sachs",
          }),
        ]),
        pagination: {
          page: 1,
          limit: 25,
          total: 50,
          totalPages: 2,
          hasNext: true,
          hasPrev: false,
        },
      });

      expect(query).toHaveBeenCalledTimes(2);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("FROM analyst_upgrade_downgrade"),
        [25, 0]
      );
    });

    test("should handle custom pagination parameters", async () => {
      query
        .mockResolvedValueOnce({ rows: mockUpgrades, rowCount: 2 })
        .mockResolvedValueOnce({ rows: [{ total: "100" }], rowCount: 1 });

      const response = await request(app)
        .get("/api/analysts/upgrades")
        .query({ page: 3, limit: 10 });

      expect(response.status).toBe(200);
      expect(response.body.pagination).toEqual({
        page: 3,
        limit: 10,
        total: 100,
        totalPages: 10,
        hasNext: true,
        hasPrev: true,
      });

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("FROM analyst_upgrade_downgrade"),
        [10, 20] // limit=10, offset=(3-1)*10=20
      );
    });

    test("should handle invalid pagination parameters", async () => {
      query
        .mockResolvedValueOnce({ rows: mockUpgrades, rowCount: 2 })
        .mockResolvedValueOnce({ rows: mockCount, rowCount: 1 });

      const response = await request(app)
        .get("/api/analysts/upgrades")
        .query({ page: "invalid", limit: "invalid" });

      expect(response.status).toBe(200);
      expect(response.body.pagination).toEqual({
        page: 1, // Should default to 1
        limit: 25, // Should default to 25
        total: 50,
        totalPages: 2,
        hasNext: true,
        hasPrev: false,
      });
    });

    test("should handle empty upgrades data", async () => {
      query
        .mockResolvedValueOnce({ rows: [], rowCount: 0 })
        .mockResolvedValueOnce({ rows: [{ total: "0" }], rowCount: 1 });

      const response = await request(app).get("/api/analysts/upgrades");

      expect(response.status).toBe(200);
      expect(response.body.data).toEqual([]);
      expect(response.body.pagination.total).toBe(0);
      expect(response.body.pagination.totalPages).toBe(0);
    });

    test("should handle database table not found", async () => {
      query.mockRejectedValue(
        new Error('relation "analyst_upgrade_downgrade" does not exist')
      );

      const response = await request(app).get("/api/analysts/upgrades");

      expect(response.status).toBe(500);
      expect(response.body.error).toBe("Failed to fetch analyst upgrades");
      expect(response.body.message).toContain("does not exist");
    });

    test("should handle malformed upgrades data", async () => {
      query.mockResolvedValueOnce({ rows: "not an array" });

      const response = await request(app).get("/api/analysts/upgrades");

      expect(response.status).toBe(500);
      expect(response.body.error).toBe("Failed to fetch analyst upgrades");
    });

    test("should handle missing count data", async () => {
      query
        .mockResolvedValueOnce({ rows: mockUpgrades, rowCount: 2 })
        .mockResolvedValueOnce({ rows: [], rowCount: 0 });

      const response = await request(app).get("/api/analysts/upgrades");

      expect(response.status).toBe(500);
      expect(response.body).toEqual({
        error: "Failed to fetch analyst upgrades",
        message: "No count returned from analyst_upgrade_downgrade query",
      });
    });

    test("should handle database query error", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app).get("/api/analysts/upgrades");

      expect(response.status).toBe(500);
      expect(response.body).toEqual({
        error: "Failed to fetch analyst upgrades",
        message: "Database connection failed",
      });
    });

    test("should validate SQL query structure", async () => {
      query
        .mockResolvedValueOnce({ rows: mockUpgrades, rowCount: 2 })
        .mockResolvedValueOnce({ rows: mockCount, rowCount: 1 });

      await request(app).get("/api/analysts/upgrades");

      const calls = query.mock.calls;
      expect(calls[0][0]).toContain("FROM analyst_upgrade_downgrade aud");
      expect(calls[0][0]).toContain("LEFT JOIN company_profile cp");
      expect(calls[0][0]).toContain("ORDER BY aud.date DESC");
      expect(calls[0][0]).toContain("LIMIT $1 OFFSET $2");
      expect(calls[1][0]).toContain("COUNT(*) as total");
    });
  });

  describe("GET /api/analysts/:ticker/recommendations", () => {
    const mockRecommendations = [
      {
        period: "2024-01",
        strong_buy: 15,
        buy: 10,
        hold: 5,
        sell: 2,
        strong_sell: 1,
        collected_date: "2024-01-15",
      },
      {
        period: "2023-12",
        strong_buy: 12,
        buy: 8,
        hold: 6,
        sell: 3,
        strong_sell: 1,
        collected_date: "2023-12-15",
      },
    ];

    test("should return recommendations for valid ticker", async () => {
      query.mockResolvedValue({ rows: mockRecommendations, rowCount: 2 });

      const response = await request(app).get(
        "/api/analysts/AAPL/recommendations"
      );

      expect(response.status).toBe(200);
      expect(response.body).toEqual({
        ticker: "AAPL",
        recommendations: mockRecommendations,
      });

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("FROM analyst_recommendations"),
        ["AAPL"]
      );
    });

    test("should convert ticker to uppercase", async () => {
      query.mockResolvedValue({ rows: mockRecommendations, rowCount: 2 });

      await request(app).get("/api/analysts/aapl/recommendations");

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("WHERE symbol = $1"),
        ["AAPL"]
      );
    });

    test("should handle empty recommendations", async () => {
      query.mockResolvedValue({ rows: [], rowCount: 0 });

      const response = await request(app).get(
        "/api/analysts/XYZ/recommendations"
      );

      expect(response.status).toBe(200);
      expect(response.body.recommendations).toEqual([]);
    });

    test("should handle database error for recommendations", async () => {
      query.mockRejectedValue(new Error("Table not found"));

      const response = await request(app).get(
        "/api/analysts/AAPL/recommendations"
      );

      expect(response.status).toBe(500);
      expect(response.body).toEqual({
        error: "Failed to fetch recommendations",
      });
    });

    test("should limit recommendations to 12 results", async () => {
      query.mockResolvedValue({ rows: mockRecommendations, rowCount: 2 });

      await request(app).get("/api/analysts/AAPL/recommendations");

      expect(query).toHaveBeenCalledWith(expect.stringContaining("LIMIT 12"), [
        "AAPL",
      ]);
    });

    test("should order by collected_date DESC", async () => {
      query.mockResolvedValue({ rows: mockRecommendations, rowCount: 2 });

      await request(app).get("/api/analysts/AAPL/recommendations");

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("ORDER BY collected_date DESC"),
        ["AAPL"]
      );
    });
  });

  describe("Error Handling", () => {
    test("should handle malformed database responses", async () => {
      query.mockResolvedValue({ rows: null });

      const response = await request(app).get("/api/analysts/upgrades");

      expect(response.status).toBe(500);
      expect(response.body.error).toBe("Failed to fetch analyst upgrades");
    });

    test("should handle network timeouts", async () => {
      query.mockRejectedValue(new Error("Connection timeout"));

      const response = await request(app).get(
        "/api/analysts/AAPL/recommendations"
      );

      expect(response.status).toBe(500);
      expect(response.body.error).toBe("Failed to fetch recommendations");
    });

    test("should log errors appropriately", async () => {
      query.mockRejectedValue(new Error("Test error"));

      await request(app).get("/api/analysts/upgrades");

      expect(console.error).toHaveBeenCalledWith(
        "Error fetching analyst upgrades:",
        expect.any(Error)
      );
    });
  });

  describe("Data Transformation", () => {
    test("should map company_name to company field", async () => {
      const upgradesWithCompany = [
        {
          symbol: "TEST",
          company_name: "Test Company Inc.",
          from_grade: "Hold",
          to_grade: "Buy",
        },
      ];

      query
        .mockResolvedValueOnce({ rows: upgradesWithCompany, rowCount: 1 })
        .mockResolvedValueOnce({ rows: [{ total: "1" }], rowCount: 1 });

      const response = await request(app).get("/api/analysts/upgrades");

      expect(response.body.data[0]).toHaveProperty(
        "company",
        "Test Company Inc."
      );
      expect(response.body.data[0]).toHaveProperty(
        "company_name",
        "Test Company Inc."
      );
    });

    test("should handle null company_name", async () => {
      const upgradesWithNullCompany = [
        {
          symbol: "TEST",
          company_name: null,
          from_grade: "Hold",
          to_grade: "Buy",
        },
      ];

      query
        .mockResolvedValueOnce({ rows: upgradesWithNullCompany, rowCount: 1 })
        .mockResolvedValueOnce({ rows: [{ total: "1" }], rowCount: 1 });

      const response = await request(app).get("/api/analysts/upgrades");

      expect(response.body.data[0]).toHaveProperty("company", null);
    });
  });

  describe("Pagination Logic", () => {
    test("should calculate pagination correctly for edge cases", async () => {
      query
        .mockResolvedValueOnce({ rows: [], rowCount: 0 })
        .mockResolvedValueOnce({ rows: [{ total: "1" }], rowCount: 1 });

      const response = await request(app)
        .get("/api/analysts/upgrades")
        .query({ page: 1, limit: 10 });

      expect(response.body.pagination).toEqual({
        page: 1,
        limit: 10,
        total: 1,
        totalPages: 1,
        hasNext: false,
        hasPrev: false,
      });
    });

    test("should handle large page numbers", async () => {
      query
        .mockResolvedValueOnce({ rows: [], rowCount: 0 })
        .mockResolvedValueOnce({ rows: [{ total: "100" }], rowCount: 1 });

      const response = await request(app)
        .get("/api/analysts/upgrades")
        .query({ page: 50, limit: 5 });

      expect(response.body.pagination).toEqual({
        page: 50,
        limit: 5,
        total: 100,
        totalPages: 20,
        hasNext: false,
        hasPrev: true,
      });

      // Offset should be (50-1)*5 = 245
      expect(query).toHaveBeenCalledWith(expect.any(String), [5, 245]);
    });

    test("should handle zero total results", async () => {
      query
        .mockResolvedValueOnce({ rows: [], rowCount: 0 })
        .mockResolvedValueOnce({ rows: [{ total: "0" }], rowCount: 1 });

      const response = await request(app).get("/api/analysts/upgrades");

      expect(response.body.pagination.totalPages).toBe(0);
      expect(response.body.pagination.hasNext).toBe(false);
      expect(response.body.pagination.hasPrev).toBe(false);
    });
  });

  describe("SQL Query Validation", () => {
    test("should use proper joins and filters", async () => {
      query
        .mockResolvedValueOnce({ rows: [], rowCount: 0 })
        .mockResolvedValueOnce({ rows: [{ total: "0" }], rowCount: 1 });

      await request(app).get("/api/analysts/upgrades");

      const upgradesQuery = query.mock.calls[0][0];
      expect(upgradesQuery).toContain(
        "LEFT JOIN company_profile cp ON aud.symbol = cp.ticker"
      );
      expect(upgradesQuery).toContain("ORDER BY aud.date DESC");

      const countQuery = query.mock.calls[1][0];
      expect(countQuery).toContain("SELECT COUNT(*) as total");
      expect(countQuery).toContain("FROM analyst_upgrade_downgrade");
    });

    test("should use parameterized queries", async () => {
      query.mockResolvedValue({ rows: [], rowCount: 0 });

      await request(app).get("/api/analysts/AAPL/recommendations");

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("WHERE symbol = $1"),
        ["AAPL"]
      );
    });
  });
});
