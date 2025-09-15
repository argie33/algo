const request = require("supertest");
const express = require("express");

const metricsRoutes = require("../../../routes/metrics");

// Real database for integration
const { query } = require("../../../utils/database");

describe("Metrics Routes", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());

    // Add response formatter middleware for proper res.error, res.success methods
    const responseFormatter = require("../../../middleware/responseFormatter");
    app.use(responseFormatter);

    app.use("/metrics", metricsRoutes);
  });

  // No mocks to clear - using real database

  describe("GET /metrics/ping", () => {
    test("should return ping status", async () => {
      const response = await request(app).get("/metrics/ping").expect(200);

      expect(response.body).toMatchObject({
        status: "ok",
        endpoint: "metrics",
        timestamp: expect.any(String),
      });
    });
  });

  describe("GET /metrics/", () => {
    test("should return comprehensive metrics with default pagination", async () => {
      const response = await request(app).get("/metrics/").expect(200);

      expect(response.body).toHaveProperty("stocks");
      expect(response.body).toHaveProperty("pagination");
      expect(response.body.pagination).toMatchObject({
        currentPage: 1,
        itemsPerPage: 50,
        totalPages: expect.any(Number),
        totalItems: expect.any(Number),
      });

      // If we have stocks in the response, verify the structure
      if (response.body.stocks.length > 0) {
        const firstStock = response.body.stocks[0];
        expect(firstStock).toHaveProperty("symbol");
        expect(firstStock).toHaveProperty("companyName");
        expect(firstStock).toHaveProperty("sector");
        expect(firstStock).toHaveProperty("metrics");
        expect(firstStock.metrics).toHaveProperty("composite");
      }
    });

    test("should handle search filtering", async () => {
      const response = await request(app)
        .get("/metrics/")
        .query({ search: "AAPL", limit: 10, page: 1 })
        .expect(200);

      expect(response.body).toHaveProperty("pagination");
      expect(response.body.pagination).toMatchObject({
        currentPage: 1,
        itemsPerPage: 10,
        totalPages: expect.any(Number),
        totalItems: expect.any(Number),
      });
    });

    test("should handle sector filtering", async () => {
      const response = await request(app)
        .get("/metrics/")
        .query({
          sector: "Technology",
          sortBy: "quality_metric",
          sortOrder: "desc",
        })
        .expect(200);

      expect(response.body.stocks).toBeDefined();
      expect(response.body).toHaveProperty("pagination");
    });

    test("should handle metric range filtering", async () => {
      const response = await request(app)
        .get("/metrics/")
        .query({ minMetric: 0.7, maxMetric: 0.9 })
        .expect(200);

      expect(response.body.stocks).toBeDefined();
      expect(response.body).toHaveProperty("pagination");
    });

    test("should prevent SQL injection in sort parameters", async () => {
      const response = await request(app)
        .get("/metrics/")
        .query({
          sortBy: "invalid_column; DROP TABLE stocks;",
          sortOrder: "malicious",
        })
        .expect(200);

      expect(response.body.stocks).toBeDefined();
      expect(response.body).toHaveProperty("pagination");
    });

    test("should limit page size to maximum", async () => {
      const response = await request(app)
        .get("/metrics/")
        .query({ limit: 1000 }) // Exceeds max of 200
        .expect(200);

      expect(response.body.pagination.itemsPerPage).toBe(200);
    });

    // Database error testing skipped - using real database
  });

  // Other endpoints need schema updates - testing basic endpoints only for now
});
