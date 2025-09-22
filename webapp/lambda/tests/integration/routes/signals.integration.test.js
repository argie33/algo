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
      expect(response.body).toHaveProperty("data");
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty("summary");
      expect(response.body.summary).toHaveProperty("buy_signals");
      expect(response.body.summary).toHaveProperty("sell_signals");

      // Verify loader table structure fields from buy_sell_daily when data exists
      if (response.body.data.length > 0) {
        const signal = response.body.data[0];
        expect(signal).toHaveProperty("symbol");
        expect(signal).toHaveProperty("signal");
        expect(signal).toHaveProperty("date");
        expect(signal).toHaveProperty("confidence");
        expect(signal).toHaveProperty("currentPrice");
      }
    });
  });

  describe("GET /api/signals/:symbol", () => {
    test("should return symbol-specific signals", async () => {
      const response = await request(app).get("/api/signals/AAPL");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty("symbol");
      expect(response.body.symbol).toBe("AAPL");
    });
  });

  describe("GET /api/signals/trending", () => {
    test("should return trending signals with proper structure", async () => {
      const response = await request(app).get("/api/signals/trending");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(Array.isArray(response.body.data)).toBe(true);
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
        expect(signal).toHaveProperty("signal_type");
        expect(signal).toHaveProperty("date");
        expect(signal).toHaveProperty("current_price");
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
    test("should create signal alert successfully", async () => {
      const alertData = {
        symbol: "AAPL",
        signal_type: "BUY",
        min_strength: 0.8,
        notification_method: "email",
      };

      const response = await request(app)
        .post("/api/signals/alerts")
        .send(alertData);

      expect(response.status).toBe(201);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("alert_id");
    });

    test("should handle missing symbol in request body", async () => {
      const response = await request(app).post("/api/signals/alerts").send({});

      expect(response.status).toBe(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("symbol");
    });
  });

  describe("GET /api/signals/backtest", () => {
    test("should return backtest results with proper structure", async () => {
      const response = await request(app).get(
        "/api/signals/backtest?symbol=AAPL&start_date=2023-01-01"
      );

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
    });

    test("should handle missing parameters gracefully", async () => {
      const response = await request(app).get("/api/signals/backtest");

      expect(response.status).toBe(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("required");
    });
  });

  describe("GET /api/signals/performance", () => {
    test("should return performance metrics with proper structure", async () => {
      const response = await request(app).get("/api/signals/performance");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
    });

    test("should handle timeframe parameter correctly", async () => {
      const response = await request(app).get(
        "/api/signals/performance?timeframe=1M"
      );

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
    });
  });

  describe("DELETE /api/signals/alerts/:alertId", () => {
    test("should delete alert successfully", async () => {
      const response = await request(app).delete("/api/signals/alerts/123");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("message");
    });
  });
});
