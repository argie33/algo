/**
 * Sentiment Routes Unit Tests
 *
 * routes/sentiment.js's real endpoints are /, /data, /summary, /analyst, /history,
 * /current, /divergence, /social/insights/:symbol, /aaii, /analyst/insights/:symbol.
 * /health, /analysis, /stock/:symbol, /social, /trending, and /market (the endpoints the
 * old version of this file tested) don't exist - grep confirms no matching router.get
 * calls. Replaced with coverage of the real endpoints.
 */
const express = require("express");
const request = require("supertest");

jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

const { query } = require("../../../utils/database");
const sentimentRouter = require("../../../routes/sentiment");

describe("Sentiment Routes Unit Tests", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/sentiment", sentimentRouter);
  });

  beforeEach(() => {
    query.mockReset();
  });

  describe("GET /sentiment", () => {
    test("returns the API pointer message", async () => {
      const response = await request(app).get("/sentiment").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.message).toContain(
        "use /summary, /data, /analyst"
      );
    });
  });

  describe("GET /sentiment/data", () => {
    test("returns paginated sentiment rows", async () => {
      query
        .mockResolvedValueOnce({ rows: [{ total: "1" }] }) // count query
        .mockResolvedValueOnce({
          rows: [
            {
              symbol: "AAPL",
              date: "2026-01-01",
              analyst_count: 10,
              bullish_count: 6,
              bearish_count: 2,
              neutral_count: 2,
            },
          ],
        });

      const response = await request(app).get("/sentiment/data").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.items).toHaveLength(1);
      expect(response.body.items[0].symbol).toBe("AAPL");
    });

    test("returns a 503 placeholder when there is no data", async () => {
      query
        .mockResolvedValueOnce({ rows: [{ total: "0" }] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app).get("/sentiment/data").expect(503);

      expect(response.body.success).toBe(false);
    });

    test("500s when the database query throws", async () => {
      query.mockRejectedValue(new Error("connection lost"));

      const response = await request(app).get("/sentiment/data").expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain("Failed to fetch sentiment data");
    });
  });

  describe("GET /sentiment/summary", () => {
    test("combines fear_greed/naaim/aaii/analyst into one summary object", async () => {
      query
        .mockResolvedValueOnce({ rows: [{ value: 55, date: "2026-01-01" }] })
        .mockResolvedValueOnce({
          rows: [{ naaim_number_mean: 60, bullish: 5, bearish: 2, date: "2026-01-01" }],
        })
        .mockResolvedValueOnce({
          rows: [{ bullish: 35, neutral: 40, bearish: 25, date: "2026-01-01" }],
        })
        .mockResolvedValueOnce({
          rows: [{ analyst_count: 12, bullish_count: 8, bearish_count: 2, neutral_count: 2, date: "2026-01-01" }],
        });

      const response = await request(app)
        .get("/sentiment/summary")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.fear_greed.value).toBe(55);
      expect(response.body.data.naaim.naaim_number_mean).toBe(60);
      expect(response.body.data.aaii.bullish).toBe(35);
      expect(response.body.data.analyst.analyst_count).toBe(12);
    });

    test("tolerates individual data sources failing", async () => {
      query
        .mockRejectedValueOnce(new Error("fear_greed_index missing"))
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/sentiment/summary")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.fear_greed).toBeNull();
    });
  });

  describe("GET /sentiment/aaii", () => {
    test("returns the latest AAII row", async () => {
      query.mockResolvedValueOnce({
        rows: [{ bullish: 35.5, neutral: 36.3, bearish: 28.2, date: "2026-01-01" }],
      });

      const response = await request(app).get("/sentiment/aaii").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toMatchObject({ bullish: 35.5, bearish: 28.2 });
    });

    test("returns a 503 placeholder when no AAII data exists", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app).get("/sentiment/aaii").expect(503);

      expect(response.body.success).toBe(false);
    });
  });

  describe("GET /sentiment/social/insights/:symbol", () => {
    test("always returns 404 - social sentiment data is not available", async () => {
      const response = await request(app)
        .get("/sentiment/social/insights/AAPL")
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toBe("Social sentiment data not available");
    });
  });
});
