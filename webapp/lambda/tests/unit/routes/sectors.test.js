/**
 * Sectors Routes Unit Tests
 *
 * routes/sectors.js only defines 4 endpoints: / (paginated sector rankings),
 * /trends-batch, /:sector/trend, and /:sector (must be last - a bare wildcard). There is
 * no dedicated /health, /analysis, /list, /:sector/details, /ranking-history, or
 * /industries/ranking-history - index.js only mounts this router at /api/sectors with no
 * other related routes, and grep confirms no matching router.get calls. Requests like
 * GET /sectors/health don't 404 gracefully; they're silently captured by the /:sector
 * wildcard (which treats "health" as a sector name) and either 404 "Sector not found" or
 * 500 depending on the mock - not a dedicated health-check response. Replaced with
 * coverage of the endpoints that actually exist.
 */
const request = require("supertest");
const express = require("express");

jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

const { query } = require("../../../utils/database");
const sectorsRoutes = require("../../../routes/sectors");

describe("Sectors Routes", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/sectors", sectorsRoutes);
  });

  beforeEach(() => {
    query.mockReset();
  });

  describe("GET /sectors/", () => {
    test("returns paginated sector rankings", async () => {
      query
        .mockResolvedValueOnce({
          rows: [
            {
              sector_name: "Technology",
              stock_count: "120",
              composite_score: "65.5",
              momentum_score: "70.2",
              value_score: "40.1",
              quality_score: "68.0",
              growth_score: "72.3",
              stability_score: "55.0",
              perf_1d: "0.5",
              perf_5d: "1.2",
              perf_20d: "3.1",
              current_rank: "1",
              rank_12w_ago: null,
              avg_trailing_pe: "28.5",
              avg_forward_pe: "25.1",
              pe_percentile: "60.0",
            },
          ],
        })
        .mockResolvedValueOnce({ rows: [{ count: "11" }] });

      const response = await request(app).get("/sectors/").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.items).toHaveLength(1);
      const sector = response.body.items[0];
      expect(sector.sector_name).toBe("Technology");
      expect(sector.current_rank).toBe(1);
      expect(sector.current_trend).toBe("Uptrend"); // perf_20d = 3.1 > 2
      expect(sector.pe).toEqual({
        trailing: 28.5,
        forward: 25.1,
        percentile: 60,
      });
      expect(response.body.pagination.total).toBe(11);
    });

    test("500s when the database query fails", async () => {
      query.mockRejectedValueOnce(new Error("connection lost"));

      const response = await request(app).get("/sectors/").expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain("Failed to fetch sectors");
    });
  });

  describe("GET /sectors/trends-batch", () => {
    test("requires the sectors query parameter", async () => {
      const response = await request(app)
        .get("/sectors/trends-batch")
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain("sectors parameter required");
    });

    test("groups returns by sector and compounds into a price index", async () => {
      query.mockResolvedValueOnce({
        rows: [
          { sector: "Technology", date: "2026-01-01", return_pct: "1.0" },
          { sector: "Technology", date: "2026-01-02", return_pct: "-0.5" },
        ],
      });

      const response = await request(app)
        .get("/sectors/trends-batch")
        .query({ sectors: "Technology", days: 30 })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.Technology).toHaveLength(2);
      expect(response.body.data.Technology[0].avgPrice).toBe(101);
    });
  });

  describe("GET /sectors/:sector/trend", () => {
    test("returns historical daily average prices for the sector", async () => {
      query.mockResolvedValueOnce({
        rows: [{ date: "2026-01-01", avgprice: "150.25", stockcount: "42" }],
      });

      const response = await request(app)
        .get("/sectors/Technology/trend")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.sector).toBe("Technology");
      expect(response.body.data.trendData[0]).toMatchObject({
        date: "2026-01-01",
        avgPrice: 150.25,
      });
    });

    test("404s when there is no price data for the sector", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/sectors/NoSuchSector/trend")
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain(
        "No price data for sector: NoSuchSector"
      );
    });
  });

  describe("GET /sectors/:sector", () => {
    test("returns aggregated scores for a known sector", async () => {
      query.mockResolvedValueOnce({
        rows: [
          {
            sector_name: "Technology",
            stock_count: "120",
            composite_score: "65.5",
            momentum_score: "70.2",
            value_score: "40.1",
            quality_score: "68.0",
            growth_score: "72.3",
            stability_score: "55.0",
          },
        ],
      });

      const response = await request(app)
        .get("/sectors/Technology")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual({
        sector_name: "Technology",
        stock_count: 120,
        composite_score: 65.5,
        momentum_score: 70.2,
        value_score: 40.1,
        quality_score: 68,
        growth_score: 72.3,
        stability_score: 55,
      });
    });

    test("404s for an unknown sector - this is what GET /sectors/health actually hits", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app).get("/sectors/health").expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain("Sector not found: health");
    });
  });
});
