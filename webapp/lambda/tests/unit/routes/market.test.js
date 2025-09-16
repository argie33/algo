const express = require("express");
const request = require("supertest");

// Real database for integration
const { query } = require("../../../utils/database");

describe("Market Routes Unit Tests", () => {
  let app;

  beforeAll(() => {
    // Create test app
    app = express();
    app.use(express.json());

    // Mock authentication middleware - allow all requests through
    app.use((req, res, next) => {
      req.user = { sub: "test-user-123" }; // Mock authenticated user
      next();
    });

    // Add response formatter middleware
    const responseFormatter = require("../../../middleware/responseFormatter");
    app.use(responseFormatter);

    // Load market routes
    const marketRouter = require("../../../routes/market");
    app.use("/market", marketRouter);
  });

  describe("GET /market/", () => {
    test("should return market info", async () => {
      const response = await request(app).get("/market/").expect(200);

      expect(response.body).toHaveProperty("success");
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("endpoint");
      expect(response.body.data.endpoint).toBe("market");
      expect(response.body.data).toHaveProperty("available_routes");
      expect(Array.isArray(response.body.data.available_routes)).toBe(true);
    });
  });

  describe("GET /market/debug", () => {
    test("should return debug information", async () => {
      const response = await request(app).get("/market/debug").expect(200);

      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("tables");
      expect(response.body).toHaveProperty("recordCounts");
    });
  });

  describe("GET /market/overview", () => {
    test("should return market overview", async () => {
      const response = await request(app).get("/market/overview").expect(200);

      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("data");
    });
  });

  describe("GET /market/sectors", () => {
    test("should return sector data", async () => {
      const response = await request(app).get("/market/sectors").expect(200);

      expect(response.body).toHaveProperty("success");
    });
  });

  describe("GET /market/economic", () => {
    test("should return economic data", async () => {
      const response = await request(app).get("/market/economic").expect(200);

      expect(response.body).toHaveProperty("success");
    });
  });

  describe("GET /market/sentiment", () => {
    test("should return sentiment history with AAII data", async () => {
      const response = await request(app)
        .get("/market/sentiment?days=30")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");

      // The /sentiment endpoint returns current sentiment data, not historical
      expect(response.body.data).toHaveProperty("fear_greed");
      expect(response.body.data).toHaveProperty("naaim");

      // Check if AAII data is present
      if (response.body.data.aaii) {
        expect(response.body.data.aaii).toHaveProperty("bullish");
        expect(response.body.data.aaii).toHaveProperty("neutral");
        expect(response.body.data.aaii).toHaveProperty("bearish");
        expect(response.body.data.aaii).toHaveProperty("date");
      }
    });

    test("should handle sentiment with custom parameters", async () => {
      const response = await request(app)
        .get("/market/sentiment?days=7&limit=10")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("fear_greed");
      expect(response.body.data).toHaveProperty("naaim");
    });
  });

  describe("GET /market/aaii", () => {
    test("should return AAII sentiment data", async () => {
      const response = await request(app).get("/market/aaii").expect(200);

      // AAII endpoint returns data directly without success wrapper
      if (response.body && typeof response.body === "object") {
        expect(response.body).toHaveProperty("bullish");
        expect(response.body).toHaveProperty("neutral");
        expect(response.body).toHaveProperty("bearish");
        expect(response.body).toHaveProperty("date");
      }
    });
  });

  // Add comprehensive tests for major market endpoints
  describe("GET /market/data", () => {
    test("should return market data with success flag", async () => {
      const response = await request(app).get("/market/data").expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
    });

    test("should handle query parameters", async () => {
      const response = await request(app)
        .get("/market/data?limit=5&sort=volume")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
    });
  });

  describe("GET /market/overview", () => {
    test("should return market overview data", async () => {
      const response = await request(app).get("/market/overview").expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");

      if (response.body.data) {
        expect(response.body.data).toHaveProperty("indices");
        expect(response.body.data).toHaveProperty("market_status");
      }
    });

    test("should handle market overview with parameters", async () => {
      const response = await request(app)
        .get("/market/overview?detailed=true")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
    });
  });

  describe("GET /market/sectors/performance", () => {
    test("should return sector performance data", async () => {
      const response = await request(app)
        .get("/market/sectors/performance")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
    });

    test("should handle sector performance with timeframe", async () => {
      const response = await request(app)
        .get("/market/sectors/performance?timeframe=1d")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
    });
  });

  describe("GET /market/economic/indicators", () => {
    test("should return economic indicators", async () => {
      const response = await request(app)
        .get("/market/economic/indicators")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");

      if (response.body.data) {
        expect(response.body.data).toHaveProperty("indicators");
        expect(response.body.data).toHaveProperty("summary");
      }
    });

    test("should filter by category", async () => {
      const response = await request(app)
        .get("/market/economic/indicators?category=inflation")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
    });

    test("should include historical data when requested", async () => {
      const response = await request(app)
        .get("/market/economic/indicators?historical=true")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      if (response.body.data && response.body.data.indicators) {
        const indicators = Object.values(response.body.data.indicators);
        if (indicators.length > 0) {
          // Some indicators should have historical data
          const hasHistorical = indicators.some((ind) => ind.historical_data);
          expect(hasHistorical).toBeTruthy();
        }
      }
    });
  });

  describe("GET /market/breadth", () => {
    test("should return market breadth data", async () => {
      const response = await request(app).get("/market/breadth").expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
    });

    test("should handle breadth with parameters", async () => {
      const response = await request(app)
        .get("/market/breadth?period=5d")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
    });
  });

  describe("GET /market/summary", () => {
    test("should return market summary", async () => {
      const response = await request(app).get("/market/summary").expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
    });

    test("should handle summary with filters", async () => {
      const response = await request(app)
        .get("/market/summary?include_sectors=true")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
    });
  });

  describe("GET /market/naaim", () => {
    test("should return NAAIM data", async () => {
      const response = await request(app).get("/market/naaim").expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
    });
  });

  describe("GET /market/ping", () => {
    test("should return ping response", async () => {
      const response = await request(app).get("/market/ping").expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("message");
    });
  });

  // Error handling tests
  describe("Error Handling", () => {
    test("should handle invalid query parameters gracefully", async () => {
      const response = await request(app)
        .get("/market/overview?limit=invalid")
        .expect(200); // Most endpoints handle invalid params gracefully

      expect(response.body).toHaveProperty("success");
    });

    test("should handle missing optional parameters", async () => {
      const response = await request(app)
        .get("/market/economic/indicators?category=")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
    });
  });
});
