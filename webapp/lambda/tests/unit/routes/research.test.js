const request = require("supertest");
const express = require("express");
const researchRouter = require("../../../routes/research");

const app = express();
app.use("/api/research", researchRouter);

describe("Research Routes", () => {
  let consoleSpy;

  beforeEach(() => {
    consoleSpy = jest.spyOn(console, "log").mockImplementation();
    jest.spyOn(console, "error").mockImplementation();
    jest.clearAllMocks();
  });

  afterEach(() => {
    consoleSpy.mockRestore();
    jest.restoreAllMocks();
  });

  describe("GET /api/research/", () => {
    it("should return 501 status for not implemented endpoint", async () => {
      const response = await request(app)
        .get("/api/research/")
        .expect(501);

      expect(response.body).toEqual({
        success: false,
        error: "Research reports not implemented",
        details: "This endpoint requires research data integration with financial data providers for analyst reports, market research, and investment analysis.",
        troubleshooting: {
          suggestion: "Research reports require research data feed integration",
          required_setup: [
            "Research data provider integration (Bloomberg, Refinitiv, FactSet)",
            "Research reports database with full-text search",
            "Report categorization and tagging system",
            "Analyst and firm attribution tracking",
            "Research content aggregation and delivery"
          ],
          status: "Not implemented - requires research data integration"
        },
        symbol: null,
        filters: {
          category: "all",
          source: "all",
          limit: 15,
          days: 30
        },
        timestamp: expect.any(String)
      });
    });

    it("should handle symbol parameter", async () => {
      const response = await request(app)
        .get("/api/research/?symbol=AAPL")
        .expect(501);

      expect(response.body.symbol).toBe("AAPL");
      expect(consoleSpy).toHaveBeenCalledWith("📋 Research reports requested - symbol: AAPL, category: all");
    });

    it("should handle category parameter", async () => {
      const response = await request(app)
        .get("/api/research/?category=earnings")
        .expect(501);

      expect(response.body.filters.category).toBe("earnings");
      expect(consoleSpy).toHaveBeenCalledWith("📋 Research reports requested - symbol: all, category: earnings");
    });

    it("should handle source parameter", async () => {
      const response = await request(app)
        .get("/api/research/?source=bloomberg")
        .expect(501);

      expect(response.body.filters.source).toBe("bloomberg");
    });

    it("should handle limit parameter", async () => {
      const response = await request(app)
        .get("/api/research/?limit=25")
        .expect(501);

      expect(response.body.filters.limit).toBe(25);
    });

    it("should handle days parameter", async () => {
      const response = await request(app)
        .get("/api/research/?days=60")
        .expect(501);

      expect(response.body.filters.days).toBe(60);
    });

    it("should handle multiple parameters", async () => {
      const response = await request(app)
        .get("/api/research/?symbol=TSLA&category=market&source=refinitiv&limit=50&days=7")
        .expect(501);

      expect(response.body.symbol).toBe("TSLA");
      expect(response.body.filters).toEqual({
        category: "market",
        source: "refinitiv",
        limit: 50,
        days: 7
      });
    });

    it("should use default values when parameters are not provided", async () => {
      const response = await request(app)
        .get("/api/research/")
        .expect(501);

      expect(response.body.filters).toEqual({
        category: "all",
        source: "all",
        limit: 15,
        days: 30
      });
      expect(response.body.symbol).toBe(null);
    });

    it("should log correct request information", async () => {
      await request(app)
        .get("/api/research/?symbol=GOOGL&category=sector");

      expect(consoleSpy).toHaveBeenCalledWith("📋 Research reports requested - symbol: GOOGL, category: sector");
      expect(consoleSpy).toHaveBeenCalledWith("📋 Research reports - not implemented");
    });

    it("should include valid ISO timestamp", async () => {
      const response = await request(app)
        .get("/api/research/")
        .expect(501);

      const timestamp = response.body.timestamp;
      expect(timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
      expect(new Date(timestamp)).toBeInstanceOf(Date);
      expect(new Date(timestamp).getTime()).not.toBeNaN();
    });

    it("should have consistent troubleshooting structure", async () => {
      const response = await request(app)
        .get("/api/research/")
        .expect(501);

      expect(response.body.troubleshooting).toHaveProperty("suggestion");
      expect(response.body.troubleshooting).toHaveProperty("required_setup");
      expect(response.body.troubleshooting).toHaveProperty("status");
      expect(Array.isArray(response.body.troubleshooting.required_setup)).toBe(true);
      expect(response.body.troubleshooting.required_setup).toHaveLength(5);
    });

    it("should handle route error and return 500", async () => {
      // Mock console.log to throw an error
      consoleSpy.mockImplementation(() => {
        throw new Error("Logging failed");
      });

      const response = await request(app)
        .get("/api/research/")
        .expect(500);

      expect(response.body).toEqual({
        success: false,
        error: "Failed to fetch research reports",
        details: "Logging failed"
      });

      expect(console.error).toHaveBeenCalledWith("Research reports error:", expect.any(Error));
    });

    it("should handle edge case parameter values", async () => {
      const response = await request(app)
        .get("/api/research/?limit=0&days=-1")
        .expect(501);

      expect(response.body.filters.limit).toBe(0);
      expect(response.body.filters.days).toBe(-1);
    });

    it("should handle non-numeric limit parameter", async () => {
      const response = await request(app)
        .get("/api/research/?limit=abc&days=xyz")
        .expect(501);

      // parseInt("abc") returns NaN, which gets serialized as null in JSON
      expect(response.body.filters.limit).toBe(null);
      expect(response.body.filters.days).toBe(null);
    });
  });

  describe("GET /api/research/report/:id", () => {
    it("should return 404 for specific report requests", async () => {
      const response = await request(app)
        .get("/api/research/report/123")
        .expect(404);

      expect(response.body).toEqual({
        success: false,
        error: "Research report not found",
        message: "Research report 123 requires integration with research data providers",
        data_source: "database_query_required",
        recommendation: "Configure research data feeds and populate research_reports table"
      });
    });

    it("should handle different report IDs", async () => {
      const reportIds = ["abc", "123", "report-456", "uuid-format"];

      for (const id of reportIds) {
        const response = await request(app)
          .get(`/api/research/report/${id}`)
          .expect(404);

        expect(response.body.message).toBe(`Research report ${id} requires integration with research data providers`);
        expect(response.body.success).toBe(false);
      }
    });

    it("should handle special characters in report ID", async () => {
      const response = await request(app)
        .get("/api/research/report/test@report#123")
        .expect(404);

      // URL parsing stops at # (fragment), so only test@report is included in the ID
      expect(response.body.message).toBe("Research report test@report requires integration with research data providers");
    });

    it("should maintain consistent response structure", async () => {
      const response = await request(app)
        .get("/api/research/report/test-id")
        .expect(404);

      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body).toHaveProperty("message");
      expect(response.body).toHaveProperty("data_source");
      expect(response.body).toHaveProperty("recommendation");
    });
  });

  describe("GET /api/research/reports", () => {
    it("should return 501 for reports endpoint", async () => {
      const response = await request(app)
        .get("/api/research/reports")
        .expect(501);

      expect(response.body).toEqual({
        success: false,
        error: "Research reports not available",
        message: "Research reports require integration with research data providers",
        data_source: "database_query_required"
      });
    });

    it("should maintain consistent error structure", async () => {
      const response = await request(app)
        .get("/api/research/reports")
        .expect(501);

      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body).toHaveProperty("message");
      expect(response.body).toHaveProperty("data_source");
    });

    it("should not be affected by query parameters", async () => {
      const response = await request(app)
        .get("/api/research/reports?symbol=AAPL&category=all")
        .expect(501);

      // Response should be the same regardless of query params
      expect(response.body.error).toBe("Research reports not available");
    });
  });

  describe("Route consistency", () => {
    it("should handle all valid category values", async () => {
      const validCategories = ["all", "earnings", "market", "sector", "company"];

      for (const category of validCategories) {
        const response = await request(app)
          .get(`/api/research/?category=${category}`)
          .expect(501);

        expect(response.body.filters.category).toBe(category);
        expect(response.body.success).toBe(false);
      }
    });

    it("should handle invalid category gracefully", async () => {
      const response = await request(app)
        .get("/api/research/?category=invalid_category")
        .expect(501);

      expect(response.body.filters.category).toBe("invalid_category");
      expect(response.body.success).toBe(false);
    });

    it("should maintain error structure across all endpoints", async () => {
      const endpoints = [
        "/api/research/",
        "/api/research/reports"
      ];

      for (const endpoint of endpoints) {
        const response = await request(app)
          .get(endpoint)
          .expect(res => res.status === 501);

        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });
  });
});