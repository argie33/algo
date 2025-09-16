const request = require("supertest");
const express = require("express");
const screenerRouter = require("../../../routes/screener");
const { db } = require("../../../utils/database");

// Mock the database
jest.mock("../../../utils/database", () => ({
  db: {
    query: jest.fn(),
  },
}));

describe("AI Scan Endpoint", () => {
  let app;

  beforeEach(() => {
    app = express();
    app.use(express.json());
    app.use("/api/screener", screenerRouter);
    jest.clearAllMocks();
  });

  const mockStockData = [
    {
      symbol: "AAPL",
      current_price: 150.25,
      change_percent: 5.2,
      volume: 75000000,
      avg_volume: 30000000,
      rsi: 65.3,
      market_cap: 2400000000000,
      volume_ratio: 2.5,
      bollinger_position: 0.8,
      macd_signal: "bullish",
      resistance_broken: true,
      consolidation_pattern: "emerging",
      price_volatility: 1.2,
      news_score: 0.75,
    },
    {
      symbol: "TSLA",
      current_price: 180.5,
      change_percent: -8.1,
      volume: 120000000,
      avg_volume: 40000000,
      rsi: 25.8,
      market_cap: 580000000000,
      volume_ratio: 3.0,
      bollinger_position: 0.15,
      macd_signal: "bearish",
      resistance_broken: false,
      consolidation_pattern: "stable",
      price_volatility: 2.8,
      news_score: 0.45,
    },
  ];

  describe("GET /ai-scan", () => {
    it("returns momentum scan results with default parameters", async () => {
      db.query.mockResolvedValue({ rows: mockStockData });

      const response = await request(app)
        .get("/api/screener/ai-scan")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: {
          results: expect.arrayContaining([
            expect.objectContaining({
              symbol: "AAPL",
              price: 150.25,
              priceChange: 5.2,
              volumeRatio: 2.5,
              aiScore: expect.any(Number),
              signals: expect.any(Array),
            }),
          ]),
          scanType: "momentum",
          timestamp: expect.any(String),
          totalResults: 2,
        },
      });

      expect(db.query).toHaveBeenCalledWith(
        expect.stringContaining("WHERE sp.change_percent BETWEEN"),
        expect.arrayContaining([5, 25, 2, 10, 60, 85])
      );
    });

    it("returns reversal scan results when type is reversal", async () => {
      db.query.mockResolvedValue({ rows: mockStockData });

      const response = await request(app)
        .get("/api/screener/ai-scan?type=reversal")
        .expect(200);

      expect(response.body.data.scanType).toBe("reversal");
      expect(db.query).toHaveBeenCalledWith(
        expect.stringContaining("WHERE sp.change_percent BETWEEN"),
        expect.arrayContaining([-15, -5, 20, 40, 1.5, 5, 0.3])
      );
    });

    it("returns breakout scan results when type is breakout", async () => {
      db.query.mockResolvedValue({ rows: mockStockData });

      const response = await request(app)
        .get("/api/screener/ai-scan?type=breakout")
        .expect(200);

      expect(response.body.data.scanType).toBe("breakout");
      expect(db.query).toHaveBeenCalledWith(
        expect.stringContaining("sp.resistance_broken = true"),
        expect.arrayContaining([3, 20, 1.8, 8])
      );
    });

    it("returns unusual activity scan results when type is unusual", async () => {
      db.query.mockResolvedValue({ rows: mockStockData });

      const response = await request(app)
        .get("/api/screener/ai-scan?type=unusual")
        .expect(200);

      expect(response.body.data.scanType).toBe("unusual");
      expect(db.query).toHaveBeenCalledWith(
        expect.stringContaining("WHERE sp.volume_ratio BETWEEN"),
        expect.arrayContaining([3, 20, 1.5, 5, 0.6, 1.0])
      );
    });

    it("respects limit parameter", async () => {
      db.query.mockResolvedValue({ rows: mockStockData });

      await request(app).get("/api/screener/ai-scan?limit=25").expect(200);

      expect(db.query).toHaveBeenCalledWith(
        expect.stringContaining("LIMIT 25"),
        expect.any(Array)
      );
    });

    it("defaults to limit 50 when not specified", async () => {
      db.query.mockResolvedValue({ rows: mockStockData });

      await request(app).get("/api/screener/ai-scan").expect(200);

      expect(db.query).toHaveBeenCalledWith(
        expect.stringContaining("LIMIT 50"),
        expect.any(Array)
      );
    });

    it("calculates AI scores correctly", async () => {
      db.query.mockResolvedValue({ rows: mockStockData });

      const response = await request(app)
        .get("/api/screener/ai-scan")
        .expect(200);

      const aaplResult = response.body.data.results.find(
        (r) => r.symbol === "AAPL"
      );
      const tslaResult = response.body.data.results.find(
        (r) => r.symbol === "TSLA"
      );

      // AAPL: base(50) + momentum(10) + volume(10) + rsi(10) + marketCap(5) + technical(15) = 100
      expect(aaplResult.aiScore).toBe(100);

      // TSLA: base(50) + momentum(-20) + volume(15) + rsi(-10) + marketCap(5) + technical(-5) = 35
      expect(tslaResult.aiScore).toBe(35);
    });

    it("generates appropriate trading signals", async () => {
      db.query.mockResolvedValue({ rows: mockStockData });

      const response = await request(app)
        .get("/api/screener/ai-scan")
        .expect(200);

      const aaplResult = response.body.data.results.find(
        (r) => r.symbol === "AAPL"
      );
      const tslaResult = response.body.data.results.find(
        (r) => r.symbol === "TSLA"
      );

      expect(aaplResult.signals).toEqual(
        expect.arrayContaining([
          "Strong Buy",
          "High Volume",
          "RSI Bullish",
          "Breakout",
        ])
      );

      expect(tslaResult.signals).toEqual(
        expect.arrayContaining([
          "Oversold",
          "High Volume",
          "Potential Reversal",
        ])
      );
    });

    it("assigns confidence levels based on AI scores", async () => {
      db.query.mockResolvedValue({ rows: mockStockData });

      const response = await request(app)
        .get("/api/screener/ai-scan")
        .expect(200);

      const aaplResult = response.body.data.results.find(
        (r) => r.symbol === "AAPL"
      );
      const tslaResult = response.body.data.results.find(
        (r) => r.symbol === "TSLA"
      );

      expect(aaplResult.confidence).toBe("high");
      expect(tslaResult.confidence).toBe("low");
    });

    it("handles unknown scan type by defaulting to momentum", async () => {
      db.query.mockResolvedValue({ rows: mockStockData });

      const response = await request(app)
        .get("/api/screener/ai-scan?type=unknown")
        .expect(200);

      expect(response.body.data.scanType).toBe("momentum");
    });

    it("handles database errors gracefully", async () => {
      db.query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app)
        .get("/api/screener/ai-scan")
        .expect(500);

      expect(response.body).toEqual({
        success: false,
        error: "Failed to fetch AI scan results",
        message: expect.any(String),
      });
    });

    it("handles empty results from database", async () => {
      db.query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/screener/ai-scan")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: {
          results: [],
          scanType: "momentum",
          timestamp: expect.any(String),
          totalResults: 0,
        },
      });
    });

    it("validates limit parameter bounds", async () => {
      db.query.mockResolvedValue({ rows: mockStockData });

      // Test maximum limit
      await request(app).get("/api/screener/ai-scan?limit=101").expect(200);

      expect(db.query).toHaveBeenCalledWith(
        expect.stringContaining("LIMIT 100"),
        expect.any(Array)
      );

      // Test minimum limit
      await request(app).get("/api/screener/ai-scan?limit=0").expect(200);

      expect(db.query).toHaveBeenCalledWith(
        expect.stringContaining("LIMIT 1"),
        expect.any(Array)
      );
    });

    it("includes performance metrics in response", async () => {
      db.query.mockResolvedValue({ rows: mockStockData });

      const response = await request(app)
        .get("/api/screener/ai-scan")
        .expect(200);

      expect(response.body.data).toHaveProperty("timestamp");
      expect(response.body.data).toHaveProperty("totalResults");
      expect(response.body.data).toHaveProperty("scanType");
    });

    it("sorts results by AI score in descending order", async () => {
      const mixedScoreData = [
        { ...mockStockData[1], symbol: "LOW_SCORE", change_percent: -15 }, // Low score
        { ...mockStockData[0], symbol: "HIGH_SCORE", change_percent: 15 }, // High score
        { ...mockStockData[0], symbol: "MED_SCORE", change_percent: 8 }, // Medium score
      ];

      db.query.mockResolvedValue({ rows: mixedScoreData });

      const response = await request(app)
        .get("/api/screener/ai-scan")
        .expect(200);

      const symbols = response.body.data.results.map((r) => r.symbol);
      expect(symbols[0]).toBe("HIGH_SCORE");
      expect(symbols[symbols.length - 1]).toBe("LOW_SCORE");
    });

    it("includes all required fields in response", async () => {
      db.query.mockResolvedValue({ rows: mockStockData });

      const response = await request(app)
        .get("/api/screener/ai-scan")
        .expect(200);

      const result = response.body.data.results[0];

      expect(result).toHaveProperty("symbol");
      expect(result).toHaveProperty("price");
      expect(result).toHaveProperty("priceChange");
      expect(result).toHaveProperty("volumeRatio");
      expect(result).toHaveProperty("rsi");
      expect(result).toHaveProperty("marketCap");
      expect(result).toHaveProperty("aiScore");
      expect(result).toHaveProperty("confidence");
      expect(result).toHaveProperty("signals");
      expect(result).toHaveProperty("scanReason");
    });

    it("calculates different scores for different scan types", async () => {
      db.query.mockResolvedValue({ rows: [mockStockData[1]] }); // TSLA with negative change

      // Test reversal scan (should favor oversold stocks)
      const reversalResponse = await request(app)
        .get("/api/screener/ai-scan?type=reversal")
        .expect(200);

      // Test momentum scan (should penalize negative change)
      const momentumResponse = await request(app)
        .get("/api/screener/ai-scan?type=momentum")
        .expect(200);

      const reversalScore = reversalResponse.body.data.results[0].aiScore;
      const momentumScore = momentumResponse.body.data.results[0].aiScore;

      expect(reversalScore).toBeGreaterThan(momentumScore);
    });
  });

  describe("AI Scoring Algorithm", () => {
    beforeEach(() => {
      db.query.mockResolvedValue({ rows: mockStockData });
    });

    it("applies momentum bonus correctly", async () => {
      const highMomentumStock = {
        ...mockStockData[0],
        change_percent: 12, // High positive momentum
      };

      db.query.mockResolvedValue({ rows: [highMomentumStock] });

      const response = await request(app)
        .get("/api/screener/ai-scan?type=momentum")
        .expect(200);

      expect(response.body.data.results[0].aiScore).toBeGreaterThan(75);
    });

    it("applies volume multiplier correctly", async () => {
      const highVolumeStock = {
        ...mockStockData[0],
        volume_ratio: 5.0, // Very high volume
      };

      db.query.mockResolvedValue({ rows: [highVolumeStock] });

      const response = await request(app)
        .get("/api/screener/ai-scan")
        .expect(200);

      expect(response.body.data.results[0].aiScore).toBeGreaterThan(80);
    });

    it("penalizes extreme RSI values appropriately", async () => {
      const overboughtStock = {
        ...mockStockData[0],
        rsi: 85, // Overbought
      };

      const oversoldStock = {
        ...mockStockData[0],
        rsi: 15, // Oversold
      };

      // Test overbought in momentum scan (should be penalized)
      db.query.mockResolvedValue({ rows: [overboughtStock] });
      const overboughtResponse = await request(app)
        .get("/api/screener/ai-scan?type=momentum")
        .expect(200);

      // Test oversold in reversal scan (should be favored)
      db.query.mockResolvedValue({ rows: [oversoldStock] });
      const oversoldResponse = await request(app)
        .get("/api/screener/ai-scan?type=reversal")
        .expect(200);

      expect(oversoldResponse.body.data.results[0].aiScore).toBeGreaterThan(
        overboughtResponse.body.data.results[0].aiScore
      );
    });
  });

  describe("Signal Generation", () => {
    it("generates breakout signals correctly", async () => {
      const breakoutStock = {
        ...mockStockData[0],
        resistance_broken: true,
        change_percent: 8,
        volume_ratio: 3.0,
      };

      db.query.mockResolvedValue({ rows: [breakoutStock] });

      const response = await request(app)
        .get("/api/screener/ai-scan?type=breakout")
        .expect(200);

      expect(response.body.data.results[0].signals).toContain("Breakout");
    });

    it("generates volume surge signals correctly", async () => {
      const highVolumeStock = {
        ...mockStockData[0],
        volume_ratio: 4.0,
      };

      db.query.mockResolvedValue({ rows: [highVolumeStock] });

      const response = await request(app)
        .get("/api/screener/ai-scan")
        .expect(200);

      expect(response.body.data.results[0].signals).toContain("High Volume");
    });

    it("generates reversal signals for oversold conditions", async () => {
      const oversoldStock = {
        ...mockStockData[1],
        rsi: 25,
        change_percent: -12,
        bollinger_position: 0.1,
      };

      db.query.mockResolvedValue({ rows: [oversoldStock] });

      const response = await request(app)
        .get("/api/screener/ai-scan?type=reversal")
        .expect(200);

      expect(response.body.data.results[0].signals).toEqual(
        expect.arrayContaining(["Oversold", "Potential Reversal"])
      );
    });
  });
});
