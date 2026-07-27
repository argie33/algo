const request = require("supertest");
const express = require("express");

// Mock database - algo.js's /swing-scores handler uses getPool().query(), not the
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

describe("GET /api/algo/swing-scores", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("returns null grade/pass_gates (not F/0) for a row with missing composite_score", async () => {
    // Regression test: a stock with no composite_score data previously fell through
    // to `score = r.composite_score || 0`, which reported it as grade "F" and
    // pass_gates=false - indistinguishable from a stock that was actually evaluated
    // and failed. Missing data must read as "no grade available", not the worst
    // possible real grade.
    const mockPool = {
      query: jest.fn().mockResolvedValue({
        rows: [
          {
            symbol: "NEWCO",
            composite_score: null,
            momentum_score: null,
            quality_score: null,
            growth_score: null,
            value_score: null,
            positioning_score: null,
            stability_score: null,
            updated_at: "2026-07-27",
            short_name: "New Co",
            sector: "Technology",
            industry: "Software",
          },
        ],
      }),
    };
    getPool.mockReturnValue(mockPool);

    const response = await request(app).get("/api/algo/swing-scores");

    expect(response.status).toBe(200);
    const stock = response.body.items[0];
    expect(stock.composite_score).toBeNull();
    expect(stock.score).toBeNull();
    expect(stock.grade).toBeNull();
    expect(stock.pass_gates).toBe(false);
    expect(stock.fail_reason).toBe("composite_score_unavailable");
    expect(stock.components).toEqual({
      setup: null,
      trend: null,
      momentum: null,
      volume: null,
      fundamentals: null,
      sector: null,
      multi_tf: null,
    });
  });

  test("still assigns grade F and real component values for a real, validated low score", async () => {
    const mockPool = {
      query: jest.fn().mockResolvedValue({
        rows: [
          {
            symbol: "LOWCO",
            composite_score: 12.5,
            momentum_score: 5,
            quality_score: 0,
            growth_score: 10,
            value_score: 20,
            positioning_score: 15,
            stability_score: 8,
            updated_at: "2026-07-27",
            short_name: "Low Co",
            sector: "Energy",
            industry: "Oil & Gas",
          },
        ],
      }),
    };
    getPool.mockReturnValue(mockPool);

    const response = await request(app).get("/api/algo/swing-scores");

    expect(response.status).toBe(200);
    const stock = response.body.items[0];
    expect(stock.composite_score).toBe(12.5);
    expect(stock.grade).toBe("F");
    expect(stock.pass_gates).toBe(false);
    expect(stock.fail_reason).toBe("composite_score < 60");
    // quality_score: 0 is a real, validated zero - must stay 0, not be treated as missing
    expect(stock.components.fundamentals).toBe(0);
  });
});
