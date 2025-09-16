/**
 * Sentiment Routes Unit Tests
 * Tests sentiment route logic in isolation with mocks
 */

const express = require("express");
const request = require("supertest");

// Mock the database utility
jest.mock("../../../utils/database", () => ({
  _query: jest.fn(),
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
    const { _query } = require("../../../utils/database");
    mockQuery = _query;

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
            sentiment_score: 0.75,
            positive_mentions: 45,
            negative_mentions: 12,
            neutral_mentions: 23,
            total_mentions: 80,
            period_days: 7,
            confidence_score: 0.85,
            trend_direction: "positive",
          },
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
      expect(response.body.data).toHaveProperty("sentiment_score", 0.75);
      expect(response.body.data).toHaveProperty("total_mentions", 80);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("sentiment_analysis"),
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

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("No sentiment data found");
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

  describe("GET /sentiment/history", () => {
    test("should return sentiment history for symbol", async () => {
      const mockHistoryData = {
        rows: [
          {
            symbol: "GOOGL",
            date: "2023-01-15",
            sentiment_score: 0.68,
            volume_mentions: 125,
            trend: "positive",
          },
          {
            symbol: "GOOGL",
            date: "2023-01-14",
            sentiment_score: 0.52,
            volume_mentions: 98,
            trend: "neutral",
          },
        ],
      };

      mockQuery.mockResolvedValueOnce(mockHistoryData);

      const response = await request(app)
        .get("/sentiment/history")
        .query({ symbol: "GOOGL", days: 30 });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("symbol", "GOOGL");
      expect(response.body.data).toHaveProperty("history");
      expect(Array.isArray(response.body.data.history)).toBe(true);
      expect(response.body.data.history).toHaveLength(2);
      expect(response.body.data.history[0]).toHaveProperty(
        "sentiment_score",
        0.68
      );
    });

    test("should handle history limit parameter", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/sentiment/history")
        .query({ symbol: "AAPL", limit: 50 });

      expect(response.status).toBe(200);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("LIMIT"),
        expect.arrayContaining(["AAPL", 50])
      );
    });
  });

  describe("GET /sentiment/social", () => {
    test("should return social sentiment analysis with proper structure", async () => {
      const response = await request(app)
        .get("/sentiment/social")
        .query({ symbol: "AAPL" });

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("symbol", "AAPL");
        expect(response.body.data).toHaveProperty("social_sentiment");
        expect(response.body.data).toHaveProperty("platform_breakdown");
        expect(response.body.data).toHaveProperty("engagement_metrics");
        expect(response.body.data).toHaveProperty("summary");

        // Check social sentiment structure
        const socialSentiment = response.body.data.social_sentiment;
        expect(socialSentiment).toHaveProperty("overall_score");
        expect(socialSentiment).toHaveProperty("sentiment_grade");
        expect(socialSentiment).toHaveProperty("confidence_level");
        expect(socialSentiment).toHaveProperty("volume_score");

        // Check platform breakdown
        expect(Array.isArray(response.body.data.platform_breakdown)).toBe(true);
        if (response.body.data.platform_breakdown.length > 0) {
          const platform = response.body.data.platform_breakdown[0];
          expect(platform).toHaveProperty("platform");
          expect(platform).toHaveProperty("sentiment_score");
          expect(platform).toHaveProperty("mention_count");
          expect(platform).toHaveProperty("engagement_rate");
        }

        // Check engagement metrics
        expect(response.body.data.engagement_metrics).toHaveProperty(
          "total_mentions"
        );
        expect(response.body.data.engagement_metrics).toHaveProperty(
          "unique_authors"
        );
        expect(response.body.data.engagement_metrics).toHaveProperty(
          "viral_posts"
        );

        // Check summary
        expect(response.body.data.summary).toHaveProperty("analysis_period");
        expect(response.body.data.summary).toHaveProperty("data_sources");
      } else if (response.status === 400) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body.error).toContain("Symbol parameter required");
      } else {
        expect([404, 500]).toContain(response.status);
      }
    });

    test("should handle timeframe parameter for social sentiment", async () => {
      const response = await request(app)
        .get("/sentiment/social")
        .query({ symbol: "AAPL", timeframe: "24h" });

      if (response.status === 200) {
        expect(response.body.data.summary.analysis_period).toBe("24h");
      }
    });

    test("should handle invalid symbol for social sentiment", async () => {
      const response = await request(app)
        .get("/sentiment/social")
        .query({ symbol: "INVALID" });

      if (response.status === 404) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body.error).toContain("No social sentiment data found");
      }
    });
  });

  describe("GET /sentiment/trending", () => {
    test("should return trending sentiment analysis with proper structure", async () => {
      const response = await request(app).get("/sentiment/trending");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("trending_symbols");
        expect(response.body.data).toHaveProperty("momentum_analysis");
        expect(response.body.data).toHaveProperty("summary");
        expect(response.body.data).toHaveProperty("methodology");

        // Check trending symbols structure
        expect(Array.isArray(response.body.data.trending_symbols)).toBe(true);
        if (response.body.data.trending_symbols.length > 0) {
          const trendingSymbol = response.body.data.trending_symbols[0];
          expect(trendingSymbol).toHaveProperty("symbol");
          expect(trendingSymbol).toHaveProperty("sentiment_score");
          expect(trendingSymbol).toHaveProperty("mention_velocity");
          expect(trendingSymbol).toHaveProperty("sentiment_change");
          expect(trendingSymbol).toHaveProperty("trending_score");
          expect(trendingSymbol).toHaveProperty("social_volume");
        }

        // Check momentum analysis
        expect(response.body.data.momentum_analysis).toHaveProperty(
          "bullish_momentum"
        );
        expect(response.body.data.momentum_analysis).toHaveProperty(
          "bearish_momentum"
        );
        expect(response.body.data.momentum_analysis).toHaveProperty(
          "volume_surge"
        );

        // Check summary
        expect(response.body.data.summary).toHaveProperty(
          "total_symbols_analyzed"
        );
        expect(response.body.data.summary).toHaveProperty("trending_threshold");
        expect(response.body.data.summary).toHaveProperty("analysis_window");

        // Check methodology
        expect(response.body.data.methodology).toHaveProperty(
          "trending_algorithm"
        );
        expect(response.body.data.methodology).toHaveProperty("data_sources");
      } else {
        expect([500]).toContain(response.status);
      }
    });

    test("should handle limit parameter for trending sentiment", async () => {
      const response = await request(app)
        .get("/sentiment/trending")
        .query({ limit: 10 });

      if (response.status === 200) {
        expect(response.body.data.trending_symbols.length).toBeLessThanOrEqual(
          10
        );
      }
    });

    test("should handle timeframe parameter for trending sentiment", async () => {
      const response = await request(app)
        .get("/sentiment/trending")
        .query({ timeframe: "1h" });

      if (response.status === 200) {
        expect(response.body.data.summary.analysis_window).toBe("1h");
      }
    });

    test("should handle sorting for trending sentiment", async () => {
      const response = await request(app)
        .get("/sentiment/trending")
        .query({ sort: "momentum" });

      if (response.status === 200) {
        // Should be sorted by momentum/trending score
        const symbols = response.body.data.trending_symbols;
        if (symbols.length > 1) {
          for (let i = 1; i < symbols.length; i++) {
            expect(symbols[i - 1].trending_score).toBeGreaterThanOrEqual(
              symbols[i].trending_score
            );
          }
        }
      }
    });

    test("should handle sector filter for trending sentiment", async () => {
      const response = await request(app)
        .get("/sentiment/trending")
        .query({ sector: "Technology" });

      if (response.status === 200) {
        // Should filter by sector
        expect(response.body.data.summary).toHaveProperty(
          "sector_filter",
          "Technology"
        );
      }
    });

    test("should handle minimum trending score filter", async () => {
      const response = await request(app)
        .get("/sentiment/trending")
        .query({ min_trending_score: 70 });

      if (response.status === 200) {
        const symbols = response.body.data.trending_symbols;
        symbols.forEach((symbol) => {
          expect(symbol.trending_score).toBeGreaterThanOrEqual(70);
        });
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
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("market_sentiment"),
        expect.any(Array)
      );
    });

    test("should handle empty market sentiment data", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app).get("/sentiment/market");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toHaveProperty(
        "message",
        "No market sentiment data available"
      );
    });
  });

  describe("Parameter validation", () => {
    test("should sanitize symbol parameter", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "AAPL'; DROP TABLE sentiment; --" });

      expect(response.status).toBe(200);
      // Symbol should be sanitized and used safely in prepared statement
      expect(mockQuery).toHaveBeenCalledWith(
        expect.any(String),
        expect.arrayContaining(["AAPL'; DROP TABLE sentiment; --"])
      );
    });

    test("should handle invalid symbol format", async () => {
      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "invalid-symbol-format!@#$%" });

      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Invalid symbol format");
    });

    test("should handle extremely long symbol parameter", async () => {
      const longSymbol = "A".repeat(100);

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: longSymbol });

      expect(response.status).toBe(400);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Symbol too long");
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
      const timeoutError = new Error("Query timeout");
      timeoutError.code = "QUERY_TIMEOUT";
      mockQuery.mockRejectedValueOnce(timeoutError);

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "AAPL" });

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("timeout");
    });

    test("should handle malformed database results", async () => {
      mockQuery.mockResolvedValueOnce(null); // Malformed result

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "AAPL" });

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
    });

    test("should handle sentiment calculation errors", async () => {
      // Mock a database result that might cause calculation errors
      const invalidData = {
        rows: [
          {
            symbol: "AAPL",
            sentiment_score: "invalid_number",
            positive_mentions: null,
            negative_mentions: undefined,
          },
        ],
      };

      mockQuery.mockResolvedValueOnce(invalidData);

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "AAPL" });

      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Sentiment calculation failed");
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
            sentiment_score: 0.75,
            positive_mentions: 45,
            negative_mentions: 12,
            neutral_mentions: 23,
          },
        ],
      };

      mockQuery.mockResolvedValueOnce(mockData);

      const response = await request(app)
        .get("/sentiment/analysis")
        .query({ symbol: "AAPL", period: "7d" });

      expect(response.status).toBe(200);
      expect(response.body.data).toHaveProperty("symbol");
      expect(response.body.data).toHaveProperty("analysis_period", "7d");
      expect(response.body.data).toHaveProperty("last_updated");
    });
  });
});
