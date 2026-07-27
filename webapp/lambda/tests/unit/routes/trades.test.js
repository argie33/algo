/**
 * Trades Routes Unit Tests
 *
 * routes/trades.js only defines 2 endpoints: / (combined Alpaca + database trade list)
 * and /summary (aggregate stats over the same combined source) - grep confirms no
 * /health, /import/status, /history, /analytics, /import, /export, /brokers,
 * /sync/:broker, /performance, /performance/attribution, /stats, /validate, or /search
 * routes exist. This router also does NOT apply authenticateToken itself (see its own
 * comment: auth is applied at the index.js mount point, before cacheMiddleware) - each
 * handler checks req.user.sub/id directly and 401s if absent, so tests must inject
 * req.user via their own middleware rather than mocking middleware/auth.
 */
const request = require("supertest");
const express = require("express");

jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  safeFloat: (v) => (v === null || v === undefined ? null : parseFloat(v)),
  safeInt: (v) => (v === null || v === undefined ? null : parseInt(v, 10)),
}));

const { query } = require("../../../utils/database");
const tradesRouter = require("../../../routes/trades");

function buildApp(withUser = true) {
  const app = express();
  app.use(express.json());
  if (withUser) {
    app.use((req, res, next) => {
      req.user = { sub: "test-user-123" };
      next();
    });
  }
  app.use("/trades", tradesRouter);
  return app;
}

describe("Trades Routes Unit Tests", () => {
  let app;

  beforeAll(() => {
    app = buildApp();
    // No Alpaca credentials set - both handlers skip the Alpaca fetch and only hit the
    // database branch, which is what these tests exercise.
    delete process.env.APCA_API_KEY_ID;
    delete process.env.APCA_API_SECRET_KEY;
  });

  beforeEach(() => {
    query.mockReset();
  });

  describe("GET /trades/", () => {
    test("returns combined trades with pagination and filters metadata", async () => {
      query.mockResolvedValueOnce({
        rows: [
          {
            id: 1,
            symbol: "AAPL",
            side: "buy",
            quantity: "10",
            execution_price: "150.00",
            trade_date: "2026-01-15",
          },
        ],
      });

      const response = await request(app).get("/trades/").expect(200);

      // sendSuccess() detects a `pagination` key on the payload and spreads it flat
      // onto the response root instead of wrapping in `data` - see utils/apiResponse.js.
      expect(response.body.success).toBe(true);
      expect(response.body.trades).toHaveLength(1);
      expect(response.body.trades[0]).toMatchObject({
        symbol: "AAPL",
        type: "buy",
        quantity: 10,
        price: 150,
        source: "manual",
      });
      expect(response.body.pagination).toMatchObject({
        page: 1,
        limit: 50,
        total: 1,
      });
      expect(response.body.filters.sort).toBe("date_desc");
    });

    test("401s when there is no authenticated user", async () => {
      const noAuthApp = buildApp(false);
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(noAuthApp).get("/trades/").expect(401);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toBe("Authentication required");
    });

    test("scopes the query to the authenticated user", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      await request(app).get("/trades/").expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("user_id = $1"),
        expect.arrayContaining(["test-user-123"])
      );
    });
  });

  describe("GET /trades/summary", () => {
    test("aggregates totals across the returned trades", async () => {
      query.mockResolvedValueOnce({
        rows: [
          {
            symbol: "AAPL",
            side: "buy",
            quantity: "10",
            execution_price: "150.00",
            order_value: "1500.00",
            commission: "1.00",
          },
          {
            symbol: "MSFT",
            side: "sell",
            quantity: "5",
            execution_price: "300.00",
            order_value: "1500.00",
            commission: "1.00",
          },
        ],
      });

      const response = await request(app)
        .get("/trades/summary")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toMatchObject({
        totalTrades: 2,
        buys: 1,
        sells: 1,
        totalValue: 3000,
        totalCommission: 2,
        uniqueSymbols: 2,
        uniqueSources: 1,
      });
    });

    test("401s when there is no authenticated user", async () => {
      const noAuthApp = buildApp(false);

      const response = await request(noAuthApp)
        .get("/trades/summary")
        .expect(401);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toBe("Authentication required");
    });
  });
});
