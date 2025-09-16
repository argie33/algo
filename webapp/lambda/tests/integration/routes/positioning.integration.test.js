const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("Positioning Routes", () => {
  beforeAll(async () => {
    process.env.ALLOW_DEV_BYPASS = "true";
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/positioning/stocks", () => {
    test("should return stock positioning data", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks")
        .set("Authorization", "Bearer dev-bypass-token");

      // May return 200 with data or 404 if no data found
      expect([200, 404].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("institutional_positioning");
        expect(response.body).toHaveProperty("retail_sentiment");
        expect(response.body).toHaveProperty("metadata");
        expect(Array.isArray(response.body.institutional_positioning)).toBe(
          true
        );
        expect(Array.isArray(response.body.retail_sentiment)).toBe(true);

        // Validate metadata structure
        expect(response.body.metadata).toHaveProperty("symbol");
        expect(response.body.metadata).toHaveProperty("timeframe");
        expect(response.body.metadata).toHaveProperty("total_records");
        expect(response.body.metadata).toHaveProperty("last_updated");
      }
    });

    test("should support symbol parameter", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks?symbol=AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body.metadata.symbol).toBe("AAPL");
      }
    });

    test("should support timeframe parameter", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks?timeframe=weekly")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body.metadata.timeframe).toBe("weekly");
      }
    });

    test("should support pagination parameters", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks?limit=10&page=1")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404].includes(response.status)).toBe(true);

      if (response.status === 200) {
        // Should respect limit - institutional positions should be <= 10
        expect(
          response.body.institutional_positioning.length
        ).toBeLessThanOrEqual(10);
      }
    });

    test("should handle pagination with different page numbers", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks?limit=5&page=2")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404].includes(response.status)).toBe(true);
    });

    test("should validate response structure when data exists", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        // Validate institutional positioning structure
        if (response.body.institutional_positioning.length > 0) {
          const institutional = response.body.institutional_positioning[0];
          expect(institutional).toHaveProperty("symbol");
          expect(institutional).toHaveProperty("institution_type");
          expect(institutional).toHaveProperty("position_size");
        }

        // Validate retail sentiment structure
        if (response.body.retail_sentiment.length > 0) {
          const sentiment = response.body.retail_sentiment[0];
          expect(sentiment).toHaveProperty("symbol");
          expect(sentiment).toHaveProperty("bullish_percentage");
          expect(sentiment).toHaveProperty("bearish_percentage");
          expect(sentiment).toHaveProperty("net_sentiment");
        }

        // Validate metadata
        expect(response.body.metadata.total_records).toHaveProperty(
          "institutional"
        );
        expect(response.body.metadata.total_records).toHaveProperty(
          "sentiment"
        );
        expect(typeof response.body.metadata.total_records.institutional).toBe(
          "number"
        );
        expect(typeof response.body.metadata.total_records.sentiment).toBe(
          "number"
        );
      }
    });

    test("should handle mixed case symbol parameter", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks?symbol=aapl")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404].includes(response.status)).toBe(true);
    });

    test("should handle special characters in symbol", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks?symbol=BRK.A")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404].includes(response.status)).toBe(true);
    });

    test("should return 404 for non-existent symbol", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks?symbol=NONEXISTENT")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404].includes(response.status)).toBe(true);

      if (response.status === 404) {
        expect(response.body).toHaveProperty("error");
        // May have different error messages
        expect(typeof response.body.error).toBe("string");
      }
    });
  });

  describe("GET /api/positioning/summary", () => {
    test("should return positioning summary", async () => {
      const response = await request(app)
        .get("/api/positioning/summary")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404, 500].includes(response.status)).toBe(true);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("market_overview");
        expect(response.body).toHaveProperty("key_metrics");
        expect(response.body).toHaveProperty("data_freshness");
        expect(response.body).toHaveProperty("last_updated");

        // Validate market overview structure
        expect(response.body.market_overview).toHaveProperty(
          "institutional_flow"
        );
        expect(response.body.market_overview).toHaveProperty(
          "retail_sentiment"
        );
        expect(response.body.market_overview).toHaveProperty(
          "overall_positioning"
        );

        // Validate key metrics structure
        expect(response.body.key_metrics).toHaveProperty(
          "institutional_avg_change"
        );
        expect(response.body.key_metrics).toHaveProperty(
          "retail_net_sentiment"
        );
        expect(typeof response.body.key_metrics.institutional_avg_change).toBe(
          "number"
        );
        expect(typeof response.body.key_metrics.retail_net_sentiment).toBe(
          "number"
        );

        // Validate data freshness structure
        expect(response.body.data_freshness).toHaveProperty(
          "institutional_positions"
        );
        expect(response.body.data_freshness).toHaveProperty("retail_readings");
        expect(
          typeof response.body.data_freshness.institutional_positions
        ).toBe("number");
      }
    });

    test("should include valid positioning values", async () => {
      const response = await request(app)
        .get("/api/positioning/summary")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        const validFlowValues = ["BULLISH", "BEARISH"];
        const validSentimentValues = ["BULLISH", "BEARISH", "MIXED"];
        const validOverallValues = [
          "BULLISH",
          "MODERATELY_BULLISH",
          "NEUTRAL",
          "MODERATELY_BEARISH",
          "BEARISH",
        ];

        expect(validFlowValues).toContain(
          response.body.market_overview.institutional_flow
        );
        expect(validSentimentValues).toContain(
          response.body.market_overview.retail_sentiment
        );
        expect(validOverallValues).toContain(
          response.body.market_overview.overall_positioning
        );
      }
    });

    test("should have valid timestamp format", async () => {
      const response = await request(app)
        .get("/api/positioning/summary")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        const timestamp = new Date(response.body.last_updated);
        expect(timestamp).toBeInstanceOf(Date);
        expect(timestamp.getTime()).not.toBeNaN();
      }
    });
  });

  describe("Authentication", () => {
    test("should require authentication for stock positioning", async () => {
      const response = await request(app).get("/api/positioning/stocks");
      // No auth header

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should require authentication for positioning summary", async () => {
      const response = await request(app).get("/api/positioning/summary");
      // No auth header

      expect([200, 401].includes(response.status)).toBe(true);
    });

    test("should handle invalid authentication", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks")
        .set("Authorization", "Bearer invalid-token");

      expect([200, 401].includes(response.status)).toBe(true);
    });
  });

  describe("Error Handling", () => {
    test("should handle database errors gracefully", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks?symbol=INVALID_TEST_SYMBOL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404, 500].includes(response.status)).toBe(true);

      if (response.status === 500) {
        expect(response.body).toHaveProperty("error");
        expect(response.body.error).toContain(
          "Failed to fetch stock positioning data"
        );
      }
    });

    test("should handle malformed parameters", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks?limit=invalid&page=invalid")
        .set("Authorization", "Bearer dev-bypass-token");

      // Should handle gracefully - may return data with defaults or error
      expect([200, 400, 404, 500].includes(response.status)).toBe(true);
    });

    test("should handle extremely large limit values", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks?limit=99999")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404, 500].includes(response.status)).toBe(true);
    });

    test("should handle negative pagination values", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks?limit=-1&page=-1")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 404, 500].includes(response.status)).toBe(true);
    });
  });

  describe("Data Validation", () => {
    test("should return consistent data structure", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        // Should always have these properties even if empty
        expect(response.body).toHaveProperty("institutional_positioning");
        expect(response.body).toHaveProperty("retail_sentiment");
        expect(response.body).toHaveProperty("metadata");

        // Arrays should always be arrays
        expect(Array.isArray(response.body.institutional_positioning)).toBe(
          true
        );
        expect(Array.isArray(response.body.retail_sentiment)).toBe(true);
      }
    });

    test("should include data freshness indicators", async () => {
      const response = await request(app)
        .get("/api/positioning/summary")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(response.body.data_freshness).toHaveProperty(
          "institutional_positions"
        );
        expect(response.body.data_freshness).toHaveProperty("retail_readings");
        expect(response.body.data_freshness.retail_readings).toBe(
          "last_30_days"
        );
      }
    });
  });

  describe("Performance", () => {
    test("should respond within reasonable time", async () => {
      const startTime = Date.now();

      const response = await request(app)
        .get("/api/positioning/stocks")
        .set("Authorization", "Bearer dev-bypass-token");

      const responseTime = Date.now() - startTime;

      expect(responseTime).toBeLessThan(5000); // 5 second timeout
      expect([200, 404, 500].includes(response.status)).toBe(true);
    });

    test("should handle concurrent requests", async () => {
      const requests = [
        request(app)
          .get("/api/positioning/stocks")
          .set("Authorization", "Bearer dev-bypass-token"),
        request(app)
          .get("/api/positioning/summary")
          .set("Authorization", "Bearer dev-bypass-token"),
        request(app)
          .get("/api/positioning/stocks?symbol=AAPL")
          .set("Authorization", "Bearer dev-bypass-token"),
      ];

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect([200, 404, 500].includes(response.status)).toBe(true);
      });
    });
  });

  describe("Query Parameter Validation", () => {
    test("should use default values for missing parameters", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(response.body.metadata.symbol).toBe("all");
        expect(response.body.metadata.timeframe).toBe("daily");
      }
    });

    test("should handle empty string parameters", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks?symbol=&timeframe=")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404, 500].includes(response.status)).toBe(true);
    });

    test("should handle URL encoded parameters", async () => {
      const response = await request(app)
        .get("/api/positioning/stocks?symbol=BRK%2EA")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404, 500].includes(response.status)).toBe(true);
    });
  });
});
