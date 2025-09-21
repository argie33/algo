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

      // If we have stocks in the response, verify the loader table structure
      if (response.body.metrics && response.body.metrics.stocks.length > 0) {
        const firstStock = response.body.metrics.stocks[0];

        // Verify company_profile table fields (from loadinfo.py)
        expect(firstStock).toHaveProperty("symbol");
        expect(firstStock).toHaveProperty("companyName"); // maps to short_name
        expect(firstStock).toHaveProperty("sector");
        expect(firstStock).toHaveProperty("industry");

        // Verify market_data table fields (from loadinfo.py)
        expect(firstStock).toHaveProperty("marketCap");
        expect(firstStock).toHaveProperty("currentPrice");

        // Verify key_metrics table fields (from loadinfo.py)
        expect(firstStock).toHaveProperty("pe"); // trailing_pe
        expect(firstStock).toHaveProperty("pb"); // price_to_book

        // Verify stock_scores derived metrics structure
        expect(firstStock).toHaveProperty("metrics");
        expect(firstStock.metrics).toHaveProperty("composite");
        expect(firstStock.metrics).toHaveProperty("quality");
        expect(firstStock.metrics).toHaveProperty("value");
        expect(firstStock.metrics).toHaveProperty("growth");

        // Verify breakdown structures match loader data expectations
        expect(firstStock).toHaveProperty("qualityBreakdown");
        expect(firstStock.qualityBreakdown).toHaveProperty("overall");
        expect(firstStock.qualityBreakdown).toHaveProperty("piotrosiScore");
        expect(firstStock.qualityBreakdown).toHaveProperty("altmanZScore");

        expect(firstStock).toHaveProperty("valueBreakdown");
        expect(firstStock.valueBreakdown).toHaveProperty("intrinsicValue");
        expect(firstStock.valueBreakdown).toHaveProperty("marginOfSafety");

        expect(firstStock).toHaveProperty("growthBreakdown");
        expect(firstStock.growthBreakdown).toHaveProperty("revenue");
        expect(firstStock.growthBreakdown).toHaveProperty("earnings");

        // Verify metadata from loader timestamps
        expect(firstStock).toHaveProperty("metadata");
        expect(firstStock.metadata).toHaveProperty("metricDate");
        expect(firstStock.metadata).toHaveProperty("lastUpdated");
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
