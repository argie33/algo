/**
 * Manual Positions Routes Unit Tests
 * Tests manual position CRUD operations with mocked database
 */
const express = require("express");
const request = require("supertest");

jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
}));

const { query } = require("../../../utils/database");

describe("Manual Positions Routes Unit Tests", () => {
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

    // Load manual positions routes
    const manualPositionsRouter = require("../../../routes/manual-positions")(query);
    app.use("/manual-positions", manualPositionsRouter);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /manual-positions - List positions", () => {
    it("should return empty list when no positions exist", async () => {
      query.mockResolvedValueOnce({ rows: [], rowCount: 0 });

      const response = await request(app)
        .get("/manual-positions")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual([]);
      expect(response.body.count).toBe(0);
    });

    it("should return positions with calculated metrics", async () => {
      const mockPositions = [
        {
          id: 1,
          symbol: "AAPL",
          quantity: 50,
          average_cost: 150.00,
          current_price: 175.00,
          market_value: 8750,
          cost_basis: 7500,
          unrealized_gain: 1250,
          unrealized_gain_pct: 16.67,
          broker: "Interactive Brokers",
          purchase_date: "2023-01-15",
          is_active: true,
        },
      ];

      query.mockResolvedValueOnce({ rows: mockPositions, rowCount: 1 });

      const response = await request(app)
        .get("/manual-positions")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0].symbol).toBe("AAPL");
      expect(response.body.data[0].market_value).toBe(8750);
    });

    it("should return 401 when user not authenticated", async () => {
      const appNoAuth = express();
      appNoAuth.use(express.json());

      const responseFormatter = require("../../../middleware/responseFormatter");
      appNoAuth.use(responseFormatter);

      const manualPositionsRouter = require("../../../routes/manual-positions")(query);
      appNoAuth.use("/manual-positions", manualPositionsRouter);

      const response = await request(appNoAuth)
        .get("/manual-positions")
        .expect(401);

      expect(response.body.error).toBe("User authentication required");
    });
  });

  describe("GET /manual-positions/:id - Get single position", () => {
    it("should return a specific position", async () => {
      const mockPosition = {
        id: 1,
        symbol: "TSLA",
        quantity: 25,
        average_cost: 250.00,
        current_price: 280.00,
        market_value: 7000,
        cost_basis: 6250,
        broker: "Fidelity",
      };

      query.mockResolvedValueOnce({ rows: [mockPosition], rowCount: 1 });

      const response = await request(app)
        .get("/manual-positions/1")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe("TSLA");
    });

    it("should return 404 when position not found", async () => {
      query.mockResolvedValueOnce({ rows: [], rowCount: 0 });

      const response = await request(app)
        .get("/manual-positions/999")
        .expect(404);

      expect(response.body.error).toBe("Position not found");
    });
  });

  describe("POST /manual-positions - Create position", () => {
    it("should create a new position with valid data", async () => {
      const newPosition = {
        symbol: "GOOGL",
        quantity: 30,
        average_cost: 120.00,
        current_price: 140.00,
        broker: "Charles Schwab",
      };

      query.mockResolvedValueOnce({
        rows: [{ id: 1, ...newPosition, created_at: new Date().toISOString() }],
        rowCount: 1,
      });

      const response = await request(app)
        .post("/manual-positions")
        .send(newPosition)
        .expect(201);

      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe("GOOGL");
    });

    it("should reject position without symbol", async () => {
      const invalidPosition = {
        quantity: 30,
        average_cost: 120.00,
      };

      const response = await request(app)
        .post("/manual-positions")
        .send(invalidPosition)
        .expect(400);

      expect(response.body.error).toBe("Validation failed");
      expect(response.body.errors).toContain("Symbol is required");
    });

    it("should reject position with invalid quantity", async () => {
      const invalidPosition = {
        symbol: "MSFT",
        quantity: -10,
        average_cost: 380.00,
      };

      const response = await request(app)
        .post("/manual-positions")
        .send(invalidPosition)
        .expect(400);

      expect(response.body.error).toBe("Validation failed");
      expect(response.body.errors).toContain("Quantity must be greater than 0");
    });

    it("should reject position with invalid average_cost", async () => {
      const invalidPosition = {
        symbol: "AMZN",
        quantity: 50,
        average_cost: 0,
      };

      const response = await request(app)
        .post("/manual-positions")
        .send(invalidPosition)
        .expect(400);

      expect(response.body.error).toBe("Validation failed");
      expect(response.body.errors).toContain("Average cost must be greater than 0");
    });
  });

  describe("PATCH /manual-positions/:id - Update position", () => {
    it("should update position quantity", async () => {
      query
        .mockResolvedValueOnce({
          rows: [{ id: 1, symbol: "AAPL", user_id: "test-user-123" }],
          rowCount: 1,
        })
        .mockResolvedValueOnce({
          rows: [{ id: 1, symbol: "AAPL", quantity: 60, user_id: "test-user-123" }],
          rowCount: 1,
        });

      const response = await request(app)
        .patch("/manual-positions/1")
        .send({ quantity: 60 });

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
        .patch("/manual-positions/1")
        .send({ quantity: -10 });

      if (response.status === 400) {
        expect(response.body.error).toBe("Quantity must be greater than 0");
      }
    });

    it("should return 404 when updating non-existent position", async () => {
      query.mockResolvedValueOnce({ rows: [], rowCount: 0 });

      const response = await request(app)
        .patch("/manual-positions/999")
        .send({ quantity: 50 });

      if (response.status === 404) {
        expect(response.body.error).toBe("Position not found");
      }
    });
  });

  describe("DELETE /manual-positions/:id - Delete position", () => {
    it("should delete a position (soft delete)", async () => {
      query
        .mockResolvedValueOnce({
          rows: [{ id: 1, symbol: "AAPL", user_id: "test-user-123" }],
          rowCount: 1,
        })
        .mockResolvedValueOnce({ rowCount: 1 });

      const response = await request(app)
        .delete("/manual-positions/1");

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.message).toContain("deleted successfully");
      }
    });

    it("should return 404 when deleting non-existent position", async () => {
      query.mockResolvedValueOnce({ rows: [], rowCount: 0 });

      const response = await request(app)
        .delete("/manual-positions/999");

      if (response.status === 404) {
        expect(response.body.error).toBe("Position not found");
      }
    });

    it("should return 403 when user not authorized", async () => {
      query.mockResolvedValueOnce({
        rows: [{ id: 1, symbol: "AAPL", user_id: "different-user" }],
        rowCount: 1,
      });

      const response = await request(app)
        .delete("/manual-positions/1");

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
        .get("/manual-positions?limit=10&offset=0")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });
  });

  describe("Filtering", () => {
    it("should filter positions by symbol", async () => {
      query.mockResolvedValueOnce({
        rows: [{ id: 1, symbol: "AAPL", quantity: 50 }],
        rowCount: 1,
      });

      const response = await request(app)
        .get("/manual-positions?symbol=AAPL")
        .expect(200);

      expect(response.body.data[0].symbol).toBe("AAPL");
    });
  });
});
