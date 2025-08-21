const request = require("supertest");
const express = require("express");
const tradingRouter = require("../../../routes/trading");

// Mock dependencies
jest.mock("../../../utils/database");
const { query } = require("../../../utils/database");

describe("Trading Routes", () => {
  let app;

  beforeEach(() => {
    app = express();
    app.use("/trading", tradingRouter);
    jest.clearAllMocks();
  });

  describe("GET /trading/health", () => {
    test("should return operational status", async () => {
      const response = await request(app).get("/trading/health").expect(200);

      expect(response.body).toEqual({
        success: true,
        status: "operational",
        service: "trading",
        timestamp: expect.any(String),
        message: "Trading service is running",
      });

      // Validate timestamp format
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
    });

    test("should not require authentication", async () => {
      // Should work without any authorization headers
      await request(app).get("/trading/health").expect(200);
    });
  });

  describe("GET /trading/", () => {
    test("should return API ready message", async () => {
      const response = await request(app).get("/trading/").expect(200);

      expect(response.body).toEqual({
        success: true,
        message: "Trading API - Ready",
        timestamp: expect.any(String),
        status: "operational",
      });
    });

    test("should be a public endpoint", async () => {
      // Should work without authentication
      await request(app).get("/trading/").expect(200);
    });
  });

  describe("GET /trading/debug", () => {
    const mockTablesExist = {
      rows: [{ exists: true }],
    };

    const mockTablesNotExist = {
      rows: [{ exists: false }],
    };

    test("should return debug information when all tables exist", async () => {
      query.mockResolvedValue(mockTablesExist);

      const response = await request(app).get("/trading/debug").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.tables).toBeDefined();

      // Check that all expected tables are checked
      const expectedTables = [
        "buy_sell_daily",
        "buy_sell_weekly",
        "buy_sell_monthly",
        "market_data",
        "company_profile",
        "swing_trader",
      ];

      expectedTables.forEach((tableName) => {
        expect(response.body.tables[tableName]).toBe(true);
      });
    });

    test("should handle missing tables", async () => {
      query.mockResolvedValue(mockTablesNotExist);

      const response = await request(app).get("/trading/debug").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.tables).toBeDefined();

      // All tables should be false when they don't exist
      Object.values(response.body.tables).forEach((exists) => {
        expect(exists).toBe(false);
      });
    });

    test("should handle database errors gracefully", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app).get("/trading/debug").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.tables).toBeDefined();

      // All tables should be false when there's an error
      Object.values(response.body.tables).forEach((exists) => {
        expect(exists).toBe(false);
      });
    });

    test("should call correct SQL for table existence check", async () => {
      query.mockResolvedValue(mockTablesExist);

      await request(app).get("/trading/debug").expect(200);

      // Verify the correct SQL query is used
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("SELECT EXISTS"),
        expect.any(Array)
      );

      // Check that query was called for each required table
      const expectedTables = [
        "buy_sell_daily",
        "buy_sell_weekly",
        "buy_sell_monthly",
        "market_data",
        "company_profile",
        "swing_trader",
      ];

      expectedTables.forEach((tableName) => {
        expect(query).toHaveBeenCalledWith(
          expect.stringContaining("SELECT EXISTS"),
          [tableName]
        );
      });
    });
  });

  describe("GET /trading/signals", () => {
    const mockSignalsData = {
      rows: [
        {
          id: 1,
          symbol: "AAPL",
          signal_type: "BUY",
          strength: 0.85,
          created_at: "2023-01-01T10:00:00Z",
        },
        {
          id: 2,
          symbol: "MSFT",
          signal_type: "SELL",
          strength: 0.78,
          created_at: "2023-01-01T11:00:00Z",
        },
      ],
    };

    test("should return trading signals", async () => {
      query.mockResolvedValue(mockSignalsData);

      const response = await request(app).get("/trading/signals").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveLength(2);
      expect(response.body.data[0]).toEqual({
        id: 1,
        symbol: "AAPL",
        signal_type: "BUY",
        strength: 0.85,
        created_at: "2023-01-01T10:00:00Z",
      });
    });

    test("should handle empty signals", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app).get("/trading/signals").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual([]);
    });

    test("should filter signals by symbol", async () => {
      query.mockResolvedValue({
        rows: [mockSignalsData.rows[0]], // Only AAPL
      });

      const response = await request(app)
        .get("/trading/signals?symbol=AAPL")
        .expect(200);

      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0].symbol).toBe("AAPL");

      // Verify the SQL query includes the symbol filter
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("WHERE symbol = $1"),
        ["AAPL"]
      );
    });

    test("should handle database errors", async () => {
      query.mockRejectedValue(new Error("Database error"));

      const response = await request(app).get("/trading/signals").expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Database error");
    });
  });

  describe("POST /trading/orders", () => {
    const validOrderData = {
      symbol: "AAPL",
      quantity: 100,
      side: "buy",
      type: "market",
    };

    test("should create a new trading order", async () => {
      const mockOrderResult = {
        rows: [
          {
            id: 1,
            ...validOrderData,
            status: "pending",
            created_at: "2023-01-01T10:00:00Z",
          },
        ],
      };

      query.mockResolvedValue(mockOrderResult);

      const response = await request(app)
        .post("/trading/orders")
        .send(validOrderData)
        .expect(201);

      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe("AAPL");
      expect(response.body.data.status).toBe("pending");
    });

    test("should validate required fields", async () => {
      const invalidOrderData = {
        symbol: "AAPL",
        // Missing required fields
      };

      const response = await request(app)
        .post("/trading/orders")
        .send(invalidOrderData)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("required");
    });

    test("should validate order side", async () => {
      const invalidOrderData = {
        ...validOrderData,
        side: "invalid",
      };

      const response = await request(app)
        .post("/trading/orders")
        .send(invalidOrderData)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("side must be buy or sell");
    });

    test("should validate order type", async () => {
      const invalidOrderData = {
        ...validOrderData,
        type: "invalid",
      };

      const response = await request(app)
        .post("/trading/orders")
        .send(invalidOrderData)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("type must be market or limit");
    });

    test("should validate quantity is positive", async () => {
      const invalidOrderData = {
        ...validOrderData,
        quantity: -10,
      };

      const response = await request(app)
        .post("/trading/orders")
        .send(invalidOrderData)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("quantity must be positive");
    });

    test("should require limit_price for limit orders", async () => {
      const limitOrderData = {
        ...validOrderData,
        type: "limit",
        // Missing limit_price
      };

      const response = await request(app)
        .post("/trading/orders")
        .send(limitOrderData)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain(
        "limit_price is required for limit orders"
      );
    });

    test("should handle database errors during order creation", async () => {
      query.mockRejectedValue(new Error("Database insertion failed"));

      const response = await request(app)
        .post("/trading/orders")
        .send(validOrderData)
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Database insertion failed");
    });
  });

  describe("GET /trading/positions", () => {
    const mockPositionsData = {
      rows: [
        {
          symbol: "AAPL",
          quantity: 100,
          avg_cost: 150.25,
          market_value: 15500.0,
          unrealized_pnl: 275.0,
          side: "long",
        },
        {
          symbol: "MSFT",
          quantity: 50,
          avg_cost: 300.0,
          market_value: 15250.0,
          unrealized_pnl: 250.0,
          side: "long",
        },
      ],
    };

    test("should return current positions", async () => {
      query.mockResolvedValue(mockPositionsData);

      const response = await request(app).get("/trading/positions").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveLength(2);
      expect(response.body.data[0].symbol).toBe("AAPL");
      expect(response.body.data[0].unrealized_pnl).toBe(275.0);
    });

    test("should handle empty positions", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app).get("/trading/positions").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual([]);
    });

    test("should calculate portfolio summary", async () => {
      query.mockResolvedValue(mockPositionsData);

      const response = await request(app)
        .get("/trading/positions?summary=true")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.summary).toBeDefined();
      expect(response.body.summary.total_value).toBe(30750.0); // 15500 + 15250
      expect(response.body.summary.total_pnl).toBe(525.0); // 275 + 250
    });
  });

  describe("checkRequiredTables helper function", () => {
    test("should check multiple tables correctly", async () => {
      // Mock different responses for different tables
      query
        .mockResolvedValueOnce({ rows: [{ exists: true }] }) // First table exists
        .mockResolvedValueOnce({ rows: [{ exists: false }] }) // Second table doesn't exist
        .mockRejectedValueOnce(new Error("DB error")); // Third table has error

      // Access the router's internal function (this would need to be exported for testing)
      // For now, we test it indirectly through the debug endpoint
      await request(app).get("/trading/debug").expect(200);

      // Verify that query was called multiple times
      expect(query).toHaveBeenCalledTimes(6); // 6 required tables
    });
  });

  describe("Error handling", () => {
    test("should handle malformed JSON in POST requests", async () => {
      const response = await request(app)
        .post("/trading/orders")
        .set("Content-Type", "application/json")
        .send('{"invalid": json}')
        .expect(400);

      expect(response.body.success).toBe(false);
    });

    test("should handle very large request bodies", async () => {
      const largeData = {
        symbol: "A".repeat(10000), // Very long symbol
        quantity: 100,
        side: "buy",
        type: "market",
      };

      const response = await request(app)
        .post("/trading/orders")
        .send(largeData)
        .expect(400);

      expect(response.body.success).toBe(false);
    });
  });
});
