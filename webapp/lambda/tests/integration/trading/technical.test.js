/**
 * Technical Analysis Integration Tests
 * Tests for technical indicators, signals, and chart data
 * Route: /routes/technical.js
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Technical Analysis", () => {
  describe("Technical Indicators", () => {
    test("should calculate RSI indicator", async () => {
      const response = await request(app).get(
        "/api/technical/daily/AAPL?indicators=rsi&period=14"
      );

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("symbol", "AAPL");

        const data = response.body.data;
        if (data && data.indicators && data.indicators.length > 0) {
          // RSI should be present in indicators array
          const indicatorData = data.indicators[0];
          const hasRSI = Object.keys(indicatorData).some((key) =>
            key.toLowerCase().includes("rsi")
          );

          expect(hasRSI).toBe(true);

          // If RSI value is present, it should be between 0 and 100
          const rsiKey = Object.keys(indicatorData).find((key) =>
            key.toLowerCase().includes("rsi")
          );
          if (rsiKey && typeof indicatorData[rsiKey] === "number") {
            expect(indicatorData[rsiKey]).toBeGreaterThanOrEqual(0);
            expect(indicatorData[rsiKey]).toBeLessThanOrEqual(100);
          }
        }
      }
    });

    test("should calculate MACD indicator", async () => {
      const response = await request(app).get(
        "/api/technical/daily/AAPL?indicators=macd"
      );

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const data = response.body.data;
        if (data && data.indicators && data.indicators.length > 0) {
          // MACD should have line, signal, and histogram
          const indicatorData = data.indicators[0];
          const macdFields = ["macd", "signal", "histogram"];
          const hasMACDData = macdFields.some((field) =>
            Object.keys(indicatorData).some((key) => key.toLowerCase().includes(field))
          );

          expect(hasMACDData).toBe(true);
        }
      }
    });

    test("should calculate moving averages", async () => {
      const response = await request(app).get(
        "/api/technical/daily/AAPL?indicators=sma,ema&periods=20,50"
      );

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const data = response.body.data;
        if (data && data.indicators && data.indicators.length > 0) {
          // Should have moving averages
          const indicatorData = data.indicators[0];
          const maFields = ["sma", "ema", "moving", "average"];
          const hasMAData = maFields.some((field) =>
            Object.keys(indicatorData).some((key) => key.toLowerCase().includes(field))
          );

          expect(hasMAData).toBe(true);
        }
      }
    });

    test("should calculate Bollinger Bands", async () => {
      const response = await request(app).get(
        "/api/technical/daily/AAPL?indicators=bollinger&period=20&std=2"
      );

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const data = response.body.data;
        if (data && data.indicators && data.indicators.length > 0) {
          // Bollinger bands should have upper, middle, lower
          const indicatorData = data.indicators[0];
          const bbFields = ["upper", "middle", "lower", "bollinger"];
          const hasBBData = bbFields.some((field) =>
            Object.keys(indicatorData).some((key) => key.toLowerCase().includes(field))
          );

          expect(hasBBData).toBe(true);
        }
      }
    });

    test("should support multiple indicators in single request", async () => {
      const response = await request(app).get(
        "/api/technical/daily/AAPL?indicators=rsi,macd,sma,bollinger"
      );

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const data = response.body.data;
        if (data && data.indicators && data.indicators.length > 0) {
          // Should have at least one of the requested indicators
          const indicatorData = data.indicators[0];
          const allIndicators = ["rsi", "macd", "sma", "bollinger"];
          const hasAnyIndicator = allIndicators.some((indicator) =>
            Object.keys(indicatorData).some((key) =>
              key.toLowerCase().includes(indicator)
            )
          );

          expect(hasAnyIndicator).toBe(true);
        }
      }
    });
  });

  describe("Trading Signals", () => {
    test("should generate trading signals based on technical analysis", async () => {
      const response = await request(app).get("/api/technical/signals/AAPL");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("symbol", "AAPL");

        const data = response.body.data;
        if (data && Object.keys(data).length > 1) {
          // Signals should include actionable information
          const signalFields = [
            "signal",
            "strength",
            "recommendation",
            "confidence",
          ];
          const hasSignalData = signalFields.some((field) =>
            Object.keys(data).some((key) => key.toLowerCase().includes(field))
          );

          expect(hasSignalData || data.analysis).toBeTruthy();

          // Signal should be buy, sell, or hold
          if (data.signal) {
            expect([
              "buy",
              "sell",
              "hold",
              "strong_buy",
              "strong_sell",
            ]).toContain(data.signal.toLowerCase());
          }
        }
      }
    });

    test("should provide signal strength and confidence levels", async () => {
      const response = await request(app).get(
        "/api/technical/signals/MSFT?include_confidence=true"
      );

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const data = response.body.data;
        if (data && Object.keys(data).length > 1) {
          // Should include strength and confidence metrics
          const confidenceFields = [
            "strength",
            "confidence",
            "probability",
            "score",
          ];
          const hasConfidenceData = confidenceFields.some((field) =>
            Object.keys(data).some((key) => key.toLowerCase().includes(field))
          );

          expect(hasConfidenceData).toBe(true);
        }
      }
    });

    test("should identify price targets and stop losses", async () => {
      const response = await request(app).get(
        "/api/technical/signals/GOOGL?include_targets=true"
      );

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const data = response.body.data;
        if (data && Object.keys(data).length > 1) {
          // Should include price targets
          const targetFields = [
            "price_target",
            "stop_loss",
            "support",
            "resistance",
          ];
          const hasTargetData = targetFields.some((field) =>
            Object.keys(data).some((key) =>
              key.toLowerCase().includes(field.replace("_", ""))
            )
          );

          expect(hasTargetData).toBe(true);
        }
      }
    });
  });

  describe("Chart Data", () => {
    test("should provide OHLCV chart data", async () => {
      const response = await request(app).get(
        "/api/technical/chart/AAPL?period=1M&interval=1d"
      );

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const data = response.body.data;
        if (data) {
          // Chart data should be structured time series
          expect(Array.isArray(data) || data.prices || data.chart).toBeTruthy();

          if (Array.isArray(data) && data.length > 0) {
            const candle = data[0];
            expect(candle).toHaveProperty("timestamp");

            // Should have OHLC data
            const ohlcFields = ["open", "high", "low", "close"];
            const hasOHLC = ohlcFields.every((field) =>
              Object.prototype.hasOwnProperty.call(candle, field)
            );

            if (Object.keys(candle).length > 1) {
              expect(hasOHLC).toBe(true);
            }
          }
        }
      }
    });

    test("should support different chart intervals", async () => {
      const intervals = ["1m", "5m", "15m", "1h", "1d", "1w"];

      for (const interval of intervals.slice(0, 3)) {
        // Test first 3 to avoid rate limits
        const response = await request(app).get(
          `/api/technical/chart/SPY?period=1D&interval=${interval}`
        );

        expect(response.status).toBe(200);

        if (response.status === 200) {
          expect(response.body).toHaveProperty("success", true);

          const data = response.body.data;
          if (Array.isArray(data) && data.length > 0) {
            expect(data[0]).toHaveProperty("timestamp");
          }
        }
      }
    });

    test("should include volume data in charts", async () => {
      const response = await request(app).get(
        "/api/technical/chart/AAPL?period=1M&include_volume=true"
      );

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const data = response.body.data;
        if (Array.isArray(data) && data.length > 0) {
          const candle = data[0];
          expect(candle).toHaveProperty("volume");
          expect(typeof candle.volume).toBe("number");
          expect(candle.volume).toBeGreaterThan(0);
        }
      }
    });
  });

  describe("Pattern Recognition", () => {
    test("should identify chart patterns", async () => {
      const response = await request(app).get("/api/technical/patterns/AAPL");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const data = response.body.data;
        if (data && Object.keys(data).length > 0) {
          // Pattern recognition should identify bullish/bearish patterns
          const patternFields = [
            "patterns",
            "bullish",
            "bearish",
            "formations",
          ];
          const hasPatternData = patternFields.some((field) =>
            Object.keys(data).some((key) => key.toLowerCase().includes(field))
          );

          expect(hasPatternData).toBe(true);
        }
      }
    });

    test("should detect support and resistance levels", async () => {
      const response = await request(app).get("/api/technical/levels/AAPL");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const data = response.body.data;
        if (data && Object.keys(data).length > 0) {
          // Should identify key price levels
          const levelFields = ["support", "resistance", "pivot", "levels"];
          const hasLevelData = levelFields.some((field) =>
            Object.keys(data).some((key) => key.toLowerCase().includes(field))
          );

          expect(hasLevelData).toBe(true);
        }
      }
    });
  });

  describe("Multi-Timeframe Analysis", () => {
    test("should provide analysis across multiple timeframes", async () => {
      const response = await request(app).get(
        "/api/technical/multi-timeframe/AAPL?timeframes=1D,1W,1M"
      );

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const data = response.body.data;
        if (data && Object.keys(data).length > 0) {
          // Should have analysis for different timeframes
          const timeframeFields = ["daily", "weekly", "monthly", "timeframes"];
          const hasTimeframeData = timeframeFields.some((field) =>
            Object.keys(data).some((key) => key.toLowerCase().includes(field))
          );

          expect(hasTimeframeData || Array.isArray(data)).toBeTruthy();
        }
      }
    });

    test("should aggregate signals across timeframes", async () => {
      const response = await request(app).get("/api/technical/consensus/AAPL");

      expect(response.status).toBe(200);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const data = response.body.data;
        if (data && Object.keys(data).length > 0) {
          // Consensus should aggregate multiple signals
          const consensusFields = [
            "consensus",
            "overall",
            "aggregate",
            "summary",
          ];
          const hasConsensusData = consensusFields.some((field) =>
            Object.keys(data).some((key) => key.toLowerCase().includes(field))
          );

          expect(hasConsensusData).toBe(true);
        }
      }
    });
  });
});
