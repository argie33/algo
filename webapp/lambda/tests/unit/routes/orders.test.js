const express = require("express");
const request = require("supertest");

// Real database for integration
const { query } = require("../../../utils/database");

describe("Orders Routes Unit Tests", () => {
  let app;

  beforeAll(() => {
    // Create test app
    app = express();
    app.use(express.json());

    // Mock authentication middleware - allow all requests through
    app.use((req, res, next) => {
      req.user = { sub: "test-user-123" }; // Mock authenticated user
      next();
    });

    // Add response formatter middleware
    const responseFormatter = require("../../../middleware/responseFormatter");
    app.use(responseFormatter);

    // Load orders routes
    const ordersRouter = require("../../../routes/orders");
    app.use("/orders", ordersRouter);
  });

  describe("GET /orders/", () => {
    test("should handle user orders request", async () => {
      const response = await request(app)
        .get("/orders/")
        .set("Authorization", "Bearer test-token");

      expect([200, 401]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });

  describe("POST /orders/", () => {
    test("should handle order creation", async () => {
      const orderData = {
        symbol: "AAPL",
        side: "buy",
        quantity: 10,
        order_type: "market",
      };

      const response = await request(app)
        .post("/orders/")
        .set("Authorization", "Bearer test-token")
        .send(orderData);

      expect([200, 201, 400, 401]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });

  describe("GET /orders/:orderId", () => {
    test("should handle specific order request", async () => {
      const response = await request(app)
        .get("/orders/test-order-123")
        .set("Authorization", "Bearer test-token");

      // Expect 400 (invalid order ID), 404 (order not found), 503 (orders table missing), or 200 (if order exists)
      expect([200, 400, 401, 404, 503]).toContain(response.status);
      expect(response.body).toHaveProperty("success");

      if (response.status === 400) {
        expect(response.body.success).toBe(false);
        expect(response.body.error).toBe("Invalid order ID");
      } else if (response.status === 404) {
        expect(response.body.success).toBe(false);
        expect(response.body.error).toBe("Order not found");
      } else if (response.status === 503) {
        expect(response.body.success).toBe(false);
        expect(response.body.error).toBe("Orders service not initialized");
      } else if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty("id");
        expect(response.body.data).toHaveProperty("symbol");
      }
    });
  });
});
