/**
 * Economic Routes Unit Tests
 *
 * GET / is just a pointer message (sendSuccess(res, { message: "...use
 * /leading-indicators, /calendar..." })) - it does not paginate economic_data rows,
 * filter by series, or 404/503 on missing data (that richer list behavior these tests
 * assumed doesn't exist at "/"). /economic/data doesn't exist as its own route either -
 * it's captured by the /:indicator wildcard (indicator="data"), which looks up a single
 * series by UPPER(series_id). Replaced with coverage of / and /:indicator.
 */
const express = require("express");
const request = require("supertest");

jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

const { query } = require("../../../utils/database");
const economicRouter = require("../../../routes/economic");

describe("Economic Routes Unit Tests", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/economic", economicRouter);
  });

  beforeEach(() => {
    query.mockReset();
  });

  describe("GET /economic", () => {
    test("returns the API pointer message", async () => {
      const response = await request(app).get("/economic").expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.message).toContain(
        "use /leading-indicators, /calendar"
      );
      expect(query).not.toHaveBeenCalled();
    });
  });

  describe("GET /economic/:indicator", () => {
    test("returns the series in chronological order with the latest point called out", async () => {
      query.mockResolvedValueOnce({
        rows: [
          { series_id: "GDP", value: "25100.0", date: "2026-01-01" },
          { series_id: "GDP", value: "25000.0", date: "2025-10-01" },
        ],
      });

      const response = await request(app)
        .get("/economic/gdp")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.indicator).toBe("GDP");
      // Route reverses the DESC-ordered rows, so data[] is chronological (oldest first)
      expect(response.body.data.data[0].date).toBe("2025-10-01");
      expect(response.body.data.latest).toEqual({
        series_id: "GDP",
        date: "2026-01-01",
        value: 25100,
      });
      expect(query).toHaveBeenCalledWith(expect.any(String), ["GDP"]);
    });

    test("404s for a series with no data", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/economic/nonexistent")
        .expect(404);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toBe("Indicator not found: nonexistent");
    });

    test("500s when the database query fails", async () => {
      query.mockRejectedValueOnce(new Error("connection lost"));

      const response = await request(app)
        .get("/economic/gdp")
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain("Failed to fetch indicator");
    });
  });
});
