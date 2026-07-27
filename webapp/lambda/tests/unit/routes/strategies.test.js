/**
 * Strategies Routes Unit Tests
 *
 * Regression coverage for a real bug: GET /covered-calls computed `offset` but never
 * passed it to sendPaginated(), which throws "pagination.offset must be explicitly
 * provided" when offset is missing (see utils/apiResponse.js) - the endpoint 500'd on
 * every single non-empty request in production. There was no test file for this route
 * at all before this fix, so nothing caught it.
 */
const request = require("supertest");
const express = require("express");

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
const strategiesRouter = require("../../../routes/strategies");

describe("Strategies Routes Unit Tests", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/strategies", strategiesRouter);
  });

  beforeEach(() => {
    query.mockReset();
  });

  describe("GET /strategies/covered-calls", () => {
    test("returns paginated covered call opportunities", async () => {
      query
        .mockResolvedValueOnce({ rows: [{ total: "1" }] }) // count query
        .mockResolvedValueOnce({
          rows: [
            {
              id: 1,
              symbol: "AAPL",
              strike: "150.00",
              expiration_date: "2026-02-20",
              premium: "2.50",
              breakeven_pct: "1.5",
              return_pct: "1.67",
              days_to_expiration: 30,
              data_date: "2026-01-15",
              created_at: "2026-01-15T00:00:00.000Z",
            },
          ],
        });

      const response = await request(app)
        .get("/strategies/covered-calls")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.items).toHaveLength(1);
      expect(response.body.items[0].symbol).toBe("AAPL");
      expect(response.body.pagination).toMatchObject({
        page: 1,
        limit: 100,
        offset: 0,
        total: 1,
      });
    });

    test("returns a 503 placeholder when there are no opportunities", async () => {
      query.mockResolvedValueOnce({ rows: [{ total: "0" }] });

      const response = await request(app)
        .get("/strategies/covered-calls")
        .expect(503);

      expect(response.body.success).toBe(false);
    });

    test("computes the correct offset for page 2", async () => {
      query
        .mockResolvedValueOnce({ rows: [{ total: "150" }] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/strategies/covered-calls")
        .query({ page: 2, limit: 50 })
        .expect(200);

      expect(response.body.pagination.offset).toBe(50);
      expect(query).toHaveBeenLastCalledWith(expect.any(String), [50, 50]);
    });
  });
});
