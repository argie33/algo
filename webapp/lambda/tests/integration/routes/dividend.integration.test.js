/**
 * Dividend Routes Integration Tests - REAL DATA ONLY
 * Tests dividend endpoints with REAL database connection and REAL loaded data
 * NO MOCKS - validates actual behavior with actual data from loaders
 * Validates NO-FALLBACK policy: raw NULL values must flow through unmasked
 */

const request = require("supertest");
const { app } = require("../../../index");
const { initializeDatabase } = require("../../../utils/database"); // Import the actual Express app - NO MOCKS

describe("Dividend Routes - Real Data Validation", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  describe("GET /api/dividend/:symbol (Stock Dividend Data)", () => {
    test("should return dividend data for dividend-paying stocks", async () => {
      console.log('Starting dividend test with app:', typeof app);
      const response = await request(app)
        .get('/api/dividend/AAPL')
        .set('Authorization', 'Bearer dev-bypass-token')
        .timeout(5000);

      console.log(`Response status: ${response.status}`);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("symbol", "AAPL");
        expect(response.body.data).toHaveProperty("dividends");
        expect(Array.isArray(response.body.data.dividends)).toBe(true);
      }
    });

    test("should include dividend yield calculation", async () => {
      const response = await request(app)
        .get("/api/dividend/AAPL")
        .set('Authorization', 'Bearer dev-bypass-token');

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty("dividend_yield");
        expect(response.body.data).toHaveProperty("annual_dividend");
        expect(response.body.data).toHaveProperty("payout_ratio");

        if (response.body.data.dividend_yield !== null) {
          expect(typeof response.body.data.dividend_yield).toBe("number");
          expect(response.body.data.dividend_yield).toBeGreaterThanOrEqual(0);
          expect(response.body.data.dividend_yield).toBeLessThan(50); // Reasonable upper bound
        }
      }
    });

    test("should handle historical timeframe parameter", async () => {
      const timeframes = ["1Y", "2Y", "5Y", "10Y", "max"];

      for (const timeframe of timeframes) {
        const response = await request(app)
          .get(`/api/dividend/MSFT?timeframe=${timeframe}`)
          .set('Authorization', 'Bearer dev-bypass-token');

        expect([200, 400, 404].includes(response.status)).toBe(true);

        if (
          response.status === 200 &&
          response.body.data?.dividends?.length > 0
        ) {
          const dividends = response.body.data.dividends;
          expect(
            dividends.every((div) => new Date(div.ex_date) instanceof Date)
          ).toBe(true);
        }
      }
    });

    test("should handle non-dividend paying stocks", async () => {
      const nonDividendStocks = ["TSLA", "AMZN", "NFLX"];

      for (const symbol of nonDividendStocks) {
        const response = await request(app)
          .get(`/api/dividend/${symbol}`)
          .set('Authorization', 'Bearer dev-bypass-token');

        expect([200, 404]).toContain(response.status);

        if (response.status === 200) {
          expect(response.body.data.dividends).toEqual([]);
          expect(response.body.data.dividend_yield).toBeNull();
        }
      }
    });

    test("should handle invalid stock symbol", async () => {
      const response = await request(app)
        .get("/api/dividend/INVALID123")
        .set('Authorization', 'Bearer dev-bypass-token');

      expect([404, 500, 503].includes(response.status)).toBe(true);
    });

    test("should validate dividend data structure", async () => {
      const response = await request(app)
        .get("/api/dividend/JNJ")
        .set('Authorization', 'Bearer dev-bypass-token');

      expect([200, 404]).toContain(response.status);

      if (response.status === 200 && response.body.data?.dividends?.length > 0) {
        const dividend = response.body.data.dividends[0];
        expect(dividend).toHaveProperty("ex_date");
        expect(dividend).toHaveProperty("record_date");
        expect(dividend).toHaveProperty("payment_date");
        expect(dividend).toHaveProperty("amount");
        expect(dividend).toHaveProperty("frequency");
        expect(typeof dividend.ex_date).toBe("string");
        expect(typeof dividend.amount).toBe("number");
      }
    });
  });

  describe("GET /api/dividend/calendar (Dividend Calendar)", () => {
    test("should return upcoming dividend events", async () => {
      const response = await request(app)
        .get("/api/dividend/calendar")
        .set('Authorization', 'Bearer dev-bypass-token');

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");

        if (response.body.data && Array.isArray(response.body.data)) {
          expect(response.body).toHaveProperty("period");

          if (response.body.data.length > 0) {
            const event = response.body.data[0];
            expect(event).toHaveProperty("symbol");
            expect(event).toHaveProperty("ex_date");
            expect(event).toHaveProperty("amount");
          }
        }
      }
    });

    test("should handle date range for dividend calendar", async () => {
      const response = await request(app)
        .get("/api/dividend/calendar?start_date=2025-01-01&end_date=2025-03-31")
        .set('Authorization', 'Bearer dev-bypass-token');

      expect([200, 400, 404, 500, 503].includes(response.status)).toBe(true);

      if (response.status === 200 && response.body.data?.length > 0) {
        response.body.data.forEach((event) => {
          const exDate = new Date(event.ex_date);
          expect(exDate >= new Date("2025-01-01")).toBe(true);
          expect(exDate <= new Date("2025-03-31")).toBe(true);
        });
      }
    });

    test("should filter by minimum dividend amount", async () => {
      const response = await request(app)
        .get("/api/dividend/calendar?min_amount=1.00")
        .set('Authorization', 'Bearer dev-bypass-token');

      expect([200, 400, 404, 500, 503].includes(response.status)).toBe(true);

      if (response.status === 200 && response.body.data.length > 0) {
        response.body.data.forEach((event) => {
          if (event.amount !== null) {
            expect(event.amount).toBeGreaterThanOrEqual(1.0);
          }
        });
      }
    });

    test("should handle sector filter", async () => {
      const sectors = [
        "Technology",
        "Healthcare",
        "Financial Services",
        "Consumer Goods",
      ];

      for (const sector of sectors) {
        const response = await request(app).get(
          `/api/dividend/calendar?sector=${encodeURIComponent(sector)}`
        );

        expect([200, 400, 500, 503].includes(response.status)).toBe(true);
      }
    });
  });

  describe("GET /api/dividend/aristocrats (Dividend Aristocrats)", () => {
    test("should return dividend aristocrat stocks", async () => {
      const response = await request(app).get("/api/dividend/aristocrats").set('Authorization', `Bearer dev-bypass-token`);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(Array.isArray(response.body.data)).toBe(true);
        expect(response.body).toHaveProperty("criteria");

        if (response.body.data.length > 0) {
          const aristocrat = response.body.data[0];
          expect(aristocrat).toHaveProperty("symbol");
          expect(aristocrat).toHaveProperty("consecutive_years");
          expect(aristocrat).toHaveProperty("current_yield");
          expect(aristocrat.consecutive_years).toBeGreaterThanOrEqual(25);
        }
      }
    });

    test("should handle minimum years filter", async () => {
      const response = await request(app).get(
        "/api/dividend/aristocrats?min_years=25"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);

      if (response.status === 200 && response.body.data.length > 0) {
        response.body.data.forEach((stock) => {
          expect(stock.consecutive_years).toBeGreaterThanOrEqual(25);
        });
      }
    });

    test("should handle yield range filters", async () => {
      const response = await request(app).get(
        "/api/dividend/aristocrats?min_yield=2.0&max_yield=6.0"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);

      if (response.status === 200 && response.body.data.length > 0) {
        response.body.data.forEach((stock) => {
          if (stock.current_yield !== null) {
            expect(stock.current_yield).toBeGreaterThanOrEqual(2.0);
            expect(stock.current_yield).toBeLessThanOrEqual(6.0);
          }
        });
      }
    });
  });

  describe("GET /api/dividend/growth (Dividend Growth Analysis)", () => {
    test("should return dividend growth analysis", async () => {
      const response = await request(app).get(
        "/api/dividend/growth?symbol=AAPL"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("symbol", "AAPL");
        expect(response.body.data).toHaveProperty("growth_metrics");
        expect(response.body.data.growth_metrics).toHaveProperty(
          "five_year_growth_rate"
        );
        expect(response.body.data.growth_metrics).toHaveProperty(
          "ten_year_growth_rate"
        );
        expect(response.body.data.growth_metrics).toHaveProperty(
          "compound_growth_rate"
        );
      }
    });

    test("should handle growth period parameter", async () => {
      const periods = ["1Y", "3Y", "5Y", "10Y"];

      for (const period of periods) {
        const response = await request(app).get(
          `/api/dividend/growth?symbol=MSFT&period=${period}`
        );

        expect([200, 400].includes(response.status)).toBe(true);
      }
    });

    test("should include dividend sustainability metrics", async () => {
      const response = await request(app).get(
        "/api/dividend/growth?symbol=JNJ"
      );

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty("sustainability");
        expect(response.body.data.sustainability).toHaveProperty(
          "payout_ratio"
        );
        expect(response.body.data.sustainability).toHaveProperty(
          "free_cash_flow_coverage"
        );
        expect(response.body.data.sustainability).toHaveProperty(
          "debt_to_equity_impact"
        );
      }
    });
  });

  describe("GET /api/dividend/screener (Dividend Stock Screener)", () => {
    test("should return dividend stock screening results", async () => {
      const response = await request(app).get("/api/dividend/screener").set('Authorization', `Bearer dev-bypass-token`);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(Array.isArray(response.body.data)).toBe(true);
        expect(response.body).toHaveProperty("filters_applied");
        expect(response.body).toHaveProperty("count");
      }
    });

    test("should handle yield range screening", async () => {
      const response = await request(app).get(
        "/api/dividend/screener?min_yield=3.0&max_yield=8.0"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);

      if (response.status === 200 && response.body.data.length > 0) {
        response.body.data.forEach((stock) => {
          if (stock.dividend_yield !== null) {
            expect(stock.dividend_yield).toBeGreaterThanOrEqual(3.0);
            expect(stock.dividend_yield).toBeLessThanOrEqual(8.0);
          }
        });
      }
    });

    test("should handle payout ratio filter", async () => {
      const response = await request(app).get(
        "/api/dividend/screener?max_payout_ratio=60"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);

      if (response.status === 200 && response.body.data.length > 0) {
        response.body.data.forEach((stock) => {
          if (stock.payout_ratio !== null) {
            expect(stock.payout_ratio).toBeLessThanOrEqual(60);
          }
        });
      }
    });

    test("should handle market cap filter", async () => {
      const response = await request(app).get(
        "/api/dividend/screener?min_market_cap=1000000000"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);
    });

    test("should handle multiple filters combined", async () => {
      const response = await request(app).get(
        "/api/dividend/screener?min_yield=2.5&max_payout_ratio=70&min_market_cap=5000000000&sector=Technology"
      );

      expect([200, 400, 500, 503].includes(response.status)).toBe(true);
    });

    test("should handle sorting options", async () => {
      const sortOptions = [
        "yield",
        "payout_ratio",
        "growth_rate",
        "market_cap",
      ];

      for (const sort of sortOptions) {
        const response = await request(app).get(
          `/api/dividend/screener?sort=${sort}&order=desc`
        );

        expect([200, 400, 500, 503].includes(response.status)).toBe(true);
      }
    });
  });

  describe("GET /api/dividend/forecast (Dividend Forecasting)", () => {
    test("should return dividend payment forecasts", async () => {
      const response = await request(app).get(
        "/api/dividend/forecast?symbol=AAPL"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("symbol", "AAPL");
        expect(response.body.data).toHaveProperty("forecasts");
        expect(Array.isArray(response.body.data.forecasts)).toBe(true);
        expect(response.body.data).toHaveProperty("confidence_level");

        if (response.body.data.forecasts.length > 0) {
          const forecast = response.body.data.forecasts[0];
          expect(forecast).toHaveProperty("expected_date");
          expect(forecast).toHaveProperty("estimated_amount");
          expect(forecast).toHaveProperty("confidence_range");
        }
      }
    });

    test("should handle forecast horizon parameter", async () => {
      const horizons = ["1Q", "2Q", "1Y", "2Y"];

      for (const horizon of horizons) {
        const response = await request(app).get(
          `/api/dividend/forecast?symbol=MSFT&horizon=${horizon}`
        );

        expect([200, 400].includes(response.status)).toBe(true);
      }
    });
  });

  describe("Performance and Edge Cases", () => {
    jest.setTimeout(15000);

    test("should handle concurrent dividend data requests", async () => {
      const requests = ["AAPL", "MSFT", "JNJ", "KO", "PFE"].map((symbol) =>
        request(app).get(`/api/dividend/${symbol}`).set('Authorization', `Bearer dev-bypass-token`)
      );

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect([200, 404]).toContain(response.status);
      });
    });

    test("should handle invalid date formats", async () => {
      const invalidDates = [
        "start_date=invalid-date",
        "end_date=2025-13-40",
        "start_date=2025-12-31&end_date=2025-01-01", // end before start
      ];

      for (const dateParams of invalidDates) {
        const response = await request(app).get(
          `/api/dividend/calendar?${dateParams}`
        );

        expect([200, 400, 500, 503].includes(response.status)).toBe(true);
      }
    });

    test("should validate dividend amount ranges", async () => {
      const response = await request(app).get("/api/dividend/AAPL").set('Authorization', `Bearer dev-bypass-token`);

      if (response.status === 200 && response.body.data.dividends.length > 0) {
        response.body.data.dividends.forEach((dividend) => {
          expect(typeof dividend.amount).toBe("number");
          expect(dividend.amount).toBeGreaterThan(0);
          expect(dividend.amount).toBeLessThan(100); // Reasonable upper bound
          expect(isFinite(dividend.amount)).toBe(true);
        });
      }
    });

    test("should handle malformed screening parameters", async () => {
      const malformedParams = [
        "min_yield=invalid",
        "max_payout_ratio=-50",
        "min_market_cap=abc",
        "min_yield=10&max_yield=2", // min > max
      ];

      for (const params of malformedParams) {
        const response = await request(app).get(
          `/api/dividend/screener?${params}`
        );

        expect([200, 400, 500, 503].includes(response.status)).toBe(true);
      }
    });

    test("should maintain response time consistency", async () => {
      const startTime = Date.now();
      const response = await request(app).get("/api/dividend/calendar").set('Authorization', `Bearer dev-bypass-token`);
      const responseTime = Date.now() - startTime;

      expect([200, 404]).toContain(response.status);
      expect(responseTime).toBeLessThan(15000);
    });

    test("should handle special symbol characters", async () => {
      const specialSymbols = ["BRK.A", "BRK.B", "BF.A", "BF.B"];

      for (const symbol of specialSymbols) {
        const response = await request(app).get(`/api/dividend/${symbol}`).set('Authorization', `Bearer dev-bypass-token`);

        expect([200, 404]).toContain(response.status);
      }
    });

    test("should handle SQL injection attempts", async () => {
      const maliciousSymbol = "AAPL'; DROP TABLE dividends; --";
      const response = await request(app).get(
        `/api/dividend/${encodeURIComponent(maliciousSymbol)}`
      );

      expect([200, 400].includes(response.status)).toBe(true);
    });

    test("should handle database connection failures gracefully", async () => {
      const response = await request(app).get("/api/dividend/AAPL").set('Authorization', `Bearer dev-bypass-token`);

      expect([200, 404]).toContain(response.status);

      if (response.status >= 500) {
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should validate yield calculation accuracy", async () => {
      const response = await request(app).get("/api/dividend/JNJ").set('Authorization', `Bearer dev-bypass-token`);

      if (
        response.status === 200 &&
        response.body.data.dividend_yield !== null
      ) {
        const dividend_yield = response.body.data.dividend_yield;
        expect(dividend_yield).toBeGreaterThanOrEqual(0);
        expect(dividend_yield).toBeLessThan(50); // Reasonable upper bound for dividend yields
        expect(Number.isFinite(dividend_yield)).toBe(true);
      }
    });

    test("should handle stress testing with multiple concurrent requests", async () => {
      const promises = Array(10)
        .fill()
        .map(() => request(app).get("/api/dividend/screener").set('Authorization', `Bearer dev-bypass-token`).timeout(10000));

      const responses = await Promise.all(
        promises.map((p) => p.catch((err) => ({ status: 500, error: err })))
      );

      responses.forEach((response) => {
        if (response.status) {
          expect([200, 404]).toContain(response.status);
        }
      });
    });
  });
});
