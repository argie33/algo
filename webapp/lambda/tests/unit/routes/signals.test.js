/**
 * Signals Routes Unit Tests
 *
 * routes/signals.js only defines 3 endpoints: / (buy/sell signals from
 * buy_sell_{daily,weekly,monthly}), /stocks (same tables, richer per-stock fields), and
 * /etf (the *_etf variant tables). /buy, /sell, /technical, /momentum, /options,
 * /alerts, /sentiment, /earnings, /crypto, /history, /sector-rotation, /list, and
 * /custom don't exist - grep confirms no matching router.get/post calls. Replaced with
 * coverage of the 3 real endpoints.
 */
const express = require("express");
const request = require("supertest");

jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

const { query } = require("../../../utils/database");
const signalsRouter = require("../../../routes/signals");

describe("Signals Routes Unit Tests", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/signals", signalsRouter);
  });

  beforeEach(() => {
    query.mockReset();
  });

  describe("GET /signals/", () => {
    test("returns paginated buy/sell signals from the daily table by default", async () => {
      query
        .mockResolvedValueOnce({ rows: [{ total: "1" }] })
        .mockResolvedValueOnce({
          rows: [
            {
              id: 1,
              symbol: "AAPL",
              date: "2026-01-15",
              signal: "buy",
              strength: "0.8",
              reason: "momentum breakout",
            },
          ],
        });

      const response = await request(app).get("/signals/").expect(200);

      // sendSuccess() spreads { signals, pagination } flat onto the response root
      // because the payload has a `pagination` key - see utils/apiResponse.js.
      expect(response.body.success).toBe(true);
      expect(response.body.signals).toHaveLength(1);
      expect(response.body.signals[0].symbol).toBe("AAPL");
      expect(response.body.pagination).toMatchObject({ total: 1, page: 1 });
      expect(query).toHaveBeenNthCalledWith(
        1,
        expect.stringContaining("buy_sell_daily"),
        expect.any(Array)
      );
    });

    test("rejects an invalid timeframe", async () => {
      const response = await request(app)
        .get("/signals/")
        .query({ timeframe: "yearly" })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain("Invalid timeframe");
    });

    test("filters by symbol and signal", async () => {
      query
        .mockResolvedValueOnce({ rows: [{ total: "0" }] })
        .mockResolvedValueOnce({ rows: [] });

      await request(app)
        .get("/signals/")
        .query({ symbol: "aapl", signal: "BUY", timeframe: "weekly" })
        .expect(200);

      expect(query).toHaveBeenNthCalledWith(
        1,
        expect.stringContaining("buy_sell_weekly"),
        ["AAPL", "buy"]
      );
    });

    test("500s when the database query fails", async () => {
      query.mockRejectedValueOnce(new Error("connection lost"));

      const response = await request(app).get("/signals/").expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain("Failed to fetch signals");
    });
  });

  describe("GET /signals/stocks", () => {
    test("queries the same buy_sell tables with per-stock enrichment", async () => {
      query
        .mockResolvedValueOnce({ rows: [{ total: "0" }] })
        .mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/signals/stocks")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(query).toHaveBeenNthCalledWith(
        1,
        expect.stringContaining("buy_sell_daily"),
        expect.any(Array)
      );
    });
  });

  describe("GET /signals/etf", () => {
    test("queries the *_etf variant tables and returns items at the top level", async () => {
      query
        .mockResolvedValueOnce({ rows: [{ total: "0" }] })
        .mockResolvedValueOnce({
          rows: [{ id: 1, symbol: "SPY", signal: "buy" }],
        });

      const response = await request(app).get("/signals/etf").expect(200);

      // /etf's sendSuccess(res, { items: result }) has no `pagination` key, so
      // sendSuccess() puts items at the top level with no `data` wrapper either - see
      // utils/apiResponse.js's `data?.items !== undefined` branch.
      expect(response.body.success).toBe(true);
      expect(response.body.items).toHaveLength(1);
      expect(response.body.items[0].symbol).toBe("SPY");
      expect(query.mock.calls[0][0]).toContain("buy_sell_daily_etf");
    });

    test("rejects an invalid timeframe", async () => {
      const response = await request(app)
        .get("/signals/etf")
        .query({ timeframe: "biannual" })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.message).toContain("Invalid timeframe");
    });
  });
});
