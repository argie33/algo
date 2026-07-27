const request = require("supertest");
const express = require("express");

// Mock database - algo.js's /circuit-breakers handler uses getPool().query(), not the
// module-level query() function other routes use.
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  closeDatabase: jest.fn(),
  initializeDatabase: jest.fn(),
  ensureConnection: jest.fn(),
  getPool: jest.fn(),
  transaction: jest.fn(),
  healthCheck: jest.fn(),
}));

const { getPool } = require("../../../utils/database");
const algoRouter = require("../../../routes/algo");

const app = express();
app.use(express.json());
app.use("/api/algo", algoRouter);

describe("GET /api/algo/circuit-breakers", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("does not permanently report drawdown as triggered when halt_drawdown_pct is stored negative", async () => {
    // Regression test: halt_drawdown_pct is stored negative in algo_config (-10 = halt
    // at 10% down, same convention as algo/risk/circuit_breaker.py and
    // loaders/compute_circuit_breakers.py). The threshold must be abs()'d before
    // comparing against the (always non-negative) current drawdown - without that, the
    // comparison "positive_drawdown >= -10" is always true and this breaker never clears.
    const mockPool = {
      query: jest.fn((sql) => {
        if (sql.includes("FROM circuit_breaker_status")) {
          return Promise.resolve({
            rows: [
              {
                portfolio_drawdown_pct: 2.5, // well under the real 10% halt line
                daily_loss_pct: 0.1,
                weekly_loss_pct: 0.2,
                open_risk_pct: 1.0,
                consecutive_losses: 0,
                vix_level: 15.0,
                market_stage: 2,
                spy_prior_day_change_pct: 0.1,
                win_rate_last_30_pct: 55.0,
              },
            ],
          });
        }
        if (sql.includes("FROM market_health_daily")) {
          return Promise.resolve({ rows: [{ market_trend: "uptrend" }] });
        }
        if (sql.includes("FROM algo_config")) {
          return Promise.resolve({
            rows: [
              { key: "halt_drawdown_pct", value: "-10" },
              { key: "max_daily_loss_pct", value: "2.0" },
              { key: "max_consecutive_losses", value: "3" },
              { key: "max_total_risk_pct", value: "4.0" },
              { key: "vix_max_threshold", value: "35.0" },
              { key: "max_weekly_loss_pct", value: "5.0" },
            ],
          });
        }
        return Promise.resolve({ rows: [] });
      }),
    };
    getPool.mockReturnValue(mockPool);

    const response = await request(app)
      .get("/api/algo/circuit-breakers")
      .expect(200);

    const body = response.body.data || response.body;
    const drawdownBreaker = body.breakers.find((b) => b.id === "drawdown");
    expect(drawdownBreaker.threshold).toBe(10);
    expect(drawdownBreaker.triggered).toBe(false);
    expect(body.any_triggered).toBe(false);
  });
});
