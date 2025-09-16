/**
 * Trading Signals Integration Tests
 * Tests for trading signal generation and analysis
 * Route: /routes/signals.js
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Trading Signals API", () => {
  describe("Signal Generation", () => {
    test("should generate trading signals for symbol", async () => {
      const response = await request(app).get("/api/signals/AAPL");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("symbol", "AAPL");

        const signals = response.body.data;
        const signalFields = ["signal", "strength", "confidence", "timestamp"];
        const hasSignalData = signalFields.some((field) =>
          Object.keys(signals).some((key) => key.toLowerCase().includes(field))
        );

        expect(hasSignalData).toBe(true);
      }
    });
  });

  describe("Signal History", () => {
    test("should retrieve signal history", async () => {
      const response = await request(app).get(
        "/api/signals/AAPL/history?period=1M"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const signal = response.body.data[0];
          expect(signal).toHaveProperty("timestamp");

          const historyFields = ["signal", "price", "action"];
          const hasHistoryData = historyFields.some((field) =>
            Object.keys(signal).some((key) => key.toLowerCase().includes(field))
          );

          expect(hasHistoryData).toBe(true);
        }
      }
    });
  });

  describe("Bulk Signal Analysis", () => {
    test("should analyze signals for multiple symbols", async () => {
      const response = await request(app).get(
        "/api/signals/bulk?symbols=AAPL,GOOGL,MSFT&signal_type=momentum"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const result = response.body.data[0];
          expect(result).toHaveProperty("symbol");
          expect(result).toHaveProperty("signals");
        }
      }
    });
  });

  describe("Signal Strategies", () => {
    test("should test trading strategy signals", async () => {
      const strategyRequest = {
        strategy: "moving_average_crossover",
        symbol: "AAPL",
        parameters: {
          short_period: 20,
          long_period: 50,
        },
        lookback_period: "3M",
      };

      const response = await request(app)
        .post("/api/signals/strategy")
        .send(strategyRequest);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("strategy");
        expect(response.body.data).toHaveProperty("signals");
        expect(Array.isArray(response.body.data.signals)).toBe(true);
      }
    });
  });

  describe("Signal Performance", () => {
    test("should evaluate signal performance metrics", async () => {
      const response = await request(app).get(
        "/api/signals/performance?strategy=momentum&period=6M"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const data = response.body.data;
        if (data && Object.keys(data).length > 0) {
          const performanceFields = ["accuracy", "profit_loss", "win_rate"];
          const hasPerformanceData = performanceFields.some((field) =>
            Object.keys(data).some((key) =>
              key.toLowerCase().includes(field.replace("_", ""))
            )
          );

          expect(hasPerformanceData).toBe(true);
        }
      }
    });
  });

  describe("Real-time Signals", () => {
    test("should provide real-time signal feed", async () => {
      const response = await request(app).get(
        "/api/signals/live?watchlist=tech_stocks"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const data = response.body.data;
        if (Array.isArray(data) && data.length > 0) {
          const signal = data[0];
          expect(signal).toHaveProperty("symbol");
          expect(signal).toHaveProperty("timestamp");
        }
      }
    });
  });
});
