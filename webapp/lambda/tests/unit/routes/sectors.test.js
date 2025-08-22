const request = require("supertest");
const express = require("express");
const sectorsRoutes = require("../../../routes/sectors");

// Mock database
const { query } = require("../../../utils/database");
jest.mock("../../../utils/database");

// Mock authentication middleware
const { authenticateToken } = require("../../../middleware/auth");
jest.mock("../../../middleware/auth");

describe("Sectors Routes", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/sectors", sectorsRoutes);
    
    // Mock authentication to pass for all tests  
    authenticateToken.mockImplementation((req, res, next) => {
      req.user = { sub: "test-user-123" };
      next();
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /sectors/health", () => {
    test("should return health status", async () => {
      const response = await request(app)
        .get("/sectors/health")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        status: "operational",
        service: "sectors",
        timestamp: expect.any(String),
        message: "Sectors service is running"
      });
    });
  });

  describe("GET /sectors/", () => {
    test("should return API status", async () => {
      const response = await request(app)
        .get("/sectors/")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        message: "Sectors API - Ready",
        timestamp: expect.any(String),
        status: "operational"
      });
    });
  });

  describe("GET /sectors/analysis", () => {
    test("should return comprehensive sector analysis with default timeframe", async () => {
      const mockSectorAnalysis = {
        rows: [
          {
            sector: "Technology",
            company_count: 145,
            market_cap_total: 15000000000000,
            avg_price: 125.50,
            price_change_1d: 2.35,
            price_change_1w: 8.72,
            price_change_1m: 15.80,
            volume_1d: 89500000,
            pe_ratio_avg: 28.5,
            dividend_yield_avg: 1.2,
            top_performer: "AAPL",
            top_performer_change: 5.2,
            worst_performer: "TECH_WORST",
            worst_performer_change: -3.1
          },
          {
            sector: "Healthcare",
            company_count: 98,
            market_cap_total: 8500000000000,
            avg_price: 98.75,
            price_change_1d: 1.85,
            price_change_1w: 4.20,
            price_change_1m: 7.45,
            volume_1d: 65200000,
            pe_ratio_avg: 22.1,
            dividend_yield_avg: 2.8,
            top_performer: "JNJ",
            top_performer_change: 3.4,
            worst_performer: "HEALTH_WORST", 
            worst_performer_change: -1.8
          }
        ]
      };

      query.mockResolvedValueOnce(mockSectorAnalysis);

      const response = await request(app)
        .get("/sectors/analysis")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            sector: "Technology",
            companyCount: 145,
            marketCapTotal: 15000000000000,
            avgPrice: 125.50,
            priceChanges: expect.objectContaining({
              daily: 2.35,
              weekly: 8.72,
              monthly: 15.80
            }),
            topPerformer: expect.objectContaining({
              symbol: "AAPL",
              change: 5.2
            })
          }),
          expect.objectContaining({
            sector: "Healthcare",
            companyCount: 98,
            topPerformer: expect.objectContaining({
              symbol: "JNJ",
              change: 3.4
            })
          })
        ]),
        timestamp: expect.any(String),
        timeframe: "daily"
      });

      expect(query).toHaveBeenCalledTimes(1);
    });

    test("should handle timeframe parameter validation", async () => {
      const response = await request(app)
        .get("/sectors/analysis")
        .query({ timeframe: "invalid" })
        .expect(400);

      expect(response.body).toEqual({
        success: false,
        error: "Invalid timeframe. Must be daily, weekly, or monthly."
      });

      expect(query).not.toHaveBeenCalled();
    });

    test("should accept valid timeframes", async () => {
      const mockData = { rows: [] };
      query.mockResolvedValueOnce(mockData);

      const response = await request(app)
        .get("/sectors/analysis")
        .query({ timeframe: "weekly" })
        .expect(200);

      expect(response.body.timeframe).toBe("weekly");
      expect(query).toHaveBeenCalledTimes(1);
    });

    test("should handle database errors", async () => {
      query.mockRejectedValueOnce(new Error("Database connection failed"));

      const response = await request(app)
        .get("/sectors/analysis")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to fetch sector analysis",
        message: "Database connection failed"
      });
    });
  });

  describe("GET /sectors/list", () => {
    test("should return list of available sectors", async () => {
      const mockSectorsList = {
        rows: [
          { sector: "Technology", company_count: 145 },
          { sector: "Healthcare", company_count: 98 },
          { sector: "Financial Services", company_count: 87 },
          { sector: "Consumer Discretionary", company_count: 76 },
          { sector: "Industrials", company_count: 65 }
        ]
      };

      query.mockResolvedValueOnce(mockSectorsList);

      const response = await request(app)
        .get("/sectors/list")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            sector: "Technology",
            companyCount: 145
          }),
          expect.objectContaining({
            sector: "Healthcare", 
            companyCount: 98
          })
        ]),
        total: 5,
        timestamp: expect.any(String)
      });

      expect(query).toHaveBeenCalledTimes(1);
    });

    test("should handle empty sector list", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/sectors/list")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: [],
        total: 0,
        timestamp: expect.any(String),
        message: "No sectors found"
      });
    });

    test("should handle database errors for sector list", async () => {
      query.mockRejectedValueOnce(new Error("Database query failed"));

      const response = await request(app)
        .get("/sectors/list")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to fetch sectors list",
        message: "Database query failed"
      });
    });
  });

  describe("GET /sectors/:sector/details", () => {
    test("should return detailed sector information", async () => {
      const mockSectorDetails = {
        rows: [
          {
            symbol: "AAPL",
            security_name: "Apple Inc.",
            current_price: 175.25,
            market_cap: 2800000000000,
            pe_ratio: 29.5,
            price_change_1d: 3.25,
            price_change_1w: 8.15,
            volume_1d: 45000000,
            dividend_yield: 0.5
          },
          {
            symbol: "MSFT", 
            security_name: "Microsoft Corporation",
            current_price: 378.50,
            market_cap: 2750000000000,
            pe_ratio: 32.1,
            price_change_1d: 2.80,
            price_change_1w: 6.90,
            volume_1d: 28000000,
            dividend_yield: 0.7
          }
        ]
      };

      query.mockResolvedValueOnce(mockSectorDetails);

      const response = await request(app)
        .get("/sectors/Technology/details")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          sector: "Technology",
          companies: expect.arrayContaining([
            expect.objectContaining({
              symbol: "AAPL",
              companyName: "Apple Inc.",
              currentPrice: 175.25,
              marketCap: 2800000000000,
              peRatio: 29.5,
              priceChanges: expect.objectContaining({
                daily: 3.25,
                weekly: 8.15
              })
            }),
            expect.objectContaining({
              symbol: "MSFT",
              companyName: "Microsoft Corporation"
            })
          ]),
          totalCompanies: 2
        },
        timestamp: expect.any(String)
      });

      expect(query).toHaveBeenCalledTimes(1);
      expect(query.mock.calls[0][1]).toContain("Technology");
    });

    test("should handle non-existent sector", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/sectors/NonExistentSector/details")
        .expect(404);

      expect(response.body).toEqual({
        success: false,
        error: "Sector not found",
        sector: "NonExistentSector",
        message: "No companies found in this sector or sector does not exist"
      });
    });

    test("should handle database errors for sector details", async () => {
      query.mockRejectedValueOnce(new Error("Database connection failed"));

      const response = await request(app)
        .get("/sectors/Technology/details")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to fetch sector details",
        message: "Database connection failed"
      });
    });

    test("should handle URL encoded sector names", async () => {
      const mockData = { rows: [] };
      query.mockResolvedValueOnce(mockData);

      const _response = await request(app)
        .get("/sectors/Consumer%20Discretionary/details")
        .expect(404); // Will be 404 because rows is empty

      expect(query.mock.calls[0][1]).toContain("Consumer Discretionary");
    });
  });
});