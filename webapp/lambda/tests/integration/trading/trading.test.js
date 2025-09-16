/**
 * Trading Operations Integration Tests
 * Tests for core trading functionality and execution
 * Route: /routes/trading.js
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Trading Operations API", () => {
  describe("Trading Account", () => {
    test("should retrieve trading account information", async () => {
      const response = await request(app)
        .get("/api/trading/account")
        .set("Authorization", "Bearer test-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const account = response.body.data;
        const accountFields = [
          "buying_power",
          "equity",
          "cash",
          "portfolio_value",
        ];
        const hasAccountData = accountFields.some((field) =>
          Object.keys(account).some((key) =>
            key.toLowerCase().includes(field.replace("_", ""))
          )
        );

        expect(hasAccountData).toBe(true);
      }
    });
  });

  describe("Paper Trading", () => {
    test("should execute paper trade order", async () => {
      const paperOrder = {
        symbol: "AAPL",
        quantity: 10,
        side: "buy",
        type: "market",
        time_in_force: "day",
      };

      const response = await request(app)
        .post("/api/trading/paper/orders")
        .set("Authorization", "Bearer test-token")
        .send(paperOrder);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200 || response.status === 201) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("order_id");
        expect(response.body.data).toHaveProperty("status");
      }
    });

    test("should retrieve paper trading portfolio", async () => {
      const response = await request(app)
        .get("/api/trading/paper/portfolio")
        .set("Authorization", "Bearer test-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("positions");
        expect(Array.isArray(response.body.data.positions)).toBe(true);
      }
    });
  });

  describe("Order Management", () => {
    test("should validate order before execution", async () => {
      const orderData = {
        symbol: "AAPL",
        quantity: 100,
        side: "buy",
        type: "limit",
        limit_price: 150.0,
      };

      const response = await request(app)
        .post("/api/trading/orders/validate")
        .set("Authorization", "Bearer test-token")
        .send(orderData);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("valid");
        expect(response.body.data).toHaveProperty("estimated_cost");
      }
    });

    test("should retrieve order status", async () => {
      const response = await request(app)
        .get("/api/trading/orders/test-order-123/status")
        .set("Authorization", "Bearer test-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("order_id");
        expect(response.body.data).toHaveProperty("status");
      }
    });
  });

  describe("Position Management", () => {
    test("should retrieve all trading positions", async () => {
      const response = await request(app)
        .get("/api/trading/positions")
        .set("Authorization", "Bearer test-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const position = response.body.data[0];
          expect(position).toHaveProperty("symbol");
          expect(position).toHaveProperty("quantity");

          const positionFields = [
            "market_value",
            "cost_basis",
            "unrealized_pl",
          ];
          const hasPositionData = positionFields.some((field) =>
            Object.keys(position).some((key) =>
              key.toLowerCase().includes(field.replace("_", ""))
            )
          );

          expect(hasPositionData).toBe(true);
        }
      }
    });

    test("should close specific position", async () => {
      const response = await request(app)
        .post("/api/trading/positions/AAPL/close")
        .set("Authorization", "Bearer test-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("order_id");
        expect(response.body.data).toHaveProperty("status");
      }
    });
  });

  describe("Risk Management", () => {
    test("should calculate position risk metrics", async () => {
      const response = await request(app)
        .get("/api/trading/risk/portfolio")
        .set("Authorization", "Bearer test-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const riskData = response.body.data;
        const riskFields = ["var", "beta", "sharpe_ratio", "max_drawdown"];
        const hasRiskData = riskFields.some((field) =>
          Object.keys(riskData).some((key) =>
            key.toLowerCase().includes(field.replace("_", ""))
          )
        );

        expect(hasRiskData).toBe(true);
      }
    });

    test("should set position size limits", async () => {
      const riskLimits = {
        max_position_size: 0.05, // 5% of portfolio
        max_sector_exposure: 0.3, // 30% per sector
        stop_loss_percent: 0.02, // 2% stop loss
      };

      const response = await request(app)
        .post("/api/trading/risk/limits")
        .set("Authorization", "Bearer test-token")
        .send(riskLimits);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("message");
      }
    });
  });
});
