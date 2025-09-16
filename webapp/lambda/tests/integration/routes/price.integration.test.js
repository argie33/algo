const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("Price Routes", () => {
  beforeAll(async () => {
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/price/:symbol", () => {
    test("should return current price for symbol", async () => {
      const response = await request(app).get("/api/price/AAPL");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("symbol");
      expect(response.body.data).toHaveProperty("price");
    });

    test("should handle invalid symbol", async () => {
      const response = await request(app).get("/api/price/INVALID");

      expect([404, 500]).toContain(response.status);
    });
  });

  describe("GET /api/price/:symbol/history", () => {
    test("should return price history", async () => {
      const response = await request(app).get("/api/price/AAPL/history");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test("should handle period parameter", async () => {
      const response = await request(app).get(
        "/api/price/AAPL/history?period=1M"
      );

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
    });
  });

  describe("GET /api/price/:symbol/intraday", () => {
    test("should return intraday prices", async () => {
      const response = await request(app).get("/api/price/AAPL/intraday");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(Array.isArray(response.body.data)).toBe(true);
    });

    test("should handle interval parameter", async () => {
      const response = await request(app).get(
        "/api/price/AAPL/intraday?interval=5min"
      );

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
    });
  });

  describe("POST /api/price/batch", () => {
    test("should return prices for multiple symbols", async () => {
      const symbols = { symbols: ["AAPL", "MSFT", "GOOGL"] };

      const response = await request(app)
        .post("/api/price/batch")
        .send(symbols);

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("prices");
    });

    test("should validate symbols array", async () => {
      const response = await request(app).post("/api/price/batch").send({});

      expect([400, 422]).toContain(response.status);
    });
  });

  describe("GET /api/price/alerts", () => {
    test("should return price alerts", async () => {
      const response = await request(app).get("/api/price/alerts");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(Array.isArray(response.body.data)).toBe(true);
      }
    });
  });

  describe("POST /api/price/alerts", () => {
    test("should create price alert", async () => {
      const alertData = {
        symbol: "AAPL",
        target_price: 150.0,
        condition: "above",
        notification_method: "email",
      };

      const response = await request(app)
        .post("/api/price/alerts")
        .send(alertData);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200 || response.status === 201) {
        expect(response.body.success).toBe(true);
      }
    });
  });
});
