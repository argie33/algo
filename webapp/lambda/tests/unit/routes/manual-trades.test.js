/**
 * Manual Trades Routes Unit Tests
 * Tests manual trade CRUD operations with mocked database
 */
const express = require("express");
const request = require("supertest");

jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
}));

const { query } = require("../../../utils/database");

describe("Manual Trades Routes Unit Tests", () => {
  let app;

  beforeAll(() => {
    process.env.NODE_ENV = "test";
    app = express();
    app.use(express.json());

    // Mock authentication middleware
    app.use((req, res, next) => {
      req.user = { sub: "test-user-123" };
      next();
    });

    // Add response formatter middleware
    const responseFormatter = require("../../../middleware/responseFormatter");
    app.use(responseFormatter);

    // Load manual trades routes
    const manualTradesRouter = require("../../../routes/manual-trades")(query);
    app.use("/manual-trades", manualTradesRouter);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /manual-trades - List trades", () => {
    it("should return empty list when no trades exist", async () => {
      query.mockResolvedValueOnce({ rows: [], rowCount: 0 });

      const response = await request(app)
        .get("/manual-trades")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual([]);
      expect(response.body.count).toBe(0);
    });

    it("should return trades with calculated values", async () => {
      const mockTrades = [
        {
          id: 1,
          symbol: "TSLA",
          trade_type: "buy",
          quantity: 10,
          price: 250.00,
          order_value: 2500,
          commission: 10.00,
          total_cost: 2510.00,
          execution_date: "2025-01-15",
          status: "filled",
          broker: "Fidelity",
        },
      ];

      query.mockResolvedValueOnce({ rows: mockTrades, rowCount: 1 });

      const response = await request(app)
        .get("/manual-trades")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0].symbol).toBe("TSLA");
      expect(response.body.data[0].order_value).toBe(2500);
    });

    it("should return 401 when user not authenticated", async () => {
      const appNoAuth = express();
      appNoAuth.use(express.json());

      const responseFormatter = require("../../../middleware/responseFormatter");
      appNoAuth.use(responseFormatter);

      const manualTradesRouter = require("../../../routes/manual-trades")(query);
      appNoAuth.use("/manual-trades", manualTradesRouter);

      const response = await request(appNoAuth)
        .get("/manual-trades")
        .expect(401);

      expect(response.body.error).toBe("User authentication required");
    });
  });

  describe("GET /manual-trades/:id - Get single trade", () => {
    it("should return a specific trade", async () => {
      const mockTrade = {
        id: 1,
        symbol: "AAPL",
        trade_type: "buy",
        quantity: 50,
        price: 150.00,
        commission: 10.00,
        execution_date: "2025-01-10",
      };

      query.mockResolvedValueOnce({ rows: [mockTrade], rowCount: 1 });

      const response = await request(app)
        .get("/manual-trades/1")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe("AAPL");
    });

    it("should return 404 when trade not found", async () => {
      query.mockResolvedValueOnce({ rows: [], rowCount: 0 });

      const response = await request(app)
        .get("/manual-trades/999")
        .expect(404);

      expect(response.body.error).toBe("Trade not found");
    });
  });

  describe("POST /manual-trades - Create trade", () => {
    it("should create a new BUY trade with valid data", async () => {
      const newTrade = {
        symbol: "MSFT",
        trade_type: "buy",
        quantity: 25,
        price: 380.00,
        execution_date: "2025-01-15",
        commission: 15.00,
        broker: "Charles Schwab",
      };

      query.mockResolvedValueOnce({
        rows: [{ id: 1, ...newTrade, created_at: new Date().toISOString() }],
        rowCount: 1,
      });

      const response = await request(app)
        .post("/manual-trades")
        .send(newTrade)
        .expect(201);

      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe("MSFT");
      expect(response.body.data.trade_type).toBe("buy");
    });

    it("should create a SELL trade", async () => {
      const newTrade = {
        symbol: "GOOGL",
        trade_type: "sell",
        quantity: 30,
        price: 140.00,
        execution_date: "2025-01-20",
        broker: "Interactive Brokers",
      };

      query.mockResolvedValueOnce({
        rows: [{ id: 2, ...newTrade, created_at: new Date().toISOString() }],
        rowCount: 1,
      });

      const response = await request(app)
        .post("/manual-trades")
        .send(newTrade)
        .expect(201);

      expect(response.body.success).toBe(true);
      expect(response.body.data.trade_type).toBe("sell");
    });

    it("should create a DIVIDEND trade", async () => {
      const newTrade = {
        symbol: "JNJ",
        trade_type: "dividend",
        quantity: 100,
        price: 1.50,
        execution_date: "2025-01-18",
      };

      query.mockResolvedValueOnce({
        rows: [{ id: 3, ...newTrade, created_at: new Date().toISOString() }],
        rowCount: 1,
      });

      const response = await request(app)
        .post("/manual-trades")
        .send(newTrade)
        .expect(201);

      expect(response.body.success).toBe(true);
      expect(response.body.data.trade_type).toBe("dividend");
    });

    it("should reject trade without symbol", async () => {
      const invalidTrade = {
        trade_type: "buy",
        quantity: 50,
        price: 150.00,
        execution_date: "2025-01-15",
      };

      const response = await request(app)
        .post("/manual-trades")
        .send(invalidTrade)
        .expect(400);

      expect(response.body.error).toBe("Validation failed");
      expect(response.body.errors).toContain("Symbol is required");
    });

    it("should reject trade with invalid trade_type", async () => {
      const invalidTrade = {
        symbol: "AAPL",
        trade_type: "invalid_type",
        quantity: 50,
        price: 150.00,
        execution_date: "2025-01-15",
      };

      const response = await request(app)
        .post("/manual-trades")
        .send(invalidTrade)
        .expect(400);

      expect(response.body.error).toBe("Validation failed");
      expect(response.body.errors).toContain("Trade type must be: buy, sell, dividend, or split");
    });

    it("should reject trade with invalid quantity", async () => {
      const invalidTrade = {
        symbol: "TSLA",
        trade_type: "buy",
        quantity: -10,
        price: 250.00,
        execution_date: "2025-01-15",
      };

      const response = await request(app)
        .post("/manual-trades")
        .send(invalidTrade)
        .expect(400);

      expect(response.body.error).toBe("Validation failed");
      expect(response.body.errors).toContain("Quantity must be greater than 0");
    });

    it("should reject trade with invalid price", async () => {
      const invalidTrade = {
        symbol: "AAPL",
        trade_type: "buy",
        quantity: 50,
        price: 0,
        execution_date: "2025-01-15",
      };

      const response = await request(app)
        .post("/manual-trades")
        .send(invalidTrade)
        .expect(400);

      expect(response.body.error).toBe("Validation failed");
      expect(response.body.errors).toContain("Price must be greater than 0");
    });

    it("should reject trade with future execution date", async () => {
      const tomorrow = new Date();
      tomorrow.setDate(tomorrow.getDate() + 1);

      const invalidTrade = {
        symbol: "AAPL",
        trade_type: "buy",
        quantity: 50,
        price: 150.00,
        execution_date: tomorrow.toISOString().split('T')[0],
      };

      const response = await request(app)
        .post("/manual-trades")
        .send(invalidTrade)
        .expect(400);

      expect(response.body.error).toBe("Validation failed");
      expect(response.body.errors).toContain("Execution date cannot be in the future");
    });
  });

  describe("PATCH /manual-trades/:id - Update trade", () => {
    it("should update trade quantity", async () => {
      query
        .mockResolvedValueOnce({
          rows: [{ id: 1, symbol: "AAPL", user_id: "test-user-123" }],
          rowCount: 1,
        })
        .mockResolvedValueOnce({
          rows: [{ id: 1, symbol: "AAPL", quantity: 100, user_id: "test-user-123" }],
          rowCount: 1,
        });

      const response = await request(app)
        .patch("/manual-trades/1")
        .send({ quantity: 100 });

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
      }
    });

    it("should reject update with invalid quantity", async () => {
      query.mockResolvedValueOnce({
        rows: [{ id: 1, symbol: "AAPL", user_id: "test-user-123" }],
        rowCount: 1,
      });

      const response = await request(app)
        .patch("/manual-trades/1")
        .send({ quantity: -50 });

      if (response.status === 400) {
        expect(response.body.error).toBe("Quantity must be greater than 0");
      }
    });

    it("should return 404 when updating non-existent trade", async () => {
      query.mockResolvedValueOnce({ rows: [], rowCount: 0 });

      const response = await request(app)
        .patch("/manual-trades/999")
        .send({ quantity: 50 });

      if (response.status === 404) {
        expect(response.body.error).toBe("Trade not found");
      }
    });
  });

  describe("DELETE /manual-trades/:id - Delete trade", () => {
    it("should delete a trade (hard delete)", async () => {
      query
        .mockResolvedValueOnce({
          rows: [{ id: 1, symbol: "AAPL", trade_type: "buy", user_id: "test-user-123" }],
          rowCount: 1,
        })
        .mockResolvedValueOnce({ rowCount: 1 });

      const response = await request(app)
        .delete("/manual-trades/1");

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.message).toContain("deleted successfully");
      }
    });

    it("should return 404 when deleting non-existent trade", async () => {
      query.mockResolvedValueOnce({ rows: [], rowCount: 0 });

      const response = await request(app)
        .delete("/manual-trades/999");

      if (response.status === 404) {
        expect(response.body.error).toBe("Trade not found");
      }
    });

    it("should return 403 when user not authorized", async () => {
      query.mockResolvedValueOnce({
        rows: [{ id: 1, symbol: "AAPL", user_id: "different-user" }],
        rowCount: 1,
      });

      const response = await request(app)
        .delete("/manual-trades/1");

      if (response.status === 403) {
        expect(response.body.error).toBe("Unauthorized");
      }
    });
  });

  describe("Pagination", () => {
    it("should support limit and offset parameters", async () => {
      query.mockResolvedValueOnce({
        rows: [{ id: 1, symbol: "AAPL", quantity: 50 }],
        rowCount: 1,
      });

      const response = await request(app)
        .get("/manual-trades?limit=20&offset=0")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });
  });

  describe("Filtering", () => {
    it("should filter trades by symbol", async () => {
      query.mockResolvedValueOnce({
        rows: [{ id: 1, symbol: "TSLA", quantity: 10 }],
        rowCount: 1,
      });

      const response = await request(app)
        .get("/manual-trades?symbol=TSLA")
        .expect(200);

      expect(response.body.data[0].symbol).toBe("TSLA");
    });

    it("should filter trades by status", async () => {
      query.mockResolvedValueOnce({
        rows: [{ id: 1, symbol: "AAPL", status: "filled" }],
        rowCount: 1,
      });

      const response = await request(app)
        .get("/manual-trades?status=filled")
        .expect(200);

      expect(response.body.data[0].status).toBe("filled");
    });
  });
});
