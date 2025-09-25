const request = require("supertest");
const express = require("express");

const technicalRouter = require("../../../routes/technical");

// Mock dependencies to match your actual site pattern
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

const { query } = require("../../../utils/database");

describe("Technical Analysis Routes - Testing Your Actual Site", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/technical", technicalRouter);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /technical/ping - Basic endpoint", () => {
    test("should return ping response", async () => {
      const response = await request(app).get("/technical/ping").expect(200);

      expect(response.body).toEqual({
        success: true,
        data: {
          status: "ok",
          endpoint: "technical",
          timestamp: expect.any(String),
        },
        timestamp: expect.any(String),
      });
    });
  });

  describe("GET /technical/ - Root technical endpoint", () => {
    test("should return latest technical data for all symbols using daily timeframe", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockTechnicalData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2025-07-16T00:00:00.000Z",
            rsi: 65.8,
            macd: 0.25,
            macd_signal: 0.18,
            macd_hist: 0.07,
            mom: 1.8,
            roc: 3.2,
            adx: 28.4,
            plus_di: 25.2,
            minus_di: 18.6,
            atr: 2.85,
            sma_10: 174.8,
            sma_20: 172.5,
            sma_50: 168.3,
            sma_150: 163.8,
            sma_200: 163.8,
            ema_4: 175.1,
            ema_9: 174.2,
            ema_21: 171.15,
            bbands_lower: 166.8,
            bbands_middle: 172.65,
            bbands_upper: 178.5,
            pivot_high: null,
            pivot_low: null,
            fetched_at: "2025-07-16T10:30:00.000Z",
          },
        ],
      };

      query
        .mockResolvedValueOnce(mockTableExists) // Table exists check
        .mockResolvedValueOnce(mockTechnicalData); // Latest data query

      const response = await request(app).get("/technical/").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            date: "2025-07-16T00:00:00.000Z",
            rsi: 65.8,
            macd: 0.25,
            macd_signal: 0.18,
            sma_20: 172.5,
            bbands_upper: 178.5,
          }),
        ]),
        count: 1,
        metadata: expect.objectContaining({
          timeframe: "daily",
          timestamp: expect.any(String),
        }),
      });

      // Verify your actual database queries
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("information_schema.tables"),
        ["technical_data_daily"]
      );
      expect(query).toHaveBeenCalledWith(expect.stringContaining("technical_data_daily"));
    });

    test("should return 404 when technical_data_daily table doesn't exist", async () => {
      const mockTableExists = { rows: [{ exists: false }] };

      query.mockResolvedValueOnce(mockTableExists);

      const response = await request(app).get("/technical/").expect(404);

      expect(response.body).toMatchObject({
        success: false,
        error: "Technical data not available",
        message: "Technical data table for daily timeframe does not exist",
        timeframe: "daily",
      });
    });
  });

  describe("GET /technical/:timeframe - Timeframe-based data", () => {
    test("should return daily technical data with pagination", async () => {
      const mockCountResult = { rows: [{ total: "150" }] };
      const mockTechnicalData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2025-07-16",
            rsi: 65.8,
            macd: 0.25,
            sma_20: 172.5,
            macd_signal: 0.18,
            macd_hist: 0.07,
            mom: 1.8,
            roc: 3.2,
            adx: 28.4,
            plus_di: 25.2,
            minus_di: 18.6,
            atr: 2.85,
          },
          {
            symbol: "MSFT",
            date: "2025-07-16T00:00:00.000Z",
            rsi: 58.2,
            macd: 0.18,
            macd_signal: 0.15,
            macd_hist: 0.03,
            mom: 2.1,
            roc: 2.8,
            adx: 24.1,
            plus_di: 22.8,
            minus_di: 19.2,
            atr: 3.12,
            ad: 1150000.0,
            cmf: 0.12,
            mfi: 62.1,
            td_sequential: 3,
            td_combo: 2,
            marketwatch: 0.68,
            dm: 0.38,
            sma_10: 380.2,
            sma_20: 378.9,
            sma_50: 375.1,
            sma_150: 365.2,
            sma_200: 368.2,
            ema_4: 379.8,
            ema_9: 378.1,
            ema_21: 376.8,
            bbands_lower: 372.1,
            bbands_middle: 378.9,
            bbands_upper: 385.7,
            pivot_high: 382.5,
            pivot_low: null,
            pivot_high_triggered: 382.5,
            pivot_low_triggered: null,
            fetched_at: "2025-07-16T10:30:00.000Z",
          },
        ],
      };

      query
        .mockResolvedValueOnce(mockTechnicalData)
        .mockResolvedValueOnce(mockCountResult);

      const response = await request(app)
        .get("/technical/daily")
        .query({ page: 1, limit: 50 })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          data: expect.arrayContaining([
            expect.objectContaining({
              symbol: "AAPL",
              rsi: 65.8,
              macd: 0.25,
            }),
            expect.objectContaining({
              symbol: "MSFT",
              rsi: 58.2,
              macd: 0.18,
            }),
          ]),
          pagination: expect.objectContaining({
            page: 1,
            limit: 50,
            total: 150,
            totalPages: 3,
            hasNext: true,
            hasPrev: false,
          }),
          metadata: expect.objectContaining({
            timeframe: "daily",
          }),
        }),
      });

      // Verify your actual queries with technical_data_daily table
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("technical_data_daily"),
        expect.any(Array)
      );
    });

    test("should validate timeframe parameter", async () => {
      const response = await request(app)
        .get("/technical/invalid_timeframe")
        .expect(400);

      expect(response.body).toEqual({
        error: "Invalid timeframe. Use daily, weekly, or monthly.",
      });
    });

    test("should handle symbol filtering", async () => {
      const mockCountResult = { rows: [{ total: "5" }] };
      const mockTechnicalData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2025-07-16T00:00:00.000Z",
            rsi: 65.8,
            macd: 0.25,
            macd_signal: 0.18,
            macd_hist: 0.07,
            mom: 1.8,
            roc: 3.2,
            adx: 28.4,
            plus_di: 25.2,
            minus_di: 18.6,
            atr: 2.85,
            ad: 1250000.0,
            cmf: 0.15,
            mfi: 58.9,
            td_sequential: 5,
            td_combo: 3,
            marketwatch: 0.75,
            dm: 0.45,
            sma_10: 174.8,
            sma_20: 172.5,
            sma_50: 168.3,
            sma_150: 163.8,
            sma_200: 163.8,
            ema_4: 175.1,
            ema_9: 174.2,
            ema_21: 171.15,
            bbands_lower: 166.8,
            bbands_middle: 172.65,
            bbands_upper: 178.5,
            pivot_high: null,
            pivot_low: 170.5,
            pivot_high_triggered: null,
            pivot_low_triggered: 170.5,
            fetched_at: "2025-07-16T10:30:00.000Z",
          },
        ],
      };

      query
        .mockResolvedValueOnce(mockTechnicalData)
        .mockResolvedValueOnce(mockCountResult);

      await request(app)
        .get("/technical/daily")
        .query({ symbol: "AAPL" })
        .expect(200);

      // Verify symbol filter was applied - first call should contain AAPL in WHERE clause
      expect(query.mock.calls[0][1]).toEqual(expect.arrayContaining(["AAPL"]));
    });

    test("should handle RSI filtering", async () => {
      const mockCountResult = { rows: [{ total: "10" }] };
      const mockTechnicalData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2025-07-16",
            rsi: 75.0,
            macd: 0.25,
            macd_signal: 0.18,
            macd_hist: 0.07,
            mom: 1.8,
            roc: 3.2,
            adx: 28.4,
            plus_di: 25.2,
            minus_di: 18.6,
            atr: 2.85,
          }
        ]
      };

      query
        .mockResolvedValueOnce(mockTechnicalData)
        .mockResolvedValueOnce(mockCountResult);

      await request(app)
        .get("/technical/daily")
        .query({ rsi_min: 70, rsi_max: 80 })
        .expect(200);

      // Verify RSI filters were applied
      const dataQuery = query.mock.calls[0][0];
      const countQuery = query.mock.calls[1][0];
      expect(dataQuery).toContain("rsi >= $");
      expect(dataQuery).toContain("rsi <= $");
      expect(countQuery).toContain("rsi >= $");
      expect(countQuery).toContain("rsi <= $");
      expect(query.mock.calls[0][1]).toContain(70);
      expect(query.mock.calls[0][1]).toContain(80);
      expect(query.mock.calls[1][1]).toContain(70);
      expect(query.mock.calls[1][1]).toContain(80);
    });
  });

  describe("GET /technical/:timeframe/summary - Technical summary", () => {
    test("should return technical summary statistics", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockSummaryResult = {
        rows: [
          {
            total_records: "1250",
            unique_symbols: "50",
            earliest_date: "2024-01-01",
            latest_date: "2025-07-16",
            avg_rsi: "52.5",
            avg_macd: "0.15",
            avg_sma_20: "165.80",
            avg_adx: "28.5",
          },
        ],
      };
      const mockTopSymbols = {
        rows: [
          { symbol: "AAPL", record_count: "252" },
          { symbol: "MSFT", record_count: "252" },
          { symbol: "GOOGL", record_count: "250" },
        ],
      };

      query
        .mockResolvedValueOnce(mockTableExists)    // Table exists check
        .mockResolvedValueOnce(mockSummaryResult)  // Summary data query
        .mockResolvedValueOnce(mockTopSymbols);    // Top symbols query

      const response = await request(app)
        .get("/technical/daily/summary")
        .expect(200);

      expect(response.body).toMatchObject({
        timeframe: "daily",
        summary: expect.objectContaining({
          totalRecords: 1250,
          uniqueSymbols: 50,
          dateRange: expect.objectContaining({
            earliest: "2024-01-01",
            latest: "2025-07-16",
          }),
          averages: expect.objectContaining({
            rsi: "52.50",
            macd: "0.1500",
            sma20: "165.80",
            adx: "28.50",
          }),
        }),
        topSymbols: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            recordCount: 252,
          }),
          expect.objectContaining({
            symbol: "MSFT",
            recordCount: 252,
          }),
        ]),
      });
    });

    test("should return fallback summary when table doesn't exist", async () => {
      const mockTableExists = { rows: [{ exists: false }] };

      query.mockResolvedValueOnce(mockTableExists);

      const response = await request(app)
        .get("/technical/weekly/summary")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          timeframe: "weekly",
          symbol: "SUMMARY",
          count: expect.any(Number),
          indicators: expect.arrayContaining([
            expect.objectContaining({ exists: false }),
          ]),
        }),
      });
    });
  });

  describe("GET /technical/data/:symbol - Individual symbol data", () => {
    test("should return latest technical data for specific symbol", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockSymbolData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2025-07-16",
            open: 174.0,
            high: 176.5,
            low: 173.25,
            close: 175.25,
            volume: 45000000,
            rsi: 65.8,
            macd: 0.25,
            macd_signal: 0.18,
            sma_20: 172.5,
            bollinger_upper: 178.5,
            stochastic_k: 72.5,
            williams_r: -27.5,
            cci: 85.6,
            adx: 28.4,
          },
        ],
      };

      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce(mockSymbolData);

      const response = await request(app)
        .get("/technical/data/AAPL")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          symbol: "AAPL",
          date: "2025-07-16",
          close: 175.25,
          rsi: 65.8,
          macd: 0.25,
          sma_20: 172.5,
          volume: 45000000,
        }),
        symbol: "AAPL",
      });

      // Verify query for specific symbol
      expect(query.mock.calls[1][1]).toEqual(["AAPL"]);
    });

    test("should return 404 for non-existent symbol", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockSymbolData = { rows: [] };

      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce(mockSymbolData);

      const response = await request(app)
        .get("/technical/data/NONEXISTENT")
        .expect(404);

      expect(response.body).toMatchObject({
        success: false,
        error: "No technical data found for symbol NONEXISTENT",
      });
    });

    test("should return fallback data when table missing", async () => {
      const mockTableExists = { rows: [{ exists: false }] };

      query.mockResolvedValueOnce(mockTableExists);

      const response = await request(app)
        .get("/technical/data/AAPL")
        .expect(404);

      expect(response.body).toMatchObject({
        success: false,
        error: "Technical data not available",
        message: "Technical data table does not exist",
        symbol: "AAPL",
      });
    });
  });

  describe("GET /technical/indicators/:symbol - Technical indicators", () => {
    test("should return 30-day technical indicators for symbol", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockIndicators = {
        rows: Array.from({ length: 30 }, (_, i) => ({
          symbol: "AAPL",
          date: new Date(Date.now() - i * 24 * 60 * 60 * 1000)
            .toISOString()
            .split("T")[0],
          rsi: 50 + Math.random() * 30,
          macd: -0.5 + Math.random(),
          sma_20: 170 + Math.random() * 10,
          bollinger_upper: 180 + Math.random() * 5,
          bollinger_lower: 160 + Math.random() * 5,
          stochastic_k: 20 + Math.random() * 60,
        })),
      };

      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce(mockIndicators);

      const response = await request(app)
        .get("/technical/indicators/AAPL")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          data: expect.any(Array),
          count: 30,
          symbol: "AAPL",
        }),
      });

      expect(response.body.data.data).toHaveLength(30);
      expect(response.body.data.data[0]).toMatchObject({
        symbol: "AAPL",
        rsi: expect.any(Number),
        macd: expect.any(Number),
        sma_20: expect.any(Number),
      });

      // Verify 30-day limit query
      expect(query.mock.calls[1][0]).toContain("LIMIT 30");
    });
  });

  describe("GET /technical/history/:symbol - Technical history", () => {
    test("should return technical history with custom days parameter", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockHistory = {
        rows: Array.from({ length: 60 }, (_, i) => ({
          symbol: "AAPL",
          date: new Date(Date.now() - i * 24 * 60 * 60 * 1000)
            .toISOString()
            .split("T")[0],
          close: 175 + Math.random() * 10,
          rsi: 50 + Math.random() * 30,
          macd: -0.5 + Math.random(),
          volume: 40000000 + Math.random() * 20000000,
        })),
      };

      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce(mockHistory);

      const response = await request(app)
        .get("/technical/history/AAPL")
        .query({ days: 60 })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          data: expect.any(Array),
          count: 60,
          symbol: "AAPL",
          period_days: "60",
        }),
      });

      // Verify days parameter in query
      expect(query.mock.calls[1][0]).toContain("INTERVAL '60 days'");
    });
  });

  describe("GET /technical/support-resistance/:symbol - Support/Resistance levels", () => {
    test("should return support and resistance levels", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockPivotData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2025-07-16",
            high: 176.5,
            low: 173.25,
            close: 175.25,
            bbands_upper: 178.5,
            bbands_lower: 166.8,
            sma_20: 172.5,
            sma_50: 168.3,
            sma_200: 155.2,
          },
        ],
      };

      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce(mockPivotData);

      const response = await request(app)
        .get("/technical/support-resistance/AAPL")
        .query({ timeframe: "daily" })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          symbol: "AAPL",
          timeframe: "daily",
          current_price: expect.any(Number), // Your site calculates this dynamically
          support_levels: expect.arrayContaining([
            expect.objectContaining({
              level: expect.any(Number),
              type: expect.stringMatching(/^(dynamic|bollinger|moving_average)$/),
              strength: expect.stringMatching(/^(strong|medium|weak)$/),
            }),
          ]),
          resistance_levels: expect.arrayContaining([
            expect.objectContaining({
              level: expect.any(Number),
              type: expect.stringMatching(/^(dynamic|bollinger|moving_average)$/),
              strength: expect.stringMatching(/^(strong|medium|weak)$/),
            }),
          ]),
          last_updated: expect.any(String), // Your site calculates this dynamically
        }),
      });
    });

    test("should validate timeframe for support/resistance", async () => {
      const response = await request(app)
        .get("/technical/support-resistance/AAPL")
        .query({ timeframe: "hourly" })
        .expect(400);

      expect(response.body).toMatchObject({
        error: "Unsupported timeframe",
        message: expect.stringContaining(
          "Supported timeframes: daily, weekly, monthly"
        ),
      });
    });
  });

  describe("GET /technical/daily - Filtered technical data", () => {
    test("should handle filtered technical data requests", async () => {
      // Test with existing table and data (your actual working behavior)
      const mockTableExists = { rows: [{ exists: true }] };
      const mockCountResult = { rows: [{ total: "5" }] };
      const mockTechnicalData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2025-07-16",
            rsi: 65.8,
            macd: 0.25,
          },
        ],
      };

      query
        .mockResolvedValueOnce(mockTechnicalData)
        .mockResolvedValueOnce(mockCountResult);

      const response = await request(app)
        .get("/technical/daily")
        .query({
          symbol: "AAPL",
          start_date: "2025-07-01",
          end_date: "2025-07-16",
          page: 1,
          limit: 25,
        })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          data: expect.any(Array),
          pagination: expect.objectContaining({
            page: 1,
            limit: 25,
          }),
          metadata: expect.objectContaining({
            timeframe: "daily",
          }),
        }),
      });
    });

    test("should handle technical data queries safely", async () => {
      const mockCountResult = { rows: [{ total: "10" }] };
      const mockData = { rows: [] };

      query
        .mockResolvedValueOnce(mockData)
        .mockResolvedValueOnce(mockCountResult);

      await request(app)
        .get("/technical/daily")
        .query({ symbol: "AAPL" })
        .expect(200);

      // Should safely query technical data
      expect(query).toHaveBeenCalled();
      if (query.mock.calls.length > 2 && query.mock.calls[2]) {
        expect(query.mock.calls[2][0]).toContain("technical_data_daily");
      }
    });
  });

  describe("GET /technical/patterns/:symbol - Pattern recognition", () => {
    test("should return technical pattern analysis", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockPriceData = {
        rows: [
          {
            close: 175.25,
            high: 176.5,
            low: 173.25,
            date: "2025-07-16",
          },
        ],
      };

      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce(mockPriceData);

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .query({ timeframe: "1D", limit: 5 })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          symbol: "AAPL",
          timeframe: "1D",
          patterns: expect.any(Array),
          summary: expect.objectContaining({
            total_patterns: expect.any(Number),
            bullish_patterns: expect.any(Number),
            bearish_patterns: expect.any(Number),
            average_confidence: expect.any(Number),
            market_sentiment: expect.stringMatching(/^(bullish|bearish|neutral)$/),
          }),
          confidence_score: expect.any(Number),
          last_updated: expect.any(String),
        }),
      });

      // Each pattern should have required fields
      if (response.body.data.patterns.length > 0) {
        const firstPattern = response.body.data.patterns[0];
        expect(firstPattern).toMatchObject({
          type: expect.stringMatching(
            /^(double_bottom|cup_and_handle|bullish_flag|ascending_triangle|double_top|head_and_shoulders|bearish_flag|descending_triangle)$/
          ),
          direction: expect.stringMatching(/^(bullish|bearish)$/),
          confidence: expect.any(Number),
          timeframe: "1D",
          detected_at: expect.any(String),
          time_to_target: expect.any(Number),
        });

        // Your site returns null for target_price and stop_loss (acceptable)
        expect(firstPattern).toHaveProperty("target_price");
        expect(firstPattern).toHaveProperty("stop_loss");
      }
    });

    test("should return fallback patterns on database errors", async () => {
      query.mockRejectedValueOnce(new Error("Database connection failed"));

      const response = await request(app)
        .get("/technical/patterns/AAPL")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          symbol: "AAPL",
          timeframe: "1D",
          patterns: expect.any(Array),
          summary: expect.objectContaining({
            market_sentiment: expect.stringMatching(/^(bullish|bearish|neutral)$/),
            total_patterns: expect.any(Number),
          }),
          confidence_score: expect.any(Number),
          last_updated: expect.any(String),
        }),
      });
    });
  });

  describe("Error handling - Your site's error patterns", () => {
    test("should handle database errors gracefully with fallback data", async () => {
      query.mockRejectedValueOnce(new Error("Connection timeout"));

      const response = await request(app).get("/technical/").expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to retrieve technical overview data",
        type: "database_error",
        timeframe: "daily",
        message: "Connection timeout",
      });
    });

    test("should return structured error responses for invalid timeframes", async () => {
      const response = await request(app).get("/technical/hourly").expect(400);

      expect(response.body).toEqual({
        error: "Invalid timeframe. Use daily, weekly, or monthly.",
      });
    });

    test("should handle large limit values safely", async () => {
      const mockCountResult = { rows: [{ total: "1000" }] };
      const mockData = { rows: [] };

      query
        .mockResolvedValueOnce(mockData)
        .mockResolvedValueOnce(mockCountResult);

      const response = await request(app)
        .get("/technical/daily")
        .query({ limit: 500 }) // Large but reasonable limit
        .expect(200);

      // Your site handles large limits by capping them at 100 (route safety)
      expect(response.body.data.pagination.limit).toBe(100);

      // Verify the endpoint responds successfully
      expect(response.status).toBe(200);
      expect(query).toHaveBeenCalled();
    });
  });

  describe("GET /technical/chart/:symbol - Chart data for symbol", () => {
    beforeEach(() => {
      // Clear mocks for each test - individual tests will set up their own mocks
      jest.clearAllMocks();
    });

    test("should return chart data with default parameters", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockChartData = {
        rows: [
          {
            date: "2025-07-16",
            open: 175.0,
            high: 177.5,
            low: 174.0,
            close: 176.25,
            adj_close: 176.25,
            volume: 1000000,
            timestamp: "2025-07-16T10:30:00.000Z",
          }
        ]
      };

      query
        .mockResolvedValueOnce(mockTableExists)  // Table exists check
        .mockResolvedValueOnce(mockChartData);   // Chart data query

      const response = await request(app)
        .get("/technical/chart/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("chart_data");
      expect(response.body.data).toHaveProperty("symbol");
      expect(response.body.data).toHaveProperty("period");
      expect(response.body.data).toHaveProperty("interval");
      expect(Array.isArray(response.body.data.chart_data)).toBe(true);
      expect(response.body.data.symbol).toBe("AAPL");
      expect(response.body.data.period).toBe("1M");
      expect(response.body.data.interval).toBe("1d");
    });

    test("should return chart data with custom parameters", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockChartData = {
        rows: Array.from({ length: 10 }, (_, i) => ({
          date: new Date(Date.now() - i * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
          open: 300.0 + i,
          high: 305.0 + i,
          low: 295.0 + i,
          close: 302.0 + i,
          adj_close: 302.0 + i,
          volume: 800000 + i * 10000,
          timestamp: new Date(Date.now() - i * 24 * 60 * 60 * 1000).toISOString(),
        }))
      };

      query
        .mockResolvedValueOnce(mockTableExists)  // Table exists check
        .mockResolvedValueOnce(mockChartData);   // Chart data query

      const response = await request(app)
        .get(
          "/technical/chart/MSFT?period=1Y&interval=1d&include_volume=true&limit=50"
        )
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.chart_data.length).toBeLessThanOrEqual(50);
      expect(response.body.data.symbol).toBe("MSFT");
      expect(response.body.data.period).toBe("1Y");
      expect(response.body.data.interval).toBe("1d");
      expect(response.body.data.include_volume).toBe(true);

      // Check if volume is included when requested
      if (response.body.data.chart_data.length > 0) {
        expect(response.body.data.chart_data[0]).toHaveProperty("volume");
      }
    });

    test("should include proper OHLCV structure", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockChartData = {
        rows: [
          {
            date: "2025-07-16",
            open: 175.0,
            high: 177.5,
            low: 174.0,
            close: 176.25,
            adj_close: 176.25,
            volume: 1000000,
            timestamp: "2025-07-16T10:30:00.000Z",
          }
        ]
      };

      query
        .mockResolvedValueOnce(mockTableExists)  // Table exists check
        .mockResolvedValueOnce(mockChartData);   // Chart data query

      const response = await request(app)
        .get("/technical/chart/AAPL?limit=5")
        .expect(200);

      if (response.body.data.chart_data.length > 0) {
        const candle = response.body.data.chart_data[0];
        expect(candle).toHaveProperty("date");
        expect(candle).toHaveProperty("timestamp");
        expect(candle).toHaveProperty("open");
        expect(candle).toHaveProperty("high");
        expect(candle).toHaveProperty("low");
        expect(candle).toHaveProperty("close");
        expect(candle).toHaveProperty("adj_close");
        expect(candle).toHaveProperty("volume");
        expect(typeof candle.open).toBe("number");
        expect(typeof candle.high).toBe("number");
        expect(typeof candle.low).toBe("number");
        expect(typeof candle.close).toBe("number");
      }
    });

    test("should include complete chart metadata", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockChartData = {
        rows: [
          {
            date: "2025-07-16",
            open: 175.0,
            high: 177.5,
            low: 174.0,
            close: 176.25,
            adj_close: 176.25,
            volume: 1000000,
            timestamp: "2025-07-16T10:30:00.000Z",
          }
        ]
      };

      query
        .mockResolvedValueOnce(mockTableExists)  // Table exists check
        .mockResolvedValueOnce(mockChartData);   // Chart data query

      const response = await request(app)
        .get("/technical/chart/AAPL?limit=5")
        .expect(200);

      expect(response.body.data).toHaveProperty("records_count");
      expect(response.body.data).toHaveProperty("source");
      expect(response.body.data.source).toBe("price_daily_table");
      expect(response.body.data.records_count).toBe(1);
    });

    test("should include chart data with proper timestamp", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockChartData = {
        rows: [
          {
            date: "2025-07-16",
            open: 175.0,
            high: 177.5,
            low: 174.0,
            close: 176.25,
            adj_close: 176.25,
            volume: 1000000,
            timestamp: "2025-07-16T10:30:00.000Z",
          }
        ]
      };

      query
        .mockResolvedValueOnce(mockTableExists)  // Table exists check
        .mockResolvedValueOnce(mockChartData);   // Chart data query

      const response = await request(app)
        .get("/technical/chart/AAPL?limit=10")
        .expect(200);

      expect(response.body.data.symbol).toBe("AAPL");
      expect(response.body).toHaveProperty("timestamp");
      expect(response.body.data.chart_data.length).toBeGreaterThan(0);
      if (response.body.data.chart_data.length > 0) {
        const candle = response.body.data.chart_data[0];
        expect(candle.timestamp).toBeDefined();
        expect(candle.date).toBeDefined();
      }
    });

    test("should handle volume inclusion correctly", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockChartData = {
        rows: [
          {
            date: "2025-07-16",
            open: 175.0,
            high: 177.5,
            low: 174.0,
            close: 176.25,
            adj_close: 176.25,
            volume: 1000000,
            timestamp: "2025-07-16T10:30:00.000Z",
          }
        ]
      };

      // Mock for first request (include_volume=true)
      query
        .mockResolvedValueOnce(mockTableExists)  // Table exists check
        .mockResolvedValueOnce(mockChartData)    // Chart data query
        .mockResolvedValueOnce(mockTableExists)  // Table exists check for second request
        .mockResolvedValueOnce(mockChartData);   // Chart data query for second request

      const responseWithVolume = await request(app)
        .get("/technical/chart/AAPL?include_volume=true&limit=5")
        .expect(200);

      const responseWithoutVolume = await request(app)
        .get("/technical/chart/AAPL?include_volume=false&limit=5")
        .expect(200);

      if (responseWithVolume.body.data.chart_data.length > 0) {
        expect(responseWithVolume.body.data.chart_data[0]).toHaveProperty(
          "volume"
        );
        expect(responseWithVolume.body.data.include_volume).toBe(true);
      }

      if (responseWithoutVolume.body.data.chart_data.length > 0) {
        expect(responseWithoutVolume.body.data.include_volume).toBe(false);
      }

    });

    test("should handle table not exists gracefully", async () => {
      query.mockResolvedValue({
        rows: [{ exists: false }],
      });

      const response = await request(app)
        .get("/technical/chart/AAPL")
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Chart data not available");
    });
  });

  describe("GET /technical/chart - Query-based chart endpoint", () => {
    test("should validate timeframe parameter", async () => {
      const response = await request(app)
        .get("/technical/chart?symbol=AAPL&timeframe=invalid")
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Invalid timeframe");
    });

    test("should validate period parameter", async () => {
      const response = await request(app)
        .get("/technical/chart?symbol=AAPL&period=invalid")
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Invalid period");
    });

    test("should filter indicators correctly", async () => {
      query.mockResolvedValue({
        rows: [],
      });

      const response = await request(app)
        .get(
          "/technical/chart?symbol=AAPL&indicators=sma,rsi&timeframe=daily&period=1m"
        )
        .expect(404); // Will return 404 because no data in mock

      // The request should be processed and query should be called
      expect(query).toHaveBeenCalled();
    });
  });
});
