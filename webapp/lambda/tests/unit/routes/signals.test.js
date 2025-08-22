const request = require("supertest");
const express = require("express");
const signalsRoutes = require("../../../routes/signals");

// Mock database
const { query } = require("../../../utils/database");
jest.mock("../../../utils/database");

describe("Signals Routes", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/signals", signalsRoutes);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /signals/buy", () => {
    test("should return buy signals with default parameters", async () => {
      const mockBuySignals = {
        rows: [
          {
            symbol: "AAPL",
            company_name: "Apple Inc.",
            sector: "Technology",
            signal: "8.5",
            date: "2023-12-15",
            current_price: 175.25,
            market_cap: 2800000000000,
            trailing_pe: 29.5,
            dividend_yield: 0.5
          },
          {
            symbol: "MSFT",
            company_name: "Microsoft Corporation", 
            sector: "Technology",
            signal: "7.8",
            date: "2023-12-15",
            current_price: 378.50,
            market_cap: 2750000000000,
            trailing_pe: 32.1,
            dividend_yield: 0.7
          }
        ]
      };

      const mockCount = { rows: [{ total: "2" }] };

      query
        .mockResolvedValueOnce(mockBuySignals)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/signals/buy")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            companyName: "Apple Inc.",
            sector: "Technology",
            signal: 8.5,
            date: "2023-12-15",
            currentPrice: 175.25,
            marketCap: 2800000000000
          }),
          expect.objectContaining({
            symbol: "MSFT",
            companyName: "Microsoft Corporation",
            signal: 7.8
          })
        ]),
        pagination: expect.objectContaining({
          total: 2,
          page: 1,
          limit: 25
        }),
        timeframe: "daily"
      });

      expect(query).toHaveBeenCalledTimes(2);
    });

    test("should handle timeframe parameter", async () => {
      const mockData = { rows: [] };
      const mockCount = { rows: [{ total: "0" }] };

      query
        .mockResolvedValueOnce(mockData)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/signals/buy")
        .query({ timeframe: "weekly", limit: 10, page: 2 })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: [],
        pagination: expect.objectContaining({
          total: 0,
          page: 2,
          limit: 10
        }),
        timeframe: "weekly"
      });

      expect(query).toHaveBeenCalledTimes(2);
      // Verify weekly table was used
      expect(query.mock.calls[0][0]).toContain("buy_sell_weekly");
    });

    test("should validate timeframe parameter", async () => {
      const response = await request(app)
        .get("/signals/buy")
        .query({ timeframe: "invalid" })
        .expect(400);

      expect(response.body).toEqual({
        error: "Invalid timeframe. Must be daily, weekly, or monthly"
      });

      expect(query).not.toHaveBeenCalled();
    });

    test("should handle pagination", async () => {
      const mockData = { rows: [] };
      const mockCount = { rows: [{ total: "0" }] };

      query
        .mockResolvedValueOnce(mockData)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/signals/buy")
        .query({ page: 3, limit: 50 })
        .expect(200);

      expect(response.body.pagination).toEqual({
        total: 0,
        page: 3,
        limit: 50,
        totalPages: 0,
        hasNext: false,
        hasPrev: true
      });

      // Verify offset calculation (page 3, limit 50 = offset 100)
      expect(query.mock.calls[0][1]).toEqual([50, 100]);
    });

    test("should handle database errors", async () => {
      query.mockRejectedValueOnce(new Error("Database connection failed"));

      const response = await request(app)
        .get("/signals/buy")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to fetch buy signals",
        message: "Database connection failed"
      });
    });

    test("should handle monthly timeframe", async () => {
      const mockData = { rows: [] };
      const mockCount = { rows: [{ total: "0" }] };

      query
        .mockResolvedValueOnce(mockData)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/signals/buy")
        .query({ timeframe: "monthly" })
        .expect(200);

      expect(response.body.timeframe).toBe("monthly");
      expect(query.mock.calls[0][0]).toContain("buy_sell_monthly");
    });

    test("should handle empty results", async () => {
      const mockData = { rows: [] };
      const mockCount = { rows: [{ total: "0" }] };

      query
        .mockResolvedValueOnce(mockData)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/signals/buy")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: [],
        pagination: {
          total: 0,
          page: 1,
          limit: 25,
          totalPages: 0,
          hasNext: false,
          hasPrev: false
        },
        timeframe: "daily",
        message: "No buy signals found"
      });
    });
  });

  describe("GET /signals/sell", () => {
    test("should return sell signals with default parameters", async () => {
      const mockSellSignals = {
        rows: [
          {
            symbol: "NFLX",
            company_name: "Netflix Inc.",
            sector: "Communication Services",
            signal: "6.2",
            date: "2023-12-15",
            current_price: 485.75,
            market_cap: 215000000000,
            trailing_pe: 45.8,
            dividend_yield: 0.0
          }
        ]
      };

      const mockCount = { rows: [{ total: "1" }] };

      query
        .mockResolvedValueOnce(mockSellSignals)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/signals/sell")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "NFLX",
            companyName: "Netflix Inc.",
            sector: "Communication Services",
            signal: 6.2,
            date: "2023-12-15",
            currentPrice: 485.75
          })
        ]),
        pagination: expect.objectContaining({
          total: 1,
          page: 1,
          limit: 25
        }),
        timeframe: "daily"
      });

      expect(query).toHaveBeenCalledTimes(2);
    });

    test("should handle timeframe parameter for sell signals", async () => {
      const mockData = { rows: [] };
      const mockCount = { rows: [{ total: "0" }] };

      query
        .mockResolvedValueOnce(mockData)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/signals/sell")
        .query({ timeframe: "weekly" })
        .expect(200);

      expect(response.body.timeframe).toBe("weekly");
      expect(query.mock.calls[0][0]).toContain("buy_sell_weekly");
    });

    test("should validate timeframe parameter for sell signals", async () => {
      const response = await request(app)
        .get("/signals/sell")
        .query({ timeframe: "hourly" })
        .expect(400);

      expect(response.body).toEqual({
        error: "Invalid timeframe. Must be daily, weekly, or monthly"
      });

      expect(query).not.toHaveBeenCalled();
    });

    test("should handle database errors for sell signals", async () => {
      query.mockRejectedValueOnce(new Error("Database query failed"));

      const response = await request(app)
        .get("/signals/sell")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to fetch sell signals",
        message: "Database query failed"
      });
    });

    test("should handle large page numbers", async () => {
      const mockData = { rows: [] };
      const mockCount = { rows: [{ total: "100" }] };

      query
        .mockResolvedValueOnce(mockData)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/signals/sell")
        .query({ page: 10, limit: 25 })
        .expect(200);

      expect(response.body.pagination).toEqual({
        total: 100,
        page: 10,
        limit: 25,
        totalPages: 4,
        hasNext: false,
        hasPrev: true
      });

      // Verify offset calculation (page 10, limit 25 = offset 225)
      expect(query.mock.calls[0][1]).toEqual([25, 225]);
    });

    test("should handle null/empty signal values", async () => {
      const mockData = { rows: [] };
      const mockCount = { rows: [{ total: "0" }] };

      query
        .mockResolvedValueOnce(mockData)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/signals/sell")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual([]);
      
      // Verify query filters out null/empty signals
      expect(query.mock.calls[0][0]).toContain("AND bs.signal IS NOT NULL");
      expect(query.mock.calls[0][0]).toContain("AND bs.signal != ''");
    });

    test("should handle missing company data gracefully", async () => {
      const mockSellSignals = {
        rows: [
          {
            symbol: "TEST",
            company_name: null,
            sector: null,
            signal: "5.5",
            date: "2023-12-15",
            current_price: null,
            market_cap: null,
            trailing_pe: null,
            dividend_yield: null
          }
        ]
      };

      const mockCount = { rows: [{ total: "1" }] };

      query
        .mockResolvedValueOnce(mockSellSignals)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/signals/sell")
        .expect(200);

      expect(response.body.data[0]).toMatchObject({
        symbol: "TEST",
        companyName: null,
        sector: null,
        signal: 5.5,
        currentPrice: null,
        marketCap: null
      });
    });
  });
});