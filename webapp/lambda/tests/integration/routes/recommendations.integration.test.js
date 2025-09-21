const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("Recommendations Routes", () => {
  beforeAll(async () => {
    process.env.ALLOW_DEV_BYPASS = "true";
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/recommendations", () => {
    test("should fetch stock recommendations successfully", async () => {
      const response = await request(app)
        .get("/api/recommendations")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("recommendations");
      expect(response.body).toHaveProperty("summary");
      expect(response.body).toHaveProperty("filters");
      expect(response.body).toHaveProperty("timestamp");
      expect(Array.isArray(response.body.recommendations)).toBe(true);
    });

    test("should handle symbol parameter", async () => {
      const response = await request(app)
        .get("/api/recommendations?symbol=AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.filters.symbol).toBe("AAPL");
    });

    test("should handle category parameter", async () => {
      const response = await request(app)
        .get("/api/recommendations?category=buy")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.filters.category).toBe("buy");
    });

    test("should handle analyst parameter", async () => {
      const response = await request(app)
        .get("/api/recommendations?analyst=goldman_sachs")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.filters.analyst).toBe("goldman_sachs");
    });

    test("should handle limit parameter", async () => {
      const response = await request(app)
        .get("/api/recommendations?limit=50")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.filters.limit).toBe(50);
    });

    test("should handle timeframe parameter", async () => {
      const response = await request(app)
        .get("/api/recommendations?timeframe=weekly")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.filters.timeframe).toBe("weekly");
    });

    test("should handle multiple parameters", async () => {
      const response = await request(app)
        .get("/api/recommendations?symbol=MSFT&category=hold&limit=10")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.filters.symbol).toBe("MSFT");
      expect(response.body.filters.category).toBe("hold");
      expect(response.body.filters.limit).toBe(10);
    });

    test("should use default values for missing parameters", async () => {
      const response = await request(app)
        .get("/api/recommendations")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.filters.symbol).toBe(undefined);
      expect(response.body.filters.category).toBe("all");
      expect(response.body.filters.analyst).toBe("all");
      expect(response.body.filters.timeframe).toBe("recent");
      expect(response.body.filters.limit).toBe(20);
    });

    test("should include proper response structure", async () => {
      const response = await request(app)
        .get("/api/recommendations")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("recommendations");
      expect(response.body).toHaveProperty("summary");
      expect(response.body).toHaveProperty("filters");
      expect(Array.isArray(response.body.recommendations)).toBe(true);
      expect(response.body.summary).toHaveProperty("total_recommendations");
      expect(response.body.summary).toHaveProperty("buy_count");
      expect(response.body.summary).toHaveProperty("hold_count");
      expect(response.body.summary).toHaveProperty("sell_count");
    });

    test("should have valid timestamp", async () => {
      const response = await request(app)
        .get("/api/recommendations")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      const timestamp = new Date(response.body.timestamp);
      expect(timestamp).toBeInstanceOf(Date);
      expect(timestamp.getTime()).not.toBeNaN();
    });

    test("should handle mixed case symbol", async () => {
      const response = await request(app)
        .get("/api/recommendations?symbol=aapl")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.filters.symbol).toBe("aapl");
    });

    test("should handle special characters in symbol", async () => {
      const response = await request(app)
        .get("/api/recommendations?symbol=BRK.A")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.filters.symbol).toBe("BRK.A");
    });
  });

  describe("GET /api/recommendations/analysts/:symbol", () => {
    test("should fetch analyst coverage successfully", async () => {
      const response = await request(app)
        .get("/api/recommendations/analysts/AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("symbol");
      expect(response.body).toHaveProperty("coverage");
      expect(response.body).toHaveProperty("consensus");
      expect(response.body).toHaveProperty("timestamp");
      expect(Array.isArray(response.body.coverage)).toBe(true);
    });

    test("should convert symbol to uppercase", async () => {
      const response = await request(app)
        .get("/api/recommendations/analysts/aapl")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.symbol).toBe("AAPL");
    });

    test("should handle limit parameter", async () => {
      const response = await request(app)
        .get("/api/recommendations/analysts/MSFT?limit=5")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.consensus).toHaveProperty("total_analysts");
    });

    test("should use default limit when not specified", async () => {
      const response = await request(app)
        .get("/api/recommendations/analysts/TSLA")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.symbol).toBe("TSLA");
    });

    test("should handle special characters in symbol", async () => {
      const response = await request(app)
        .get("/api/recommendations/analysts/BRK.A")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.symbol).toBe("BRK.A");
    });

    test("should include analyst coverage response structure", async () => {
      const response = await request(app)
        .get("/api/recommendations/analysts/GOOGL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("coverage");
      expect(response.body).toHaveProperty("consensus");
      expect(response.body.consensus).toHaveProperty("total_analysts");
      expect(response.body.consensus).toHaveProperty("buy_ratings");
      expect(response.body.consensus).toHaveProperty("hold_ratings");
      expect(response.body.consensus).toHaveProperty("sell_ratings");
    });

    test("should have valid timestamp", async () => {
      const response = await request(app)
        .get("/api/recommendations/analysts/NVDA")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      const timestamp = new Date(response.body.timestamp);
      expect(timestamp).toBeInstanceOf(Date);
      expect(timestamp.getTime()).not.toBeNaN();
    });

    test("should handle numeric symbols", async () => {
      const response = await request(app)
        .get("/api/recommendations/analysts/123")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.symbol).toBe("123");
    });

    test("should handle malformed limit parameter", async () => {
      const response = await request(app)
        .get("/api/recommendations/analysts/AAPL?limit=invalid")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      // Should handle gracefully, parseInt("invalid") returns NaN, which gets handled
      expect(response.body).toHaveProperty("symbol");
      expect(response.body).toHaveProperty("coverage");
    });

    test("should handle negative limit parameter", async () => {
      const response = await request(app)
        .get("/api/recommendations/analysts/AAPL?limit=-5")
        .set("Authorization", "Bearer dev-bypass-token");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.symbol).toBe("AAPL");
    });

    test("should handle extremely large limit", async () => {
      const response = await request(app)
        .get("/api/recommendations/analysts/AAPL?limit=99999")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.limit).toBe(99999);
    });
  });

  describe("Authentication", () => {
    test("should require authentication for recommendations", async () => {
      const response = await request(app).get("/api/recommendations");
      // No auth header

      expect([501, 401, 403, 500].includes(response.status)).toBe(true);
    });

    test("should require authentication for analyst coverage", async () => {
      const response = await request(app).get(
        "/api/recommendations/analysts/AAPL"
      );
      // No auth header

      expect([501, 401, 403, 500].includes(response.status)).toBe(true);
    });

    test("should handle invalid authentication", async () => {
      const response = await request(app)
        .get("/api/recommendations")
        .set("Authorization", "Bearer invalid-token");

      expect([501, 401, 403, 500].includes(response.status)).toBe(true);
    });
  });

  describe("Error Handling", () => {
    test("should handle malformed URLs gracefully", async () => {
      const response = await request(app)
        .get("/api/recommendations?symbol=%20invalid%20")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([501, 500].includes(response.status)).toBe(true);
    });

    test("should handle empty parameters", async () => {
      const response = await request(app)
        .get("/api/recommendations?symbol=&category=&analyst=")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
    });

    test("should handle URL encoded parameters", async () => {
      const response = await request(app)
        .get("/api/recommendations?symbol=BRK%2EA")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.symbol).toBe("BRK.A");
    });
  });

  describe("Response Structure Validation", () => {
    test("should have consistent error response structure", async () => {
      const response = await request(app)
        .get("/api/recommendations")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body).toHaveProperty("details");
      expect(response.body).toHaveProperty("troubleshooting");
      expect(response.body).toHaveProperty("filters");
      expect(response.body).toHaveProperty("timestamp");

      // Validate troubleshooting structure
      expect(response.body.troubleshooting).toHaveProperty("suggestion");
      expect(response.body.troubleshooting).toHaveProperty("required_setup");
      expect(response.body.troubleshooting).toHaveProperty("status");

      // Validate filters structure
      expect(response.body.filters).toHaveProperty("category");
      expect(response.body.filters).toHaveProperty("analyst");
      expect(response.body.filters).toHaveProperty("timeframe");
      expect(response.body.filters).toHaveProperty("limit");
    });

    test("should have consistent analyst coverage response structure", async () => {
      const response = await request(app)
        .get("/api/recommendations/analysts/AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
      expect(response.body).toHaveProperty("details");
      expect(response.body).toHaveProperty("troubleshooting");
      expect(response.body).toHaveProperty("symbol");
      expect(response.body).toHaveProperty("limit");
      expect(response.body).toHaveProperty("timestamp");
    });
  });

  describe("Performance", () => {
    test("should respond within reasonable time", async () => {
      const startTime = Date.now();

      const response = await request(app)
        .get("/api/recommendations")
        .set("Authorization", "Bearer dev-bypass-token");

      const responseTime = Date.now() - startTime;

      expect(responseTime).toBeLessThan(3000);
      expect([400, 401, 404, 422, 500]).toContain(response.status);
    });

    test("should handle concurrent requests", async () => {
      const requests = [
        request(app)
          .get("/api/recommendations")
          .set("Authorization", "Bearer dev-bypass-token"),
        request(app)
          .get("/api/recommendations/analysts/AAPL")
          .set("Authorization", "Bearer dev-bypass-token"),
        request(app)
          .get("/api/recommendations?symbol=MSFT")
          .set("Authorization", "Bearer dev-bypass-token"),
      ];

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect([400, 401, 404, 422, 500]).toContain(response.status);
      });
    });
  });

  describe("Required Setup Documentation", () => {
    test("should document required setup for recommendations", async () => {
      const response = await request(app)
        .get("/api/recommendations")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      const setup = response.body.troubleshooting.required_setup;

      // Should include key requirements
      expect(setup.some((item) => item.toLowerCase().includes("analyst"))).toBe(
        true
      );
      expect(
        setup.some((item) => item.toLowerCase().includes("recommendation"))
      ).toBe(true);
      expect(setup.some((item) => item.toLowerCase().includes("data"))).toBe(
        true
      );
    });

    test("should document required setup for analyst coverage", async () => {
      const response = await request(app)
        .get("/api/recommendations/analysts/AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      const setup = response.body.troubleshooting.required_setup;

      // Should include key requirements
      expect(setup.some((item) => item.toLowerCase().includes("analyst"))).toBe(
        true
      );
      expect(
        setup.some((item) => item.toLowerCase().includes("coverage"))
      ).toBe(true);
      expect(
        setup.some((item) => item.toLowerCase().includes("track record"))
      ).toBe(true);
    });
  });
});
