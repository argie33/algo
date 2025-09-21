const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("Signals Routes", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/signals", () => {
    test("should return signals with proper AWS-compatible structure", async () => {
      const response = await request(app).get("/api/signals");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("signals");
      expect(Array.isArray(response.body.signals)).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("buy_signals");
      expect(Array.isArray(response.body.data.buy_signals)).toBe(true);
      expect(response.body.data).toHaveProperty("sell_signals");
      expect(Array.isArray(response.body.data.sell_signals)).toBe(true);

      // Verify loader table structure fields from buy_sell_daily when data exists
      if (response.body.signals.length > 0) {
        const signal = response.body.signals[0];
        expect(signal).toHaveProperty("symbol");
        expect(signal).toHaveProperty("signal");
        expect(signal).toHaveProperty("signal_date");
        expect(signal).toHaveProperty("confidence");
        expect(signal).toHaveProperty("entry_price"); // from price_daily JOIN
        expect(signal).toHaveProperty("sector"); // from company_profile JOIN
      }
    });
  });

  describe("GET /api/signals/:symbol", () => {
    test("should return endpoint not found error", async () => {
      const response = await request(app).get("/api/signals/AAPL");

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Endpoint /api/signals/AAPL not found");
      expect(response.body.type).toBe("not_found_error");
    });
  });

  describe("GET /api/signals/trending", () => {
    test("should return endpoint not found error", async () => {
      const response = await request(app).get("/api/signals/trending");

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe(
        "Endpoint /api/signals/trending not found"
      );
      expect(response.body.type).toBe("not_found_error");
    });
  });

  describe("GET /api/signals/buy", () => {
    test("should return buy signals with AWS-compatible structure", async () => {
      const response = await request(app).get("/api/signals/buy");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(Array.isArray(response.body.data)).toBe(true);
      if (response.body.data.length > 0) {
        const signal = response.body.data[0];
        expect(signal).toHaveProperty("symbol");
        expect(signal).toHaveProperty("signal");
        expect(signal).toHaveProperty("signal_date");
        expect(signal).toHaveProperty("confidence");
        expect(signal).toHaveProperty("entry_price"); // from price_daily JOIN
        expect(signal).toHaveProperty("sector"); // from company_profile JOIN
      }
    });

    test("should handle filters properly", async () => {
      const response = await request(app).get(
        "/api/signals/buy?min_strength=0.8"
      );

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(Array.isArray(response.body.data)).toBe(true);
    });
  });

  describe("GET /api/signals/sell", () => {
    test("should return sell signals with AWS-compatible structure", async () => {
      const response = await request(app).get("/api/signals/sell");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(Array.isArray(response.body.data)).toBe(true);
      if (response.body.data.length > 0) {
        const signal = response.body.data[0];
        expect(signal).toHaveProperty("symbol");
        expect(signal).toHaveProperty("signal");
        expect(signal).toHaveProperty("signal_date");
        expect(signal).toHaveProperty("confidence");
        expect(signal).toHaveProperty("entry_price"); // from price_daily JOIN
        expect(signal).toHaveProperty("sector"); // from company_profile JOIN
      }
    });
  });

  describe("GET /api/signals/alerts", () => {
    test("should return alerts with AWS-compatible structure", async () => {
      const response = await request(app).get("/api/signals/alerts");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(Array.isArray(response.body.data)).toBe(true);
    });
  });

  describe("POST /api/signals/alerts", () => {
    test("should return endpoint not found error", async () => {
      const alertData = {
        symbol: "AAPL",
        signal_type: "BUY",
        min_strength: 0.8,
        notification_method: "email",
      };

      const response = await request(app)
        .post("/api/signals/alerts")
        .send(alertData);

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe(
        "Endpoint /api/signals/alerts not found"
      );
      expect(response.body.type).toBe("not_found_error");
    });

    test("should return same error for empty body", async () => {
      const response = await request(app).post("/api/signals/alerts").send({});

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe(
        "Endpoint /api/signals/alerts not found"
      );
    });
  });

  describe("GET /api/signals/backtest", () => {
    test("should return endpoint not found error", async () => {
      const response = await request(app).get(
        "/api/signals/backtest?symbol=AAPL&start_date=2023-01-01"
      );

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Endpoint /api/signals/backtest");
      expect(response.body.type).toBe("not_found_error");
    });

    test("should return same error without parameters", async () => {
      const response = await request(app).get("/api/signals/backtest");

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Endpoint /api/signals/backtest");
    });
  });

  describe("GET /api/signals/performance", () => {
    test("should return endpoint not found error", async () => {
      const response = await request(app).get("/api/signals/performance");

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe(
        "Endpoint /api/signals/performance not found"
      );
      expect(response.body.type).toBe("not_found_error");
    });

    test("should return same error with parameters", async () => {
      const response = await request(app).get(
        "/api/signals/performance?timeframe=1M"
      );

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe(
        "Endpoint /api/signals/performance not found"
      );
    });
  });

  describe("DELETE /api/signals/alerts/:alertId", () => {
    test("should return endpoint not found error", async () => {
      const response = await request(app).delete("/api/signals/alerts/123");

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe(
        "Endpoint /api/signals/alerts/123 not found"
      );
      expect(response.body.type).toBe("not_found_error");
    });
  });
});
