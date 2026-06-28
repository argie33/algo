/**
 * Test suite for safeCalculations utility
 * Verifies null/undefined safety across all financial calculations
 */

import {
  toSafeNumber,
  safeDivide,
  safeSum,
  safePercentage,
  safeMultiply,
  safeSubtract,
  safeAdd,
  safeGet,
  safeGetArray,
  safeAccumulate,
  safePnlPercentage,
  safeRMultiple,
  safeDistancePercentage,
  isValidCalculation,
  renderSafeNumber,
  buildSafeObject,
} from "./safeCalculations";

describe("safeCalculations", () => {
  describe("toSafeNumber", () => {
    it("should convert valid numbers", () => {
      expect(toSafeNumber(5)).toBe(5);
      expect(toSafeNumber("10")).toBe(10);
      expect(toSafeNumber(3.14)).toBe(3.14);
    });

    it("should return default for null/undefined", () => {
      expect(toSafeNumber(null)).toBe(0);
      expect(toSafeNumber(undefined)).toBe(0);
      expect(toSafeNumber(null, 42)).toBe(42);
    });

    it("should return default for NaN", () => {
      expect(toSafeNumber(NaN)).toBe(0);
      expect(toSafeNumber("invalid")).toBe(0);
      expect(toSafeNumber(NaN, -1)).toBe(-1);
    });
  });

  describe("safeDivide", () => {
    it("should divide valid numbers", () => {
      expect(safeDivide(10, 2)).toBe(5);
      expect(safeDivide(100, 4)).toBe(25);
    });

    it("should handle divide by zero", () => {
      expect(safeDivide(10, 0)).toBe(0);
      expect(safeDivide(10, 0, 99)).toBe(99);
    });

    it("should handle null/undefined", () => {
      expect(safeDivide(null, 2)).toBe(0);
      expect(safeDivide(10, null)).toBe(0);
      expect(safeDivide(undefined, 5)).toBe(0);
    });

    it("should handle NaN in either argument", () => {
      expect(safeDivide(NaN, 5)).toBe(0);
      expect(safeDivide(10, NaN)).toBe(0);
    });
  });

  describe("safeSum", () => {
    it("should sum valid arrays", () => {
      expect(safeSum([1, 2, 3])).toBe(6);
      expect(safeSum([10, 20.5, 30])).toBe(60.5);
    });

    it("should skip null values and still sum", () => {
      expect(safeSum([1, null, 3])).toBe(4);
      expect(safeSum([10, undefined, 20])).toBe(30);
    });

    it("should handle empty array", () => {
      expect(safeSum([])).toBe(0);
      expect(safeSum([], 99)).toBe(99);
    });

    it("should handle non-array input", () => {
      expect(safeSum(null)).toBe(0);
      expect(safeSum(undefined)).toBe(0);
      expect(safeSum("not an array")).toBe(0);
    });
  });

  describe("safePercentage", () => {
    it("should calculate percentage correctly", () => {
      expect(safePercentage(25, 100)).toBe(25);
      expect(safePercentage(50, 200)).toBe(25);
    });

    it("should handle divide by zero", () => {
      expect(safePercentage(50, 0)).toBe(0);
      expect(safePercentage(50, 0, -1)).toBe(-1);
    });

    it("should handle null/undefined", () => {
      expect(safePercentage(null, 100)).toBe(0);
      expect(safePercentage(50, null)).toBe(0);
    });
  });

  describe("safeMultiply", () => {
    it("should multiply valid numbers", () => {
      expect(safeMultiply(5, 3)).toBe(15);
      expect(safeMultiply(2.5, 4)).toBe(10);
    });

    it("should handle null/undefined", () => {
      expect(safeMultiply(null, 5)).toBe(0);
      expect(safeMultiply(10, null)).toBe(0);
    });

    it("should handle zero", () => {
      expect(safeMultiply(0, 100)).toBe(0);
      expect(safeMultiply(100, 0)).toBe(0);
    });
  });

  describe("safeSubtract", () => {
    it("should subtract valid numbers", () => {
      expect(safeSubtract(10, 3)).toBe(7);
      expect(safeSubtract(5, 10)).toBe(-5);
    });

    it("should handle null/undefined", () => {
      expect(safeSubtract(null, 5)).toBe(0);
      expect(safeSubtract(10, null)).toBe(0);
    });
  });

  describe("safeAdd", () => {
    it("should add valid numbers", () => {
      expect(safeAdd(5, 3)).toBe(8);
      expect(safeAdd(10.5, 20.3)).toBe(30.8);
    });

    it("should handle null/undefined", () => {
      expect(safeAdd(null, 5)).toBe(5);
      expect(safeAdd(10, null)).toBe(10);
      expect(safeAdd(null, null)).toBe(0);
    });
  });

  describe("safeGet", () => {
    it("should access nested properties", () => {
      const obj = { a: { b: { c: 42 } } };
      expect(safeGet(obj, "a.b.c")).toBe(42);
    });

    it("should return default for missing properties", () => {
      const obj = { a: { b: null } };
      expect(safeGet(obj, "a.b.c")).toBeNull();
      expect(safeGet(obj, "a.b.c", 99)).toBe(99);
    });

    it("should handle null/undefined objects", () => {
      expect(safeGet(null, "a.b")).toBeNull();
      expect(safeGet(undefined, "a.b")).toBeNull();
      expect(safeGet(null, "a.b", "default")).toBe("default");
    });

    it("should handle invalid paths", () => {
      const obj = { a: null };
      expect(safeGet(obj, "a.b.c")).toBeNull();
    });
  });

  describe("safeGetArray", () => {
    it("should extract from array property", () => {
      const data = { items: [1, 2, 3] };
      expect(safeGetArray(data, "items")).toEqual([1, 2, 3]);
    });

    it("should extract from direct array", () => {
      expect(safeGetArray([1, 2, 3])).toEqual([1, 2, 3]);
    });

    it("should return default for invalid data", () => {
      expect(safeGetArray(null)).toEqual([]);
      expect(safeGetArray(undefined)).toEqual([]);
      expect(safeGetArray({})).toEqual([]);
    });

    it("should handle nested data structures", () => {
      const data = { data: [4, 5, 6] };
      expect(safeGetArray(data, "data")).toEqual([4, 5, 6]);
    });
  });

  describe("safeAccumulate", () => {
    it("should accumulate with accessor function", () => {
      const items = [{ value: 10 }, { value: 20 }, { value: 30 }];
      expect(safeAccumulate(items, (item) => item.value)).toBe(60);
    });

    it("should accumulate with property path", () => {
      const items = [{ amount: 100 }, { amount: 200 }];
      expect(safeAccumulate(items, "amount")).toBe(300);
    });

    it("should skip null/undefined values", () => {
      const items = [{ value: 10 }, { value: null }, { value: 20 }];
      expect(safeAccumulate(items, "value")).toBe(30);
    });

    it("should handle non-array input", () => {
      expect(safeAccumulate(null, "value")).toBe(0);
      expect(safeAccumulate(undefined, "value")).toBe(0);
    });
  });

  describe("safePnlPercentage", () => {
    it("should calculate P&L percentage", () => {
      expect(safePnlPercentage(50, 1000)).toBe(5);
      expect(safePnlPercentage(-100, 1000)).toBe(-10);
    });

    it("should handle zero portfolio value", () => {
      expect(safePnlPercentage(100, 0)).toBeNull();
      expect(safePnlPercentage(100, null)).toBeNull();
    });

    it("should handle null P&L", () => {
      expect(safePnlPercentage(null, 1000)).toBeNull();
    });
  });

  describe("safeRMultiple", () => {
    it("should calculate R multiple", () => {
      expect(safeRMultiple(100, 50)).toBe(2);
      expect(safeRMultiple(75, 25)).toBe(3);
    });

    it("should handle zero risk", () => {
      expect(safeRMultiple(100, 0)).toBeNull();
    });

    it("should handle null values", () => {
      expect(safeRMultiple(null, 50)).toBeNull();
      expect(safeRMultiple(100, null)).toBeNull();
    });
  });

  describe("safeDistancePercentage", () => {
    it("should calculate distance percentage", () => {
      const distance = safeDistancePercentage(110, 100);
      expect(distance).toBeCloseTo(10, 5);
    });

    it("should handle zero target", () => {
      expect(safeDistancePercentage(100, 0)).toBeNull();
    });

    it("should handle null values", () => {
      expect(safeDistancePercentage(null, 100)).toBeNull();
      expect(safeDistancePercentage(100, null)).toBeNull();
    });
  });

  describe("isValidCalculation", () => {
    it("should validate valid numbers", () => {
      expect(isValidCalculation(0)).toBe(true);
      expect(isValidCalculation(42)).toBe(true);
      expect(isValidCalculation(-5)).toBe(true);
    });

    it("should reject null/undefined", () => {
      expect(isValidCalculation(null)).toBe(false);
      expect(isValidCalculation(undefined)).toBe(false);
    });

    it("should reject NaN", () => {
      expect(isValidCalculation(NaN)).toBe(false);
    });
  });

  describe("renderSafeNumber", () => {
    it("should render valid numbers", () => {
      expect(renderSafeNumber(42)).toBe("42");
      expect(renderSafeNumber(3.14159, null, 2)).toBe("3.14");
    });

    it("should use fallback for invalid values", () => {
      expect(renderSafeNumber(null)).toBe("—");
      expect(renderSafeNumber(NaN, "ERROR")).toBe("ERROR");
    });
  });

  describe("buildSafeObject", () => {
    it("should build object with defaults", () => {
      const obj = { a: 10, b: 20 };
      const schema = { a: 0, b: 0, c: 0 };
      const result = buildSafeObject(obj, schema);
      expect(result).toEqual({ a: 10, b: 20, c: 0 });
    });

    it("should handle null source object", () => {
      const schema = { a: 1, b: 2 };
      const result = buildSafeObject(null, schema);
      expect(result).toEqual({ a: 1, b: 2 });
    });

    it("should use defaults for missing properties", () => {
      const obj = { a: 10 };
      const schema = { a: 0, b: 5, c: 10 };
      const result = buildSafeObject(obj, schema);
      expect(result).toEqual({ a: 10, b: 5, c: 10 });
    });
  });

  describe("Integration tests", () => {
    it("should handle complete portfolio calculation with nulls", () => {
      const positions = [
        { symbol: "AAPL", position_value: 1000, unrealized_pnl_dollars: 100 },
        { symbol: "GOOGL", position_value: null, unrealized_pnl_dollars: 50 },
        { symbol: "MSFT", position_value: 500 },
      ];

      const totalValue = safeAccumulate(positions, "position_value", 0);
      expect(totalValue).toBe(1500);

      const totalPnl = safeAccumulate(positions, "unrealized_pnl_dollars", 0);
      expect(totalPnl).toBe(150);

      const pnlPct = safePnlPercentage(totalPnl, totalValue);
      expect(pnlPct).toBeCloseTo(10, 1);
    });

    it("should calculate position risk safely", () => {
      const positions = [
        { open_risk_dollars: 100 },
        { open_risk_dollars: null },
        { open_risk_dollars: 200 },
      ];

      const totalRisk = safeAccumulate(positions, "open_risk_dollars", 0);
      expect(totalRisk).toBe(300);

      const portfolioValue = 10000;
      const riskPct = safePercentage(totalRisk, portfolioValue);
      expect(riskPct).toBe(3);
    });

    it("should handle trade ladder calculations with missing data", () => {
      const position = {
        symbol: "TEST",
        current_price: 100,
        avg_entry_price: 95,
        stop_loss_price: 90,
        target_1_price: 110,
        target_2_price: null,
        target_3_price: 130,
      };

      const entry = toSafeNumber(safeGet(position, "avg_entry_price"), 0);
      const current = toSafeNumber(safeGet(position, "current_price"), 0);
      const stop = toSafeNumber(safeGet(position, "stop_loss_price"), 0);

      expect(entry).toBe(95);
      expect(current).toBe(100);
      expect(stop).toBe(90);

      const t2 = toSafeNumber(safeGet(position, "target_2_price"), null);
      expect(t2).toBeNull();
    });
  });
});
