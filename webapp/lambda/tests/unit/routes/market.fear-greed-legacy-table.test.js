const request = require("supertest");
const express = require("express");

// Regression test: GET /api/market/fear-greed read only from fear_greed_index, a legacy
// table frozen since 2026-07-09 (superseded by the fear_greed_index column on
// market_sentiment, which the current loader keeps live - see
// algo/monitoring/pipeline_health.py KNOWN_DEPRECATED_TABLES). The chart always missed the
// most recent ~18 days of sentiment. The query now merges both sources so the freshest
// value wins regardless of which table holds it, without dropping fear_greed_index's much
// longer history (market_sentiment only has ~10 days of it).
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  closeDatabase: jest.fn(),
  initializeDatabase: jest.fn(),
  getPool: jest.fn(),
  transaction: jest.fn(),
  healthCheck: jest.fn(),
}));

const { query } = require("../../../utils/database");
const marketRouter = require("../../../routes/market");

const app = express();
app.use(express.json());
app.use("/api/market", marketRouter);

describe("GET /api/market/fear-greed", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test("query merges market_sentiment (live) and fear_greed_index (legacy) instead of the legacy table alone", async () => {
    query.mockImplementation((sql) => {
      expect(sql).toMatch(/market_sentiment/);
      expect(sql).toMatch(/fear_greed_index/);
      return Promise.resolve({
        rows: [
          { date: "2026-07-09", fear_greed_value: 70.1 },
          { date: "2026-07-27", fear_greed_value: 62.84 },
        ],
      });
    });

    const response = await request(app)
      .get("/api/market/fear-greed?range=30d")
      .expect(200);

    const body = response.body.data || response.body;
    const dates = (body.items || []).map((r) => r.date);
    expect(dates).toContain("2026-07-27");
  });
});
