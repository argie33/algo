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
            industry: "Consumer Electronics",
            market_cap: 3000000000000,
            current_price: 150.00,
            trailing_pe: 25.5,
            price_to_book: 10.2,
            dividend_yield: 0.5,
            return_on_equity: 15.2,
            return_on_assets: 8.1,
            debt_to_equity: 0.3,
            free_cash_flow: 92000000000,
            quality_metric: 0.85,
            earnings_quality_metric: 0.82,
            balance_sheet_metric: 0.88,
            profitability_metric: 0.90,
            management_metric: 0.85,
            piotroski_f_score: 8,
            altman_z_score: 3.2,
            accruals_ratio: 0.05,
            cash_conversion_ratio: 0.95,
            shareholder_yield: 0.02,
            value_metric: 0.75,
            multiples_metric: 0.70,
            intrinsic_value_metric: 0.80,
            relative_value_metric: 0.75,
            dcf_intrinsic_value: 175.50,
            dcf_margin_of_safety: 0.15,
            ddm_value: 160.00,
            rim_value: 170.00,
            current_pe: 24.8,
            current_pb: 9.8,
            current_ev_ebitda: 18.5,
            confidence_score: 0.92,
            data_completeness: 0.98,
            market_cap_tier: "large",
            date: new Date().toISOString().split('T')[0],
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
          }
        ]
      };

      const mockSectorBenchmark = {
        rows: [
          {
            avg_quality: 0.72,
            avg_value: 0.68,
            peer_count: 25
          }
        ]
      };

      query
        .mockResolvedValueOnce(mockDetailedMetrics)
        .mockResolvedValueOnce(mockSectorBenchmark);

      const response = await request(app)
        .get("/metrics/AAPL")
        .expect(200);

      expect(response.body).toMatchObject({
        symbol: "AAPL",
        companyName: "Apple Inc.",
        sector: "Technology",
        industry: "Consumer Electronics",
        currentData: expect.objectContaining({
          marketCap: 3000000000000,
          currentPrice: 150.00
        }),
        metrics: expect.objectContaining({
          composite: expect.any(Number),
          quality: 0.85,
          value: 0.75
        }),
        detailedBreakdown: expect.objectContaining({
          quality: expect.objectContaining({
            overall: 0.85,
            scores: expect.objectContaining({
              piotrosiScore: 8,
              altmanZScore: 3.2
            })
          })
        }),
        sectorComparison: expect.objectContaining({
          sectorName: "Technology",
          peerCount: 25
        }),
        interpretation: expect.objectContaining({
          overall: expect.any(String),
          recommendation: expect.any(String)
        })
      });

      expect(query).toHaveBeenCalledTimes(2);
      expect(query.mock.calls[0][1]).toContain("AAPL");
    });

    test("should handle symbol not found", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/metrics/INVALID")
        .expect(404);

      expect(response.body).toEqual({
        error: "Symbol not found or no metrics available",
        symbol: "INVALID",
        timestamp: expect.any(String)
      });
    });

    test("should handle database errors for symbol lookup", async () => {
      query.mockRejectedValueOnce(new Error("Database query failed"));

      const response = await request(app)
        .get("/metrics/AAPL")
        .expect(500);

      expect(response.body).toMatchObject({
        error: "Failed to fetch detailed metrics",
        message: "Database query failed",
        symbol: "AAPL",
        timestamp: expect.any(String)
      });
    });
  });

  describe("GET /metrics/sectors/analysis", () => {
    test("should return sector analysis metrics", async () => {
      const mockSectorAnalysis = {
        rows: [
          {
            sector: "Technology",
            stock_count: 145,
            avg_quality: 0.78,
            avg_value: 0.65,
            avg_composite: 0.72,
            quality_volatility: 0.15,
            max_quality: 0.95,
            min_quality: 0.45,
            last_updated: new Date().toISOString()
          },
          {
            sector: "Healthcare",
            stock_count: 89,
            avg_quality: 0.72,
            avg_value: 0.58,
            avg_composite: 0.65,
            quality_volatility: 0.18,
            max_quality: 0.88,
            min_quality: 0.42,
            last_updated: new Date().toISOString()
          }
        ]
      };

      query.mockResolvedValueOnce(mockSectorAnalysis);

      const response = await request(app)
        .get("/metrics/sectors/analysis")
        .expect(200);

      expect(response.body).toMatchObject({
        sectors: expect.arrayContaining([
          expect.objectContaining({
            sector: "Technology",
            stockCount: 145,
            averageMetrics: expect.objectContaining({
              composite: "0.7200",
              quality: "0.7800",
              value: "0.6500"
            }),
            metricRange: expect.objectContaining({
              min: "0.4500",
              max: "0.9500",
              volatility: "0.1500"
            })
          }),
          expect.objectContaining({
            sector: "Healthcare",
            stockCount: 89,
            averageMetrics: expect.objectContaining({
              quality: "0.7200"
            })
          })
        ]),
        summary: expect.objectContaining({
          totalSectors: 2,
          bestPerforming: expect.objectContaining({
            sector: "Technology"
          }),
          averageQuality: expect.any(String)
        })
      });

      expect(query).toHaveBeenCalledTimes(1);
    });

    test("should handle no sector data", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/metrics/sectors/analysis")
        .expect(200);

      expect(response.body).toMatchObject({
        sectors: [],
        summary: expect.objectContaining({
          totalSectors: 0
        }),
        timestamp: expect.any(String)
      });
    });

    test("should handle database errors for sector analysis", async () => {
      query.mockRejectedValueOnce(new Error("Sector analysis query failed"));

      const response = await request(app)
        .get("/metrics/sectors/analysis")
        .expect(500);

      expect(response.body).toMatchObject({
        error: "Failed to fetch sector analysis",
        message: "Sector analysis query failed",
        timestamp: expect.any(String)
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
            sector: "Technology",
            market_cap: 3000000000000,
            current_price: 150.00,
            quality_metric: 0.95,
            value_metric: 0.80,
            category_metric: 0.95,
            confidence_score: 0.92,
            updated_at: new Date().toISOString()
          },
          {
            symbol: "MSFT",
            company_name: "Microsoft Corporation",
            sector: "Technology",
            market_cap: 2800000000000,
            current_price: 380.00,
            quality_metric: 0.92,
            value_metric: 0.75,
            category_metric: 0.92,
            confidence_score: 0.89,
            updated_at: new Date().toISOString()
          }
        ]
      };

      query.mockResolvedValueOnce(mockTopQuality);

      const response = await request(app)
        .get("/metrics/top/quality")
        .expect(200);

      expect(response.body).toMatchObject({
        category: "QUALITY",
        topStocks: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            qualityMetric: 0.95,
            sector: "Technology",
            categoryMetric: 0.95
          }),
          expect.objectContaining({
            symbol: "MSFT",
            qualityMetric: 0.92,
            sector: "Technology",
            categoryMetric: 0.92
          })
        ]),
        summary: expect.objectContaining({
          count: 2,
          averageMetric: expect.any(String),
          highestMetric: expect.any(String)
        })
      });

      expect(query).toHaveBeenCalledTimes(1);
    });

    test("should return top performers by value", async () => {
      const mockTopValue = {
        rows: [
          {
            symbol: "BRK.A",
            company_name: "Berkshire Hathaway Inc.",
            sector: "Financial Services",
            market_cap: 650000000000,
            current_price: 425000.00,
            quality_metric: 0.75,
            value_metric: 0.88,
            category_metric: 0.88,
            confidence_score: 0.85,
            updated_at: new Date().toISOString()
          }
        ]
      };

      query.mockResolvedValueOnce(mockTopValue);

      const response = await request(app)
        .get("/metrics/top/value")
        .query({ limit: 10 })
        .expect(200);

      expect(response.body).toMatchObject({
        category: "VALUE",
        topStocks: expect.arrayContaining([
          expect.objectContaining({
            symbol: "BRK.A",
            valueMetric: 0.88,
            sector: "Financial Services",
            categoryMetric: 0.88
          })
        ]),
        summary: expect.objectContaining({
          count: 1,
          averageMetric: expect.any(String)
        })
      });
    });

    test("should return top performers by composite", async () => {
      const mockTopComposite = { rows: [] };

      query.mockResolvedValueOnce(mockTopComposite);

      const response = await request(app)
        .get("/metrics/top/composite")
        .expect(200);

      expect(response.body).toEqual({
        category: "COMPOSITE",
        topStocks: [],
        summary: {
          count: 0,
          averageMetric: 0,
          highestMetric: 0,
          lowestMetric: 0
        },
        timestamp: expect.any(String)
      });
    });

    test("should handle invalid category", async () => {
      const response = await request(app)
        .get("/metrics/top/invalid_category")
        .expect(400);

      expect(response.body).toMatchObject({
        error: "Invalid category",
        validCategories: ["composite", "quality", "value"],
        timestamp: expect.any(String)
      });

      // Should not call database for invalid category
      expect(query).not.toHaveBeenCalled();
    });

    test("should handle database errors for top performers", async () => {
      query.mockRejectedValueOnce(new Error("Top performers query failed"));

      const response = await request(app)
        .get("/metrics/top/quality")
        .expect(500);

      expect(response.body).toMatchObject({
        error: "Failed to fetch top stocks",
        message: "Top performers query failed",
        timestamp: expect.any(String)
      });
    });
  });
});