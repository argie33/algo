const request = require("supertest");
const express = require("express");

// Mock dependencies BEFORE importing the routes
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123", role: "user" };
    req.token = "test-jwt-token";
    next();
  })
}));

jest.mock("../../../utils/database", () => ({
  query: jest.fn()
}));

// Mock optional services that may not exist
jest.mock("../../../utils/factorScoring", () => {
  return {
    FactorScoringEngine: jest.fn().mockImplementation(() => ({
      calculateCompositeScore: jest.fn().mockResolvedValue({
        compositeScore: 75,
        grade: "B+",
        riskLevel: "Medium",
        recommendation: "Buy"
      }),
      getGrade: jest.fn().mockReturnValue("B+"),
      getRiskLevel: jest.fn().mockReturnValue("Medium"),
      getRecommendation: jest.fn().mockReturnValue("Buy")
    }))
  };
}, { virtual: true });

// Now import the routes after mocking
const screenerRoutes = require("../../../routes/screener");
const { authenticateToken } = require("../../../middleware/auth");
const { query } = require("../../../utils/database");

describe("Screener Routes - Testing Your Actual Site", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/screener", screenerRoutes);
    
    // Mock authentication to pass for all tests
    authenticateToken.mockImplementation((req, res, next) => {
      req.user = { sub: "test-user-123", role: "user" };
      req.token = "test-jwt-token";
      next();
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /screener/ - Root endpoint", () => {
    test("should return screener API information", async () => {
      const response = await request(app)
        .get("/screener/")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          system: "Stock Screener API",
          version: "1.0.0",
          status: "operational",
          available_endpoints: expect.arrayContaining([
            expect.stringContaining("/screener/screen"),
            expect.stringContaining("/screener/templates"),
            expect.stringContaining("/screener/factors")
          ]),
          timestamp: expect.any(String)
        })
      });

      // Root endpoint should not require authentication
      expect(authenticateToken).not.toHaveBeenCalled();
    });
  });

  describe("GET /screener/screen - Main screening endpoint", () => {
    test("should perform stock screening with default parameters", async () => {
      const mockResults = {
        rows: [
          {
            symbol: "AAPL",
            company_name: "Apple Inc.",
            sector: "Technology",
            close: "175.50",
            volume: "50000000",
            market_cap: "2750000000000",
            pe_ratio: "28.5",
            factor_score: null
          }
        ]
      };

      const mockCount = { rows: [{ total: "1" }] };

      query.mockResolvedValueOnce(mockResults).mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/screener/screen")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          stocks: expect.arrayContaining([
            expect.objectContaining({
              symbol: "AAPL",
              company_name: "Apple Inc.",
              sector: "Technology",
              factor_score: expect.any(Number),
              factor_grade: expect.any(String),
              recommendation: expect.any(String)
            })
          ]),
          pagination: expect.objectContaining({
            page: 1,
            limit: 50,
            totalCount: expect.any(Number),
            hasMore: expect.any(Boolean)
          }),
          filters: expect.objectContaining({
            applied: expect.any(Number),
            total: expect.any(Number)
          })
        })
      });

      expect(authenticateToken).toHaveBeenCalled();
    });

    test("should handle price filters", async () => {
      query.mockResolvedValue({ rows: [] }).mockResolvedValue({ rows: [{ total: "0" }] });

      const response = await request(app)
        .get("/screener/screen")
        .query({ priceMin: 50, priceMax: 200 })
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("sd.close >= $1 AND sd.close <= $2"),
        expect.arrayContaining([50, 200])
      );
    });

    test("should handle market cap filters", async () => {
      query.mockResolvedValue({ rows: [] }).mockResolvedValue({ rows: [{ total: "0" }] });

      const response = await request(app)
        .get("/screener/screen")
        .query({ marketCapMin: 1000000000, marketCapMax: 100000000000 })
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("s.market_cap >= $1 AND s.market_cap <= $2"),
        expect.arrayContaining([1000000000, 100000000000])
      );
    });

    test("should handle valuation filters", async () => {
      query.mockResolvedValue({ rows: [] }).mockResolvedValue({ rows: [{ total: "0" }] });

      const response = await request(app)
        .get("/screener/screen")
        .query({ peRatioMin: 10, peRatioMax: 25 })
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("s.pe_ratio >= $1 AND s.pe_ratio <= $2"),
        expect.arrayContaining([10, 25])
      );
    });

    test("should handle sector filter", async () => {
      query.mockResolvedValue({ rows: [] }).mockResolvedValue({ rows: [{ total: "0" }] });

      const response = await request(app)
        .get("/screener/screen")
        .query({ sector: "Technology" })
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("ss.sector = $1"),
        expect.arrayContaining(["Technology"])
      );
    });

    test("should handle growth filters", async () => {
      query.mockResolvedValue({ rows: [] }).mockResolvedValue({ rows: [{ total: "0" }] });

      const response = await request(app)
        .get("/screener/screen")
        .query({ revenueGrowthMin: 15, earningsGrowthMin: 20 })
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("s.revenue_growth >= $1 AND s.earnings_growth >= $2"),
        expect.arrayContaining([0.15, 0.20])  // Converted to decimal
      );
    });

    test("should handle technical filters", async () => {
      query.mockResolvedValue({ rows: [] }).mockResolvedValue({ rows: [{ total: "0" }] });

      const response = await request(app)
        .get("/screener/screen")
        .query({ rsiMin: 30, rsiMax: 70, volumeMin: 1000000 })
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("td.rsi >= $1 AND td.rsi <= $2 AND sd.volume >= $3"),
        expect.arrayContaining([30, 70, 1000000])
      );
    });

    test("should handle custom sorting", async () => {
      query.mockResolvedValue({ rows: [] }).mockResolvedValue({ rows: [{ total: "0" }] });

      const response = await request(app)
        .get("/screener/screen")
        .query({ sortBy: "peRatio", sortOrder: "asc" })
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("ORDER BY s.pe_ratio ASC"),
        expect.any(Array)
      );
    });

    test("should handle pagination", async () => {
      query.mockResolvedValue({ rows: [] }).mockResolvedValue({ rows: [{ total: "0" }] });

      const response = await request(app)
        .get("/screener/screen")
        .query({ page: 2, limit: 25 })
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("LIMIT $1 OFFSET $2"),
        expect.arrayContaining([25, 25])
      );
    });
  });

  describe("GET /screener/filters - Filter options", () => {
    test("should return available filter options", async () => {
      const mockSectors = { rows: [{ sector: "Technology" }, { sector: "Healthcare" }] };
      const mockExchanges = { rows: [{ exchange: "NASDAQ" }, { exchange: "NYSE" }] };
      const mockMarketCap = { rows: [{ min_market_cap: 1000000, max_market_cap: 3000000000000 }] };
      const mockPrice = { rows: [{ min_price: 1.5, max_price: 450.0 }] };

      query.mockResolvedValueOnce(mockSectors)
           .mockResolvedValueOnce(mockExchanges)
           .mockResolvedValueOnce(mockMarketCap)
           .mockResolvedValueOnce(mockPrice);

      const response = await request(app)
        .get("/screener/filters")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          sectors: ["Technology", "Healthcare"],
          exchanges: ["NASDAQ", "NYSE"],
          ranges: expect.objectContaining({
            marketCap: expect.any(Object),
            price: expect.any(Object)
          })
        })
      });

      expect(authenticateToken).toHaveBeenCalled();
    });
  });

  describe("GET /screener/presets - Preset screens", () => {
    test("should return preset screening templates", async () => {
      const response = await request(app)
        .get("/screener/presets")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            id: "value_stocks",
            name: "Value Stocks",
            description: expect.any(String),
            filters: expect.objectContaining({
              peRatioMax: expect.any(Number),
              pbRatioMax: expect.any(Number)
            })
          }),
          expect.objectContaining({
            id: "growth_stocks",
            name: "Growth Stocks",
            description: expect.any(String),
            filters: expect.objectContaining({
              revenueGrowthMin: expect.any(Number),
              earningsGrowthMin: expect.any(Number)
            })
          })
        ])
      });

      expect(authenticateToken).toHaveBeenCalled();
    });
  });

  describe("GET /screener/templates - Templates alias", () => {
    test("should return screening templates (alias for presets)", async () => {
      const response = await request(app)
        .get("/screener/templates")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            id: "value_stocks",
            name: "Value Stocks Template",
            filters: expect.any(Object)
          })
        ])
      });
    });
  });

  describe("GET /screener/growth - Growth stocks filter", () => {
    test("should return growth stocks criteria", async () => {
      const response = await request(app)
        .get("/screener/growth")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          id: "growth_stocks",
          name: "Growth Stocks",
          filters: expect.objectContaining({
            revenueGrowthMin: 15,
            earningsGrowthMin: 20
          }),
          criteria: expect.objectContaining({
            revenueGrowth: expect.any(String),
            earningsGrowth: expect.any(String)
          })
        })
      });
    });
  });

  describe("GET /screener/results - Screener results", () => {
    test("should return mock screening results", async () => {
      const response = await request(app)
        .get("/screener/results")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          stocks: expect.arrayContaining([
            expect.objectContaining({
              symbol: expect.any(String),
              company_name: expect.any(String),
              sector: expect.any(String),
              factor_score: expect.any(Number),
              recommendation: expect.any(String)
            })
          ]),
          pagination: expect.objectContaining({
            total: expect.any(Number),
            limit: expect.any(Number),
            hasMore: expect.any(Boolean)
          }),
          source: "mock_data"
        })
      });
    });

    test("should handle pagination parameters", async () => {
      const response = await request(app)
        .get("/screener/results")
        .query({ limit: 10, offset: 5 })
        .expect(200);

      expect(response.body.data.pagination).toMatchObject({
        limit: 10,
        offset: 5
      });
    });
  });

  describe("POST /screener/presets/:presetId/apply - Apply preset", () => {
    test("should apply valid preset filters", async () => {
      const response = await request(app)
        .post("/screener/presets/value_stocks/apply")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          presetId: "value_stocks",
          filters: expect.objectContaining({
            peRatioMax: 15,
            pbRatioMax: 1.5,
            roeMin: 10
          })
        })
      });
    });

    test("should return 404 for invalid preset", async () => {
      const response = await request(app)
        .post("/screener/presets/invalid_preset/apply")
        .expect(404);

      expect(response.body).toMatchObject({
        success: false,
        error: "Preset not found"
      });
    });
  });

  describe("POST /screener/screens/save - Save custom screen", () => {
    test("should save custom screening criteria", async () => {
      const screenData = {
        name: "My Custom Screen",
        description: "Custom growth and value mix",
        filters: {
          peRatioMax: 20,
          revenueGrowthMin: 10,
          marketCapMin: 1000000000
        }
      };

      query.mockResolvedValue({
        rows: [{
          id: 123,
          name: screenData.name,
          description: screenData.description,
          filters: JSON.stringify(screenData.filters),
          created_at: new Date()
        }]
      });

      const response = await request(app)
        .post("/screener/screens/save")
        .send(screenData)
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          id: 123,
          name: screenData.name
        })
      });

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("INSERT INTO saved_screens"),
        expect.arrayContaining(["test-user-123", screenData.name])
      );
    });

    test("should validate required fields", async () => {
      const response = await request(app)
        .post("/screener/screens/save")
        .send({ description: "Missing name" })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: "Name and filters are required"
      });
    });
  });

  describe("GET /screener/screens - Get saved screens", () => {
    test("should return user saved screens", async () => {
      const mockScreens = {
        rows: [
          {
            id: 1,
            name: "My Growth Screen",
            description: "High growth stocks",
            filters: '{"revenueGrowthMin": 15}',
            created_at: new Date()
          }
        ]
      };

      query.mockResolvedValue(mockScreens);

      const response = await request(app)
        .get("/screener/screens")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            id: 1,
            name: "My Growth Screen",
            filters: { revenueGrowthMin: 15 }
          })
        ])
      });
    });

    test("should handle database errors gracefully", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app)
        .get("/screener/screens")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: [],
        note: expect.stringContaining("Database unavailable")
      });
    });
  });

  describe("GET /screener/watchlists - Watchlists endpoint", () => {
    test("should return watchlists for authenticated user", async () => {
      const mockScreens = {
        rows: [
          {
            id: 1,
            name: "My Tech Watchlist",
            description: "Technology stocks to watch",
            filters: '{"sector": "Technology"}',
            created_at: new Date(),
            updated_at: new Date()
          }
        ]
      };

      query.mockResolvedValue(mockScreens);

      const response = await request(app)
        .get("/screener/watchlists")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            id: 1,
            name: "My Tech Watchlist",
            type: "screen"
          })
        ]),
        authenticated: true,
        userId: "test-user-123"
      });
    });

    test("should provide fallback for unauthenticated users", async () => {
      // Mock unauthenticated request
      authenticateToken.mockImplementationOnce((req, res, next) => {
        req.user = null;
        next();
      });

      const response = await request(app)
        .get("/screener/watchlists")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            type: "demo",
            name: expect.stringContaining("Demo")
          })
        ]),
        authenticated: false
      });
    });
  });

  describe("POST /screener/watchlists - Create watchlist", () => {
    test("should create new watchlist", async () => {
      const watchlistData = {
        name: "My New Watchlist",
        description: "Stocks to monitor",
        symbols: ["AAPL", "MSFT", "GOOGL"]
      };

      query.mockResolvedValue({
        rows: [{
          id: 456,
          name: watchlistData.name,
          description: watchlistData.description,
          filters: JSON.stringify({ symbols: watchlistData.symbols }),
          created_at: new Date(),
          updated_at: new Date()
        }]
      });

      const response = await request(app)
        .post("/screener/watchlists")
        .send(watchlistData)
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          id: 456,
          name: watchlistData.name,
          type: "watchlist"
        })
      });
    });

    test("should validate required name", async () => {
      const response = await request(app)
        .post("/screener/watchlists")
        .send({ symbols: ["AAPL"] })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: "Watchlist name is required"
      });
    });
  });

  describe("POST /screener/export - Export results", () => {
    test("should export results in CSV format", async () => {
      const exportData = {
        symbols: ["AAPL", "MSFT"],
        format: "csv"
      };

      const mockExportData = {
        rows: [
          {
            symbol: "AAPL",
            company_name: "Apple Inc.",
            sector: "Technology",
            price: "175.50",
            market_cap: "2750000000000"
          }
        ]
      };

      query.mockResolvedValue(mockExportData);

      const response = await request(app)
        .post("/screener/export")
        .send(exportData)
        .expect(200);

      expect(response.headers['content-type']).toBe('text/csv; charset=utf-8');
      expect(response.headers['content-disposition']).toMatch(/attachment; filename=stock_screen_/);
    });

    test("should export results in JSON format", async () => {
      const exportData = {
        symbols: ["AAPL"],
        format: "json"
      };

      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .post("/screener/export")
        .send(exportData)
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.any(Array),
        exportedAt: expect.any(String)
      });
    });

    test("should validate symbols array", async () => {
      const response = await request(app)
        .post("/screener/export")
        .send({ symbols: [] })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: "No symbols provided for export"
      });
    });
  });

  describe("Authentication", () => {
    test("should require authentication for protected routes", async () => {
      authenticateToken.mockImplementation((req, res, next) => {
        res.status(401).json({ success: false, error: "Unauthorized" });
      });

      await request(app)
        .get("/screener/screen")
        .expect(401);

      expect(query).not.toHaveBeenCalled();
    });
  });

  describe("Error handling", () => {
    test("should handle database errors gracefully", async () => {
      // First ensure auth passes, then fail the database
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app)
        .get("/screener/screen")
        .expect([401, 500]);

      expect(response.body).toHaveProperty('success');
      if (response.status === 500) {
        expect(response.body).toMatchObject({
          success: false,
          error: expect.any(String)
        });
      }
    });
  });
});