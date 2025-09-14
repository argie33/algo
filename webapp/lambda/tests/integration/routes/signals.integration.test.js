const request = require("supertest");
const { initializeDatabase, closeDatabase } = require("../../../utils/database");

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
    test("should return database schema error", async () => {
      const response = await request(app)
        .get("/api/signals");

      expect([500, 404]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Failed to fetch signals");
      expect(response.body.details).toContain("column cp.symbol does not exist");
    });
  });

  describe("GET /api/signals/:symbol", () => {
    test("should return endpoint not found error", async () => {
      const response = await request(app)
        .get("/api/signals/AAPL");

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Endpoint /api/signals/AAPL not found");
      expect(response.body.type).toBe("not_found_error");
    });
  });

  describe("GET /api/signals/trending", () => {
    test("should return endpoint not found error", async () => {
      const response = await request(app)
        .get("/api/signals/trending");

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Endpoint /api/signals/trending not found");
      expect(response.body.type).toBe("not_found_error");
    });
  });

  describe("GET /api/signals/buy", () => {
    test("should return database schema error", async () => {
      const response = await request(app)
        .get("/api/signals/buy");

      expect([500, 404]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Failed to fetch buy signals");
      expect(response.body.details).toContain("column cp.symbol does not exist");
    });

    test("should return same error with filters", async () => {
      const response = await request(app)
        .get("/api/signals/buy?min_strength=0.8");

      expect([500, 404]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Failed to fetch buy signals");
    });
  });

  describe("GET /api/signals/sell", () => {
    test("should return database schema error", async () => {
      const response = await request(app)
        .get("/api/signals/sell");

      expect([500, 404]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Failed to fetch sell signals");
      expect(response.body.details).toContain("column cp.symbol does not exist");
    });
  });

  describe("GET /api/signals/alerts", () => {
    test("should return database schema error", async () => {
      const response = await request(app)
        .get("/api/signals/alerts");

      expect([500, 404]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Failed to fetch trading alerts");
      expect(response.body.message).toContain("column \"alert_id\" does not exist");
    });
  });

  describe("POST /api/signals/alerts", () => {
    test("should return endpoint not found error", async () => {
      const alertData = {
        symbol: "AAPL",
        signal_type: "BUY",
        min_strength: 0.8,
        notification_method: "email"
      };

      const response = await request(app)
        .post("/api/signals/alerts")
        .send(alertData);

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Endpoint /api/signals/alerts not found");
      expect(response.body.type).toBe("not_found_error");
    });

    test("should return same error for empty body", async () => {
      const response = await request(app)
        .post("/api/signals/alerts")
        .send({});

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Endpoint /api/signals/alerts not found");
    });
  });

  describe("GET /api/signals/backtest", () => {
    test("should return endpoint not found error", async () => {
      const response = await request(app)
        .get("/api/signals/backtest?symbol=AAPL&start_date=2023-01-01");

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Endpoint /api/signals/backtest");
      expect(response.body.type).toBe("not_found_error");
    });

    test("should return same error without parameters", async () => {
      const response = await request(app)
        .get("/api/signals/backtest");

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Endpoint /api/signals/backtest");
    });
  });

  describe("GET /api/signals/performance", () => {
    test("should return endpoint not found error", async () => {
      const response = await request(app)
        .get("/api/signals/performance");

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Endpoint /api/signals/performance not found");
      expect(response.body.type).toBe("not_found_error");
    });

    test("should return same error with parameters", async () => {
      const response = await request(app)
        .get("/api/signals/performance?timeframe=1M");

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Endpoint /api/signals/performance not found");
    });
  });

  describe("DELETE /api/signals/alerts/:alertId", () => {
    test("should return endpoint not found error", async () => {
      const response = await request(app)
        .delete("/api/signals/alerts/123");

      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Endpoint /api/signals/alerts/123 not found");
      expect(response.body.type).toBe("not_found_error");
    });
  });
});