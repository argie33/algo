const request = require("supertest");
const express = require("express");

// Mock database - algo.js's PUT /config/:key handler uses getPool().query(), not the
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

// requireAuth/requireAdmin gate this route with real token verification; replace with
// a stub that always passes and attaches a fixed user, so the route handler under test
// runs without needing the full auth stack.
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: "test-admin-user", role: "admin" };
    next();
  },
  requireAdmin: (req, res, next) => next(),
  requireRole: () => (req, res, next) => next(),
  optionalAuth: (req, res, next) => next(),
  validateSession: (req, res, next) => next(),
  rateLimitByUser: (req, res, next) => next(),
  rateLimitAuth: (req, res, next) => next(),
  logApiAccess: (req, res, next) => next(),
}));

const { getPool } = require("../../../utils/database");
const algoRouter = require("../../../routes/algo");

const app = express();
app.use(express.json());
app.use("/api/algo", algoRouter);

describe("PUT /api/algo/config/:key", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("writes an algo_config_audit row on every config change", async () => {
    // Regression test: this endpoint is the actual path admins use to edit risk-critical
    // config (halt_drawdown_pct, max_daily_loss_pct, sector_drawdown_halt_pct, etc.) via
    // the dashboard, but it never wrote to algo_config_audit - the same audit trail
    // algo/infrastructure/config/main.py's AlgoConfig.update_config() always records.
    const queries = [];
    const mockPool = {
      query: jest.fn((sql, params) => {
        queries.push({ sql, params });
        if (sql.includes("SELECT key, value, value_type, description FROM algo_config")) {
          return Promise.resolve({
            rows: [
              {
                key: "max_daily_loss_pct",
                value: "2.0",
                value_type: "float",
                description: "Max daily loss % before halt",
              },
            ],
          });
        }
        if (sql.trim().startsWith("UPDATE algo_config")) {
          return Promise.resolve({
            rows: [
              {
                key: "max_daily_loss_pct",
                value: "1.5",
                value_type: "float",
                description: "Max daily loss % before halt",
                updated_at: new Date().toISOString(),
              },
            ],
          });
        }
        if (sql.trim().startsWith("INSERT INTO algo_config_audit")) {
          return Promise.resolve({ rows: [] });
        }
        return Promise.resolve({ rows: [] });
      }),
    };
    getPool.mockReturnValue(mockPool);

    const response = await request(app)
      .put("/api/algo/config/max_daily_loss_pct")
      .send({ value: "1.5" })
      .expect(200);

    const body = response.body.data || response.body;
    expect(body.value).toBe(1.5);

    const auditInsert = queries.find((q) =>
      q.sql.trim().startsWith("INSERT INTO algo_config_audit")
    );
    expect(auditInsert).toBeDefined();
    expect(auditInsert.params).toEqual([
      "max_daily_loss_pct",
      "2.0", // old_value
      "1.5", // new_value
      "test-admin-user", // changed_by (from req.user.sub)
    ]);
  });
});
