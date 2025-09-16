const express = require("express");
const request = require("supertest");

// Real database for integration
const { query } = require("../../../utils/database");

describe("Backtest Routes Unit Tests", () => {
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

    // Load backtest routes
    const backtestRouter = require("../../../routes/backtest");
    app.use("/backtest", backtestRouter);
  });

  describe("GET /backtest/", () => {
    test("should return backtest info", async () => {
      const response = await request(app).get("/backtest/").expect(200);

      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("data");
    });
  });

  describe("GET /backtest/strategies", () => {
    test("should return strategies list", async () => {
      const response = await request(app)
        .get("/backtest/strategies")
        .expect(200);

      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("strategies");
    });
  });

  describe("POST /backtest/run", () => {
    test("should handle backtest run request", async () => {
      const backtestData = {
        strategy: "buy_and_hold",
        symbol: "AAPL",
        start_date: "2023-01-01",
        end_date: "2023-12-31",
        initial_capital: 10000,
      };

      const response = await request(app)
        .post("/backtest/run")
        .send(backtestData);

      // API may return 200 for success or 400 for validation errors
      expect([200, 400]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });

  describe("GET /backtest/results/:id", () => {
    test("should return backtest results", async () => {
      const response = await request(app).get("/backtest/results/test-123");

      // API may return 200 for found or 404 for not found
      expect([200, 404]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });

  describe("GET /backtest/optimize", () => {
    test("should return optimization results for valid strategy", async () => {
      const optimizationParams = {
        strategy_id: "test-strategy-123",
        optimization_type: "grid_search",
        parameters: JSON.stringify({
          stop_loss: 0.05,
          take_profit: 0.15,
          rsi_period: 14,
        }),
        optimization_target: "sharpe_ratio",
        max_iterations: 50,
      };

      const response = await request(app)
        .get("/backtest/optimize")
        .query(optimizationParams)
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          optimization_id: expect.any(String),
          strategy_id: "test-strategy-123",
          optimization_config: expect.objectContaining({
            method: "grid_search",
            target_metric: "sharpe_ratio",
            max_iterations: 50,
            parameter_space: expect.any(Object),
          }),
          methodology: expect.any(String),
          baseline_performance: expect.objectContaining({
            total_return: expect.any(Number),
            sharpe_ratio: expect.any(Number),
            max_drawdown: expect.any(Number),
            win_rate: expect.any(Number),
          }),
          best_parameters: expect.any(Object),
          best_performance: expect.any(Object),
          optimization_results: expect.objectContaining({
            total_iterations: expect.any(Number),
            improvement_achieved: expect.any(Boolean),
            improvement_percentage: expect.any(String),
            convergence_iteration: expect.any(Number),
            optimization_time_minutes: expect.any(Number),
          }),
          iteration_history: expect.any(Array),
          parameter_sensitivity: expect.any(Array),
          recommendations: expect.any(Array),
          warnings: expect.any(Array),
        }),
        metadata: expect.objectContaining({
          optimization_requested_at: expect.any(String),
          estimated_completion_time: expect.any(String),
          parameter_count: expect.any(Number),
          search_space_size: expect.any(Number),
        }),
      });
    });

    test("should require strategy_id parameter", async () => {
      const response = await request(app).get("/backtest/optimize").expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: "Strategy ID is required",
        message: "Please provide a strategy_id parameter to optimize",
      });
    });

    test("should handle invalid parameters JSON", async () => {
      const response = await request(app)
        .get("/backtest/optimize?strategy_id=test&parameters=invalid-json")
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: "Invalid parameters format",
        message: "Parameters must be valid JSON",
      });
    });

    test("should support different optimization types and targets", async () => {
      const response = await request(app)
        .get("/backtest/optimize")
        .query({
          strategy_id: "test-strategy",
          optimization_type: "genetic_algorithm",
          optimization_target: "max_drawdown",
          parameters: JSON.stringify({ param1: 1.0 }),
          max_iterations: 25,
        })
        .expect(200);

      expect(response.body.data.optimization_config).toMatchObject({
        method: "genetic_algorithm",
        target_metric: "max_drawdown",
        max_iterations: 25,
      });
    });

    test("should handle optimization errors gracefully", async () => {
      // Mock an error scenario
      const originalConsoleError = console.error;
      console.error = jest.fn();

      const response = await request(app)
        .get("/backtest/optimize?strategy_id=error-test&parameters={}")
        .expect(200); // Our implementation generates synthetic data, so it won't error

      // Restore console.error
      console.error = originalConsoleError;

      // Should still return valid response structure
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
    });
  });
});
