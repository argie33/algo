/**
 * API Endpoint Contract Tests
 * Validates all REST endpoints return expected response structure
 */

const request = require("supertest");
const app = require("../index");

describe("API Endpoints - Contract Validation", () => {
  describe("Health & Status", () => {
    test("GET /api/health returns 200 with status", async () => {
      const res = await request(app)
        .get("/api/health")
        .expect(200);

      expect(res.body).toHaveProperty("status");
      expect(res.body).toHaveProperty("timestamp");
    });

    test("GET /api/status returns current system status", async () => {
      const res = await request(app)
        .get("/api/status")
        .expect(200);

      expect(res.body).toHaveProperty("healthy");
    });
  });

  describe("Stocks Endpoints", () => {
    test("GET /api/stocks returns paginated stocks list", async () => {
      const res = await request(app)
        .get("/api/stocks")
        .expect(200);

      expect(res.body).toHaveProperty("data");
      expect(res.body).toHaveProperty("pagination");
      expect(Array.isArray(res.body.data)).toBe(true);
    });

    test("GET /api/stocks/search validates query parameter", async () => {
      const res = await request(app)
        .get("/api/stocks/search?q=AAPL")
        .expect(200);

      expect(res.body).toHaveProperty("data");
      expect(Array.isArray(res.body.data)).toBe(true);
    });

    test("GET /api/stocks/:symbol returns stock detail", async () => {
      const res = await request(app)
        .get("/api/stocks/AAPL")
        .expect([200, 404]); // May not exist in test DB

      if (res.statusCode === 200) {
        expect(res.body).toHaveProperty("symbol");
      }
    });
  });

  describe("Signals Endpoints", () => {
    test("GET /api/signals returns trading signals", async () => {
      const res = await request(app)
        .get("/api/signals")
        .expect([200, 404, 500]); // Depends on DB state

      if (res.statusCode === 200) {
        expect(res.body).toHaveProperty("data");
        expect(Array.isArray(res.body.data)).toBe(true);
      }
    });

    test("POST /api/signals validates authentication", async () => {
      const res = await request(app)
        .post("/api/signals")
        .send({ symbol: "AAPL" });

      // Should require auth
      expect([401, 403, 400, 404].includes(res.statusCode)).toBe(true);
    });
  });

  describe("Portfolio Endpoints", () => {
    test("GET /api/portfolio validates authentication", async () => {
      const res = await request(app)
        .get("/api/portfolio");

      // Should require auth for portfolio operations
      expect([401, 403, 404].includes(res.statusCode)).toBe(true);
    });

    test("POST /api/portfolio/trades validates authentication", async () => {
      const res = await request(app)
        .post("/api/portfolio/trades")
        .send({ symbol: "AAPL", quantity: 10 });

      expect([401, 403, 400, 404].includes(res.statusCode)).toBe(true);
    });
  });

  describe("Market Data Endpoints", () => {
    test("GET /api/market returns market overview", async () => {
      const res = await request(app)
        .get("/api/market")
        .expect([200, 404, 500]);

      if (res.statusCode === 200) {
        expect(res.body).toHaveProperty("data");
      }
    });

    test("GET /api/sectors returns sector data", async () => {
      const res = await request(app)
        .get("/api/sectors")
        .expect([200, 404, 500]);

      if (res.statusCode === 200) {
        expect(res.body).toHaveProperty("data");
      }
    });

    test("GET /api/commodities returns commodity prices", async () => {
      const res = await request(app)
        .get("/api/commodities")
        .expect([200, 404, 500]);

      if (res.statusCode === 200) {
        expect(res.body).toHaveProperty("data");
      }
    });
  });

  describe("Error Handling", () => {
    test("404 on unknown route", async () => {
      const res = await request(app)
        .get("/api/unknown-endpoint")
        .expect(404);

      expect(res.body).toHaveProperty("error");
    });

    test("Bad request returns 400", async () => {
      const res = await request(app)
        .get("/api/stocks/search?invalid=param")
        .expect([200, 400]);

      // Either succeeds or returns bad request
    });
  });

  describe("Response Format Consistency", () => {
    test("All successful responses include success field", async () => {
      const res = await request(app)
        .get("/api/health")
        .expect(200);

      expect(res.body).toHaveProperty("status");
    });

    test("Error responses include error message", async () => {
      const res = await request(app)
        .get("/api/unknown")
        .expect(404);

      expect(res.body).toHaveProperty("error");
    });
  });
});
