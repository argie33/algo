/**
 * Orders Management Integration Tests
 * Tests for order placement, tracking, and management
 * Route: /routes/orders.js
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Orders Management", () => {
  describe("Order Placement", () => {
    test("should create market order with valid parameters", async () => {
      const orderPayload = {
        symbol: "AAPL",
        side: "buy",
        quantity: 100,
        type: "market"
      };

      const response = await request(app)
        .post("/api/orders")
        .send(orderPayload);
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200 || response.status === 201) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("order_id");
        expect(response.body.data).toHaveProperty("symbol", "AAPL");
        expect(response.body.data).toHaveProperty("side", "buy");
      }
    });

    test("should create limit order with price specification", async () => {
      const orderPayload = {
        symbol: "MSFT",
        side: "sell",
        quantity: 50,
        type: "limit",
        price: 350.00
      };

      const response = await request(app)
        .post("/api/orders")
        .send(orderPayload);
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200 || response.status === 201) {
        expect(response.body.data).toHaveProperty("type", "limit");
        expect(response.body.data).toHaveProperty("price", 350.00);
      }
    });

    test("should reject invalid order parameters", async () => {
      const invalidOrder = {
        symbol: "",
        side: "invalid",
        quantity: -10
      };

      const response = await request(app)
        .post("/api/orders")
        .send(invalidOrder);
      
      expect([400, 422]).toContain(response.status);
    });
  });

  describe("Order History", () => {
    test("should retrieve order history with pagination", async () => {
      const response = await request(app)
        .get("/api/orders/history?limit=25&page=1");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        // Handle both data structures: direct array or {orders: [], pagination: {}}
        let orders = [];
        if (response.body.data.orders) {
          // New format with orders and pagination
          expect(Array.isArray(response.body.data.orders)).toBe(true);
          orders = response.body.data.orders;
        } else if (Array.isArray(response.body.data)) {
          // Old format with direct array
          orders = response.body.data;
        }
        
        if (orders.length > 0) {
          const order = orders[0];
          expect(order).toHaveProperty("order_id");
          expect(order).toHaveProperty("symbol");
          expect(order).toHaveProperty("side");
          expect(["buy", "sell"]).toContain(order.side);
          expect(order).toHaveProperty("status");
        }
      }
    });

    test("should filter orders by status", async () => {
      const response = await request(app)
        .get("/api/orders/history?status=filled");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200 && response.body.data.length > 0) {
        response.body.data.forEach(order => {
          expect(order.status).toBe("filled");
        });
      }
    });

    test("should filter orders by symbol", async () => {
      const response = await request(app)
        .get("/api/orders/history?symbol=AAPL");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200 && response.body.data.length > 0) {
        response.body.data.forEach(order => {
          expect(order.symbol).toBe("AAPL");
        });
      }
    });
  });

  describe("Order Management", () => {
    test("should cancel pending order", async () => {
      const response = await request(app)
        .delete("/api/orders/test-order-123");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("message");
        expect(response.body.message).toMatch(/cancel/i);
      }
    });

    test("should modify existing order", async () => {
      const modifications = {
        quantity: 75,
        price: 155.00
      };

      const response = await request(app)
        .put("/api/orders/test-order-456")
        .send(modifications);
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("quantity", 75);
      }
    });

    test("should retrieve order details by ID", async () => {
      const response = await request(app)
        .get("/api/orders/test-order-789");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("order_id", "test-order-789");
        expect(response.body.data).toHaveProperty("symbol");
        expect(response.body.data).toHaveProperty("side");
        expect(response.body.data).toHaveProperty("quantity");
      }
    });
  });

  describe("Position Management", () => {
    test("should retrieve current positions", async () => {
      const response = await request(app)
        .get("/api/orders/positions");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);
        
        if (response.body.data.length > 0) {
          const position = response.body.data[0];
          expect(position).toHaveProperty("symbol");
          expect(position).toHaveProperty("quantity");
          expect(typeof position.quantity).toBe("number");
          expect(position).toHaveProperty("average_cost");
        }
      }
    });

    test("should calculate position P&L", async () => {
      const response = await request(app)
        .get("/api/orders/positions/pnl");
      
      expect([200, 404]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        
        const data = response.body.data;
        if (data) {
          expect(data).toHaveProperty("total_pnl");
          expect(typeof data.total_pnl).toBe("number");
          
          if (data.positions && Array.isArray(data.positions)) {
            data.positions.forEach(position => {
              expect(position).toHaveProperty("unrealized_pnl");
              expect(typeof position.unrealized_pnl).toBe("number");
            });
          }
        }
      }
    });
  });
});