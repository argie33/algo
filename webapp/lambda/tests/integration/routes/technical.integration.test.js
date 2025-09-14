const request = require("supertest");
const express = require("express");

// Mock dependencies
jest.mock("../../../utils/database");

const { query } = require("../../../utils/database");

// Mock response formatter middleware
const mockResponseFormatter = (req, res, next) => {
  res.success = (data) => res.status(200).json({ success: true, ...data });
  res.error = (message, statusCode = 500) => res.status(statusCode).json({ success: false, error: message });
  next();
};

// Import route after mocks are set up
const technicalRouter = require("../../../routes/technical");

// Create Express app for testing
const app = express();
app.use(express.json());
app.use(mockResponseFormatter);
app.use("/api/technical", technicalRouter);

describe("Technical Router", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("GET /ping", () => {
    test("should return ping response", async () => {
      const response = await request(app)
        .get("/api/technical/ping")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.status).toBe("ok");
      expect(response.body.endpoint).toBe("technical");
      expect(response.body.timestamp).toBeDefined();
    });
  });

  describe("GET /daily/:symbol", () => {
    test("should return daily technical data for valid symbol", async () => {
      const mockTechnicalData = [
        {
          symbol: "AAPL",
          date: "2024-01-03",
          rsi: 55.25,
          sma_20: 175.50,
          sma_50: 172.30,
          sma_200: 168.75,
          ema_12: 176.20,
          ema_26: 174.80,
          macd: 1.40,
          macd_signal: 1.15,
          macd_histogram: 0.25,
          bollinger_upper: 180.25,
          bollinger_middle: 175.50,
          bollinger_lower: 170.75,
          stochastic_k: 65.8,
          stochastic_d: 62.3,
          williams_r: -25.4,
          volume: 45000000,
          price: 175.50
        },
        {
          symbol: "AAPL",
          date: "2024-01-02",
          rsi: 52.80,
          sma_20: 174.25,
          sma_50: 171.90,
          sma_200: 168.40,
          ema_12: 175.10,
          ema_26: 174.20,
          macd: 0.90,
          macd_signal: 1.05,
          macd_histogram: -0.15,
          bollinger_upper: 179.80,
          bollinger_middle: 174.25,
          bollinger_lower: 168.70,
          stochastic_k: 58.2,
          stochastic_d: 60.1,
          williams_r: -35.8,
          volume: 38000000,
          price: 174.25
        }
      ];

      query.mockResolvedValue({ rows: mockTechnicalData });

      const response = await request(app)
        .get("/api/technical/daily/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe("AAPL");
      expect(response.body.data.timeframe).toBe("daily");
      expect(response.body.data.indicators).toHaveLength(2);
      expect(response.body.data.indicators[0].rsi).toBe(55.25);
      expect(response.body.data.indicators[0].macd).toBe(1.40);
    });

    test("should handle lowercase symbol input", async () => {
      const mockData = [{ symbol: "MSFT", date: "2024-01-01", rsi: 60.5 }];
      query.mockResolvedValue({ rows: mockData });

      const response = await request(app)
        .get("/api/technical/daily/msft")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe("MSFT");
      expect(query).toHaveBeenCalledWith(
        expect.any(String),
        ["MSFT"]
      );
    });

    test("should return 404 for symbol with no technical data", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/technical/daily/NONEXISTENT")
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Technical data not found");
      expect(response.body.message).toContain("NONEXISTENT");
    });

    test("should handle database errors gracefully", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app)
        .get("/api/technical/daily/AAPL")
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Failed to fetch daily technical data");
    });

    test("should limit results to 30 records", async () => {
      const largeMockData = Array(50).fill().map((_, i) => ({
        symbol: "AAPL",
        date: `2024-01-${String(i + 1).padStart(2, '0')}`,
        rsi: 50 + i,
        sma_20: 175 + i
      }));

      query.mockResolvedValue({ rows: largeMockData });

      await request(app)
        .get("/api/technical/daily/AAPL")
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("LIMIT 30"),
        ["AAPL"]
      );
    });
  });

  describe("GET /weekly/:symbol", () => {
    test("should return weekly technical data", async () => {
      const mockWeeklyData = [
        {
          symbol: "AAPL",
          date: "2024-01-01",
          rsi: 58.7,
          sma_20: 175.80,
          macd: 2.15,
          volume: 250000000
        }
      ];

      query.mockResolvedValue({ rows: mockWeeklyData });

      const response = await request(app)
        .get("/api/technical/weekly/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.timeframe).toBe("weekly");
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("technical_data_weekly"),
        ["AAPL"]
      );
    });

    test("should handle empty weekly data", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/technical/weekly/UNKNOWN")
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain("weekly technical data");
    });
  });

  describe("GET /monthly/:symbol", () => {
    test("should return monthly technical data", async () => {
      const mockMonthlyData = [
        {
          symbol: "AAPL",
          date: "2024-01-01",
          rsi: 62.3,
          sma_20: 178.40,
          macd: 3.25,
          volume: 1200000000
        }
      ];

      query.mockResolvedValue({ rows: mockMonthlyData });

      const response = await request(app)
        .get("/api/technical/monthly/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.timeframe).toBe("monthly");
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("technical_data_monthly"),
        ["AAPL"]
      );
    });
  });

  describe("GET /compare", () => {
    test("should compare technical indicators across multiple symbols", async () => {
      const mockComparisonData = [
        {
          symbol: "AAPL",
          rsi: 55.2,
          macd: 1.4,
          sma_20: 175.5,
          date: "2024-01-01"
        },
        {
          symbol: "MSFT",
          rsi: 48.7,
          macd: -0.8,
          sma_20: 380.2,
          date: "2024-01-01"
        }
      ];

      query.mockResolvedValue({ rows: mockComparisonData });

      const response = await request(app)
        .get("/api/technical/compare?symbols=AAPL,MSFT")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.comparison).toHaveLength(2);
      expect(response.body.data.comparison[0].symbol).toBe("AAPL");
      expect(response.body.data.comparison[1].symbol).toBe("MSFT");
    });

    test("should require symbols query parameter", async () => {
      const response = await request(app)
        .get("/api/technical/compare")
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Symbols parameter required");
    });

    test("should limit number of symbols for comparison", async () => {
      const tooManySymbols = Array(20).fill().map((_, i) => `STOCK${i}`).join(",");

      const response = await request(app)
        .get(`/api/technical/compare?symbols=${tooManySymbols}`)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Too many symbols");
    });
  });

  describe("GET /signals/:symbol", () => {
    test("should return technical signals for symbol", async () => {
      const mockSignals = [
        {
          symbol: "AAPL",
          signal_type: "BUY",
          indicator: "RSI_OVERSOLD",
          strength: 0.8,
          timestamp: "2024-01-01T10:30:00Z",
          price: 175.50,
          description: "RSI below 30 indicates oversold condition"
        },
        {
          symbol: "AAPL", 
          signal_type: "SELL",
          indicator: "MACD_BEARISH_CROSSOVER",
          strength: 0.6,
          timestamp: "2024-01-01T14:15:00Z",
          price: 174.80,
          description: "MACD line crossed below signal line"
        }
      ];

      query.mockResolvedValue({ rows: mockSignals });

      const response = await request(app)
        .get("/api/technical/signals/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe("AAPL");
      expect(response.body.data.signals).toHaveLength(2);
      expect(response.body.data.signals[0].signal_type).toBe("BUY");
      expect(response.body.data.signals[0].strength).toBe(0.8);
    });

    test("should handle no signals available", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/technical/signals/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.signals).toHaveLength(0);
      expect(response.body.data.message).toContain("No signals");
    });

    test("should filter signals by type", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/technical/signals/AAPL?type=BUY")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("signal_type = $2"),
        ["AAPL", "BUY"]
      );
    });
  });

  describe("GET /screener", () => {
    test("should return stocks matching technical criteria", async () => {
      const mockScreenerResults = [
        {
          symbol: "AAPL",
          name: "Apple Inc.",
          rsi: 25.5,
          macd: 2.1,
          price: 175.50,
          volume: 45000000,
          match_score: 0.85
        },
        {
          symbol: "MSFT",
          name: "Microsoft Corporation", 
          rsi: 28.3,
          macd: 1.8,
          price: 380.25,
          volume: 38000000,
          match_score: 0.78
        }
      ];

      query.mockResolvedValue({ rows: mockScreenerResults });

      const response = await request(app)
        .get("/api/technical/screener?rsi_max=30&macd_min=1")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.results).toHaveLength(2);
      expect(response.body.data.criteria).toBeDefined();
      expect(response.body.data.count).toBe(2);
    });

    test("should handle various screening criteria", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/technical/screener?rsi_min=30&rsi_max=70&volume_min=1000000")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("rsi BETWEEN"),
        expect.arrayContaining([30, 70, 1000000])
      );
    });

    test("should limit screener results", async () => {
      const largeResults = Array(500).fill().map((_, i) => ({
        symbol: `STOCK${i}`,
        rsi: 50 + i
      }));

      query.mockResolvedValue({ rows: largeResults });

      const response = await request(app)
        .get("/api/technical/screener?rsi_max=30")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("LIMIT"),
        expect.any(Array)
      );
    });
  });

  describe("POST /alerts", () => {
    test("should create technical alert", async () => {
      query.mockResolvedValue({ rows: [{ id: 1 }] });

      const alertData = {
        symbol: "AAPL",
        indicator: "RSI",
        condition: "BELOW",
        value: 30,
        notification_type: "EMAIL"
      };

      const response = await request(app)
        .post("/api/technical/alerts")
        .send(alertData)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.alert_id).toBe(1);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("INSERT INTO technical_alerts"),
        expect.arrayContaining(["AAPL", "RSI", "BELOW", 30, "EMAIL"])
      );
    });

    test("should validate required alert fields", async () => {
      const response = await request(app)
        .post("/api/technical/alerts")
        .send({ symbol: "AAPL" })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Required fields");
    });

    test("should validate indicator types", async () => {
      const response = await request(app)
        .post("/api/technical/alerts")
        .send({
          symbol: "AAPL",
          indicator: "INVALID_INDICATOR",
          condition: "ABOVE",
          value: 50
        })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Invalid indicator");
    });
  });

  describe("Error Handling", () => {
    test("should handle invalid symbol characters", async () => {
      const response = await request(app)
        .get("/api/technical/daily/INVALID@SYMBOL")
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Invalid symbol format");
    });

    test("should handle SQL injection attempts", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/technical/daily/AAPL'; DROP TABLE technical_data_daily; --")
        .expect(404);

      expect(response.body.success).toBe(false);
      // Should be sanitized and return 404 for non-existent symbol
    });

    test("should handle database timeout errors", async () => {
      query.mockRejectedValue(new Error("Query timeout"));

      const response = await request(app)
        .get("/api/technical/daily/AAPL")
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("timeout");
    });

    test("should handle malformed database responses", async () => {
      query.mockResolvedValue(null);

      const response = await request(app)
        .get("/api/technical/daily/AAPL")
        .expect(500);

      expect(response.body.success).toBe(false);
    });
  });

  describe("Performance and Optimization", () => {
    test("should handle concurrent requests efficiently", async () => {
      query.mockResolvedValue({ rows: [{ symbol: "AAPL", rsi: 50 }] });

      const requests = Array(10).fill().map(() =>
        request(app).get("/api/technical/daily/AAPL")
      );

      const responses = await Promise.all(requests);

      responses.forEach(response => {
        expect([200, 404]).toContain(response.status);
        expect(response.body.success).toBe(true);
      });
    });

    test("should handle large datasets efficiently", async () => {
      const largeDataset = Array(1000).fill().map((_, i) => ({
        symbol: "AAPL",
        date: `2024-01-${String(i % 30 + 1).padStart(2, '0')}`,
        rsi: 50 + (i % 40),
        macd: (i % 10) - 5
      }));

      query.mockResolvedValue({ rows: largeDataset });

      const response = await request(app)
        .get("/api/technical/daily/AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      // Should handle large datasets without timeout
    });
  });
});