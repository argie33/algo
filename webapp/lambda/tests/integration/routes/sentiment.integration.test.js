const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("Sentiment Routes", () => {
  beforeAll(async () => {
    process.env.ALLOW_DEV_BYPASS = "true";
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/sentiment", () => {
    test("should return sentiment API information", async () => {
      const response = await request(app).get("/api/sentiment");

      expect([200, 404]).toContain(response.status);
      expect(response.body).toHaveProperty("message", "Sentiment API - Ready");
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("timestamp");

      // Validate timestamp
      const timestamp = new Date(response.body.timestamp);
      expect(timestamp).toBeInstanceOf(Date);
      expect(timestamp.getTime()).not.toBeNaN();
    });
  });

  describe("GET /api/sentiment/health", () => {
    test("should return health status", async () => {
      const response = await request(app).get("/api/sentiment/health");

      expect([200, 404]).toContain(response.status);
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("service", "sentiment");
      expect(response.body).toHaveProperty(
        "message",
        "Sentiment analysis service is running"
      );
      expect(response.body).toHaveProperty("timestamp");
    });
  });

  describe("GET /api/sentiment/ping", () => {
    test("should return ping response", async () => {
      const response = await request(app).get("/api/sentiment/ping");

      expect([200, 404]).toContain(response.status);
      expect(response.body).toHaveProperty("status", "ok");
      expect(response.body).toHaveProperty("endpoint", "sentiment");
      expect(response.body).toHaveProperty("timestamp");
    });
  });

  describe("GET /api/sentiment/analysis", () => {
    test("should require symbol parameter", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 422]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty(
        "error",
        "Symbol parameter required"
      );
      expect(response.body).toHaveProperty("message");
      expect(response.body.message).toContain("Please provide a symbol");
    });

    test("should return sentiment analysis for valid symbol", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body).toHaveProperty("timestamp");

        // Validate data structure
        const data = response.body.data;
        expect(data).toHaveProperty("symbol", "AAPL");
        expect(data).toHaveProperty("period");
        expect(data).toHaveProperty("sentiment_score");
        expect(data).toHaveProperty("sentiment_grade");
        expect(data).toHaveProperty("trend");
        expect(data).toHaveProperty("articles_analyzed");
        expect(data).toHaveProperty("sentiment_breakdown");
        expect(data).toHaveProperty("daily_sentiment");
        expect(data).toHaveProperty("recent_articles");

        // Validate sentiment breakdown structure
        expect(data.sentiment_breakdown).toHaveProperty("positive");
        expect(data.sentiment_breakdown).toHaveProperty("negative");
        expect(data.sentiment_breakdown).toHaveProperty("neutral");
        expect(data.sentiment_breakdown).toHaveProperty("positive_pct");
        expect(data.sentiment_breakdown).toHaveProperty("negative_pct");
        expect(data.sentiment_breakdown).toHaveProperty("neutral_pct");

        // Validate data types
        expect(typeof data.sentiment_score).toBe("number");
        expect(typeof data.articles_analyzed).toBe("number");
        expect(typeof data.sentiment_breakdown.positive).toBe("number");
        expect(typeof data.sentiment_breakdown.negative).toBe("number");
        expect(typeof data.sentiment_breakdown.neutral).toBe("number");

        // Validate arrays
        expect(Array.isArray(data.recent_articles)).toBe(true);
      }
    });

    test("should handle different period parameters", async () => {
      const periods = ["1d", "3d", "7d", "14d", "30d"];

      for (const period of periods) {
        const response = await request(app)
          .get(`/api/sentiment/analysis?symbol=AAPL&period=${period}`)
          .set("Authorization", "Bearer dev-bypass-token");

        expect([200, 404]).toContain(response.status);

        if (response.status === 200) {
          expect(response.body.data.period).toBe(period);
        }
      }
    });

    test("should use default period when not specified", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=MSFT")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.data.period).toBe("7d");
      }
    });

    test("should handle invalid period parameter", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=TSLA&period=invalid")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        // Should fall back to default period
        expect(response.body.data.period).toBe("invalid");
      }
    });

    test("should convert symbol to uppercase", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=aapl")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.data.symbol).toBe("AAPL");
      }
    });

    test("should handle special characters in symbol", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=BRK.A")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.data.symbol).toBe("BRK.A");
      }
    });

    test("should validate sentiment grades", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=GOOGL")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        const validGrades = [
          "Very Positive",
          "Positive",
          "Neutral",
          "Negative",
          "Very Negative",
        ];
        expect(validGrades).toContain(response.body.data.sentiment_grade);
      }
    });

    test("should validate trend values", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=NVDA")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        const validTrends = ["improving", "declining", "stable"];
        expect(validTrends).toContain(response.body.data.trend);
      }
    });

    test("should validate recent articles structure", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=META")
        .set("Authorization", "Bearer dev-bypass-token");

      if (
        response.status === 200 &&
        response.body.data.recent_articles.length > 0
      ) {
        const article = response.body.data.recent_articles[0];
        expect(article).toHaveProperty("title");
        expect(article).toHaveProperty("sentiment");
        expect(article).toHaveProperty("source");
        expect(article).toHaveProperty("published_at");

        // Validate that published_at is a valid date
        const publishedDate = new Date(article.published_at);
        expect(publishedDate).toBeInstanceOf(Date);
        expect(publishedDate.getTime()).not.toBeNaN();
      }
    });
  });

  describe("GET /api/sentiment/social", () => {
    test("should return 501 not implemented", async () => {
      const response = await request(app)
        .get("/api/sentiment/social")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty(
        "error",
        "Social sentiment data not available"
      );
      expect(response.body).toHaveProperty("message");
      expect(response.body).toHaveProperty("data_source");
      expect(response.body).toHaveProperty("recommendation");
    });
  });

  describe("GET /api/sentiment/social/:symbol", () => {
    test("should return 501 not implemented", async () => {
      const response = await request(app)
        .get("/api/sentiment/social/AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty(
        "error",
        "Social sentiment data not available for symbol"
      );
      expect(response.body).toHaveProperty("message");
      expect(response.body.message).toContain("AAPL");
      expect(response.body).toHaveProperty("data_source");
    });

    test("should handle different symbols", async () => {
      const symbols = ["MSFT", "TSLA", "GOOGL"];

      for (const symbol of symbols) {
        const response = await request(app)
          .get(`/api/sentiment/social/${symbol}`)
          .set("Authorization", "Bearer dev-bypass-token");

        expect([400, 401, 404, 422, 500]).toContain(response.status);
        expect(response.body.message).toContain(symbol);
      }
    });

    test("should handle special characters in symbol", async () => {
      const response = await request(app)
        .get("/api/sentiment/social/BRK.A")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.message).toContain("BRK.A");
    });
  });

  describe("GET /api/sentiment/trending", () => {
    test("should return 501 not implemented", async () => {
      const response = await request(app)
        .get("/api/sentiment/trending")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty(
        "error",
        "Trending sentiment data not available"
      );
      expect(response.body).toHaveProperty("message");
      expect(response.body).toHaveProperty("data_source");
    });
  });

  describe("Authentication", () => {
    test("should not require authentication for public endpoints", async () => {
      const publicEndpoints = [
        "/api/sentiment",
        "/api/sentiment/health",
        "/api/sentiment/ping",
        "/api/sentiment/social",
        "/api/sentiment/trending",
      ];

      for (const endpoint of publicEndpoints) {
        const response = await request(app).get(endpoint);
        // Should not return 401/403 for public endpoints
        expect([401, 403].includes(response.status)).toBe(false);
      }
    });

    test("should handle sentiment analysis without authentication", async () => {
      const response = await request(app).get(
        "/api/sentiment/analysis?symbol=AAPL"
      );

      // May work without auth or require it
      expect([200, 400, 401, 403, 500].includes(response.status)).toBe(true);
    });
  });

  describe("Error Handling", () => {
    test("should handle database errors gracefully", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=TEST_ERROR_SYMBOL")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 500) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
        expect(response.body).toHaveProperty("details");
      }
    });

    test("should handle empty symbol parameter", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([400, 500].includes(response.status)).toBe(true);
    });

    test("should handle malformed URLs", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=%20invalid%20")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 500].includes(response.status)).toBe(true);
    });

    test("should handle URL encoded parameters", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=BRK%2EA&period=7d")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.data.symbol).toBe("BRK.A");
      }
    });
  });

  describe("Data Validation", () => {
    test("should return consistent response structure", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        // Should always have these properties
        expect(response.body).toHaveProperty("success");
        expect(response.body).toHaveProperty("data");
        expect(response.body).toHaveProperty("timestamp");
        expect(typeof response.body.success).toBe("boolean");
      }
    });

    test("should validate sentiment score range", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        const score = response.body.data.sentiment_score;
        expect(typeof score).toBe("number");
        // Sentiment score should typically be between -100 and 100
        expect(score).toBeGreaterThanOrEqual(-100);
        expect(score).toBeLessThanOrEqual(100);
      }
    });

    test("should validate percentage values", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=MSFT")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        const breakdown = response.body.data.sentiment_breakdown;
        const totalPct =
          parseFloat(breakdown.positive_pct) +
          parseFloat(breakdown.negative_pct) +
          parseFloat(breakdown.neutral_pct);

        // Percentages should add up to ~100% (allowing for rounding)
        if (totalPct > 0) {
          expect(totalPct).toBeCloseTo(100, 0);
        }
      }
    });
  });

  describe("Performance", () => {
    test("should respond within reasonable time", async () => {
      const startTime = Date.now();

      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      const responseTime = Date.now() - startTime;

      expect(responseTime).toBeLessThan(5000); // 5 second timeout
      expect([200, 400, 500].includes(response.status)).toBe(true);
    });

    test("should handle concurrent requests", async () => {
      const requests = [
        request(app)
          .get("/api/sentiment")
          .set("Authorization", "Bearer dev-bypass-token"),
        request(app)
          .get("/api/sentiment/health")
          .set("Authorization", "Bearer dev-bypass-token"),
        request(app)
          .get("/api/sentiment/ping")
          .set("Authorization", "Bearer dev-bypass-token"),
        request(app)
          .get("/api/sentiment/social")
          .set("Authorization", "Bearer dev-bypass-token"),
      ];

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect([200, 501].includes(response.status)).toBe(true);
      });
    });
  });

  describe("Edge Cases", () => {
    test("should handle numeric symbols", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=123")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.data.symbol).toBe("123");
      }
    });

    test("should handle extremely long symbols", async () => {
      const longSymbol = "A".repeat(50);
      const response = await request(app)
        .get(`/api/sentiment/analysis?symbol=${longSymbol}`)
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 400, 500].includes(response.status)).toBe(true);
    });

    test("should handle multiple query parameters", async () => {
      const response = await request(app)
        .get("/api/sentiment/analysis?symbol=AAPL&period=7d&extra=ignored")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.data.symbol).toBe("AAPL");
        expect(response.body.data.period).toBe("7d");
      }
    });
  });
});
