const request = require("supertest");
const express = require("express");
const metricsRoutes = require("../../../routes/metrics");

// Mock database
const { query } = require("../../../utils/database");
jest.mock("../../../utils/database");

describe("Metrics Routes", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/metrics", metricsRoutes);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /metrics/ping", () => {
    test("should return ping status", async () => {
      const response = await request(app)
        .get("/metrics/ping")
        .expect(200);

      expect(response.body).toMatchObject({
        status: "ok",
        endpoint: "metrics",
        timestamp: expect.any(String)
      });
    });
  });

  describe("GET /metrics/", () => {
    test("should return comprehensive metrics with default pagination", async () => {
      const mockMetrics = {
        rows: [
          {
            symbol: "AAPL",
            company_name: "Apple Inc.",
            sector: "Technology",
            industry: "Consumer Electronics",
            market_cap: 3000000000000,
            current_price: 150.00,
            trailing_pe: 25.5,
            price_to_book: 10.2,
            quality_metric: 0.85,
            earnings_quality_metric: 0.82,
            balance_sheet_metric: 0.88,
            profitability_metric: 0.90,
            management_metric: 0.85,
            piotroski_f_score: 8,
            altman_z_score: 3.2,
            quality_confidence: 0.92,
            value_metric: 0.75,
            composite_metric: 0.80,
            last_updated: new Date().toISOString()
          }
        ]
      };

      const mockCount = { rows: [{ total: "1" }] };

      query
        .mockResolvedValueOnce(mockMetrics)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/metrics/")
        .expect(200);

      expect(response.body).toMatchObject({
        stocks: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            companyName: "Apple Inc.",
            sector: "Technology",
            metrics: expect.objectContaining({
              composite: 0.80,
              quality: 0.85,
              value: 0.75
            })
          })
        ]),
        pagination: {
          totalItems: 1,
          currentPage: 1,
          itemsPerPage: 50,
          totalPages: 1
        }
      });

      expect(query).toHaveBeenCalledTimes(2);
    });

    test("should handle search filtering", async () => {
      const mockMetrics = { rows: [] };
      const mockCount = { rows: [{ total: "0" }] };

      query
        .mockResolvedValueOnce(mockMetrics)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/metrics/")
        .query({ search: "AAPL", limit: 10, page: 1 })
        .expect(200);

      expect(response.body.pagination).toEqual({
        totalItems: 0,
        currentPage: 1,
        itemsPerPage: 10,
        totalPages: 0,
        hasNext: false,
        hasPrev: false
      });

      expect(query).toHaveBeenCalledTimes(2);
      // Verify search parameter was included in the query
      expect(query.mock.calls[0][1]).toContain("%AAPL%");
    });

    test("should handle sector filtering", async () => {
      const mockMetrics = { rows: [] };
      const mockCount = { rows: [{ total: "0" }] };

      query
        .mockResolvedValueOnce(mockMetrics)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/metrics/")
        .query({ sector: "Technology", sortBy: "quality_metric", sortOrder: "desc" })
        .expect(200);

      expect(response.body.stocks).toBeDefined();
      expect(query).toHaveBeenCalledTimes(2);
      // Verify sector parameter was included in the query
      expect(query.mock.calls[0][1]).toContain("Technology");
    });

    test("should handle metric range filtering", async () => {
      const mockMetrics = { rows: [] };
      const mockCount = { rows: [{ total: "0" }] };

      query
        .mockResolvedValueOnce(mockMetrics)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/metrics/")
        .query({ minMetric: 0.7, maxMetric: 0.9 })
        .expect(200);

      expect(response.body.stocks).toBeDefined();
      expect(query).toHaveBeenCalledTimes(2);
      // Verify metric range parameters were included
      expect(query.mock.calls[0][1]).toContain(0.7);
      expect(query.mock.calls[0][1]).toContain(0.9);
    });

    test("should prevent SQL injection in sort parameters", async () => {
      const mockMetrics = { rows: [] };
      const mockCount = { rows: [{ total: "0" }] };

      query
        .mockResolvedValueOnce(mockMetrics)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/metrics/")
        .query({ sortBy: "invalid_column; DROP TABLE stocks;", sortOrder: "malicious" })
        .expect(200);

      expect(response.body.stocks).toBeDefined();
      expect(query).toHaveBeenCalledTimes(2);
      // Should default to safe sort column and order
      expect(query.mock.calls[0][0]).toContain("ORDER BY quality_metric DESC");
    });

    test("should limit page size to maximum", async () => {
      const mockMetrics = { rows: [] };
      const mockCount = { rows: [{ total: "0" }] };

      query
        .mockResolvedValueOnce(mockMetrics)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/metrics/")
        .query({ limit: 1000 }) // Exceeds max of 200
        .expect(200);

      expect(response.body.pagination.itemsPerPage).toBe(200);
      expect(query).toHaveBeenCalledTimes(2);
    });

    test("should handle database errors", async () => {
      query.mockRejectedValueOnce(new Error("Database connection failed"));

      const response = await request(app)
        .get("/metrics/")
        .expect(500);

      expect(response.body).toEqual({
        error: "Failed to fetch metrics",
        message: "Database connection failed",
        timestamp: expect.any(String)
      });
    });
  });

  describe("GET /metrics/:symbol", () => {
    test("should return detailed metrics for specific symbol", async () => {
      const mockDetailedMetrics = {
        rows: [
          {
            symbol: "AAPL",
            company_name: "Apple Inc.",
            sector: "Technology",
            quality_metric: 0.85,
            earnings_quality_metric: 0.82,
            balance_sheet_metric: 0.88,
            profitability_metric: 0.90,
            piotroski_f_score: 8,
            altman_z_score: 3.2,
            value_metric: 0.75,
            composite_metric: 0.80,
            last_updated: new Date().toISOString()
          }
        ]
      };

      query.mockResolvedValueOnce(mockDetailedMetrics);

      const response = await request(app)
        .get("/metrics/AAPL")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          symbol: "AAPL",
          company_name: "Apple Inc.",
          quality_metric: 0.85,
          value_metric: 0.75,
          composite_metric: 0.80,
          piotroski_f_score: 8,
          altman_z_score: 3.2
        })
      });

      expect(query).toHaveBeenCalledTimes(1);
      expect(query.mock.calls[0][1]).toContain("AAPL");
    });

    test("should handle symbol not found", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/metrics/INVALID")
        .expect(404);

      expect(response.body).toEqual({
        success: false,
        error: "Symbol not found",
        message: "No metrics data available for INVALID"
      });
    });

    test("should handle database errors for symbol lookup", async () => {
      query.mockRejectedValueOnce(new Error("Database query failed"));

      const response = await request(app)
        .get("/metrics/AAPL")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to fetch symbol metrics",
        message: "Database query failed"
      });
    });
  });

  describe("GET /metrics/sectors/analysis", () => {
    test("should return sector analysis metrics", async () => {
      const mockSectorAnalysis = {
        rows: [
          {
            sector: "Technology",
            avg_quality_metric: 0.78,
            avg_value_metric: 0.65,
            avg_composite_metric: 0.72,
            stock_count: 145,
            top_performer: "AAPL",
            bottom_performer: "TECH_WORST",
            avg_market_cap: 125000000000
          },
          {
            sector: "Healthcare",
            avg_quality_metric: 0.72,
            avg_value_metric: 0.58,
            avg_composite_metric: 0.65,
            stock_count: 89,
            top_performer: "JNJ",
            bottom_performer: "HEALTH_WORST",
            avg_market_cap: 85000000000
          }
        ]
      };

      query.mockResolvedValueOnce(mockSectorAnalysis);

      const response = await request(app)
        .get("/metrics/sectors/analysis")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            sector: "Technology",
            avg_quality_metric: 0.78,
            avg_composite_metric: 0.72,
            stock_count: 145,
            top_performer: "AAPL"
          }),
          expect.objectContaining({
            sector: "Healthcare",
            avg_quality_metric: 0.72,
            stock_count: 89,
            top_performer: "JNJ"
          })
        ])
      });

      expect(query).toHaveBeenCalledTimes(1);
    });

    test("should handle no sector data", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/metrics/sectors/analysis")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: [],
        message: "No sector analysis data available"
      });
    });

    test("should handle database errors for sector analysis", async () => {
      query.mockRejectedValueOnce(new Error("Sector analysis query failed"));

      const response = await request(app)
        .get("/metrics/sectors/analysis")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to fetch sector analysis",
        message: "Sector analysis query failed"
      });
    });
  });

  describe("GET /metrics/top/:category", () => {
    test("should return top performers by quality", async () => {
      const mockTopQuality = {
        rows: [
          {
            symbol: "AAPL",
            company_name: "Apple Inc.",
            quality_metric: 0.95,
            composite_metric: 0.88,
            sector: "Technology"
          },
          {
            symbol: "MSFT",
            company_name: "Microsoft Corporation",
            quality_metric: 0.92,
            composite_metric: 0.85,
            sector: "Technology"
          }
        ]
      };

      query.mockResolvedValueOnce(mockTopQuality);

      const response = await request(app)
        .get("/metrics/top/quality")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            quality_metric: 0.95,
            sector: "Technology"
          }),
          expect.objectContaining({
            symbol: "MSFT",
            quality_metric: 0.92,
            sector: "Technology"
          })
        ]),
        category: "quality",
        total: 2
      });

      expect(query).toHaveBeenCalledTimes(1);
    });

    test("should return top performers by value", async () => {
      const mockTopValue = {
        rows: [
          {
            symbol: "BRK.A",
            company_name: "Berkshire Hathaway Inc.",
            value_metric: 0.88,
            composite_metric: 0.82,
            sector: "Financial Services"
          }
        ]
      };

      query.mockResolvedValueOnce(mockTopValue);

      const response = await request(app)
        .get("/metrics/top/value")
        .query({ limit: 10 })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "BRK.A",
            value_metric: 0.88,
            sector: "Financial Services"
          })
        ]),
        category: "value",
        total: 1
      });
    });

    test("should return top performers by composite", async () => {
      const mockTopComposite = { rows: [] };

      query.mockResolvedValueOnce(mockTopComposite);

      const response = await request(app)
        .get("/metrics/top/composite")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: [],
        category: "composite",
        total: 0,
        message: "No top performers found"
      });
    });

    test("should handle invalid category", async () => {
      const mockEmpty = { rows: [] };
      query.mockResolvedValueOnce(mockEmpty);

      const response = await request(app)
        .get("/metrics/top/invalid_category")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: [],
        category: "invalid_category",
        total: 0
      });

      // Should still call database but with default quality metric
      expect(query).toHaveBeenCalledTimes(1);
    });

    test("should handle database errors for top performers", async () => {
      query.mockRejectedValueOnce(new Error("Top performers query failed"));

      const response = await request(app)
        .get("/metrics/top/quality")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to fetch top performers",
        message: "Top performers query failed"
      });
    });
  });
});