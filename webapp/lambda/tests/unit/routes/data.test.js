const request = require("supertest");
const express = require("express");
const dataRouter = require("../../../routes/data");

// Mock dependencies
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn().mockResolvedValue({}),
  healthCheck: jest.fn(),
  getPool: jest.fn(),
  closeDatabase: jest.fn(),
  transaction: jest.fn(),
}));

const { query } = require("../../../utils/database");

describe("Data Routes", () => {
  let app;

  beforeEach(() => {
    app = express();
    app.use(express.json());
    
    // Add response formatter middleware
    app.use((req, res, next) => {
      res.success = (data, status = 200) => {
        res.status(status).json({
          success: true,
          data: data
        });
      };
      
      res.error = (message, status = 500) => {
        res.status(status).json({
          success: false,
          error: message
        });
      };
      
      next();
    });
    
    app.use("/data", dataRouter);
    jest.clearAllMocks();
  });

  describe("GET /data/eps-revisions", () => {
    test("should return EPS revisions data with pagination", async () => {
      const mockRevisions = {
        rows: [
          {
            symbol: "AAPL",
            period: "Q3 2024",
            current_estimate: 1.25,
            seven_days_ago: 1.23,
            thirty_days_ago: 1.20,
            sixty_days_ago: 1.18,
            ninety_days_ago: 1.15,
            revision_direction: "up",
            fetched_at: new Date().toISOString()
          }
        ]
      };

      const mockCount = { rows: [{ total: "50" }] };

      query
        .mockResolvedValueOnce(mockRevisions)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/data/eps-revisions")
        .query({ page: 1, limit: 25 })
        .expect(200);

      expect(response.body).toMatchObject({
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            period: "Q3 2024",
            current_estimate: 1.25,
            revision_direction: "up"
          })
        ]),
        pagination: {
          page: 1,
          limit: 25,
          total: 50,
          totalPages: 2,
          hasNext: true,
          hasPrev: false
        }
      });
      expect(query).toHaveBeenCalledTimes(2);
    });

    test("should filter by symbol", async () => {
      const mockRevisions = {
        rows: [
          {
            symbol: "AAPL",
            period: "Q3 2024",
            current_estimate: 1.25,
            revision_direction: "up"
          }
        ]
      };
      const mockCount = { rows: [{ total: "10" }] };

      query
        .mockResolvedValueOnce(mockRevisions)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/data/eps-revisions")
        .query({ symbol: "AAPL" })
        .expect(200);

      expect(response.body.data[0].symbol).toBe("AAPL");
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("WHERE symbol = $1"),
        expect.arrayContaining(["AAPL", 25, 0])
      );
    });

    test("should handle no data found", async () => {
      query
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [{ total: "0" }] });

      const response = await request(app).get("/data/eps-revisions").expect(404);

      expect(response.body).toEqual({
        error: "No data found for this query"
      });
    });

    test("should handle database errors", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app).get("/data/eps-revisions").expect(500);

      expect(response.body).toMatchObject({
        error: "Database error",
        details: "Database connection failed"
      });
    });
  });

  describe("GET /data/eps-trend", () => {
    test("should return EPS trend data with pagination", async () => {
      const mockTrend = {
        rows: [
          {
            symbol: "MSFT",
            period: "Q4 2024",
            current_estimate: 2.50,
            seven_days_ago: 2.48,
            thirty_days_ago: 2.45,
            sixty_days_ago: 2.40,
            ninety_days_ago: 2.35,
            number_of_revisions_up: 5,
            number_of_revisions_down: 2,
            fetched_at: new Date().toISOString()
          }
        ]
      };

      const mockCount = { rows: [{ total: "75" }] };

      query
        .mockResolvedValueOnce(mockTrend)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app).get("/data/eps-trend").expect(200);

      expect(response.body).toMatchObject({
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "MSFT",
            period: "Q4 2024",
            current_estimate: 2.50,
            number_of_revisions_up: 5,
            number_of_revisions_down: 2
          })
        ]),
        pagination: {
          page: 1,
          limit: 25,
          total: 75,
          totalPages: 3,
          hasNext: true,
          hasPrev: false
        }
      });
    });

    test("should filter by symbol for trend data", async () => {
      const mockTrend = { rows: [{ symbol: "MSFT", period: "Q4 2024" }] };
      const mockCount = { rows: [{ total: "8" }] };

      query
        .mockResolvedValueOnce(mockTrend)
        .mockResolvedValueOnce(mockCount);

      const _response = await request(app)
        .get("/data/eps-trend")
        .query({ symbol: "msft" })
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("WHERE symbol = $1"),
        expect.arrayContaining(["MSFT", 25, 0])
      );
    });
  });

  describe("GET /data/growth-estimates", () => {
    test("should return growth estimates with analyst data", async () => {
      const mockGrowth = {
        rows: [
          {
            symbol: "GOOGL",
            period: "2024",
            growth_estimate: 0.15,
            number_of_analysts: 12,
            low_estimate: 0.10,
            high_estimate: 0.20,
            mean_estimate: 0.15,
            fetched_at: new Date().toISOString()
          }
        ]
      };

      const mockCount = { rows: [{ total: "100" }] };

      query
        .mockResolvedValueOnce(mockGrowth)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app).get("/data/growth-estimates").expect(200);

      expect(response.body).toMatchObject({
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "GOOGL",
            period: "2024",
            growth_estimate: 0.15,
            number_of_analysts: 12,
            low_estimate: 0.10,
            high_estimate: 0.20,
            mean_estimate: 0.15
          })
        ]),
        pagination: expect.objectContaining({
          total: 100,
          totalPages: 4
        })
      });
    });
  });

  describe("GET /data/economic", () => {
    test("should return economic data with pagination", async () => {
      const mockEconomic = {
        rows: [
          {
            series_id: "GDP",
            date: "2024-01-01",
            value: 25000.5,
            title: "Gross Domestic Product",
            units: "Billions of Dollars",
            frequency: "Quarterly",
            last_updated: new Date().toISOString()
          }
        ]
      };

      const mockCount = { rows: [{ total: "200" }] };

      query
        .mockResolvedValueOnce(mockEconomic)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app).get("/data/economic").expect(200);

      expect(response.body).toMatchObject({
        data: expect.arrayContaining([
          expect.objectContaining({
            series_id: "GDP",
            title: "Gross Domestic Product",
            value: 25000.5,
            units: "Billions of Dollars",
            frequency: "Quarterly"
          })
        ]),
        pagination: expect.objectContaining({
          total: 200
        })
      });
    });

    test("should filter by series ID", async () => {
      const mockEconomic = { rows: [{ series_id: "GDP", value: 25000.5 }] };
      const mockCount = { rows: [{ total: "25" }] };

      query
        .mockResolvedValueOnce(mockEconomic)
        .mockResolvedValueOnce(mockCount);

      const _response = await request(app)
        .get("/data/economic")
        .query({ series: "GDP" })
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("WHERE series_id = $1"),
        expect.arrayContaining(["GDP", 25, 0])
      );
    });
  });

  describe("GET /data/economic/data", () => {
    test("should return economic data in simple format", async () => {
      const mockEconomicData = {
        rows: [
          {
            series_id: "GDP",
            date: "2024-01-01",
            value: 25000.5
          },
          {
            series_id: "UNEMPLOYMENT",
            date: "2024-01-01",
            value: 3.7
          }
        ]
      };

      query.mockResolvedValue(mockEconomicData);

      const response = await request(app)
        .get("/data/economic/data")
        .query({ limit: 50 })
        .expect(200);

      expect(response.body).toEqual({
        data: expect.arrayContaining([
          {
            series_id: "GDP",
            date: "2024-01-01",
            value: 25000.5
          },
          {
            series_id: "UNEMPLOYMENT",
            date: "2024-01-01",
            value: 3.7
          }
        ]),
        count: 2,
        limit: 50,
        timestamp: expect.any(String)
      });
    });

    test("should enforce maximum limit of 100", async () => {
      const mockData = { rows: [{ series_id: "GDP", date: "2024-01-01", value: 25000.5 }] };
      query.mockResolvedValue(mockData);

      const _response = await request(app)
        .get("/data/economic/data")
        .query({ limit: 200 })
        .expect(200);

      expect(query).toHaveBeenCalledWith(expect.any(String), [100]);
    });
  });

  describe("GET /data/naaim", () => {
    test("should return NAAIM exposure data", async () => {
      const mockNaaim = {
        rows: [
          {
            date: "2024-01-01",
            naaim_number_mean: 65.5,
            bearish: 15.2,
            bullish: 84.8
          }
        ]
      };

      query.mockResolvedValue(mockNaaim);

      const response = await request(app).get("/data/naaim").expect(200);

      expect(response.body).toEqual({
        data: expect.arrayContaining([
          {
            date: "2024-01-01",
            naaim_number_mean: 65.5,
            bearish: 15.2,
            bullish: 84.8
          }
        ]),
        count: 1
      });
    });

    test("should handle custom limit for NAAIM data", async () => {
      const mockData = { rows: [{ date: "2024-01-01", naaim_number_mean: 65.5 }] };
      query.mockResolvedValue(mockData);

      const _response = await request(app)
        .get("/data/naaim")
        .query({ limit: 100 })
        .expect(200);

      expect(query).toHaveBeenCalledWith(expect.any(String), [100]);
    });
  });

  describe("GET /data/fear-greed", () => {
    test("should return Fear & Greed Index data", async () => {
      const mockFearGreed = {
        rows: [
          {
            date: "2024-01-01",
            index_value: 75,
            rating: "Greed",
            fetched_at: new Date().toISOString()
          }
        ]
      };

      query.mockResolvedValue(mockFearGreed);

      const response = await request(app).get("/data/fear-greed").expect(200);

      expect(response.body).toEqual({
        data: expect.arrayContaining([
          {
            date: "2024-01-01",
            index_value: 75,
            rating: "Greed",
            fetched_at: expect.any(String)
          }
        ]),
        count: 1
      });
    });
  });

  describe("GET /data/validation-summary", () => {
    test("should return validation summary for all tables", async () => {
      const mockSummary = {
        rows: [
          {
            table_name: "stock_symbols",
            record_count: "5000",
            last_updated: null
          },
          {
            table_name: "earnings_estimates",
            record_count: "2500",
            last_updated: new Date().toISOString()
          },
          {
            table_name: "technical_data_daily",
            record_count: "100000",
            last_updated: new Date().toISOString()
          }
        ]
      };

      query.mockResolvedValue(mockSummary);

      const response = await request(app).get("/data/validation-summary").expect(200);

      expect(response.body).toEqual({
        summary: expect.arrayContaining([
          expect.objectContaining({
            table_name: "stock_symbols",
            record_count: "5000"
          }),
          expect.objectContaining({
            table_name: "earnings_estimates",
            record_count: "2500",
            last_updated: expect.any(String)
          }),
          expect.objectContaining({
            table_name: "technical_data_daily",
            record_count: "100000"
          })
        ]),
        generated_at: expect.any(String)
      });
    });
  });

  describe("GET /data/financials/:symbol", () => {
    test("should return comprehensive financial data for symbol", async () => {
      const mockFinancialData = {
        rows: [
          {
            date: "2023-12-31",
            item_name: "Total Revenue",
            value: 25000000000
          },
          {
            date: "2023-12-31",
            item_name: "Net Income",
            value: 5000000000
          }
        ]
      };

      // Mock all 8 financial statement queries
      for (let i = 0; i < 8; i++) {
        query.mockResolvedValueOnce(mockFinancialData);
      }

      const response = await request(app).get("/data/financials/AAPL").expect(200);

      expect(response.body).toMatchObject({
        symbol: "AAPL",
        data: expect.objectContaining({
          "TTM Income Statement": expect.arrayContaining([
            expect.objectContaining({
              date: "2023-12-31",
              items: expect.objectContaining({
                "Total Revenue": 25000000000,
                "Net Income": 5000000000
              })
            })
          ]),
          "TTM Cash Flow": expect.any(Array),
          "Annual Income Statement": expect.any(Array),
          "Annual Cash Flow": expect.any(Array),
          "Balance Sheet": expect.any(Array),
          "Quarterly Income Statement": expect.any(Array),
          "Quarterly Cash Flow": expect.any(Array),
          "Quarterly Balance Sheet": expect.any(Array)
        }),
        limit: 10
      });
      expect(query).toHaveBeenCalledTimes(8);
    });

    test("should handle missing tables gracefully", async () => {
      // First query succeeds, rest fail
      query
        .mockResolvedValueOnce({ rows: [{ date: "2023-12-31", item_name: "Revenue", value: 1000 }] })
        .mockRejectedValue(new Error("Table does not exist"))
        .mockRejectedValue(new Error("Table does not exist"))
        .mockRejectedValue(new Error("Table does not exist"))
        .mockRejectedValue(new Error("Table does not exist"))
        .mockRejectedValue(new Error("Table does not exist"))
        .mockRejectedValue(new Error("Table does not exist"))
        .mockRejectedValue(new Error("Table does not exist"));

      const response = await request(app).get("/data/financials/AAPL").expect(200);

      expect(response.body.symbol).toBe("AAPL");
      expect(response.body.data["TTM Income Statement"]).toHaveLength(1);
      expect(response.body.data["TTM Cash Flow"]).toEqual([]);
    });

    test("should handle symbol with no data", async () => {
      // All queries return empty results
      for (let i = 0; i < 8; i++) {
        query.mockResolvedValueOnce({ rows: [] });
      }

      const response = await request(app).get("/data/financials/NONEXISTENT").expect(404);

      expect(response.body).toEqual({
        error: "No data found for this query"
      });
    });
  });

  describe("GET /data/financial-metrics", () => {
    test("should return available financial metrics across all tables", async () => {
      const mockMetrics = {
        rows: [
          {
            item_name: "Total Revenue",
            occurrence_count: "500"
          },
          {
            item_name: "Net Income",
            occurrence_count: "500"
          },
          {
            item_name: "Total Assets",
            occurrence_count: "300"
          }
        ]
      };

      // Mock all 8 table queries
      for (let i = 0; i < 8; i++) {
        query.mockResolvedValueOnce(mockMetrics);
      }

      const response = await request(app).get("/data/financial-metrics").expect(200);

      expect(response.body).toMatchObject({
        metrics: expect.objectContaining({
          ttm_income_stmt: expect.arrayContaining([
            expect.objectContaining({
              item_name: "Total Revenue",
              occurrence_count: "500"
            })
          ]),
          ttm_cashflow: expect.any(Array),
          income_stmt: expect.any(Array),
          cash_flow: expect.any(Array),
          balance_sheet: expect.any(Array),
          quarterly_income_stmt: expect.any(Array),
          quarterly_cashflow: expect.any(Array),
          quarterly_balance_sheet: expect.any(Array)
        }),
        tables: expect.arrayContaining([
          "ttm_income_stmt",
          "ttm_cashflow",
          "income_stmt",
          "cash_flow",
          "balance_sheet",
          "quarterly_income_stmt",
          "quarterly_cashflow",
          "quarterly_balance_sheet"
        ]),
        generated_at: expect.any(String)
      });
      expect(query).toHaveBeenCalledTimes(8);
    });

    test("should handle missing tables gracefully", async () => {
      // Some queries succeed, others fail
      query
        .mockResolvedValueOnce({ rows: [{ item_name: "Revenue", occurrence_count: "100" }] })
        .mockRejectedValueOnce(new Error("Table does not exist"))
        .mockResolvedValueOnce({ rows: [{ item_name: "Assets", occurrence_count: "50" }] })
        .mockRejectedValueOnce(new Error("Table does not exist"))
        .mockRejectedValueOnce(new Error("Table does not exist"))
        .mockRejectedValueOnce(new Error("Table does not exist"))
        .mockRejectedValueOnce(new Error("Table does not exist"))
        .mockRejectedValueOnce(new Error("Table does not exist"));

      const response = await request(app).get("/data/financial-metrics").expect(200);

      expect(response.body.metrics.ttm_income_stmt).toHaveLength(1);
      expect(response.body.metrics.ttm_cashflow).toEqual([]);
      expect(response.body.metrics.income_stmt).toHaveLength(1);
      expect(response.body.metrics.cash_flow).toEqual([]);
    });
  });
});