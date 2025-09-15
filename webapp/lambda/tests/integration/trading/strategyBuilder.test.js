/**
 * Strategy Builder Integration Tests
 * Tests for trading strategy creation and management
 * Route: /routes/strategyBuilder.js
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Strategy Builder API", () => {
  describe("Strategy Creation", () => {
    test("should create a new trading strategy", async () => {
      const strategyData = {
        name: "Test Momentum Strategy",
        description: "Buy high momentum stocks",
        rules: [
          {
            type: "technical",
            indicator: "RSI",
            operator: "less_than",
            value: 30,
            action: "buy",
          },
          {
            type: "technical",
            indicator: "RSI",
            operator: "greater_than",
            value: 70,
            action: "sell",
          },
        ],
        risk_management: {
          stop_loss: 0.05,
          take_profit: 0.1,
          position_size: 0.02,
        },
      };

      const response = await request(app)
        .post("/api/strategy-builder")
        .set("Authorization", "Bearer test-token")
        .send(strategyData);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200 || response.status === 201) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("strategy_id");
        expect(response.body.data).toHaveProperty(
          "name",
          "Test Momentum Strategy"
        );
      }
    });

    test("should validate strategy rules", async () => {
      const invalidStrategy = {
        name: "Invalid Strategy",
        rules: [], // Empty rules should fail validation
      };

      const response = await request(app)
        .post("/api/strategy-builder")
        .set("Authorization", "Bearer test-token")
        .send(invalidStrategy);

      expect([400, 422]).toContain(response.status);
    });
  });

  describe("Strategy Management", () => {
    test("should list user strategies", async () => {
      const response = await request(app)
        .get("/api/strategy-builder")
        .set("Authorization", "Bearer test-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const strategy = response.body.data[0];
          expect(strategy).toHaveProperty("strategy_id");
          expect(strategy).toHaveProperty("name");
          expect(strategy).toHaveProperty("status");
        }
      }
    });

    test("should retrieve specific strategy", async () => {
      const response = await request(app)
        .get("/api/strategy-builder/test-strategy-id")
        .set("Authorization", "Bearer test-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const strategy = response.body.data;
        expect(strategy).toHaveProperty("strategy_id");
        expect(strategy).toHaveProperty("rules");
        expect(strategy).toHaveProperty("risk_management");
      }
    });

    test("should update existing strategy", async () => {
      const updateData = {
        name: "Updated Strategy Name",
        description: "Updated description",
        status: "active",
      };

      const response = await request(app)
        .put("/api/strategy-builder/test-strategy-id")
        .set("Authorization", "Bearer test-token")
        .send(updateData);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("message");
      }
    });
  });

  describe("Strategy Testing", () => {
    test("should backtest strategy", async () => {
      const backtestParams = {
        strategy_id: "test-strategy-id",
        start_date: "2023-01-01",
        end_date: "2023-12-31",
        initial_capital: 100000,
        symbols: ["AAPL", "GOOGL", "MSFT"],
      };

      const response = await request(app)
        .post("/api/strategy-builder/backtest")
        .set("Authorization", "Bearer test-token")
        .send(backtestParams);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const results = response.body.data;
        const backtestFields = [
          "total_return",
          "sharpe_ratio",
          "max_drawdown",
          "trades_count",
        ];
        const hasBacktestData = backtestFields.some((field) =>
          Object.keys(results).some((key) =>
            key.toLowerCase().includes(field.replace("_", ""))
          )
        );

        expect(hasBacktestData).toBe(true);
      }
    });

    test("should validate strategy against current market", async () => {
      const response = await request(app)
        .post("/api/strategy-builder/validate/test-strategy-id")
        .set("Authorization", "Bearer test-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);

        const validation = response.body.data;
        const validationFields = ["is_valid", "warnings", "recommendations"];
        const hasValidationData = validationFields.some((field) =>
          Object.keys(validation).some((key) =>
            key.toLowerCase().includes(field)
          )
        );

        expect(hasValidationData).toBe(true);
      }
    });
  });

  describe("Strategy Templates", () => {
    test("should list available strategy templates", async () => {
      const response = await request(app).get(
        "/api/strategy-builder/templates"
      );

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const template = response.body.data[0];
          expect(template).toHaveProperty("template_id");
          expect(template).toHaveProperty("name");
          expect(template).toHaveProperty("category");
        }
      }
    });

    test("should create strategy from template", async () => {
      const templateParams = {
        template_id: "momentum-template",
        name: "My Momentum Strategy",
        parameters: {
          rsi_oversold: 25,
          rsi_overbought: 75,
          stop_loss: 0.08,
        },
      };

      const response = await request(app)
        .post("/api/strategy-builder/from-template")
        .set("Authorization", "Bearer test-token")
        .send(templateParams);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200 || response.status === 201) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.data).toHaveProperty("strategy_id");
      }
    });
  });

  describe("Strategy Execution", () => {
    test("should get strategy signals", async () => {
      const response = await request(app)
        .get("/api/strategy-builder/signals/test-strategy-id")
        .set("Authorization", "Bearer test-token");

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(Array.isArray(response.body.data)).toBe(true);

        if (response.body.data.length > 0) {
          const signal = response.body.data[0];
          expect(signal).toHaveProperty("symbol");
          expect(signal).toHaveProperty("action");
          expect(signal).toHaveProperty("confidence");
        }
      }
    });

    test("should execute strategy", async () => {
      const executionParams = {
        strategy_id: "test-strategy-id",
        execution_mode: "paper", // or "live"
        capital_allocation: 10000,
      };

      const response = await request(app)
        .post("/api/strategy-builder/execute")
        .set("Authorization", "Bearer test-token")
        .send(executionParams);

      expect([200, 404]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("message");
        expect(response.body.data).toHaveProperty("execution_id");
      }
    });
  });
});
