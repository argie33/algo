/**
 * Sentiment Routes Unit Tests
 * Tests sentiment route logic in isolation with mocks
 */

const express = require("express");
const request = require("supertest");

// Mock the database utility
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

// Mock the auth middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = {
      sub: "test-user-123",
      email: "test@example.com",
      username: "testuser",
    };
    next();
  }),
}));

describe("Sentiment Routes Unit Tests", () => {
  let app;
  let sentimentRouter;
  let mockQuery;

  beforeEach(() => {
    jest.clearAllMocks();

    // Set up mocks
    const { query } = require("../../../utils/database");
    mockQuery = query;

    // Create test app
    app = express();
    app.use(express.json());

    // Add response helper middleware
    app.use((req, res, next) => {
      res.error = (message, status) =>
        res.status(status).json({
          success: false,
          error: message,
        });
      res.success = (data) =>
        res.json({
          success: true,
          ...data,
        });
      next();
    });

    // Load the route module
    sentimentRouter = require("../../../routes/sentiment");
    app.use("/sentiment", sentimentRouter);
  });

  describe("GET /sentiment/health", () => {
    test("should return health status without authentication", async () => {
      const response = await request(app).get("/sentiment/health");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("service", "sentiment");
      expect(response.body).toHaveProperty("timestamp");
      expect(response.body).toHaveProperty(
        "message",
        "Sentiment analysis service is running"
      );

      // Verify timestamp is a valid ISO string
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(mockQuery).not.toHaveBeenCalled(); // Health doesn't use database
    });
  });

  describe("GET /sentiment", () => {
    test("should return sentiment API information without authentication", async () => {
      const response = await request(app).get("/sentiment");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("message", "Sentiment API - Ready");
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("timestamp");

      // Verify timestamp is a valid ISO string
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(mockQuery).not.toHaveBeenCalled(); // Root endpoint doesn't use database
    });
  });

  describe("GET /sentiment/analysis", () => {
    test("should require symbol parameter", async () => {
      const response = await request(app).get("/sentiment/analysis");

      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty(
        "error",
        "Symbol parameter required"
      );
      expect(response.body).toHaveProperty(
        "message",
        "Please provide a symbol using ?symbol=TICKER"
      );
      expect(mockQuery).not.toHaveBeenCalled();
    });

    test("should return sentiment analysis with valid symbol", async () => {
      const mockSentimentData = {
        rows: [
          {
            symbol: "AAPL",
            date: new Date(),
            recommendation_mean: 2.1,
            price_target_vs_current: 5.5,
            sentiment: 0.75,
            reddit_sentiment_score: 0.68,
            search_volume_index: 85,
            news_article_count: 152,
            title: "AAPL Shows Strong Performance",
            source: "Financial News Today",
            published_at: new Date()
          }
        ],
      };

      mockQuery.mockResolvedValueOnce(mockSentimentData);

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "AAPL", period: "7d" });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("symbol", "AAPL");
      expect(response.body.data).toHaveProperty("sentiment_score");
      expect(response.body.data).toHaveProperty("articles_analyzed");
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("analyst_sentiment_analysis"),
        expect.arrayContaining(["AAPL", 7])
      );
    });

    test("should handle default period parameter", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "AAPL" });

      expect(response.status).toBe(200);
      // Should use default period of 7 days
      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        expect.arrayContaining(["AAPL", 7])
      );
    });

    test("should handle different period parameters", async () => {
      const periods = ["1d", "3d", "7d", "14d", "30d"];
      const expectedDays = [1, 3, 7, 14, 30];

      for (let i = 0; i < periods.length; i++) {
        mockQuery.mockClear();
        mockQuery.mockResolvedValueOnce({ rows: [] });

        const response = await request(app)
          .get("/sentiment/analysis")
          .query({ symbol: "AAPL", period: periods[i] });

        expect(response.status).toBe(200);
        expect(mockQuery).toHaveBeenCalledWith(
          expect.any(String),
          expect.arrayContaining(["AAPL", expectedDays[i]])
        );
      }
    });

    test("should handle invalid period gracefully", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "AAPL", period: "invalid_period" });

      expect(response.status).toBe(200);
      // Should default to 7 days for invalid period
      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        expect.arrayContaining(["AAPL", 7])
      );
    });

    test("should handle lowercase symbol conversion", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      await request(app).get("/sentiment/analysis").query({ symbol: "aapl" });

      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        expect.arrayContaining(["AAPL"]) // Should be converted to uppercase
      );
    });

    test("should handle empty sentiment data", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "INVALID" });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toHaveProperty("sentiment_score");
      expect(typeof response.body.data.sentiment_score).toBe("number");
      expect(response.body.data.sentiment_score).toBeGreaterThanOrEqual(0);
    });

    test("should handle database query errors", async () => {
      const dbError = new Error("Database connection failed");
      mockQuery.mockRejectedValueOnce(dbError);

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "AAPL" });

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toBeDefined();
    });
  });

  describe("GET /sentiment/stock/:symbol", () => {
    test("should return stock sentiment for symbol", async () => {
      const response = await request(app)
        .get("/sentiment/stock/GOOGL")
        .query({ period: "7d" });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("symbol", "GOOGL");
      expect(response.body.data).toHaveProperty("sentiment_score");
      expect(response.body.data).toHaveProperty("total_mentions");
      expect(response.body.data).toHaveProperty("period", "7d");
    });

    test("should handle period parameter for stock sentiment", async () => {
      const response = await request(app)
        .get("/sentiment/stock/AAPL")
        .query({ period: "30d" });

      expect(response.status).toBe(200);
      expect(response.body.data).toHaveProperty("period", "30d");
    });
  });

  describe("GET /sentiment/social", () => {
    test("should return social sentiment error for not implemented", async () => {
      const response = await request(app).get("/sentiment/social");

      expect(response.status).toBe(501);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error", "Social sentiment data not available");
      expect(response.body).toHaveProperty("message", "Social media sentiment analysis is not yet implemented");
    });

    test("should return twitter sentiment data", async () => {
      const response = await request(app)
        .get("/sentiment/social/twitter")
        .query({ symbol: "AAPL", limit: 10 });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("platform", "twitter");
      expect(response.body.data).toHaveProperty("tweets");
      expect(Array.isArray(response.body.data.tweets)).toBe(true);
    });

    test("should return reddit sentiment data with 404 for empty data", async () => {
      // Mock empty database result
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/sentiment/social/reddit")
        .query({ symbol: "INVALID" });

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("No Reddit sentiment data found");
    });
  });

  describe("GET /sentiment/trending", () => {
    test("should return trending sentiment error for not implemented", async () => {
      const response = await request(app).get("/sentiment/trending");

      expect(response.status).toBe(501);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error", "Trending sentiment data not available");
      expect(response.body).toHaveProperty("message", "Trending social media sentiment analysis is not yet implemented");
    });

    test("should return social trending data", async () => {
      const response = await request(app)
        .get("/sentiment/social/trending")
        .query({ limit: 10 });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(Array.isArray(response.body.data)).toBe(true);
      if (response.body.data.length > 0) {
        const trending = response.body.data[0];
        expect(trending).toHaveProperty("symbol");
        expect(trending).toHaveProperty("sentiment_score");
        expect(trending).toHaveProperty("mention_count");
      }
    });
  });

  describe("GET /sentiment/market", () => {
    test("should return overall market sentiment", async () => {
      const mockMarketSentiment = {
        rows: [
          {
            overall_sentiment: 0.62,
            bullish_stocks: 145,
            bearish_stocks: 78,
            neutral_stocks: 92,
            market_mood: "cautiously_optimistic",
            fear_greed_index: 58,
            updated_at: "2023-01-15T16:30:00Z",
          },
        ],
      };

      mockQuery.mockResolvedValueOnce(mockMarketSentiment);

      const response = await request(app).get("/sentiment/market");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("overall_sentiment", 0.62);
      expect(response.body.data).toHaveProperty(
        "market_mood",
        "cautiously_optimistic"
      );
      expect(response.body.data).toHaveProperty("fear_greed_index", 58);
      expect(mockQuery).toHaveBeenCalled();
    });

    test("should handle empty market sentiment data with fallback", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app).get("/sentiment/market");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toHaveProperty("overall_sentiment");
      expect(response.body.data).toHaveProperty("market_mood");
      expect(response.body.data).toHaveProperty("fear_greed_index");
    });
  });

  describe("Parameter validation", () => {
    test("should sanitize symbol parameter", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "AAPL'; DROP TABLE sentiment; --" });

      expect(response.status).toBe(200);
      // Symbol should be converted to uppercase and used safely in prepared statement
      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        expect.arrayContaining(["AAPL'; DROP TABLE SENTIMENT; --", 7])
      );
    });

    test("should handle invalid symbol format", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "invalid-symbol-format!@#$%" });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toHaveProperty("sentiment_score");
      expect(typeof response.body.data.sentiment_score).toBe("number");
    });

    test("should handle extremely long symbol parameter", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const longSymbol = "A".repeat(100);

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: longSymbol });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toHaveProperty("sentiment_score");
      expect(typeof response.body.data.sentiment_score).toBe("number");
    });
  });

  describe("Authentication handling", () => {
    test("should allow public access to health endpoint", async () => {
      const response = await request(app).get("/sentiment/health");

      expect(response.status).toBe(200);
      // Should work without authentication
    });

    test("should allow public access to root endpoint", async () => {
      const response = await request(app).get("/sentiment");

      expect(response.status).toBe(200);
      // Should work without authentication
    });

    test("should allow public access to analysis endpoint", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "AAPL" });

      expect(response.status).toBe(200);
      // Should work without authentication for public sentiment data
    });
  });

  describe("Error handling", () => {
    test("should handle database connection timeout", async () => {
      const timeoutError = new Error("Database connection failed");
      timeoutError.code = "QUERY_TIMEOUT";
      mockQuery.mockRejectedValueOnce(timeoutError);

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "AAPL" });

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Database error occurred");
    });

    test("should handle malformed database results", async () => {
      mockQuery.mockResolvedValueOnce(null); // Malformed result

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "AAPL" });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toHaveProperty("sentiment_score");
    });

    test("should handle sentiment calculation gracefully with invalid data", async () => {
      // Mock a database result that might cause calculation errors
      const invalidData = {
        rows: [
          {
            symbol: "AAPL",
            sentiment: "invalid_number",
            recommendation_mean: null,
            price_target_vs_current: undefined,
          },
        ],
      };

      mockQuery.mockResolvedValueOnce(invalidData);

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "AAPL" });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toHaveProperty("sentiment_score", 0);
    });
  });

  describe("Response format", () => {
    test("should return consistent JSON response format", async () => {
      const response = await request(app).get("/sentiment/health");

      expect(response.headers["content-type"]).toMatch(/json/);
      expect(typeof response.body).toBe("object");
    });

    test("should include metadata in sentiment responses", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "AAPL" });

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success");
        expect(response.body).toHaveProperty("data");
      }
    });

    test("should include analysis metadata", async () => {
      const mockData = {
        rows: [
          {
            symbol: "AAPL",
            sentiment: 0.75,
            recommendation_mean: 2.1,
            price_target_vs_current: 5.5,
            reddit_sentiment_score: 0.68,
            search_volume_index: 85,
            news_article_count: 152,
            title: "AAPL Strong Performance",
            source: "Financial News",
            published_at: new Date()
          },
        ],
      };

      mockQuery.mockResolvedValueOnce(mockData);

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "AAPL", period: "7d" });

      expect(response.status).toBe(200);
      expect(response.body.data).toHaveProperty("symbol");
      expect(response.body.data).toHaveProperty("period", "7d");
      expect(response.body).toHaveProperty("timestamp");
    });
  });
});
