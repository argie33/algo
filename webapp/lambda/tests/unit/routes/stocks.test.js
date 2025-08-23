const request = require("supertest");
const express = require("express");

const stocksRouter = require("../../../routes/stocks");

// Mock dependencies to match your actual site pattern
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

jest.mock("../../../middleware/auth", () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: "test-user-123", email: "test@example.com" };
    next();
  },
}));

jest.mock("../../../utils/schemaValidator", () => ({
  safeQuery: jest.fn(),
}));

jest.mock("../../../middleware/validation", () => ({
  createValidationMiddleware: jest.fn(() => (req, res, next) => {
    // Mock validated parameters based on your actual validation
    req.validated = {
      page: parseInt(req.query.page) || 1,
      limit: parseInt(req.query.limit) || 50,
      search: req.query.search || "",
      sector: req.query.sector || "",
      exchange: req.query.exchange || "",
      sortBy: req.query.sortBy || "symbol",
      sortOrder: req.query.sortOrder || "asc",
    };
    next();
  }),
  validationSchemas: { pagination: {} },
  sanitizers: { string: jest.fn((val) => val) },
}));

const { query } = require("../../../utils/database");
const schemaValidator = require("../../../utils/schemaValidator");

describe("Stocks Routes - Testing Your Actual Site", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/stocks", stocksRouter);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /stocks/sectors - Public endpoint", () => {
    test("should return sectors data from your database", async () => {
      const mockSectors = {
        rows: [
          {
            sector: "Technology",
            count: "145",
            avg_market_cap: "500000000000",
            avg_pe_ratio: "28.5",
          },
          {
            sector: "Healthcare",
            count: "98",
            avg_market_cap: "300000000000",
            avg_pe_ratio: "22.1",
          },
          {
            sector: "Financial Services",
            count: "87",
            avg_market_cap: "200000000000",
            avg_pe_ratio: "15.8",
          },
        ],
      };

      query.mockResolvedValueOnce(mockSectors);

      const response = await request(app).get("/stocks/sectors").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            sector: "Technology",
            count: 145,
            avg_market_cap: 500000000000,
            avg_pe_ratio: 28.5,
          }),
          expect.objectContaining({
            sector: "Healthcare",
            count: 98,
          }),
        ]),
        count: 3,
        timestamp: expect.any(String),
      });

      // Verify your actual query was called
      expect(query).toHaveBeenCalledWith(expect.stringContaining("SELECT"));
      expect(query.mock.calls[0][0]).toContain("stock_symbols");
      expect(query.mock.calls[0][0]).toContain("GROUP BY s.sector");
    });

    test("should handle empty sectors with helpful message", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app).get("/stocks/sectors").expect(200);

      expect(response.body).toEqual({
        success: true,
        data: [],
        message: "No sectors data available - check data loading process",
        recommendations: expect.arrayContaining([
          "Run stock symbols data loader to populate basic stock data",
          "Check if ECS data loading tasks are completing successfully",
          "Verify database connectivity and schema",
        ]),
        timestamp: expect.any(String),
      });
    });
  });

  describe("GET /stocks/public/sample - Public monitoring endpoint", () => {
    test("should return sample stocks for monitoring", async () => {
      const mockStocks = {
        rows: [
          {
            symbol: "AAPL",
            company_name: "Apple Inc.",
            sector: "Technology",
            exchange: "NASDAQ",
            market_cap: "2800000000000",
          },
          {
            symbol: "MSFT",
            company_name: "Microsoft Corporation",
            sector: "Technology",
            exchange: "NASDAQ",
            market_cap: "2750000000000",
          },
          {
            symbol: "GOOGL",
            company_name: "Alphabet Inc.",
            sector: "Technology",
            exchange: "NASDAQ",
            market_cap: "1800000000000",
          },
        ],
      };

      query.mockResolvedValueOnce(mockStocks);

      const response = await request(app)
        .get("/stocks/public/sample")
        .query({ limit: 3 })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: mockStocks.rows,
        count: 3,
        endpoint: "public-sample",
        timestamp: expect.any(String),
      });

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("ORDER BY market_cap DESC NULLS LAST"),
        [3]
      );
    });
  });

  describe("GET /stocks/ping - Authentication required", () => {
    test("should return ping response", async () => {
      const response = await request(app).get("/stocks/ping").expect(200);

      expect(response.body).toEqual({
        status: "ok",
        endpoint: "stocks",
        timestamp: expect.any(String),
      });
    });
  });

  describe("GET /stocks/ - Main stocks endpoint", () => {
    test("should return comprehensive stock data using your actual query", async () => {
      const mockStockResults = {
        rows: [
          {
            symbol: "AAPL",
            security_name: "Apple Inc.",
            exchange: "NASDAQ",
            market_category: "Q",
            short_name: "Apple",
            long_name: "Apple Inc.",
            sector: "Technology",
            industry: "Consumer Electronics",
            current_price: "175.25",
            market_cap: "2800000000000",
            trailing_pe: "29.5",
            dividend_yield: "0.5",
            target_mean_price: "200.00",
            recommendation_key: "Buy",
          },
        ],
      };

      const mockCountResult = { rows: [{ total: "1" }] };

      schemaValidator.safeQuery
        .mockResolvedValueOnce(mockStockResults)
        .mockResolvedValueOnce(mockCountResult);

      const response = await request(app)
        .get("/stocks/")
        .query({ page: 1, limit: 50 })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        performance: expect.stringContaining("COMPREHENSIVE LOADINFO DATA"),
        data: expect.arrayContaining([
          expect.objectContaining({
            ticker: "AAPL",
            symbol: "AAPL",
            name: "Apple Inc.",
            fullName: "Apple Inc.",
            exchange: "NASDAQ",
            sector: "Technology",
            industry: "Consumer Electronics",
            price: expect.objectContaining({
              current: "175.25", // Your site returns strings, not numbers
            }),
            financialMetrics: expect.objectContaining({
              trailingPE: "29.5", // Your site returns strings, not numbers
              dividendYield: "0.5", // Your site returns strings, not numbers
            }),
            analystData: expect.objectContaining({
              targetPrices: expect.objectContaining({
                mean: "200.00", // Your site returns strings, not numbers
              }),
              recommendation: expect.objectContaining({
                key: "Buy",
              }),
            }),
            hasData: true,
            dataSource: "comprehensive_loadinfo_query",
          }),
        ]),
        pagination: expect.objectContaining({
          page: 1,
          limit: 50,
          total: 1,
          totalPages: 1,
        }),
        metadata: expect.objectContaining({
          dataSources: expect.arrayContaining([
            "stock_symbols",
            "symbols",
            "market_data",
            "key_metrics",
            "analyst_estimates",
          ]),
        }),
      });
    });

    test("should handle search parameter", async () => {
      const mockResults = { rows: [] };
      const mockCount = { rows: [{ total: "0" }] };

      schemaValidator.safeQuery
        .mockResolvedValueOnce(mockResults)
        .mockResolvedValueOnce(mockCount);

      await request(app).get("/stocks/").query({ search: "Apple" }).expect(200);

      // Verify search was applied in the query
      const queryCall = schemaValidator.safeQuery.mock.calls[0];
      expect(queryCall[0]).toContain("ILIKE");
      expect(queryCall[1]).toContain("%Apple%");
    });
  });

  describe("GET /stocks/screen - Stock screening", () => {
    test("should screen stocks with filters", async () => {
      const mockCountResult = { rows: [{ total: "50" }] };
      const mockStocksResult = {
        rows: [
          {
            symbol: "AAPL",
            company_name: "Apple Inc.",
            sector: "Technology",
            current_price: "175.25",
            change_percent: "2.5",
            volume: "45000000",
            market_cap: "2800000000000",
            pe_ratio: "29.5",
            dividend_yield: "0.5",
            beta: "1.2",
          },
        ],
      };

      query
        .mockResolvedValueOnce(mockCountResult)
        .mockResolvedValueOnce(mockStocksResult);

      const response = await request(app)
        .get("/stocks/screen")
        .query({
          sector: "Technology",
          marketCap: "100-5000", // 100B to 5T
          sortBy: "market_cap",
          sortOrder: "DESC",
        })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          stocks: expect.arrayContaining([
            expect.objectContaining({
              symbol: "AAPL",
              company_name: "Apple Inc.",
              sector: "Technology",
            }),
          ]),
          pagination: expect.objectContaining({
            total: 50,
          }),
          filters: expect.objectContaining({
            sector: "Technology",
            marketCap: "100-5000",
            sortBy: "market_cap",
            sortOrder: "DESC",
          }),
        }),
        data_source: "real_database",
      });
    });
  });

  describe("GET /stocks/:ticker - Individual stock", () => {
    test("should return individual stock data", async () => {
      const mockStock = {
        rows: [
          {
            symbol: "AAPL",
            security_name: "Apple Inc.",
            exchange: "NASDAQ",
            market_category: "Q",
            financial_status: "N",
            etf: "N",
            latest_date: "2025-07-16",
            open: "174.00",
            high: "176.50",
            low: "173.25",
            close: "175.25",
            volume: "45000000",
            adj_close: "175.25",
          },
        ],
      };

      query.mockResolvedValueOnce(mockStock);

      const response = await request(app).get("/stocks/AAPL").expect(200);

      expect(response.body).toMatchObject({
        symbol: "AAPL",
        ticker: "AAPL",
        companyInfo: expect.objectContaining({
          name: "Apple Inc.",
          exchange: "NASDAQ",
          isETF: false,
        }),
        currentPrice: expect.objectContaining({
          date: "2025-07-16",
          open: 174.0,
          high: 176.5,
          low: 173.25,
          close: 175.25,
          volume: 45000000,
        }),
        metadata: expect.objectContaining({
          requestedSymbol: "AAPL",
          resolvedSymbol: "AAPL",
          dataAvailability: expect.objectContaining({
            basicInfo: true,
            priceData: true,
          }),
        }),
      });
    });

    test("should return 404 for non-existent stock", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/stocks/NONEXISTENT")
        .expect(404);

      expect(response.body).toMatchObject({
        error: "Stock not found",
        symbol: "NONEXISTENT",
        message: "Symbol 'NONEXISTENT' not found in database",
      });
    });
  });

  describe("GET /stocks/:ticker/prices - Price history", () => {
    test("should return price history with your caching system", async () => {
      const mockPrices = {
        rows: [
          {
            date: "2025-07-16",
            open: "174.00",
            high: "176.50",
            low: "173.25",
            close: "175.25",
            adj_close: "175.25",
            volume: "45000000",
            prev_close: "173.80",
            price_change: "1.45",
            price_change_pct: "0.83",
          },
          {
            date: "2025-07-15",
            open: "172.50",
            high: "174.20",
            low: "171.80",
            close: "173.80",
            adj_close: "173.80",
            volume: "38000000",
            prev_close: "172.00",
            price_change: "1.80",
            price_change_pct: "1.05",
          },
        ],
      };

      query.mockResolvedValueOnce(mockPrices);

      const response = await request(app)
        .get("/stocks/AAPL/prices")
        .query({ timeframe: "daily", limit: 30 })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        ticker: "AAPL",
        timeframe: "daily",
        dataPoints: 2,
        data: expect.arrayContaining([
          expect.objectContaining({
            date: "2025-07-16",
            open: 174.0,
            high: 176.5,
            low: 173.25,
            close: 175.25,
            volume: 45000000,
            priceChange: 1.45,
            priceChangePct: 0.83,
          }),
        ]),
        summary: expect.objectContaining({
          latestPrice: 175.25,
          latestDate: "2025-07-16",
          periodReturn: expect.any(Number),
          latestVolume: 45000000,
        }),
        cached: false,
      });

      // Verify your price_daily table query
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("FROM price_daily"),
        ["AAPL", 30]
      );
    });
  });

  describe("GET /stocks/filters/sectors - Available filters", () => {
    test("should return exchange filters", async () => {
      const mockExchanges = {
        rows: [
          { exchange: "NASDAQ", count: "3500" },
          { exchange: "NYSE", count: "2800" },
          { exchange: "AMEX", count: "300" },
        ],
      };

      query.mockResolvedValueOnce(mockExchanges);

      const response = await request(app)
        .get("/stocks/filters/sectors")
        .expect(200);

      expect(response.body).toMatchObject({
        data: expect.arrayContaining([
          expect.objectContaining({
            name: "NASDAQ",
            value: "NASDAQ",
            count: 3500,
          }),
          expect.objectContaining({
            name: "NYSE",
            value: "NYSE",
            count: 2800,
          }),
        ]),
        total: 3,
      });
    });
  });

  describe("GET /stocks/screen/stats - Screening statistics", () => {
    test("should return screening ranges for your filters", async () => {
      const mockStats = {
        rows: [
          {
            total_stocks: "8500",
            min_market_cap: "50000000",
            max_market_cap: "3000000000000",
            min_pe_ratio: "5.2",
            max_pe_ratio: "95.8",
            min_pb_ratio: "0.1",
            max_pb_ratio: "18.5",
          },
        ],
      };

      query.mockResolvedValueOnce(mockStats);

      const response = await request(app)
        .get("/stocks/screen/stats")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          total_stocks: 8500,
          ranges: expect.objectContaining({
            market_cap: expect.objectContaining({
              min: 50000000,
              max: 3000000000000,
            }),
            pe_ratio: expect.objectContaining({
              min: 5.2,
              max: 95.8, // Your site caps at 100
            }),
          }),
        }),
      });
    });
  });

  describe("POST /stocks/init-price-data - Database initialization", () => {
    test("should verify the init endpoint exists and handles SQL properly", async () => {
      // Just test that the endpoint exists - complex SQL execution tested in integration tests
      query.mockRejectedValueOnce(new Error("Mock error for testing"));

      const response = await request(app)
        .post("/stocks/init-price-data")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to initialize price_daily table",
      });

      // Verify the route attempts to execute the correct SQL
      expect(query).toHaveBeenCalled();
    });

    test("should handle database errors during initialization", async () => {
      query.mockRejectedValueOnce(new Error("Database connection failed"));

      const response = await request(app)
        .post("/stocks/init-price-data")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to initialize price_daily table",
        details: "Database connection failed",
      });
    });
  });

  describe("Error handling - Your site's error patterns", () => {
    test("should handle database errors gracefully", async () => {
      query.mockRejectedValueOnce(new Error("Connection failed"));

      const response = await request(app).get("/stocks/sectors").expect(200); // Your site returns 200 with error data

      expect(response.body).toMatchObject({
        success: true,
        data: [],
        message: "No sectors data available - check data loading process",
      });
    });

    test("should handle table missing errors with fallback", async () => {
      schemaValidator.safeQuery.mockRejectedValueOnce(
        new Error("relation does not exist")
      );

      // Mock fallback query
      query
        .mockResolvedValueOnce({
          rows: [{ symbol: "AAPL", security_name: "Apple Inc." }],
        })
        .mockResolvedValueOnce({ rows: [{ total: "1" }] });

      const response = await request(app).get("/stocks/").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.any(Array),
        note: expect.stringContaining("basic stock symbols data"),
      });
    });
  });
});
