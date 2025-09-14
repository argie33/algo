const request = require("supertest");
const express = require("express");

const sectorsRoutes = require("../../../routes/sectors");

// Mock database
const { query } = require("../../../utils/database");

jest.mock("../../../utils/database");

// Mock authentication middleware
const { authenticateToken } = require("../../../middleware/auth");

jest.mock("../../../middleware/auth");
describe("Sectors Routes", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/sectors", sectorsRoutes);

    // Mock authentication to pass for all tests
    authenticateToken.mockImplementation((req, res, next) => {
      req.user = { sub: "test-user-123" };
      next();
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /sectors/health", () => {
    test("should return health status", async () => {
      const response = await request(app).get("/sectors/health").expect(200);

      expect(response.body).toMatchObject({
        status: "operational",
        service: "sectors",
        timestamp: expect.any(String),
        message: "Sectors service is running",
      });
    });
  });

  describe("GET /sectors/", () => {
    test("should return API status", async () => {
      const response = await request(app).get("/sectors/").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        message: "Sectors API - Ready",
        timestamp: expect.any(String),
        status: "operational",
      });
    });
  });

  describe("GET /sectors/analysis", () => {
    test("should return comprehensive sector analysis with default timeframe", async () => {
      const mockSectorAnalysis = {
        rows: [
          {
            sector: "Technology",
            industry: "Software Infrastructure",
            stock_count: 145,
            priced_stocks: 140,
            avg_price: 125.5,
            avg_daily_change: 2.35,
            avg_weekly_change: 8.72,
            avg_monthly_change: 15.8,
            avg_volume: 89500000,
            avg_rsi: 65.2,
            avg_momentum: 0.15,
            avg_macd: 0.025,
            avg_jt_momentum: 0.12,
            avg_momentum_3m: 0.08,
            avg_momentum_6m: 0.06,
            avg_risk_adj_momentum: 0.1,
            avg_momentum_strength: 85.5,
            avg_volume_momentum: 0.14,
            bullish_stocks: 95,
            bearish_stocks: 25,
            neutral_stocks: 20,
            total_dollar_volume: 12500000000,
            performance_rank: 1,
            top_performers: [
              {
                symbol: "AAPL",
                name: "Apple Inc.",
                price: 175.25,
                monthly_return: 12.5,
                momentum: 0.18,
                jt_momentum: 0.15,
              },
            ],
            bottom_performers: [
              {
                symbol: "TECH_WORST",
                name: "Tech Worst Corp",
                price: 45.3,
                monthly_return: -8.2,
                momentum: -0.05,
                jt_momentum: -0.02,
              },
            ],
          },
          {
            sector: "Healthcare",
            industry: "Drug Manufacturers",
            stock_count: 98,
            priced_stocks: 92,
            avg_price: 98.75,
            avg_daily_change: 1.85,
            avg_weekly_change: 4.2,
            avg_monthly_change: 7.45,
            avg_volume: 65200000,
            avg_rsi: 58.1,
            avg_momentum: 0.08,
            avg_macd: 0.015,
            avg_jt_momentum: 0.06,
            avg_momentum_3m: 0.04,
            avg_momentum_6m: 0.03,
            avg_risk_adj_momentum: 0.05,
            avg_momentum_strength: 72.3,
            avg_volume_momentum: 0.07,
            bullish_stocks: 55,
            bearish_stocks: 15,
            neutral_stocks: 22,
            total_dollar_volume: 6400000000,
            performance_rank: 2,
            top_performers: [
              {
                symbol: "JNJ",
                name: "Johnson & Johnson",
                price: 165.8,
                monthly_return: 9.3,
                momentum: 0.12,
                jt_momentum: 0.09,
              },
            ],
            bottom_performers: [
              {
                symbol: "HEALTH_WORST",
                name: "Health Worst Inc",
                price: 32.15,
                monthly_return: -5.4,
                momentum: -0.03,
                jt_momentum: -0.01,
              },
            ],
          },
        ],
      };

      query.mockResolvedValueOnce(mockSectorAnalysis);

      const response = await request(app).get("/sectors/analysis").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          timeframe: "daily",
          summary: expect.objectContaining({
            total_sectors: expect.any(Number),
            total_stocks_analyzed: expect.any(Number),
            avg_market_return: expect.any(String),
            bullish_sectors: expect.any(Number),
            bearish_sectors: expect.any(Number),
            neutral_sectors: expect.any(Number),
          }),
          sectors: expect.arrayContaining([
            expect.objectContaining({
              sector: "Technology",
              industry: expect.any(String),
              metrics: expect.objectContaining({
                stock_count: expect.any(Number),
                priced_stocks: expect.any(Number),
                avg_price: expect.any(String),
                performance: expect.objectContaining({
                  daily_change: expect.any(String),
                  weekly_change: expect.any(String),
                  monthly_change: expect.any(String),
                  performance_rank: expect.any(Number),
                }),
              }),
            }),
            expect.objectContaining({
              sector: "Healthcare",
              industry: expect.any(String),
              metrics: expect.objectContaining({
                stock_count: expect.any(Number),
                priced_stocks: expect.any(Number),
              }),
            }),
          ]),
        }),
        timestamp: expect.any(String),
      });

      expect(query).toHaveBeenCalledTimes(1);
    });

    test("should handle timeframe parameter validation", async () => {
      const response = await request(app)
        .get("/sectors/analysis")
        .query({ timeframe: "invalid" })
        .expect(400);

      expect(response.body).toEqual({
        success: false,
        error: "Invalid timeframe. Must be daily, weekly, or monthly.",
      });

      expect(query).not.toHaveBeenCalled();
    });

    test("should accept valid timeframes", async () => {
      const mockData = { rows: [] };
      query.mockResolvedValueOnce(mockData);

      const response = await request(app)
        .get("/sectors/analysis")
        .query({ timeframe: "weekly" })
        .expect(200);

      expect(response.body.data.timeframe).toBe("weekly");
      expect(query).toHaveBeenCalledTimes(1);
    });

    test("should handle database errors", async () => {
      query.mockRejectedValueOnce(new Error("Database connection failed"));

      const response = await request(app).get("/sectors/analysis").expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Database connection failed",
      });
    });
  });

  describe("GET /sectors/list", () => {
    test("should return list of available sectors", async () => {
      const mockSectorsList = {
        rows: [
          {
            sector: "Technology",
            industry: "Software",
            company_count: 145,
            active_companies: 140,
          },
          {
            sector: "Healthcare",
            industry: "Drug Manufacturers",
            company_count: 98,
            active_companies: 92,
          },
          {
            sector: "Financial Services",
            industry: "Banks",
            company_count: 87,
            active_companies: 82,
          },
          {
            sector: "Consumer Discretionary",
            industry: "Restaurants",
            company_count: 76,
            active_companies: 71,
          },
          {
            sector: "Industrials",
            industry: "Aerospace",
            company_count: 65,
            active_companies: 60,
          },
        ],
      };

      query.mockResolvedValueOnce(mockSectorsList);

      const response = await request(app).get("/sectors/list").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          sectors: expect.arrayContaining([
            expect.objectContaining({
              sector: "Technology",
              industries: expect.any(Array),
              total_companies: expect.any(Number),
              active_companies: expect.any(Number),
            }),
            expect.objectContaining({
              sector: "Healthcare",
              industries: expect.any(Array),
              total_companies: expect.any(Number),
              active_companies: expect.any(Number),
            }),
          ]),
          summary: expect.objectContaining({
            total_sectors: expect.any(Number),
            total_industries: expect.any(Number),
            total_companies: expect.any(Number),
            active_companies: expect.any(Number),
          }),
        }),
        timestamp: expect.any(String),
      });

      expect(query).toHaveBeenCalledTimes(1);
    });

    test("should handle empty sector list", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app).get("/sectors/list").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          sectors: [],
          summary: expect.objectContaining({
            total_sectors: 0,
            total_industries: 0,
            total_companies: 0,
            active_companies: 0,
          }),
        }),
        timestamp: expect.any(String),
      });
    });

    test("should handle database errors for sector list", async () => {
      query.mockRejectedValueOnce(new Error("Database query failed"));

      const response = await request(app).get("/sectors/list").expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Database query failed",
      });
    });
  });

  describe("GET /sectors/:sector/details", () => {
    test("should return detailed sector information", async () => {
      const mockSectorDetails = {
        rows: [
          {
            ticker: "AAPL",
            short_name: "Apple Inc.",
            long_name: "Apple Inc.",
            industry: "Consumer Electronics",
            market: "NASDAQ",
            country: "United States",
            current_price: 175.25,
            volume: 45000000,
            price_date: "2024-01-15",
            daily_change: 3.25,
            weekly_change: 8.15,
            monthly_change: 12.5,
            rsi: 65.2,
            momentum: 0.15,
            macd: 0.025,
            macd_signal: 0.02,
            sma_20: 170.5,
            sma_50: 165.8,
            jt_momentum_12_1: 0.12,
            momentum_3m: 0.08,
            momentum_6m: 0.06,
            risk_adjusted_momentum: 0.1,
            momentum_strength: 85.5,
            dollar_volume: 7875000000,
            trend: "bullish",
            rsi_signal: "neutral",
            macd_signal_type: "bullish",
          },
          {
            ticker: "MSFT",
            short_name: "Microsoft Corporation",
            long_name: "Microsoft Corporation",
            industry: "Software Infrastructure",
            market: "NASDAQ",
            country: "United States",
            current_price: 378.5,
            volume: 28000000,
            price_date: "2024-01-15",
            daily_change: 2.8,
            weekly_change: 6.9,
            monthly_change: 9.75,
            rsi: 58.1,
            momentum: 0.08,
            macd: 0.015,
            macd_signal: 0.012,
            sma_20: 375.2,
            sma_50: 370.15,
            jt_momentum_12_1: 0.06,
            momentum_3m: 0.04,
            momentum_6m: 0.03,
            risk_adjusted_momentum: 0.05,
            momentum_strength: 72.3,
            dollar_volume: 10598000000,
            trend: "neutral",
            rsi_signal: "neutral",
            macd_signal_type: "bullish",
          },
        ],
      };

      query.mockResolvedValueOnce(mockSectorDetails);

      const response = await request(app)
        .get("/sectors/Technology/details")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          sector: "Technology",
          summary: expect.objectContaining({
            stock_count: expect.any(Number),
            avg_monthly_return: expect.any(String),
            total_volume: expect.any(Number),
            avg_jt_momentum: expect.any(String),
            trend_distribution: expect.any(Object),
            industry_count: expect.any(Number),
          }),
          industries: expect.any(Array),
          stocks: expect.arrayContaining([
            expect.objectContaining({
              symbol: "AAPL",
              name: "Apple Inc.",
              industry: "Consumer Electronics",
              current_price: expect.any(String),
              volume: expect.any(Number),
              performance: expect.objectContaining({
                daily_change: expect.any(String),
                weekly_change: expect.any(String),
                monthly_change: expect.any(String),
              }),
              technicals: expect.objectContaining({
                rsi: expect.any(String),
                momentum: expect.any(String),
                macd: expect.any(String),
                trend: expect.any(String),
                rsi_signal: expect.any(String),
                macd_signal: expect.any(String),
              }),
              momentum: expect.objectContaining({
                jt_momentum_12_1: expect.any(String),
                momentum_3m: expect.any(String),
                momentum_6m: expect.any(String),
                risk_adjusted: expect.any(String),
                strength: expect.any(String),
              }),
            }),
            expect.objectContaining({
              symbol: "MSFT",
              name: "Microsoft Corporation",
              industry: "Software Infrastructure",
            }),
          ]),
        },
        timestamp: expect.any(String),
      });

      expect(query).toHaveBeenCalledTimes(1);
      expect(query.mock.calls[0][1]).toContain("Technology");
    });

    test("should handle non-existent sector", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/sectors/NonExistentSector/details")
        .expect(404);

      expect(response.body).toEqual({
        success: false,
        error:
          "Sector 'NonExistentSector' not found or has no current price data",
      });
    });

    test("should handle database errors for sector details", async () => {
      query.mockRejectedValueOnce(new Error("Database connection failed"));

      const response = await request(app)
        .get("/sectors/Technology/details")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Database connection failed",
      });
    });

    test("should handle URL encoded sector names", async () => {
      const mockData = { rows: [] };
      query.mockResolvedValueOnce(mockData);

      const _response = await request(app)
        .get("/sectors/Consumer%20Discretionary/details")
        .expect(404); // Will be 404 because rows is empty

      expect(query.mock.calls[0][1]).toContain("Consumer Discretionary");
    });
  });
});
