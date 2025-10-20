const request = require("supertest");
const express = require("express");
const positioningRouter = require("../../../routes/positioning");
const responseFormatterMiddleware = require("../../../middleware/responseFormatter");
// Mock database query
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  closeDatabase: jest.fn(),
  initializeDatabase: jest.fn(),
  getPool: jest.fn(),
  transaction: jest.fn(),
  healthCheck: jest.fn(),
}));

const { query, closeDatabase, initializeDatabase, getPool, transaction, healthCheck } = require("../../../utils/database");
const mockQuery = query;
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
    // Mock positioning_metrics data
    const mockPositioningMetrics = {
      symbol: "AAPL",
      date: "2025-10-08",
      institutional_ownership: 0.6234,
      institutional_float_held: 0.6156,
      institution_count: 3456,
      insider_ownership: 0.0045,
      shares_short: 123456789,
      shares_short_prior_month: 120000000,
      short_ratio: 1.23,
      short_percent_of_float: 0.0234,
      short_interest_change: 0.0288,
      float_shares: 5270000000,
      shares_outstanding: 15550000000,
    };
    // Mock institutional_positioning data
    const mockInstitutionalData = [
      {
        symbol: "AAPL",
        institution_type: "MUTUAL_FUND",
        institution_name: "Vanguard Group Inc",
        position_size: 1250000000,
        position_change_percent: 2.5,
        market_share: 0.08,
        filing_date: "2025-09-30",
        quarter: "2025Q3",
      },
    ];
    // Mock retail_sentiment data
    const mockSentimentData = {
      symbol: "AAPL",
      bullish_percentage: 60.5,
      bearish_percentage: 20.3,
      neutral_percentage: 19.2,
      net_sentiment: 40.2,
      sentiment_change: 5.3,
      source: "yfinance_derived",
      date: "2025-10-08",
    };
    it("should return positioning data with positioning_score successfully", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [mockPositioningMetrics] }) // positioning_metrics
        .mockResolvedValueOnce({ rows: mockInstitutionalData }) // institutional_positioning
        .mockResolvedValueOnce({ rows: [mockSentimentData] }); // retail_sentiment
      const response = await request(app)
        .get("/api/positioning/stocks")
        .expect(200);
      expect(response.body).toHaveProperty("positioning_metrics");
      expect(response.body).toHaveProperty("positioning_score");
      expect(response.body).toHaveProperty("institutional_holders");
      expect(response.body).toHaveProperty("retail_sentiment");
      expect(response.body).toHaveProperty("metadata");
      // Verify positioning_metrics
      expect(response.body.positioning_metrics.symbol).toBe("AAPL");
      expect(response.body.positioning_metrics.institutional_ownership).toBe(0.6234);
      // Verify positioning_score is calculated
      expect(response.body.positioning_score).toBeGreaterThan(0);
      expect(response.body.positioning_score).toBeLessThanOrEqual(100);
      // Verify institutional_holders
      expect(response.body.institutional_holders).toEqual(mockInstitutionalData);
      // Verify retail_sentiment
      expect(response.body.retail_sentiment).toEqual(mockSentimentData);
      expect(response.body.metadata.symbol).toBe("all");
    });
    it("should handle symbol parameter correctly", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [mockPositioningMetrics] })
        .mockResolvedValueOnce({ rows: mockInstitutionalData })
        .mockResolvedValueOnce({ rows: [mockSentimentData] });
      const response = await request(app)
        .get("/api/positioning/stocks?symbol=AAPL")
        .expect(200);
      expect(response.body.metadata.symbol).toBe("AAPL");
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("AND pm.symbol = $1"),
        expect.arrayContaining(["AAPL"])
      );
    });
    it("should handle pagination parameters", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [mockPositioningMetrics] })
        .mockResolvedValueOnce({ rows: mockInstitutionalData })
        .mockResolvedValueOnce({ rows: [mockSentimentData] });
      await request(app)
        .get("/api/positioning/stocks?limit=25&page=2")
        .expect(200);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("LIMIT"),
        expect.arrayContaining([25, 25]) // page 2 with limit 25 = offset 25
      );
    });
    it("should handle timeframe parameter", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [mockPositioningMetrics] })
        .mockResolvedValueOnce({ rows: mockInstitutionalData })
        .mockResolvedValueOnce({ rows: [mockSentimentData] });
      const response = await request(app)
        .get("/api/positioning/stocks?timeframe=weekly")
        .expect(200);
      expect(response.body.metadata.timeframe).toBe("weekly");
      expect(consoleSpy).toHaveBeenCalledWith(
        "📊 Stock positioning data requested - symbol: all, timeframe: weekly"
      );
    });
    it("should handle database query failures with 500 error", async () => {
      mockQuery.mockRejectedValueOnce(new Error("Query failed"));
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
    it("should return 404 when no data is found", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });
      const response = await request(app)
        .get("/api/positioning/stocks")
        .expect(404);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("No positioning data found");
      expect(response.body.message).toBe("No positioning data available for this symbol");
    });
    it("should handle database errors properly", async () => {
      mockQuery.mockRejectedValueOnce(new Error("Database failed"));
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
    it("should include correct metadata structure", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [mockPositioningMetrics] })
        .mockResolvedValueOnce({ rows: mockInstitutionalData })
        .mockResolvedValueOnce({ rows: [mockSentimentData] });
      const response = await request(app)
        .get("/api/positioning/stocks?symbol=TSLA&timeframe=monthly")
        .expect(200);
      expect(response.body.metadata).toEqual({
        symbol: "TSLA",
        timeframe: "monthly",
        total_records: {
          institutional: 1,
          sentiment: 1,
        },
        last_updated: expect.any(String),
      });
      // Validate timestamp format
      expect(new Date(response.body.metadata.last_updated)).toBeInstanceOf(
        Date
      );
    });
    it("should handle server errors properly", async () => {
      mockQuery.mockImplementation(() => {
        throw new Error("Database connection failed");
      });
      const response = await request(app)
        .get("/api/positioning/stocks")
        .expect(500);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe(
        "Failed to fetch stock positioning data"
      );
      expect(console.error).toHaveBeenCalledWith(
        "Error fetching stock positioning data:",
        expect.any(Error)
      );
    });
    it("should use default values when parameters are not provided", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [mockPositioningMetrics] })
        .mockResolvedValueOnce({ rows: mockInstitutionalData })
        .mockResolvedValueOnce({ rows: [mockSentimentData] });
      await request(app).get("/api/positioning/stocks").expect(200);
      // Check that institutional query has limit and offset
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("LIMIT"),
        expect.arrayContaining([50, 0]) // default limit 50, page 1 (offset 0)
      );
    });
    it("should handle large page numbers correctly", async () => {
      mockQuery
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });
      await request(app)
        .get("/api/positioning/stocks?page=100&limit=10")
        .expect(404);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("LIMIT"),
        expect.arrayContaining([10, 990]) // page 100 with limit 10 = offset 990
      );
    });
    it("should calculate positioning score correctly", async () => {
      const highScoreMetrics = {
        ...mockPositioningMetrics,
        institutional_ownership: 0.85, // >0.7 = +30
        insider_ownership: 0.12, // >0.1 = +15
        short_percent_of_float: 0.015, // <0.02 = +10
        short_interest_change: -0.12, // <-0.1 = +15
      };
      mockQuery
        .mockResolvedValueOnce({ rows: [highScoreMetrics] })
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });
      const response = await request(app)
        .get("/api/positioning/stocks?symbol=AAPL")
        .expect(200);
      // Score = 50 + 30 + 15 + 10 + 15 = 120, capped at 100
      expect(response.body.positioning_score).toBe(100);
    });
    it("should handle null metrics gracefully", async () => {
      const nullMetrics = {
        symbol: "TEST",
        institutional_ownership: null,
        insider_ownership: null,
        short_percent_of_float: null,
        short_interest_change: null,
      };
      mockQuery
        .mockResolvedValueOnce({ rows: [nullMetrics] })
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });
      const response = await request(app)
        .get("/api/positioning/stocks?symbol=TEST")
        .expect(200);
      // Should return neutral score when all null
      expect(response.body.positioning_score).toBe(50);
    });
  });
  describe("GET /api/positioning/summary", () => {
    // Mock summary data from positioning_metrics table
    const mockInstitutionalSummary = {
      rows: [
        {
          avg_institutional_ownership: 0.62,
          avg_insider_ownership: 0.03,
          avg_short_interest: 0.05,
          avg_short_change: -0.02,
          high_institutional_count: 15,
          high_short_count: 8,
          total_positions: 25,
        },
      ],
    };
    // Mock summary data from retail_sentiment table
    const mockRetailSummary = {
      rows: [
        {
          avg_bullish: 45.2,
          avg_bearish: 30.1,
          avg_net_sentiment: 15.1,
          total_readings: 100,
        },
      ],
    };
    it("should return positioning summary successfully", async () => {
      mockQuery
        .mockResolvedValueOnce(mockInstitutionalSummary)
        .mockResolvedValueOnce(mockRetailSummary);
      const response = await request(app)
        .get("/api/positioning/summary")
        .set("Authorization", "Bearer test-token")
        .expect(200);
      expect(response.body).toHaveProperty("market_overview");
      expect(response.body).toHaveProperty("key_metrics");
      expect(response.body).toHaveProperty("data_freshness");
      expect(response.body.market_overview.institutional_flow).toBe("MODERATELY_BULLISH");
      expect(response.body.key_metrics.avg_institutional_ownership).toBe(0.62);
      expect(response.body.key_metrics.avg_insider_ownership).toBe(0.03);
      expect(response.body.key_metrics.avg_short_interest).toBe(0.05);
      expect(response.body.key_metrics.avg_short_change).toBe(-0.02);
      expect(response.body.key_metrics.retail_net_sentiment).toBe(15.1);
    });
    it("should calculate bullish overall positioning", async () => {
      const bullishInstitutional = {
        rows: [{
          ...mockInstitutionalSummary.rows[0],
          avg_institutional_ownership: 0.65, // >60%
          avg_short_change: -0.06 // <-5%
        }],
      };
      const bullishRetail = {
        rows: [{ ...mockRetailSummary.rows[0], avg_net_sentiment: 45.0 }],
      };
      mockQuery
        .mockResolvedValueOnce(bullishInstitutional)
        .mockResolvedValueOnce(bullishRetail);
      const response = await request(app)
        .get("/api/positioning/summary")
        .set("Authorization", "Bearer test-token")
        .expect(200);
      expect(response.body.market_overview.overall_positioning).toBe("BULLISH");
    });
    it("should calculate moderately bullish positioning", async () => {
      const modBullishInstitutional = {
        rows: [{
          ...mockInstitutionalSummary.rows[0],
          avg_institutional_ownership: 0.55, // >50%
          avg_short_change: 0.0 // neutral
        }],
      };
      const modBullishRetail = {
        rows: [{ ...mockRetailSummary.rows[0], avg_net_sentiment: 25.0 }],
      };
      mockQuery
        .mockResolvedValueOnce(modBullishInstitutional)
        .mockResolvedValueOnce(modBullishRetail);
      const response = await request(app)
        .get("/api/positioning/summary")
        .set("Authorization", "Bearer test-token")
        .expect(200);
      expect(response.body.market_overview.overall_positioning).toBe(
        "MODERATELY_BULLISH"
      );
    });
    it("should calculate bearish positioning", async () => {
      const bearishInstitutional = {
        rows: [{
          ...mockInstitutionalSummary.rows[0],
          avg_short_interest: 0.16, // >15%
          avg_institutional_ownership: 0.45
        }],
      };
      const bearishRetail = {
        rows: [{ ...mockRetailSummary.rows[0], avg_net_sentiment: -25.0 }],
      };
      mockQuery
        .mockResolvedValueOnce(bearishInstitutional)
        .mockResolvedValueOnce(bearishRetail);
      const response = await request(app)
        .get("/api/positioning/summary")
        .set("Authorization", "Bearer test-token")
        .expect(200);
      expect(response.body.market_overview.overall_positioning).toBe("BEARISH");
    });
    it("should calculate moderately bearish positioning", async () => {
      const modBearishInstitutional = {
        rows: [{
          ...mockInstitutionalSummary.rows[0],
          avg_short_interest: 0.11, // >10%
          avg_institutional_ownership: 0.45
        }],
      };
      const modBearishRetail = {
        rows: [{ ...mockRetailSummary.rows[0], avg_net_sentiment: -10.0 }],
      };
      mockQuery
        .mockResolvedValueOnce(modBearishInstitutional)
        .mockResolvedValueOnce(modBearishRetail);
      const response = await request(app)
        .get("/api/positioning/summary")
        .set("Authorization", "Bearer test-token")
        .expect(200);
      expect(response.body.market_overview.overall_positioning).toBe(
        "MODERATELY_BEARISH"
      );
    });
    it("should default to neutral positioning", async () => {
      const neutralInstitutional = {
        rows: [{
          ...mockInstitutionalSummary.rows[0],
          avg_institutional_ownership: 0.45,
          avg_short_interest: 0.08,
          avg_short_change: 0.0
        }],
      };
      const neutralRetail = {
        rows: [{ ...mockRetailSummary.rows[0], avg_net_sentiment: 5.0 }],
      };
      mockQuery
        .mockResolvedValueOnce(neutralInstitutional)
        .mockResolvedValueOnce(neutralRetail);
      const response = await request(app)
        .get("/api/positioning/summary")
        .set("Authorization", "Bearer test-token")
        .expect(200);
      expect(response.body.market_overview.overall_positioning).toBe("NEUTRAL");
    });
    it("should handle null/undefined values in database results", async () => {
      const nullInstitutional = {
        rows: [
          {
            avg_institutional_ownership: null,
            avg_insider_ownership: null,
            avg_short_interest: null,
            avg_short_change: null,
            high_institutional_count: null,
            high_short_count: null,
            total_positions: null,
          },
        ],
      };
      const nullRetail = {
        rows: [
          {
            avg_bullish: null,
            avg_bearish: null,
            avg_net_sentiment: null,
            total_readings: null,
          },
        ],
      };
      mockQuery
        .mockResolvedValueOnce(nullInstitutional)
        .mockResolvedValueOnce(nullRetail);
      const response = await request(app)
        .get("/api/positioning/summary")
        .set("Authorization", "Bearer test-token")
        .expect(200);
      expect(response.body.key_metrics.avg_institutional_ownership).toBe(0);
      expect(response.body.key_metrics.avg_insider_ownership).toBe(0);
      expect(response.body.key_metrics.avg_short_interest).toBe(0);
      expect(response.body.key_metrics.avg_short_change).toBe(0);
      expect(response.body.key_metrics.retail_net_sentiment).toBe(0);
      expect(response.body.data_freshness.institutional_positions).toBe(0);
      expect(response.body.data_freshness.retail_readings).toBe(0);
    });
    it("should calculate retail sentiment classifications correctly", async () => {
      const testCases = [
        { sentiment: 25, expected: "BULLISH" },
        { sentiment: 0, expected: "MIXED" },
        { sentiment: -25, expected: "BEARISH" },
        { sentiment: 19, expected: "MIXED" },
        { sentiment: -19, expected: "MIXED" },
      ];
      for (const testCase of testCases) {
        const retailData = {
          rows: [
            {
              ...mockRetailSummary.rows[0],
              avg_net_sentiment: testCase.sentiment,
            },
          ],
        };
        mockQuery
          .mockResolvedValueOnce(mockInstitutionalSummary)
          .mockResolvedValueOnce(retailData);
        const response = await request(app)
          .get("/api/positioning/summary")
          .set("Authorization", "Bearer test-token")
          .expect(200);
        expect(response.body.market_overview.retail_sentiment).toBe(
          testCase.expected
        );
      }
    });
    it("should include valid timestamp in response", async () => {
      mockQuery
        .mockResolvedValueOnce(mockInstitutionalSummary)
        .mockResolvedValueOnce(mockRetailSummary);
      const response = await request(app)
        .get("/api/positioning/summary")
        .set("Authorization", "Bearer test-token")
        .expect(200);
      expect(response.body.last_updated).toMatch(
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/
      );
      expect(new Date(response.body.last_updated)).toBeInstanceOf(Date);
    });
    it("should handle database errors properly", async () => {
      mockQuery.mockRejectedValue(new Error("Summary query failed"));
      const response = await request(app)
        .get("/api/positioning/summary")
        .set("Authorization", "Bearer test-token")
        .expect(500);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Failed to fetch positioning summary");
      expect(console.error).toHaveBeenCalledWith(
        "Error fetching positioning summary:",
        expect.any(Error)
      );
    });
    it("should use correct SQL queries with positioning_metrics and retail sentiment", async () => {
      mockQuery
        .mockResolvedValueOnce(mockInstitutionalSummary)
        .mockResolvedValueOnce(mockRetailSummary);
      await request(app).get("/api/positioning/summary").set("Authorization", "Bearer test-token").expect(200);
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("FROM positioning_metrics pm")
      );
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("FROM retail_sentiment")
      );
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining(
          "WHERE pm.date >= CURRENT_DATE - INTERVAL '30 days'"
        )
      );
    });
    it("should have consistent data structure", async () => {
      mockQuery
        .mockResolvedValueOnce(mockInstitutionalSummary)
        .mockResolvedValueOnce(mockRetailSummary);
      const response = await request(app)
        .get("/api/positioning/summary")
        .set("Authorization", "Bearer test-token")
        .expect(200);
      expect(response.body).toHaveProperty("market_overview");
      expect(response.body.market_overview).toHaveProperty(
        "institutional_flow"
      );
      expect(response.body.market_overview).toHaveProperty("retail_sentiment");
      expect(response.body.market_overview).toHaveProperty(
        "overall_positioning"
      );
      expect(response.body).toHaveProperty("key_metrics");
      expect(response.body.key_metrics).toHaveProperty(
        "avg_institutional_ownership"
      );
      expect(response.body.key_metrics).toHaveProperty(
        "avg_insider_ownership"
      );
      expect(response.body.key_metrics).toHaveProperty("avg_short_interest");
      expect(response.body.key_metrics).toHaveProperty("avg_short_change");
      expect(response.body.key_metrics).toHaveProperty("retail_net_sentiment");
      expect(response.body).toHaveProperty("data_freshness");
      expect(response.body.data_freshness).toHaveProperty(
        "institutional_positions"
      );
      expect(response.body.data_freshness).toHaveProperty("retail_readings");
      expect(response.body.data_freshness).toHaveProperty(
        "high_institutional_count"
      );
      expect(response.body.data_freshness).toHaveProperty("high_short_count");
    });
  });
});
