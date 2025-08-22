const request = require("supertest");
const express = require("express");
const priceRoutes = require("../../../routes/price");

// Mock database
const { query } = require("../../../utils/database");
jest.mock("../../../utils/database");

describe("Price Routes", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/price", priceRoutes);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /price/ping", () => {
    test("should return ping status", async () => {
      const response = await request(app)
        .get("/price/ping")
        .expect(200);

      expect(response.body).toMatchObject({
        status: "ok",
        endpoint: "price",
        timestamp: expect.any(String)
      });
    });
  });

  describe("GET /price/history/:timeframe", () => {
    test("should return price history for valid timeframe and symbol", async () => {
      const mockPriceData = {
        rows: [
          {
            symbol: "AAPL",
            date: "2023-12-15",
            open: 175.25,
            high: 178.40,
            low: 174.80,
            close: 177.50,
            volume: 45000000,
            adj_close: 177.50
          },
          {
            symbol: "AAPL", 
            date: "2023-12-14",
            open: 172.10,
            high: 175.60,
            low: 171.90,
            close: 175.25,
            volume: 52000000,
            adj_close: 175.25
          }
        ]
      };

      const mockCount = { rows: [{ total: "2" }] };

      query
        .mockResolvedValueOnce(mockPriceData)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/price/history/daily")
        .query({ symbol: "AAPL", limit: 10, page: 1 })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            date: "2023-12-15",
            open: 175.25,
            high: 178.40,
            low: 174.80,
            close: 177.50,
            volume: 45000000
          })
        ]),
        pagination: expect.objectContaining({
          total: 2,
          page: 1,
          limit: 10
        }),
        timeframe: "daily"
      });

      expect(query).toHaveBeenCalledTimes(2);
    });

    test("should validate timeframe parameter", async () => {
      const response = await request(app)
        .get("/price/history/invalid")
        .query({ symbol: "AAPL" })
        .expect(400);

      expect(response.body).toEqual({
        error: "Invalid timeframe. Use daily, weekly, or monthly."
      });

      expect(query).not.toHaveBeenCalled();
    });

    test("should require symbol parameter", async () => {
      const response = await request(app)
        .get("/price/history/daily")
        .expect(400);

      expect(response.body).toEqual({
        error: "Symbol parameter is required"
      });

      expect(query).not.toHaveBeenCalled();
    });

    test("should handle date range filtering", async () => {
      const mockData = { rows: [] };
      const mockCount = { rows: [{ total: "0" }] };

      query
        .mockResolvedValueOnce(mockData)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/price/history/daily")
        .query({ 
          symbol: "AAPL", 
          start_date: "2023-12-01", 
          end_date: "2023-12-15" 
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(query).toHaveBeenCalledTimes(2);
      
      // Verify date parameters were included in query
      expect(query.mock.calls[0][1]).toContain("AAPL");
      expect(query.mock.calls[0][1]).toContain("2023-12-01");
      expect(query.mock.calls[0][1]).toContain("2023-12-15");
    });

    test("should limit page size to maximum", async () => {
      const mockData = { rows: [] };
      const mockCount = { rows: [{ total: "0" }] };

      query
        .mockResolvedValueOnce(mockData)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/price/history/weekly")
        .query({ symbol: "MSFT", limit: 1000 }) // Exceeds max of 200
        .expect(200);

      expect(response.body.pagination.limit).toBe(200);
      expect(query).toHaveBeenCalledTimes(2);
    });

    test("should handle database errors", async () => {
      query.mockRejectedValueOnce(new Error("Database connection failed"));

      const response = await request(app)
        .get("/price/history/daily")
        .query({ symbol: "AAPL" })
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to fetch price history",
        message: "Database connection failed"
      });
    });
  });

  describe("GET /price/symbols/:timeframe", () => {
    test("should return all symbols with price data for timeframe", async () => {
      const mockSymbols = {
        rows: [
          { symbol: "AAPL", latest_date: "2023-12-15", price_count: 250 },
          { symbol: "MSFT", latest_date: "2023-12-15", price_count: 248 },
          { symbol: "GOOGL", latest_date: "2023-12-14", price_count: 245 }
        ]
      };

      query.mockResolvedValueOnce(mockSymbols);

      const response = await request(app)
        .get("/price/symbols/daily")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            symbol: "AAPL",
            latestDate: "2023-12-15",
            priceCount: 250
          }),
          expect.objectContaining({
            symbol: "MSFT",
            latestDate: "2023-12-15",
            priceCount: 248
          })
        ]),
        timeframe: "daily",
        total: 3
      });

      expect(query).toHaveBeenCalledTimes(1);
    });

    test("should validate timeframe for symbols endpoint", async () => {
      const response = await request(app)
        .get("/price/symbols/invalid")
        .expect(400);

      expect(response.body).toEqual({
        error: "Invalid timeframe. Use daily, weekly, or monthly."
      });
    });

    test("should handle database errors for symbols", async () => {
      query.mockRejectedValueOnce(new Error("Database query failed"));

      const response = await request(app)
        .get("/price/symbols/daily")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to fetch symbols",
        message: "Database query failed"
      });
    });
  });

  describe("GET /price/latest/:symbol", () => {
    test("should return latest price for symbol", async () => {
      const mockLatestPrice = {
        rows: [
          {
            symbol: "AAPL",
            date: "2023-12-15",
            open: 175.25,
            high: 178.40,
            low: 174.80,
            close: 177.50,
            volume: 45000000,
            adj_close: 177.50,
            change: 2.25,
            change_percent: 1.28
          }
        ]
      };

      query.mockResolvedValueOnce(mockLatestPrice);

      const response = await request(app)
        .get("/price/latest/AAPL")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          symbol: "AAPL",
          date: "2023-12-15",
          open: 175.25,
          high: 178.40,
          low: 174.80,
          close: 177.50,
          volume: 45000000,
          change: 2.25,
          changePercent: 1.28
        })
      });

      expect(query).toHaveBeenCalledTimes(1);
      expect(query.mock.calls[0][1]).toContain("AAPL");
    });

    test("should handle symbol not found", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/price/latest/INVALID")
        .expect(404);

      expect(response.body).toEqual({
        success: false,
        error: "Symbol not found",
        symbol: "INVALID",
        message: "No price data available for symbol"
      });
    });

    test("should handle database errors for latest price", async () => {
      query.mockRejectedValueOnce(new Error("Database connection failed"));

      const response = await request(app)
        .get("/price/latest/AAPL")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to fetch latest price",
        message: "Database connection failed"
      });
    });

    test("should handle symbols with special characters", async () => {
      const mockData = {
        rows: [
          {
            symbol: "BRK.A",
            date: "2023-12-15",
            close: 520000.00,
            change: 1500.00,
            change_percent: 0.29
          }
        ]
      };

      query.mockResolvedValueOnce(mockData);

      const response = await request(app)
        .get("/price/latest/BRK.A")
        .expect(200);

      expect(response.body.data.symbol).toBe("BRK.A");
      expect(query.mock.calls[0][1]).toContain("BRK.A");
    });
  });
});