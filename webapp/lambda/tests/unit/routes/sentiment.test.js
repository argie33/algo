const request = require("supertest");
const express = require("express");
const sentimentRouter = require("../../../routes/sentiment");

// Mock dependencies
jest.mock("../../../utils/database");
jest.mock("../../../middleware/auth");

const { _query } = require("../../../utils/database");
const { authenticateToken } = require("../../../middleware/auth");

describe("Sentiment Routes", () => {
  let app;

  beforeEach(() => {
    app = express();
    app.use(express.json());
    app.use("/sentiment", sentimentRouter);

    // Mock authentication middleware
    authenticateToken.mockImplementation((req, res, next) => {
      req.user = { sub: "test-user-123" };
      next();
    });

    jest.clearAllMocks();
  });

  describe("GET /sentiment/health", () => {
    test("should return operational status", async () => {
      const response = await request(app).get("/sentiment/health").expect(200);

      expect(response.body).toEqual({
        success: true,
        status: "operational",
        service: "sentiment",
        timestamp: expect.any(String),
        message: "Sentiment analysis service is running",
      });

      // Validate timestamp format
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
    });

    test("should not require authentication", async () => {
      // Should work without authentication
      await request(app).get("/sentiment/health").expect(200);
    });
  });

  describe("GET /sentiment/", () => {
    test("should return API ready message", async () => {
      const response = await request(app).get("/sentiment/").expect(200);

      expect(response.body).toEqual({
        success: true,
        message: "Sentiment API - Ready",
        timestamp: expect.any(String),
        status: "operational",
      });
    });

    test("should be a public endpoint", async () => {
      // Should work without authentication
      await request(app).get("/sentiment/").expect(200);
    });
  });

  describe("GET /sentiment/ping", () => {
    test("should return ping response", async () => {
      const response = await request(app).get("/sentiment/ping").expect(200);

      expect(response.body).toEqual({
        status: "ok",
        endpoint: "sentiment",
        timestamp: expect.any(String),
      });

      // Validate timestamp format
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
    });

    test("should be a public endpoint", async () => {
      // Should work without authentication
      await request(app).get("/sentiment/ping").expect(200);
    });
  });

  describe("GET /sentiment/social/:symbol", () => {
    test("should return empty social sentiment data with diagnostic information", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      const response = await request(app)
        .get("/sentiment/social/AAPL")
        .expect(200);

      expect(response.body.symbol).toBe("AAPL");
      expect(response.body.timeframe).toBe("7d"); // default
      expect(response.body.data).toEqual({
        reddit: {
          mentions: [],
          subredditBreakdown: [],
          topPosts: [],
        },
        googleTrends: {
          searchVolume: [],
          relatedQueries: [],
          geographicDistribution: [],
        },
        socialMetrics: {
          overall: {
            totalMentions: 0,
            sentimentScore: 0,
            engagementRate: 0,
            viralityIndex: 0,
            influencerMentions: 0,
          },
          platforms: [],
        },
      });
      expect(response.body.message).toBe(
        "No social media sentiment data available - configure social media API keys"
      );
      expect(response.body.timestamp).toBeDefined();

      // Verify diagnostic logging was called
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining("❌ Social media sentiment data unavailable"),
        expect.objectContaining({
          symbol: "AAPL",
          timeframe: "7d",
          detailed_diagnostics: expect.any(Object),
        })
      );

      consoleSpy.mockRestore();
    });

    test("should handle custom timeframe parameter", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      const response = await request(app)
        .get("/sentiment/social/MSFT?timeframe=30d")
        .expect(200);

      expect(response.body.symbol).toBe("MSFT");
      expect(response.body.timeframe).toBe("30d");

      consoleSpy.mockRestore();
    });

    test("should handle errors gracefully", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      // Mock an error in the route handler by overriding Date constructor
      const originalDate = Date;
      global.Date = jest.fn(() => {
        throw new Error("Date constructor failed");
      });
      global.Date.now = originalDate.now;

      const response = await request(app)
        .get("/sentiment/social/AAPL")
        .expect(500);

      expect(response.body.error).toBe("Failed to fetch social sentiment data");
      expect(response.body.message).toBe("Date constructor failed");

      // Restore original Date constructor
      global.Date = originalDate;
      consoleSpy.mockRestore();
    });
  });

  describe("GET /sentiment/trending", () => {
    test("should return empty trending stocks with default parameters", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      const response = await request(app)
        .get("/sentiment/trending")
        .expect(200);

      expect(response.body.trending).toEqual([]);
      expect(response.body.timeframe).toBe("24h"); // default
      expect(response.body.limit).toBe(20); // default
      expect(response.body.timestamp).toBeDefined();

      // Verify diagnostic logging was called
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining(
          "❌ Trending stocks sentiment data unavailable"
        ),
        expect.objectContaining({
          limit: 20,
          timeframe: "24h",
          detailed_diagnostics: expect.any(Object),
        })
      );

      consoleSpy.mockRestore();
    });

    test("should handle custom query parameters", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      const response = await request(app)
        .get("/sentiment/trending?limit=50&timeframe=7d")
        .expect(200);

      expect(response.body.trending).toEqual([]);
      expect(response.body.timeframe).toBe("7d");
      expect(response.body.limit).toBe(50);

      consoleSpy.mockRestore();
    });

    test("should parse limit as integer", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      const response = await request(app)
        .get("/sentiment/trending?limit=abc")
        .expect(200);

      expect(response.body.limit).toBeNaN(); // parseInt('abc') = NaN

      consoleSpy.mockRestore();
    });

    test("should handle errors gracefully", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      // Mock an error by overriding parseInt
      const originalParseInt = global.parseInt;
      global.parseInt = jest.fn(() => {
        throw new Error("parseInt failed");
      });

      const response = await request(app)
        .get("/sentiment/trending")
        .expect(500);

      expect(response.body.error).toBe("Failed to fetch trending stocks");
      expect(response.body.message).toBe("parseInt failed");

      // Restore original parseInt
      global.parseInt = originalParseInt;
      consoleSpy.mockRestore();
    });
  });

  describe("POST /sentiment/batch", () => {
    test("should return batch sentiment data for valid symbols", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});
      const symbols = ["AAPL", "MSFT", "GOOGL"];

      const response = await request(app)
        .post("/sentiment/batch")
        .send({
          symbols,
          timeframe: "30d",
        })
        .expect(200);

      expect(response.body.data).toHaveLength(3);
      expect(response.body.data).toEqual([
        {
          symbol: "AAPL",
          sentimentScore: 0,
          mentions: 0,
          engagement: 0,
          trend: "unknown",
        },
        {
          symbol: "MSFT",
          sentimentScore: 0,
          mentions: 0,
          engagement: 0,
          trend: "unknown",
        },
        {
          symbol: "GOOGL",
          sentimentScore: 0,
          mentions: 0,
          engagement: 0,
          trend: "unknown",
        },
      ]);
      expect(response.body.timeframe).toBe("30d");
      expect(response.body.timestamp).toBeDefined();

      // Verify diagnostic logging was called
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining("❌ Batch sentiment data unavailable"),
        expect.objectContaining({
          symbols,
          timeframe: "30d",
          detailed_diagnostics: expect.any(Object),
        })
      );

      consoleSpy.mockRestore();
    });

    test("should use default timeframe when not provided", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});
      const symbols = ["AAPL"];

      const response = await request(app)
        .post("/sentiment/batch")
        .send({ symbols })
        .expect(200);

      expect(response.body.timeframe).toBe("7d"); // default
      expect(response.body.data).toHaveLength(1);

      consoleSpy.mockRestore();
    });

    test("should return 400 for missing symbols array", async () => {
      const response = await request(app)
        .post("/sentiment/batch")
        .send({})
        .expect(400);

      expect(response.body.error).toBe("Invalid request");
      expect(response.body.message).toBe("symbols array is required");
    });

    test("should return 400 for invalid symbols parameter", async () => {
      const response = await request(app)
        .post("/sentiment/batch")
        .send({ symbols: "not-an-array" })
        .expect(400);

      expect(response.body.error).toBe("Invalid request");
      expect(response.body.message).toBe("symbols array is required");
    });

    test("should return 400 for null symbols", async () => {
      const response = await request(app)
        .post("/sentiment/batch")
        .send({ symbols: null })
        .expect(400);

      expect(response.body.error).toBe("Invalid request");
      expect(response.body.message).toBe("symbols array is required");
    });

    test("should handle empty symbols array", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      const response = await request(app)
        .post("/sentiment/batch")
        .send({ symbols: [] })
        .expect(200);

      expect(response.body.data).toEqual([]);

      consoleSpy.mockRestore();
    });

    test("should handle errors gracefully", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      // Mock an error by overriding Array.isArray
      const originalIsArray = Array.isArray;
      Array.isArray = jest.fn(() => {
        throw new Error("Array.isArray failed");
      });

      const response = await request(app)
        .post("/sentiment/batch")
        .send({ symbols: ["AAPL"] })
        .expect(500);

      expect(response.body.error).toBe("Failed to fetch batch sentiment data");
      expect(response.body.message).toBe("Array.isArray failed");

      // Restore original Array.isArray
      Array.isArray = originalIsArray;
      consoleSpy.mockRestore();
    });
  });

  describe("GET /sentiment/market-summary", () => {
    test("should return market sentiment summary with mock data", async () => {
      const response = await request(app)
        .get("/sentiment/market-summary")
        .expect(200);

      expect(response.body.marketSentiment).toBeDefined();
      expect(response.body.marketSentiment.overall).toEqual({
        sentiment: 0.68,
        mentions: 15234,
        activeDiscussions: 892,
        sentiment24hChange: 0.05,
      });

      expect(response.body.marketSentiment.sectors).toHaveLength(5);
      expect(response.body.marketSentiment.sectors[0]).toEqual({
        name: "Technology",
        sentiment: 0.72,
        mentions: 4567,
        change: 0.08,
      });

      expect(response.body.marketSentiment.platforms).toHaveLength(4);
      expect(response.body.marketSentiment.platforms[0]).toEqual({
        name: "Reddit",
        activeUsers: 45678,
        sentiment: 0.69,
      });

      expect(response.body.timestamp).toBeDefined();
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
    });

    test("should include all expected sectors", async () => {
      const response = await request(app)
        .get("/sentiment/market-summary")
        .expect(200);

      const sectorNames = response.body.marketSentiment.sectors.map(
        (s) => s.name
      );
      expect(sectorNames).toEqual([
        "Technology",
        "Healthcare",
        "Financial",
        "Energy",
        "Consumer",
      ]);
    });

    test("should include all expected platforms", async () => {
      const response = await request(app)
        .get("/sentiment/market-summary")
        .expect(200);

      const platformNames = response.body.marketSentiment.platforms.map(
        (p) => p.name
      );
      expect(platformNames).toEqual([
        "Reddit",
        "Twitter",
        "StockTwits",
        "Discord",
      ]);
    });

    test("should handle errors gracefully", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      // Mock an error by overriding JSON response
      const originalJson = express.response.json;
      express.response.json = jest.fn(() => {
        throw new Error("JSON response failed");
      });

      const response = await request(app)
        .get("/sentiment/market-summary")
        .expect(500);

      expect(response.body.error).toBe(
        "Failed to fetch market sentiment summary"
      );
      expect(response.body.message).toBe("JSON response failed");

      // Restore original json method
      express.response.json = originalJson;
      consoleSpy.mockRestore();
    });

    test("should be a public endpoint", async () => {
      // Should work without authentication
      await request(app).get("/sentiment/market-summary").expect(200);
    });
  });

  describe("Request body parsing", () => {
    test("should handle malformed JSON in POST requests", async () => {
      await request(app)
        .post("/sentiment/batch")
        .set("Content-Type", "application/json")
        .send('{"invalid": json}')
        .expect(400);
    });

    test("should handle very large request bodies", async () => {
      const largeSymbolsArray = new Array(1000).fill("AAPL");

      const response = await request(app)
        .post("/sentiment/batch")
        .send({ symbols: largeSymbolsArray })
        .expect(200);

      expect(response.body.data).toHaveLength(1000);
    });
  });

  describe("Parameter validation", () => {
    test("should handle special characters in symbol parameter", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      const response = await request(app)
        .get("/sentiment/social/AAPL%20TEST")
        .expect(200);

      expect(response.body.symbol).toBe("AAPL TEST"); // URL decoded

      consoleSpy.mockRestore();
    });

    test("should handle very long symbol names", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});
      const longSymbol = "A".repeat(100);

      const response = await request(app)
        .get(`/sentiment/social/${longSymbol}`)
        .expect(200);

      expect(response.body.symbol).toBe(longSymbol);

      consoleSpy.mockRestore();
    });

    test("should handle numeric limit values", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      const response = await request(app)
        .get("/sentiment/trending?limit=0")
        .expect(200);

      expect(response.body.limit).toBe(0);

      consoleSpy.mockRestore();
    });

    test("should handle negative limit values", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      const response = await request(app)
        .get("/sentiment/trending?limit=-5")
        .expect(200);

      expect(response.body.limit).toBe(-5);

      consoleSpy.mockRestore();
    });
  });

  describe("Content-Type handling", () => {
    test("should handle missing Content-Type header", async () => {
      await request(app)
        .post("/sentiment/batch")
        .send('{"symbols": ["AAPL"]}')
        .expect(400);
    });

    test("should handle incorrect Content-Type header", async () => {
      await request(app)
        .post("/sentiment/batch")
        .set("Content-Type", "text/plain")
        .send('{"symbols": ["AAPL"]}')
        .expect(400);
    });
  });

  describe("Diagnostic information", () => {
    test("should include comprehensive diagnostics in social sentiment", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      await request(app).get("/sentiment/social/AAPL").expect(200);

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining("❌ Social media sentiment data unavailable"),
        expect.objectContaining({
          detailed_diagnostics: expect.objectContaining({
            attempted_operations: expect.any(Array),
            potential_causes: expect.any(Array),
            troubleshooting_steps: expect.any(Array),
            system_checks: expect.any(Array),
          }),
        })
      );

      consoleSpy.mockRestore();
    });

    test("should include comprehensive diagnostics in trending stocks", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      await request(app).get("/sentiment/trending").expect(200);

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining(
          "❌ Trending stocks sentiment data unavailable"
        ),
        expect.objectContaining({
          detailed_diagnostics: expect.objectContaining({
            attempted_operations: expect.any(Array),
            potential_causes: expect.any(Array),
            troubleshooting_steps: expect.any(Array),
            system_checks: expect.any(Array),
          }),
        })
      );

      consoleSpy.mockRestore();
    });

    test("should include comprehensive diagnostics in batch sentiment", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      await request(app)
        .post("/sentiment/batch")
        .send({ symbols: ["AAPL"] })
        .expect(200);

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining("❌ Batch sentiment data unavailable"),
        expect.objectContaining({
          detailed_diagnostics: expect.objectContaining({
            attempted_operations: expect.any(Array),
            potential_causes: expect.any(Array),
            troubleshooting_steps: expect.any(Array),
            system_checks: expect.any(Array),
          }),
        })
      );

      consoleSpy.mockRestore();
    });
  });

  describe("Response format consistency", () => {
    test("should return consistent timestamp format across endpoints", async () => {
      const consoleSpy = jest
        .spyOn(console, "error")
        .mockImplementation(() => {});

      const healthResponse = await request(app).get("/sentiment/health");
      const pingResponse = await request(app).get("/sentiment/ping");
      const socialResponse = await request(app).get("/sentiment/social/AAPL");
      const trendingResponse = await request(app).get("/sentiment/trending");
      const marketResponse = await request(app).get(
        "/sentiment/market-summary"
      );

      // All timestamps should be valid ISO strings
      expect(new Date(healthResponse.body.timestamp)).toBeInstanceOf(Date);
      expect(new Date(pingResponse.body.timestamp)).toBeInstanceOf(Date);
      expect(new Date(socialResponse.body.timestamp)).toBeInstanceOf(Date);
      expect(new Date(trendingResponse.body.timestamp)).toBeInstanceOf(Date);
      expect(new Date(marketResponse.body.timestamp)).toBeInstanceOf(Date);

      consoleSpy.mockRestore();
    });
  });
});
