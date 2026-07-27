const request = require("supertest");
const express = require("express");

// Regression test: GET /api/algo/performance and /api/algo/performance-analytics used to
// read from algo_performance_metrics, a table with no writer since 2026-06-30 (see
// lambda/api/routes/algo_handlers/metrics.py for the same bug already fixed on the Python
// dashboard API). Both endpoints silently served that one fixed 2026-06-30 snapshot as if
// it were today's performance on every request. They now read sharpe/sortino/calmar/
// max_drawdown from algo_performance_daily (written every orchestrator run) and compute
// trade counts/win rate/avg win-loss/profit factor live from algo_trades.
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  closeDatabase: jest.fn(),
  initializeDatabase: jest.fn(),
  ensureConnection: jest.fn(),
  getPool: jest.fn(),
  transaction: jest.fn(),
  healthCheck: jest.fn(),
}));

jest.mock("../../../middleware/auth", () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: "test-user", role: "user" };
    next();
  },
  requireAdmin: (req, res, next) => next(),
  requireRole: () => (req, res, next) => next(),
  optionalAuth: (req, res, next) => next(),
  validateSession: (req, res, next) => next(),
}));

const { getPool } = require("../../../utils/database");
const algoRouter = require("../../../routes/algo");

const app = express();
app.use(express.json());
app.use("/api/algo", algoRouter);

describe("GET /api/algo/performance", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("never queries the dead algo_performance_metrics table", async () => {
    const mockPool = {
      query: jest.fn((sql) => {
        expect(sql).not.toMatch(/algo_performance_metrics/);
        if (sql.includes("FROM algo_positions")) {
          return Promise.resolve({
            rows: [
              {
                open_count: 0,
                open_wins: 0,
                open_losses: 0,
                total_unrealized_pnl: 0,
              },
            ],
          });
        }
        return Promise.resolve({
          rows: [
            {
              total_trades: 33,
              winning_trades: 13,
              losing_trades: 15,
              win_rate_pct: "46.43",
              avg_win_pct: "0.949",
              avg_loss_pct: "-1.157",
              avg_win_r: null,
              avg_loss_r: null,
              expectancy_r: null,
              profit_factor: "0.7833",
              total_pnl_dollars: "-81.81",
              gross_win_dollars: "295.64",
              gross_loss_dollars: "-377.45",
              total_return_pct: null,
              sharpe_annualized: "-0.7790",
              sortino_annualized: "-0.9620",
              calmar_ratio: "-0.5600",
              max_drawdown_pct: "7.35",
              current_win_streak: null,
              best_win_streak: null,
              worst_loss_streak: null,
              avg_hold_days: null,
              portfolio_snapshots_count: null,
            },
          ],
        });
      }),
    };
    getPool.mockReturnValue(mockPool);

    const response = await request(app).get("/api/algo/performance").expect(200);
    const body = response.body.data || response.body;

    expect(body.max_drawdown_pct).toBeCloseTo(7.35);
    expect(body.sharpe_annualized).toBeCloseTo(-0.779);
    expect(body.calmar_ratio).toBeCloseTo(-0.56);
    expect(body.total_pnl_dollars).toBeCloseTo(-81.81);
  });
});

describe("GET /api/algo/performance-analytics", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("never queries the dead algo_performance_metrics table and maps calmar correctly", async () => {
    // Also locks in a second, independent bug: the old query selected calmar_ratio
    // unaliased while the response schema looked up "calmar", so perf.calmar was always
    // null regardless of table freshness.
    const mockPool = {
      query: jest.fn((sql) => {
        expect(sql).not.toMatch(/algo_performance_metrics/);
        return Promise.resolve({
          rows: [
            {
              win_rate_pct: "42.31",
              avg_win_pct: "0.949",
              avg_loss_pct: "-1.157",
              profit_factor: "0.7833",
              total_return_pct: null,
              sharpe252: "-0.7790",
              sortino: "-0.9620",
              calmar: "-0.5600",
              max_drawdown_pct: "7.35",
              best_win_streak: null,
              worst_loss_streak: null,
              avg_holding_days: null,
            },
          ],
        });
      }),
    };
    getPool.mockReturnValue(mockPool);

    const response = await request(app)
      .get("/api/algo/performance-analytics")
      .expect(200);
    const body = response.body.data || response.body;

    expect(body.calmar).toBeCloseTo(-0.56);
    expect(body.maxdd).toBeCloseTo(7.35);
    expect(body.sharpe252).toBeCloseTo(-0.779);
  });
});
