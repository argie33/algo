/**
 * Performance Routes Unit Tests
 *
 * routes/performance.js was rewritten down to 3 endpoints (/, /metrics, /trades) that
 * read algo_performance_daily/algo_trades directly - the old /health, /benchmark,
 * /analytics, /attribution, /portfolio/:symbol endpoints and the utils/performanceMonitor
 * dependency this file used to mock don't exist anymore (grep confirms zero references
 * to performanceMonitor in routes/performance.js). Replaced with coverage of what's
 * actually there.
 */
const express = require("express");
const request = require("supertest");

jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123" };
    next();
  }),
}));

const { query } = require("../../../utils/database");
const performanceRouter = require("../../../routes/performance");

describe("Performance Routes Unit Tests", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/performance", performanceRouter);
  });

  beforeEach(() => {
    query.mockReset();
  });

  describe("GET /performance/ and /performance/metrics", () => {
    const fullMetricsRow = {
      total_trades: 20,
      win_count: 12,
      loss_count: 8,
      win_rate_pct: 60,
      gross_profit: 5000,
      gross_loss: -2000,
      profit_factor: 2.5,
      total_pnl: 3000,
      avg_pnl_per_trade: 150,
      avg_return_pct: 0.02,
      avg_win: 416.67,
      avg_loss: -250,
      avg_win_pct: 3.5,
      avg_loss_pct: -2.1,
      avg_hold_days: 5.5,
      avg_r_multiple: 1.2,
      sharpe_ratio: 1.8,
      max_drawdown: -8.5,
      calmar_ratio: 1.1,
      biggest_win: 900,
      biggest_loss: -400,
      best_trade_r: 3.2,
      worst_trade_r: -1.5,
    };

    test("root endpoint returns the same metrics as /metrics", async () => {
      query.mockResolvedValue({ rows: [fullMetricsRow], rowCount: 1 });

      const response = await request(app).get("/performance/").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.summary.total_trades).toBe(20);
      expect(response.body.data.profitability.total_pnl).toBe(3000);
      expect(response.body.data.risk_metrics.sharpe_ratio).toBe(1.8);
    });

    test("returns zeroed summary when no report exists for today", async () => {
      query.mockResolvedValue({ rows: [], rowCount: 0 });

      const response = await request(app)
        .get("/performance/metrics")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.summary).toEqual({
        total_trades: 0,
        win_count: 0,
        loss_count: 0,
        breakeven_count: 0,
        win_rate_pct: 0,
      });
    });

    test("503s when a critical metric is missing from the row", async () => {
      const { sharpe_ratio, ...incomplete } = fullMetricsRow;
      query.mockResolvedValue({ rows: [incomplete], rowCount: 1 });

      const response = await request(app)
        .get("/performance/metrics")
        .expect(503);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain("incomplete data");
      expect(response.body.message).toContain("sharpe_ratio");
    });

    test("500s when the database query throws", async () => {
      query.mockRejectedValue(new Error("connection lost"));

      const response = await request(app)
        .get("/performance/metrics")
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toBe("Failed to fetch performance metrics");
    });
  });

  describe("GET /performance/trades", () => {
    test("returns recent closed trades", async () => {
      query.mockResolvedValue({
        rows: [
          {
            trade_id: "TRD-1",
            symbol: "AAPL",
            entry_date: "2026-01-01",
            entry_price: "150.00",
            exit_date: "2026-01-10",
            exit_price: "160.00",
            profit_loss_dollars: "1000.00",
            profit_loss_pct: "6.67",
            trade_duration_days: 9,
            exit_r_multiple: "2.0",
            status: "closed",
          },
        ],
        rowCount: 1,
      });

      const response = await request(app)
        .get("/performance/trades")
        .expect(200);

      // sendSuccess() wraps array payloads as { items, pagination }, not { data } -
      // see utils/apiResponse.js.
      expect(response.body.success).toBe(true);
      expect(response.body.items).toHaveLength(1);
      expect(response.body.items[0]).toMatchObject({
        trade_id: "TRD-1",
        symbol: "AAPL",
        entry_price: 150,
        exit_price: 160,
        pnl_dollars: 1000,
        r_multiple: 2,
        status: "closed",
      });
      expect(query).toHaveBeenCalledWith(expect.any(String), [20]);
    });

    test("respects a custom limit query param", async () => {
      query.mockResolvedValue({ rows: [], rowCount: 0 });

      await request(app).get("/performance/trades?limit=5").expect(200);

      expect(query).toHaveBeenCalledWith(expect.any(String), [5]);
    });

    test("500s when the database query throws", async () => {
      query.mockRejectedValue(new Error("connection lost"));

      const response = await request(app)
        .get("/performance/trades")
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toBe("Failed to fetch recent trades");
    });
  });
});
