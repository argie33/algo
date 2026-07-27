/**
 * Commodities Routes Unit Tests
 *
 * /health and /news don't exist in routes/commodities.js (grep confirms no matching
 * router.get calls) - the real endpoints are /, /categories, /full/:symbol, /prices,
 * /summary, /market-summary, /cot/:symbol, /seasonality/:symbol, /correlations,
 * /technicals/:symbol, /macro, /events. Covers /, /categories, /prices,
 * /market-summary, and /correlations against their real response shapes.
 */
const request = require("supertest");
const express = require("express");

const mockQuery = jest.fn();
jest.mock("../../../utils/database", () => ({
  query: (...args) => mockQuery(...args),
  safeFloat: (v) => (v === null || v === undefined ? null : parseFloat(v)),
  safeInt: (v) => (v === null || v === undefined ? null : parseInt(v, 10)),
  safeFixed: (v, decimals = 2) =>
    v === null || v === undefined ? null : parseFloat(v).toFixed(decimals),
}));

const commoditiesRouter = require("../../../routes/commodities");

describe("Commodities Routes", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/api/commodities", commoditiesRouter);
  });

  beforeEach(() => {
    mockQuery.mockReset();
  });

  describe("GET /api/commodities/", () => {
    test("returns paginated commodity categories", async () => {
      mockQuery
        .mockResolvedValueOnce({
          rows: [{ id: 1, category: "energy", symbols: "CL,NG" }],
        })
        .mockResolvedValueOnce({ rows: [{ total: "1" }] });

      const response = await request(app)
        .get("/api/commodities/")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.items).toEqual([
        { id: 1, category: "energy", symbols: "CL,NG" },
      ]);
      expect(response.body.pagination.total).toBe(1);
    });

    test("500s when the database query fails", async () => {
      mockQuery.mockRejectedValueOnce(new Error("connection lost"));

      const response = await request(app)
        .get("/api/commodities/")
        .expect(500);

      expect(response.body.success).toBe(false);
    });
  });

  describe("GET /api/commodities/categories", () => {
    test("returns categories with derived display name", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            symbol: "GC",
            category: "precious-metals",
            subcategory: "gold",
            unit: "oz",
            exchange: "COMEX",
            avg_change_1d: "0.5",
            commodity_count: "1",
          },
        ],
      });

      const response = await request(app)
        .get("/api/commodities/categories")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.items[0]).toEqual({
        symbol: "GC",
        category: "precious-metals",
        subcategory: "gold",
        unit: "oz",
        exchange: "COMEX",
        name: "Precious-metals",
      });
    });

    test("503s when the commodity tables are unavailable", async () => {
      mockQuery.mockRejectedValueOnce(new Error("relation does not exist"));

      const response = await request(app)
        .get("/api/commodities/categories")
        .expect(503);

      expect(response.body.success).toBe(false);
    });
  });

  describe("GET /api/commodities/prices", () => {
    test("returns current commodity prices with both snake_case and camelCase aliases", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            symbol: "GC",
            name: "Gold",
            price: "2050.5",
            change_amount: "12.3",
            change_percent: "0.6",
            volume: "1500",
            high_52w: "2100.0",
            low_52w: "1800.0",
            category: "precious-metals",
            subcategory: "gold",
            unit: "oz",
            exchange: "COMEX",
            updated_at: "2026-01-01T00:00:00.000Z",
          },
        ],
      });

      const response = await request(app)
        .get("/api/commodities/prices")
        .expect(200);

      expect(response.body.success).toBe(true);
      const gold = response.body.items[0];
      expect(gold.symbol).toBe("GC");
      expect(gold.price).toBe(2050.5);
      expect(gold.change_percent).toBe("0.60");
      expect(gold.changePercent).toBe("0.60");
      expect(gold.high52w).toBe(2100);
    });

    test("filters by category when provided", async () => {
      mockQuery.mockResolvedValueOnce({ rows: [] });

      await request(app)
        .get("/api/commodities/prices")
        .query({ category: "energy" })
        .expect(200);

      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("cc.category = $1"),
        expect.arrayContaining(["energy"])
      );
    });
  });

  describe("GET /api/commodities/market-summary", () => {
    test("returns overview, top gainers/losers, and sector breakdown", async () => {
      mockQuery
        .mockResolvedValueOnce({
          rows: [
            { symbol: "GC", name: "Gold", change_percent: "2.0", price: "2050", category: "precious-metals" },
            { symbol: "CL", name: "Crude Oil", change_percent: "-1.5", price: "75", category: "energy" },
          ],
        })
        .mockResolvedValueOnce({ rows: [{ total: "50000" }] })
        .mockResolvedValueOnce({
          rows: [{ category: "energy", avg_change_1d: "-1.5", count: "1" }],
        });

      const response = await request(app)
        .get("/api/commodities/market-summary")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.overview).toEqual({
        activeContracts: 2,
        totalVolume: 50000,
      });
      expect(response.body.data.topGainers[0].symbol).toBe("GC");
      expect(response.body.data.topLosers[0].symbol).toBe("CL");
      expect(response.body.data.sectors[0]).toMatchObject({
        category: "energy",
        trend: "down",
      });
    });
  });

  describe("GET /api/commodities/correlations", () => {
    test("classifies correlation strength and filters by minCorrelation", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [
          {
            symbol1: "GC",
            symbol2: "SI",
            name1: "Gold",
            name2: "Silver",
            coefficient: "0.85",
          },
        ],
      });

      const response = await request(app)
        .get("/api/commodities/correlations")
        .query({ minCorrelation: 0.7 })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.correlations[0]).toMatchObject({
        pair: "Gold vs Silver",
        strength: "strong",
      });
      expect(mockQuery).toHaveBeenCalledWith(
        expect.stringContaining("correlation_90d"),
        [0.7]
      );
    });
  });
});
