import { describe, it, expect } from "vitest";
import {
  safeGetMarketCurrent,
  safeGetFactors,
  safeGetSentimentData,
  safeGetArray,
  safeGetObject,
} from "../../../utils/dataValidation";

describe("Null Safety Utilities", () => {
  describe("safeGetMarketCurrent", () => {
    it("handles null markets", () => {
      expect(safeGetMarketCurrent(null)).toBeNull();
      expect(safeGetMarketCurrent(undefined)).toBeNull();
    });

    it("handles markets without current", () => {
      const markets = { active_tier: {} };
      expect(safeGetMarketCurrent(markets)).toBeNull();
    });

    it("returns safe defaults for all properties", () => {
      const markets = {
        current: {
          exposure_pct: 75,
          raw_score: 85,
          regime: "healthy_uptrend",
        },
      };
      const result = safeGetMarketCurrent(markets);
      expect(result.exposure_pct).toBe(75);
      expect(result.raw_score).toBe(85);
      expect(result.regime).toBe("healthy_uptrend");
      expect(result.factors).toEqual({});
      expect(result.halt_reasons).toBe(null);
    });

    it("provides defaults when properties are missing", () => {
      const markets = { current: {} };
      const result = safeGetMarketCurrent(markets);
      expect(result.exposure_pct).toBe(0);
      expect(result.raw_score).toBe(0);
      expect(result.regime).toBe("unknown");
      expect(result.factors).toEqual({});
    });
  });

  describe("safeGetFactors", () => {
    it("handles null current", () => {
      expect(safeGetFactors(null)).toEqual({});
      expect(safeGetFactors(undefined)).toEqual({});
    });

    it("handles current without factors", () => {
      expect(safeGetFactors({})).toEqual({});
    });

    it("returns safe defaults for all sub-objects", () => {
      const current = {
        factors: {
          vix_regime: { value: 20, rising: true },
          distribution_days: { regime: "strong" },
        },
      };
      const result = safeGetFactors(current);
      expect(result.vix_regime.value).toBe(20);
      expect(result.distribution_days.regime).toBe("strong");
      expect(result.breadth_50dma).toEqual({});
      expect(result.spy_momentum).toEqual({});
    });
  });

  describe("safeGetSentimentData", () => {
    it("handles null data", () => {
      const result = safeGetSentimentData(null);
      expect(result).toEqual({
        aaii: { history: [], data: [] },
        naaim: { current: null },
        fearGreed: { current: null },
      });
    });

    it("provides array defaults for aaii history", () => {
      const data = { aaii: { history: [{ date: "2026-01-01", bullish: 40 }] } };
      const result = safeGetSentimentData(data);
      expect(Array.isArray(result.aaii.history)).toBe(true);
    });

    it("handles missing nested objects", () => {
      const data = { aaii: null };
      const result = safeGetSentimentData(data);
      expect(result.aaii.history).toEqual([]);
    });
  });

  describe("safeGetArray", () => {
    it("handles arrays directly", () => {
      const arr = [1, 2, 3];
      expect(safeGetArray(arr)).toEqual(arr);
    });

    it("extracts from object.items by default", () => {
      const obj = { items: [1, 2, 3] };
      expect(safeGetArray(obj)).toEqual([1, 2, 3]);
    });

    it("extracts from custom key", () => {
      const obj = { sectors: [{ name: "tech" }] };
      expect(safeGetArray(obj, "sectors")).toEqual([{ name: "tech" }]);
    });

    it("returns empty array for invalid inputs", () => {
      expect(safeGetArray(null)).toEqual([]);
      expect(safeGetArray({})).toEqual([]);
      expect(safeGetArray({ items: "not an array" })).toEqual([]);
    });
  });

  describe("safeGetObject", () => {
    it("handles null data", () => {
      expect(safeGetObject(null)).toEqual({});
    });

    it("extracts from data.data format", () => {
      const data = { data: { name: "test" } };
      const result = safeGetObject(data);
      expect(result.name).toBe("test");
    });

    it("returns object directly if no nested data", () => {
      const data = { name: "test", value: 123 };
      const result = safeGetObject(data);
      expect(result.name).toBe("test");
    });

    it("ignores data.data if it is an array", () => {
      const data = { data: [1, 2, 3] };
      const result = safeGetObject(data);
      expect(result.data).toEqual([1, 2, 3]);
    });
  });

  describe("Integration tests - Component data safety", () => {
    it("can safely render MarketsHealth data", () => {
      // Simulate API returning null values at various levels
      const marketsData = {
        current: null,
        sectors: null,
        market_health: { vix_level: null },
      };

      const safeCurrent = safeGetMarketCurrent(marketsData);
      expect(safeCurrent).toBeNull(); // OK - RegimeBanner handles this

      const safeFactors = safeCurrent ? safeGetFactors(safeCurrent) : {};
      expect(safeFactors).toEqual({});
    });

    it("can safely render Portfolio data with missing market info", () => {
      const markets = {
        current: { exposure_pct: undefined },
        active_tier: null,
      };

      const safeCurrent = safeGetMarketCurrent(markets);
      expect(safeCurrent.exposure_pct).toBe(0); // Safe default
      expect(safeCurrent).not.toBe(null); // Safe object to work with
    });

    it("can safely process sector data when symbols is null", () => {
      const batchData = { symbols: null };
      const symbolMap =
        safeGetObject(batchData, {}).symbols &&
        typeof safeGetObject(batchData, {}).symbols === "object"
          ? safeGetObject(batchData, {}).symbols
          : {};
      expect(symbolMap).toEqual({});
    });
  });
});
