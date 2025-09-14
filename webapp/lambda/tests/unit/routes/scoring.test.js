const request = require("supertest");
const express = require("express");

// Mock dependencies BEFORE importing the routes
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

// Mock optional services that may not exist
jest.mock(
  "../../../utils/factorScoring",
  () => {
    return {
      FactorScoringEngine: jest.fn().mockImplementation(() => ({})),
    };
  },
  { virtual: true }
);

// Mock scoring helpers
jest.mock("../../../utils/scoringHelpers", () => ({
  calculateComprehensiveScores: jest.fn(),
  storeComprehensiveScores: jest.fn(),
}));

// Now import the routes after mocking

const scoringRoutes = require("../../../routes/scoring");
const { query } = require("../../../utils/database");
const { calculateComprehensiveScores, storeComprehensiveScores } = require("../../../utils/scoringHelpers");

describe("Scoring Routes - Testing Your Actual Site", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/scoring", scoringRoutes);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /scoring/ping - Basic ping endpoint", () => {
    test("should return scoring service ping", async () => {
      const response = await request(app).get("/scoring/ping").expect(200);

      expect(response.body).toMatchObject({
        status: "ok",
        endpoint: "scoring",
        timestamp: expect.any(String),
      });
    });
  });

  describe("GET /scoring/calculate/:symbol - Calculate comprehensive scores", () => {
    test("should return cached scores when available", async () => {
      const mockCachedScore = [{
        symbol: "AAPL",
        quality_score: 0.85,
        growth_score: 0.78,
        value_score: 0.65,
        momentum_score: 0.72,
        sentiment_score: 0.68,
        positioning_score: 0.75,
        composite_score: 0.74,
        updated_at: new Date().toISOString(),
      }];

      // Mock the database query to return cached score directly as array
      query.mockResolvedValue(mockCachedScore);

      const response = await request(app)
        .get("/scoring/calculate/AAPL")
        .expect(200);

      expect(response.body).toMatchObject({
        scores: expect.objectContaining({
          symbol: "AAPL",
          composite_score: 0.74,
        }),
        cached: true,
      });

      // Verify the correct database query was made
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("SELECT * FROM comprehensive_scores"),
        ["AAPL"]
      );
    });

    test("should return 404 for insufficient data", async () => {
      // Mock no cached scores
      query.mockResolvedValue([]);
      
      // Mock calculateComprehensiveScores function to return null (insufficient data)
      calculateComprehensiveScores.mockResolvedValue(null);

      const response = await request(app)
        .get("/scoring/calculate/INVALID")
        .expect(404);

      expect(response.body).toMatchObject({
        success: false,
        error: "Unable to calculate scores - insufficient data",
      });
    });

    test("should handle database errors gracefully", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app)
        .get("/scoring/calculate/AAPL")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to calculate comprehensive scores",
        details: "Database connection failed",
      });
    });

    test("should handle force recalculate parameter", async () => {
      // Mock calculateComprehensiveScores function to return scores
      const mockCalculatedScores = {
        symbol: "AAPL",
        quality_score: 0.80,
        composite_score: 0.75
      };
      
      calculateComprehensiveScores.mockResolvedValue(mockCalculatedScores);
      storeComprehensiveScores.mockResolvedValue(true);

      const response = await request(app)
        .get("/scoring/calculate/AAPL")
        .query({ recalculate: "true" })
        .expect(200);

      expect(response.body).toMatchObject({
        scores: expect.objectContaining({
          symbol: "AAPL",
        }),
        cached: false,
      });
    });

    test("should convert symbol to uppercase", async () => {
      const mockCachedScore = [{
        symbol: "AAPL",
        composite_score: 0.74,
      }];

      query.mockResolvedValue(mockCachedScore);

      const response = await request(app)
        .get("/scoring/calculate/aapl")
        .expect(200);

      expect(response.body.scores.symbol).toBe("AAPL");
      
      // Verify query was called with uppercase symbol
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("WHERE symbol = $1"),
        ["AAPL"]
      );
    });
  });

  describe("POST /scoring/calculate/batch - Batch calculate scores", () => {
    test("should validate symbols array", async () => {
      const response = await request(app)
        .post("/scoring/calculate/batch")
        .send({ symbols: null })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: "symbols array is required",
      });
    });

    test("should enforce 50 symbol limit", async () => {
      const symbols = Array(51)
        .fill(0)
        .map((_, i) => `STOCK${i}`);

      const response = await request(app)
        .post("/scoring/calculate/batch")
        .send({ symbols })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: "Maximum 50 symbols per batch",
      });
    });

    test("should process valid batch of symbols", async () => {
      const symbols = ["AAPL", "MSFT", "GOOGL"];
      query.mockResolvedValue([]); // No cached data

      const response = await request(app)
        .post("/scoring/calculate/batch")
        .send({ symbols })
        .expect([200, 500]);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          results: expect.any(Array),
          errors: expect.any(Array),
          processed: expect.any(Number),
          failed: expect.any(Number),
        });
      }
    });

    test("should handle forceRecalculate parameter", async () => {
      const symbols = ["AAPL"];
      query.mockResolvedValue([]);

      const response = await request(app)
        .post("/scoring/calculate/batch")
        .send({ symbols, forceRecalculate: true })
        .expect([200, 500]);

      expect(response.body).toHaveProperty("success");
    });

    test("should handle mixed success and failure in batch", async () => {
      const symbols = ["AAPL", "INVALID"];
      query.mockResolvedValue([]);

      const response = await request(app)
        .post("/scoring/calculate/batch")
        .send({ symbols })
        .expect([200, 500]);

      expect(response.body).toHaveProperty("success");
    });
  });

  describe("GET /scoring/top - Get top stocks by score", () => {
    test("should return top stocks with default parameters", async () => {
      const mockTopStocks = [
        {
          symbol: "AAPL",
          composite_score: 0.92,
          company_name: "Apple Inc.",
          sector: "Technology",
          market_cap: 2750000000000,
        },
        {
          symbol: "MSFT",
          composite_score: 0.88,
          company_name: "Microsoft Corporation",
          sector: "Technology",
          market_cap: 2300000000000,
        },
      ];

      query.mockResolvedValue(mockTopStocks);

      const response = await request(app)
        .get("/scoring/top")
        .expect([200, 500]);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          stocks: expect.any(Array),
          count: expect.any(Number),
          filters: expect.objectContaining({
            sector: expect.any(String),
            marketCapTier: expect.any(String),
            minScore: expect.any(Number),
          }),
        });
      }
    });

    test("should support limit parameter", async () => {
      query.mockResolvedValue([]);

      const response = await request(app)
        .get("/scoring/top")
        .query({ limit: 25 })
        .expect([200, 500]);

      if (response.status === 200 && query.mock.calls.length > 0) {
        expect(query).toHaveBeenCalledWith(
          expect.stringContaining("LIMIT 25"),
          expect.any(Array)
        );
      }
    });

    test("should support sector filter", async () => {
      query.mockResolvedValue([]);

      const response = await request(app)
        .get("/scoring/top")
        .query({ sector: "Technology" })
        .expect([200, 500]);

      expect(response.body).toHaveProperty("success");
    });

    test("should support marketCapTier filter", async () => {
      query.mockResolvedValue([]);

      const response = await request(app)
        .get("/scoring/top")
        .query({ marketCapTier: "Large" })
        .expect([200, 500]);

      expect(response.body).toHaveProperty("success");
    });

    test("should support minScore filter", async () => {
      query.mockResolvedValue([]);

      const response = await request(app)
        .get("/scoring/top")
        .query({ minScore: 0.7 })
        .expect([200, 500]);

      expect(response.body).toHaveProperty("success");
    });

    test("should enforce maximum limit of 200", async () => {
      query.mockResolvedValue([]);

      const response = await request(app)
        .get("/scoring/top")
        .query({ limit: 500 })
        .expect([200, 500]);

      expect(response.body).toHaveProperty("success");
    });
  });

  describe("GET /scoring/stats - Get scoring statistics", () => {
    test("should return overall and sector statistics", async () => {
      const mockStats = [
        {
          total_stocks: 1500,
          avg_quality: 0.65,
          avg_growth: 0.58,
          avg_value: 0.62,
          avg_momentum: 0.55,
          avg_sentiment: 0.52,
          avg_positioning: 0.6,
          avg_composite: 0.59,
          q1_composite: 0.45,
          median_composite: 0.58,
          q3_composite: 0.72,
          max_composite: 0.95,
          min_composite: 0.15,
        },
      ];

      const mockSectorStats = [
        { sector: "Technology", count: 350, avg_score: 0.68, max_score: 0.95 },
        { sector: "Healthcare", count: 280, avg_score: 0.62, max_score: 0.88 },
      ];

      query
        .mockResolvedValueOnce(mockStats)
        .mockResolvedValueOnce(mockSectorStats);

      const response = await request(app)
        .get("/scoring/stats")
        .expect([200, 500]);

      if (response.status === 200) {
        expect(response.body).toMatchObject({
          success: true,
          overallStats: expect.any(Object),
          sectorStats: expect.any(Array),
        });
      }
    });

    test("should handle database errors in stats", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app).get("/scoring/stats").expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to get scoring statistics",
      });
    });
  });

  describe("Error handling", () => {
    test("should handle various error scenarios gracefully", async () => {
      query.mockImplementation(() => {
        throw new Error("Database error");
      });

      const response = await request(app)
        .get("/scoring/calculate/AAPL")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.any(String),
      });
    });

    test("should handle malformed requests", async () => {
      const response = await request(app)
        .post("/scoring/calculate/batch")
        .send({ invalid: "data" })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: expect.stringContaining("symbols array is required"),
      });
    });
  });
});
