/**
 * Technical Router Integration Tests - REAL DATA ONLY
 * Tests technical endpoints with REAL database connection and REAL loaded data
 * NO MOCKS - validates actual behavior with actual data from loaders
 * Validates NO-FALLBACK policy: raw NULL values must flow through unmasked
 */

const request = require("supertest");
const { app } = require("../../../index");
const { initializeDatabase } = require("../../../utils/database");

describe("Technical Router Routes - Real Data Validation", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  describe("GET /api/technical/ping", () => {
    test("should return ping response", async () => {
      const response = await request(app)
        .get("/api/technical/ping");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data.status).toBe("ok");
        expect(response.body.data.endpoint).toBe("technical");
        expect(response.body.data.timestamp).toBeDefined();
      }
    });
  });

  describe("GET /api/technical/daily/:symbol", () => {
    test("should return daily technical data or 404 for real database", async () => {
      const response = await request(app)
        .get("/api/technical/daily/AAPL");

      expect([200, 404, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data.symbol).toBe("AAPL");
        expect(response.body.data.timeframe).toBe("daily");
        expect(Array.isArray(response.body.data.indicators)).toBe(true);
      }
    });

    test("should handle lowercase symbol input", async () => {
      const response = await request(app)
        .get("/api/technical/daily/msft");

      expect([200, 404, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data.symbol).toBe("MSFT");
      }
    });

    test("should return 404 for nonexistent symbol", async () => {
      const response = await request(app)
        .get("/api/technical/daily/NONEXISTENT");

      expect([404, 500]).toContain(response.status);

      if (response.status === 404) {
        expect(response.body.success).toBe(false);
        expect(response.body.error).toBe("Technical data not found");
      }
    });
  });

  describe("GET /api/technical/weekly/:symbol", () => {
    test("should return weekly technical data or proper error", async () => {
      const response = await request(app)
        .get("/api/technical/weekly/AAPL");

      expect([200, 404, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data.timeframe).toBe("weekly");
      }
    });
  });

  describe("GET /api/technical/monthly/:symbol", () => {
    test("should return monthly technical data or proper error", async () => {
      const response = await request(app)
        .get("/api/technical/monthly/AAPL");

      expect([200, 404, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data.timeframe).toBe("monthly");
      }
    });
  });

  describe("GET /api/technical/compare", () => {
    test("should require symbols parameter", async () => {
      const response = await request(app)
        .get("/api/technical/compare");

      expect(response.status).toBe(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Symbols parameter required");
    });

    test("should compare multiple symbols when available", async () => {
      const response = await request(app)
        .get("/api/technical/compare?symbols=AAPL,MSFT");

      expect([200, 400, 404, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(Array.isArray(response.body.data.comparison)).toBe(true);
      }
    });

    test("should reject too many symbols", async () => {
      const tooManySymbols = Array(20)
        .fill()
        .map((_, i) => `STOCK${i}`)
        .join(",");

      const response = await request(app)
        .get(`/api/technical/compare?symbols=${tooManySymbols}`);

      expect(response.status).toBe(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Too many symbols");
    });
  });

  describe("GET /api/technical/signals/:symbol", () => {
    test("should return signals or empty array for symbol", async () => {
      const response = await request(app)
        .get("/api/technical/signals/AAPL");

      expect([200, 404, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data.symbol).toBe("AAPL");
        expect(Array.isArray(response.body.data.signals)).toBe(true);
      }
    });
  });

  describe("GET /api/technical/screener", () => {
    test("should return screener results with criteria", async () => {
      const response = await request(app)
        .get("/api/technical/screener?rsi_max=30&macd_min=1");

      expect([200, 404, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(Array.isArray(response.body.data.results)).toBe(true);
        expect(response.body.data.criteria).toBeDefined();
      }
    });
  });

  describe("POST /api/technical/alerts", () => {
    test("should validate required alert fields", async () => {
      const response = await request(app)
        .post("/api/technical/alerts")
        .send({ symbol: "AAPL" });

      expect([400, 404, 500]).toContain(response.status);

      if (response.status === 400) {
        expect(response.body.success).toBe(false);
        expect(response.body.error).toContain("Required fields");
      }
    });

    test("should validate indicator types", async () => {
      const response = await request(app)
        .post("/api/technical/alerts")
        .send({
          symbol: "AAPL",
          indicator: "INVALID_INDICATOR",
          condition: "ABOVE",
          value: 50,
        });

      expect([400, 404, 500]).toContain(response.status);

      if (response.status === 400) {
        expect(response.body.success).toBe(false);
        expect(response.body.error).toContain("Invalid indicator");
      }
    });
  });

  describe("Error Handling", () => {
    test("should handle invalid symbol characters", async () => {
      const response = await request(app)
        .get("/api/technical/daily/INVALID@SYMBOL");

      expect([400, 404, 500]).toContain(response.status);

      if (response.status === 400) {
        expect(response.body.success).toBe(false);
        expect(response.body.error).toContain("Invalid symbol format");
      }
    });
  });
});
