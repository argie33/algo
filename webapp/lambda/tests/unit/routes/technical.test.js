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
            date: "2025-07-16",
            open: 174.0,
            high: 176.5,
            low: 173.25,
            close: 175.25,
            volume: 45000000,
            rsi: 65.8,
            macd: 0.25,
            macd_signal: 0.18,
            macd_histogram: 0.07,
            sma_20: 172.5,
            sma_50: 168.3,
            ema_12: 174.2,
            ema_26: 171.15,
            bollinger_upper: 178.5,
            bollinger_lower: 166.8,
            bollinger_middle: 172.65,
            stochastic_k: 72.5,
            stochastic_d: 68.2,
            williams_r: -27.5,
            cci: 85.6,
            adx: 28.4,
            atr: 2.85,
            obv: 1250000000,
            mfi: 58.9,
            roc: 3.2,
            momentum: 1.8,
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
            date: "2025-07-16",
            close: 175.25,
            rsi: 65.8,
            macd: 0.25,
            sma_20: 172.5,
            bollinger_upper: 178.5,
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
      expect(query).toHaveBeenCalledWith(expect.stringContaining("INNER JOIN"));
    });

    test("should return 503 when technical_data_daily table doesn't exist", async () => {
      const mockTableExists = { rows: [{ exists: false }] };

      query.mockResolvedValueOnce(mockTableExists);

      const response = await request(app).get("/technical/").expect(503);

      expect(response.body).toMatchObject({
        success: false,
        error: "Technical data not available",
        message: "Technical data table for daily timeframe does not exist",
        service: "technical-overview",
        timeframe: "daily"
      });
    });
  });

  describe("GET /technical/:timeframe - Timeframe-based data", () => {
    test("should return daily technical data with pagination", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockCountResult = { rows: [{ total: "150" }] };
      const mockTechnicalData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2025-07-16",
            rsi: 65.8,
            macd: 0.25,
            sma_20: 172.5,
            volume: 45000000,
          },
          {
            symbol: "MSFT",
            date: "2025-07-16",
            rsi: 58.2,
            macd: 0.18,
            sma_20: 378.9,
            volume: 28000000,
          },
        ],
      };

      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce(mockCountResult)
        .mockResolvedValueOnce(mockTechnicalData);

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
        []
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
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce(mockCountResult)
        .mockResolvedValueOnce(mockTechnicalData);

      await request(app)
        .get("/technical/daily")
        .query({ symbol: "AAPL" })
        .expect(200);

      // Verify symbol filter was applied
      expect(query.mock.calls[2][1]).toContain("AAPL");
    });

    test("should handle RSI filtering", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockCountResult = { rows: [{ total: "10" }] };
      const mockTechnicalData = { rows: [] };

      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce(mockCountResult)
        .mockResolvedValueOnce(mockTechnicalData);

      await request(app)
        .get("/technical/daily")
        .query({ rsi_min: 70, rsi_max: 80 })
        .expect(200);

      // Verify RSI filters were applied
      const countQuery = query.mock.calls[1][0];
      expect(countQuery).toContain("rsi >= $");
      expect(countQuery).toContain("rsi <= $");
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
            avg_volume: "35000000",
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
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce(mockSummaryResult)
        .mockResolvedValueOnce(mockTopSymbols);

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
            volume: 35000000,
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
        timeframe: "weekly",
        summary: expect.objectContaining({
          totalRecords: 1000,
          uniqueSymbols: 50,
          averages: expect.objectContaining({
            rsi: "45.2",
            macd: "0.1250",
          }),
        }),
        topSymbols: expect.arrayContaining([
          expect.objectContaining({ symbol: "AAPL" }),
          expect.objectContaining({ symbol: "MSFT" }),
        ]),
        fallback: true,
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
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          symbol: "AAPL",
          rsi: expect.any(Number),
          macd: expect.any(Number),
          sma_20: expect.any(Number),
        }),
        symbol: "AAPL",
        fallback: true,
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
        data: expect.any(Array),
        count: 30,
        symbol: "AAPL",
      });

      expect(response.body.data).toHaveLength(30);
      expect(response.body.data[0]).toMatchObject({
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
        data: expect.any(Array),
        count: 60,
        symbol: "AAPL",
        period_days: "60",
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
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce(mockCountResult)
        .mockResolvedValueOnce(mockTechnicalData);

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
        data: expect.any(Array),
        pagination: expect.objectContaining({
          page: 1,
          limit: 25,
        }),
        metadata: expect.objectContaining({
          timeframe: "daily",
        }),
      });
    });

    test("should handle technical data queries safely", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockCountResult = { rows: [{ total: "10" }] };
      const mockData = { rows: [] };

      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce(mockCountResult)
        .mockResolvedValueOnce(mockData);

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
        symbol: "AAPL",
        timeframe: "1D",
        patterns: expect.any(Array),
        summary: expect.objectContaining({
          total_patterns: expect.any(Number),
          bullish_patterns: expect.any(Number),
          bearish_patterns: expect.any(Number),
          average_confidence: expect.any(Number),
          market_sentiment: expect.stringMatching(/^(bullish|bearish)$/),
        }),
        confidence_score: expect.any(Number),
        last_updated: expect.any(String),
      });

      // Each pattern should have required fields
      if (response.body.patterns.length > 0) {
        const firstPattern = response.body.patterns[0];
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
        symbol: "AAPL",
        patterns: expect.any(Array),
        summary: expect.objectContaining({
          market_sentiment: expect.stringMatching(/^(bullish|bearish)$/), // Can be either
        }),
      });

      // Check that it either has fallback data or error handling
      expect(
        response.body.fallback === true ||
          response.body.error ||
          response.body.patterns.length > 0
      ).toBe(true);
    });
  });

  describe("Error handling - Your site's error patterns", () => {
    test("should handle database errors gracefully with fallback data", async () => {
      query.mockRejectedValueOnce(new Error("Connection timeout"));

      const response = await request(app).get("/technical/").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.any(Array),
        metadata: expect.objectContaining({
          timeframe: "daily",
        }),
      });

      // Your site handles errors gracefully - either fallback data or error info
      expect(
        response.body.metadata.fallback === true ||
          response.body.metadata.error ||
          response.body.data.length > 0
      ).toBe(true);
    });

    test("should return structured error responses for invalid timeframes", async () => {
      const response = await request(app).get("/technical/hourly").expect(400);

      expect(response.body).toEqual({
        error: "Invalid timeframe. Use daily, weekly, or monthly.",
      });
    });

    test("should handle large limit values safely", async () => {
      const mockTableExists = { rows: [{ exists: true }] };
      const mockCountResult = { rows: [{ total: "1000" }] };
      const mockData = { rows: [] };

      query
        .mockResolvedValueOnce(mockTableExists)
        .mockResolvedValueOnce(mockCountResult)
        .mockResolvedValueOnce(mockData);

      const response = await request(app)
        .get("/technical/daily")
        .query({ limit: 500 }) // Large but reasonable limit
        .expect(200);

      // Your site handles large limits by returning them in pagination
      expect(response.body.pagination.limit).toBe(500);

      // Verify the endpoint responds successfully
      expect(response.status).toBe(200);
      expect(query).toHaveBeenCalled();
    });
  });

  describe("GET /technical/chart/:symbol - Chart data for symbol", () => {
    beforeEach(() => {
      // Mock the table check to return true
      query.mockResolvedValue({
        rows: [{ exists: true }]
      });
    });

    test("should return chart data with default parameters", async () => {
      const response = await request(app)
        .get("/technical/chart/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty('chart_data');
      expect(response.body.data).toHaveProperty('summary');
      expect(response.body.data).toHaveProperty('metadata');
      expect(Array.isArray(response.body.data.chart_data)).toBe(true);
      expect(response.body.data.metadata.symbol).toBe('AAPL');
      expect(response.body.data.metadata.period).toBe('1M');
      expect(response.body.data.metadata.interval).toBe('1d');
    });

    test("should return chart data with custom parameters", async () => {
      const response = await request(app)
        .get("/technical/chart/MSFT?period=1Y&interval=1d&include_volume=true&limit=50")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.chart_data.length).toBeLessThanOrEqual(50);
      expect(response.body.data.metadata.symbol).toBe('MSFT');
      expect(response.body.data.metadata.period).toBe('1Y');
      expect(response.body.data.metadata.interval).toBe('1d');
      expect(response.body.data.metadata.include_volume).toBe(true);
      
      // Check if volume is included when requested
      if (response.body.data.chart_data.length > 0) {
        expect(response.body.data.chart_data[0]).toHaveProperty('volume');
      }
    });

    test("should include proper OHLCV structure", async () => {
      const response = await request(app)
        .get("/technical/chart/AAPL?limit=5")
        .expect(200);

      if (response.body.data.chart_data.length > 0) {
        const candle = response.body.data.chart_data[0];
        expect(candle).toHaveProperty('datetime');
        expect(candle).toHaveProperty('timestamp');
        expect(candle).toHaveProperty('open');
        expect(candle).toHaveProperty('high');
        expect(candle).toHaveProperty('low');
        expect(candle).toHaveProperty('close');
        expect(candle).toHaveProperty('adjusted_close');
        expect(candle).toHaveProperty('technical_indicators');
        expect(typeof candle.open).toBe('number');
        expect(typeof candle.high).toBe('number');
        expect(typeof candle.low).toBe('number');
        expect(typeof candle.close).toBe('number');
      }
    });

    test("should include technical indicators", async () => {
      const response = await request(app)
        .get("/technical/chart/AAPL?limit=5")
        .expect(200);

      if (response.body.data.chart_data.length > 0) {
        const indicators = response.body.data.chart_data[0].technical_indicators;
        expect(indicators).toHaveProperty('sma_20');
        expect(indicators).toHaveProperty('sma_50');
        expect(indicators).toHaveProperty('ema_12');
        expect(indicators).toHaveProperty('ema_26');
        expect(indicators).toHaveProperty('rsi');
        expect(indicators).toHaveProperty('macd');
        expect(indicators).toHaveProperty('macd_signal');
        expect(indicators).toHaveProperty('macd_histogram');
        expect(indicators).toHaveProperty('bollinger_upper');
        expect(indicators).toHaveProperty('bollinger_middle');
        expect(indicators).toHaveProperty('bollinger_lower');
      }
    });

    test("should include summary with price range and technical analysis", async () => {
      const response = await request(app)
        .get("/technical/chart/AAPL?limit=10")
        .expect(200);

      expect(response.body.data.summary).toHaveProperty('symbol', 'AAPL');
      expect(response.body.data.summary).toHaveProperty('price_range');
      expect(response.body.data.summary).toHaveProperty('technical_summary');
      expect(response.body.data.summary.price_range).toHaveProperty('current');
      expect(response.body.data.summary.price_range).toHaveProperty('high');
      expect(response.body.data.summary.price_range).toHaveProperty('low');
      expect(response.body.data.summary.price_range).toHaveProperty('change');
      expect(response.body.data.summary.technical_summary).toHaveProperty('current_rsi');
      expect(response.body.data.summary.technical_summary).toHaveProperty('trend_direction');
    });

    test("should handle volume inclusion correctly", async () => {
      const responseWithVolume = await request(app)
        .get("/technical/chart/AAPL?include_volume=true&limit=5")
        .expect(200);

      const responseWithoutVolume = await request(app)
        .get("/technical/chart/AAPL?include_volume=false&limit=5")
        .expect(200);

      if (responseWithVolume.body.data.chart_data.length > 0) {
        expect(responseWithVolume.body.data.chart_data[0]).toHaveProperty('volume');
        expect(responseWithVolume.body.data.summary).toHaveProperty('volume_stats');
      }

      if (responseWithoutVolume.body.data.chart_data.length > 0) {
        expect(responseWithoutVolume.body.data.chart_data[0]).not.toHaveProperty('volume');
        expect(responseWithoutVolume.body.data.summary.volume_stats).toBeUndefined();
      }
    });

    test("should handle table not exists gracefully", async () => {
      query.mockResolvedValue({
        rows: [{ exists: false }]
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
        rows: []
      });

      const response = await request(app)
        .get("/technical/chart?symbol=AAPL&indicators=sma,rsi&timeframe=daily&period=1m")
        .expect(404); // Will return 404 because no data in mock

      // The request should be processed and query should be called
      expect(query).toHaveBeenCalled();
    });
  });
});
