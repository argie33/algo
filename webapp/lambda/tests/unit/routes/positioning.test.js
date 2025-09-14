const request = require("supertest");
const express = require("express");
const positioningRouter = require("../../../routes/positioning");
const responseFormatterMiddleware = require("../../../middleware/responseFormatter");

// Mock database query
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

const { query: mockQuery } = require("../../../utils/database");

const app = express();
app.use(responseFormatterMiddleware);
app.use("/api/positioning", positioningRouter);

describe("Positioning Routes", () => {
  let consoleSpy;

  beforeEach(() => {
    consoleSpy = jest.spyOn(console, "log").mockImplementation();
    jest.spyOn(console, "error").mockImplementation();
    jest.spyOn(console, "warn").mockImplementation();
    jest.clearAllMocks();
    mockQuery.mockClear();
  });

  afterEach(() => {
    consoleSpy.mockRestore();
    jest.restoreAllMocks();
  });

  describe("GET /api/positioning/stocks", () => {
    const mockInstitutionalData = [
      {
        symbol: "AAPL",
        institution_type: "hedge_fund",
        institution_name: "Test Fund",
        position_size: 1000000,
        position_change_percent: 5.5,
        market_share: 2.1,
        filing_date: "2023-12-01",
        quarter: "Q4"
      }
    ];

    const mockSentimentData = [
      {
        symbol: "AAPL",
        bullish_percentage: 60.5,
        bearish_percentage: 25.3,
        neutral_percentage: 14.2,
        net_sentiment: 35.2,
        sentiment_change: 2.1,
        source: "retail_tracker",
        date: "2023-12-15"
      }
    ];

    it("should return positioning data successfully", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: mockInstitutionalData })
        .mockResolvedValueOnce({ rows: mockSentimentData });

      const response = await request(app)
        .get("/api/positioning/stocks")
        .expect(200);

      expect(response.body).toHaveProperty("institutional_positioning");
      expect(response.body).toHaveProperty("retail_sentiment");
      expect(response.body).toHaveProperty("metadata");
      expect(response.body.institutional_positioning).toEqual(mockInstitutionalData);
      expect(response.body.retail_sentiment).toEqual(mockSentimentData);
      expect(response.body.metadata.symbol).toBe("all");
    });

    it("should handle symbol parameter correctly", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: mockInstitutionalData })
        .mockResolvedValueOnce({ rows: mockSentimentData });

      const response = await request(app)
        .get("/api/positioning/stocks?symbol=AAPL")
        .expect(200);

      expect(response.body.metadata.symbol).toBe("AAPL");
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("WHERE symbol = $1"),
        expect.arrayContaining(["AAPL"])
      );
    });

    it("should handle pagination parameters", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: mockInstitutionalData })
        .mockResolvedValueOnce({ rows: mockSentimentData });

      await request(app)
        .get("/api/positioning/stocks?limit=25&page=2")
        .expect(200);

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("LIMIT $1 OFFSET $2"),
        expect.arrayContaining([25, 25]) // page 2 with limit 25 = offset 25
      );
    });

    it("should handle timeframe parameter", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: mockInstitutionalData })
        .mockResolvedValueOnce({ rows: mockSentimentData });

      const response = await request(app)
        .get("/api/positioning/stocks?timeframe=weekly")
        .expect(200);

      expect(response.body.metadata.timeframe).toBe("weekly");
      expect(consoleSpy).toHaveBeenCalledWith(
        "📊 Stock positioning data requested - symbol: all, timeframe: weekly"
      );
    });

    it("should handle database query failures gracefully", async () => {
      mockQuery
        .mockRejectedValueOnce(new Error("Institutional query failed"))
        .mockRejectedValueOnce(new Error("Sentiment query failed"));

      const response = await request(app)
        .get("/api/positioning/stocks")
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("No positioning data found not found");
      expect(console.warn).toHaveBeenCalledWith(
        "Institutional positioning query failed:",
        "Institutional query failed"
      );
      expect(console.warn).toHaveBeenCalledWith(
        "Retail sentiment query failed:",
        "Sentiment query failed"
      );
    });

    it("should return 404 when no data is found", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/api/positioning/stocks")
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("No positioning data found not found");
    });

    it("should handle one data source failing while other succeeds", async () => {
      mockQuery
        .mockRejectedValueOnce(new Error("Institutional failed"))
        .mockResolvedValueOnce({ rows: mockSentimentData });

      const response = await request(app)
        .get("/api/positioning/stocks")
        .expect(200);

      expect(response.body.institutional_positioning).toEqual([]);
      expect(response.body.retail_sentiment).toEqual(mockSentimentData);
    });

    it("should include correct metadata structure", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: mockInstitutionalData })
        .mockResolvedValueOnce({ rows: mockSentimentData });

      const response = await request(app)
        .get("/api/positioning/stocks?symbol=TSLA&timeframe=monthly")
        .expect(200);

      expect(response.body.metadata).toEqual({
        symbol: "TSLA",
        timeframe: "monthly",
        total_records: {
          institutional: 1,
          sentiment: 1
        },
        last_updated: expect.any(String)
      });

      // Validate timestamp format
      expect(new Date(response.body.metadata.last_updated)).toBeInstanceOf(Date);
    });

    it("should handle server errors properly", async () => {
      mockQuery.mockImplementation(() => {
        throw new Error("Database connection failed");
      });

      const response = await request(app)
        .get("/api/positioning/stocks")
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Failed to fetch stock positioning data");
      expect(console.error).toHaveBeenCalledWith(
        "Error fetching stock positioning data:",
        expect.any(Error)
      );
    });

    it("should use default values when parameters are not provided", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: mockInstitutionalData })
        .mockResolvedValueOnce({ rows: mockSentimentData });

      await request(app)
        .get("/api/positioning/stocks")
        .expect(200);

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("LIMIT $1 OFFSET $2"),
        [50, 0] // default limit 50, page 1 (offset 0)
      );
    });

    it("should handle large page numbers correctly", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      await request(app)
        .get("/api/positioning/stocks?page=100&limit=10")
        .expect(404);

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("LIMIT $1 OFFSET $2"),
        [10, 990] // page 100 with limit 10 = offset 990
      );
    });
  });

  describe("GET /api/positioning/summary", () => {
    const mockInstitutionalSummary = {
      rows: [{
        avg_change: 2.5,
        bullish_count: 15,
        bearish_count: 8,
        total_positions: 25
      }]
    };

    const mockRetailSummary = {
      rows: [{
        avg_bullish: 45.2,
        avg_bearish: 30.1,
        avg_net_sentiment: 15.1
      }]
    };

    it("should return positioning summary successfully", async () => {
      mockQuery
        .mockResolvedValueOnce(mockInstitutionalSummary)
        .mockResolvedValueOnce(mockRetailSummary);

      const response = await request(app)
        .get("/api/positioning/summary")
        .expect(200);

      expect(response.body).toHaveProperty("market_overview");
      expect(response.body).toHaveProperty("key_metrics");
      expect(response.body).toHaveProperty("data_freshness");
      expect(response.body.market_overview.institutional_flow).toBe("BULLISH");
      expect(response.body.key_metrics.institutional_avg_change).toBe(2.5);
    });

    it("should calculate bullish overall positioning", async () => {
      const bullishInstitutional = { rows: [{ ...mockInstitutionalSummary.rows[0], avg_change: 3.0 }] };
      const bullishRetail = { rows: [{ ...mockRetailSummary.rows[0], avg_net_sentiment: 45.0 }] };

      mockQuery
        .mockResolvedValueOnce(bullishInstitutional)
        .mockResolvedValueOnce(bullishRetail);

      const response = await request(app)
        .get("/api/positioning/summary")
        .expect(200);

      expect(response.body.market_overview.overall_positioning).toBe("BULLISH");
    });

    it("should calculate moderately bullish positioning", async () => {
      const modBullishInstitutional = { rows: [{ ...mockInstitutionalSummary.rows[0], avg_change: 1.0 }] };
      const modBullishRetail = { rows: [{ ...mockRetailSummary.rows[0], avg_net_sentiment: 25.0 }] };

      mockQuery
        .mockResolvedValueOnce(modBullishInstitutional)
        .mockResolvedValueOnce(modBullishRetail);

      const response = await request(app)
        .get("/api/positioning/summary")
        .expect(200);

      expect(response.body.market_overview.overall_positioning).toBe("MODERATELY_BULLISH");
    });

    it("should calculate bearish positioning", async () => {
      const bearishInstitutional = { rows: [{ ...mockInstitutionalSummary.rows[0], avg_change: -3.0 }] };
      const bearishRetail = { rows: [{ ...mockRetailSummary.rows[0], avg_net_sentiment: -25.0 }] };

      mockQuery
        .mockResolvedValueOnce(bearishInstitutional)
        .mockResolvedValueOnce(bearishRetail);

      const response = await request(app)
        .get("/api/positioning/summary")
        .expect(200);

      expect(response.body.market_overview.overall_positioning).toBe("BEARISH");
    });

    it("should calculate moderately bearish positioning", async () => {
      const modBearishInstitutional = { rows: [{ ...mockInstitutionalSummary.rows[0], avg_change: -1.0 }] };
      const modBearishRetail = { rows: [{ ...mockRetailSummary.rows[0], avg_net_sentiment: -10.0 }] };

      mockQuery
        .mockResolvedValueOnce(modBearishInstitutional)
        .mockResolvedValueOnce(modBearishRetail);

      const response = await request(app)
        .get("/api/positioning/summary")
        .expect(200);

      expect(response.body.market_overview.overall_positioning).toBe("MODERATELY_BEARISH");
    });

    it("should default to neutral positioning", async () => {
      const neutralInstitutional = { rows: [{ ...mockInstitutionalSummary.rows[0], avg_change: 0.5 }] };
      const neutralRetail = { rows: [{ ...mockRetailSummary.rows[0], avg_net_sentiment: 5.0 }] };

      mockQuery
        .mockResolvedValueOnce(neutralInstitutional)
        .mockResolvedValueOnce(neutralRetail);

      const response = await request(app)
        .get("/api/positioning/summary")
        .expect(200);

      expect(response.body.market_overview.overall_positioning).toBe("NEUTRAL");
    });

    it("should handle null/undefined values in database results", async () => {
      const nullInstitutional = { rows: [{ avg_change: null, bullish_count: null, bearish_count: null, total_positions: null }] };
      const nullRetail = { rows: [{ avg_bullish: null, avg_bearish: null, avg_net_sentiment: null }] };

      mockQuery
        .mockResolvedValueOnce(nullInstitutional)
        .mockResolvedValueOnce(nullRetail);

      const response = await request(app)
        .get("/api/positioning/summary")
        .expect(200);

      expect(response.body.key_metrics.institutional_avg_change).toBe(0);
      expect(response.body.key_metrics.retail_net_sentiment).toBe(0);
      expect(response.body.data_freshness.institutional_positions).toBe(0);
    });

    it("should calculate retail sentiment classifications correctly", async () => {
      const testCases = [
        { sentiment: 25, expected: "BULLISH" },
        { sentiment: 0, expected: "MIXED" },
        { sentiment: -25, expected: "BEARISH" },
        { sentiment: 19, expected: "MIXED" },
        { sentiment: -19, expected: "MIXED" }
      ];

      for (const testCase of testCases) {
        const retailData = { rows: [{ ...mockRetailSummary.rows[0], avg_net_sentiment: testCase.sentiment }] };
        
        mockQuery
          .mockResolvedValueOnce(mockInstitutionalSummary)
          .mockResolvedValueOnce(retailData);

        const response = await request(app)
          .get("/api/positioning/summary")
          .expect(200);

        expect(response.body.market_overview.retail_sentiment).toBe(testCase.expected);
      }
    });

    it("should include valid timestamp in response", async () => {
      mockQuery
        .mockResolvedValueOnce(mockInstitutionalSummary)
        .mockResolvedValueOnce(mockRetailSummary);

      const response = await request(app)
        .get("/api/positioning/summary")
        .expect(200);

      expect(response.body.last_updated).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
      expect(new Date(response.body.last_updated)).toBeInstanceOf(Date);
    });

    it("should handle database errors properly", async () => {
      mockQuery.mockRejectedValue(new Error("Summary query failed"));

      const response = await request(app)
        .get("/api/positioning/summary")
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Failed to fetch positioning summary");
      expect(console.error).toHaveBeenCalledWith(
        "Error fetching positioning summary:",
        expect.any(Error)
      );
    });

    it("should use correct SQL queries with date intervals", async () => {
      mockQuery
        .mockResolvedValueOnce(mockInstitutionalSummary)
        .mockResolvedValueOnce(mockRetailSummary);

      await request(app)
        .get("/api/positioning/summary")
        .expect(200);

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("WHERE filing_date >= CURRENT_DATE - INTERVAL '90 days'")
      );
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("WHERE date >= CURRENT_DATE - INTERVAL '30 days'")
      );
    });

    it("should have consistent data structure", async () => {
      mockQuery
        .mockResolvedValueOnce(mockInstitutionalSummary)
        .mockResolvedValueOnce(mockRetailSummary);

      const response = await request(app)
        .get("/api/positioning/summary")
        .expect(200);

      expect(response.body).toHaveProperty("market_overview");
      expect(response.body.market_overview).toHaveProperty("institutional_flow");
      expect(response.body.market_overview).toHaveProperty("retail_sentiment");
      expect(response.body.market_overview).toHaveProperty("overall_positioning");
      
      expect(response.body).toHaveProperty("key_metrics");
      expect(response.body.key_metrics).toHaveProperty("institutional_avg_change");
      expect(response.body.key_metrics).toHaveProperty("retail_net_sentiment");
      
      expect(response.body).toHaveProperty("data_freshness");
      expect(response.body.data_freshness).toHaveProperty("institutional_positions");
      expect(response.body.data_freshness).toHaveProperty("retail_readings");
    });
  });
});