/**
 * Formatters Utility Unit Tests
 * Tests currency, percentage, and number formatting functions
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  formatCurrency,
  formatPercentage,
  formatNumber,
  formatPercent,
  formatRatio,
  formatDate,
  formatDateTime,
  getChangeColor,
  getChangeIcon,
  getMarketCapCategory,
  getFinancialHealthScore,
  getTechStatus,
  debounce,
} from "../../../utils/formatters.js";

describe("Formatters Utility", () => {
  describe("formatCurrency", () => {
    it("formats basic currency values", () => {
      expect(formatCurrency(100)).toBe("$100.00");
      expect(formatCurrency(0)).toBe("$0.00");
    });

    it("formats large currency values with abbreviations", () => {
      expect(formatCurrency(1500000)).toBe("$1.50M");
      expect(formatCurrency(2500000000)).toBe("$2.50B");
      expect(formatCurrency(3500000000000)).toBe("$3.50T");
      expect(formatCurrency(1500)).toBe("$1.50K");
      expect(formatCurrency(1234.56)).toBe("$1.23K");
    });

    it("handles negative currency values", () => {
      expect(formatCurrency(-1234.56)).toBe("-$1.23K");
      expect(formatCurrency(-1500000)).toBe("-$1.50M");
    });

    it("handles edge cases", () => {
      expect(formatCurrency(null)).toBe("N/A");
      expect(formatCurrency(undefined)).toBe("N/A");
      expect(formatCurrency(NaN)).toBe("N/A");
      expect(formatCurrency("invalid")).toBe("N/A");
    });

    it("respects decimal places parameter", () => {
      expect(formatCurrency(1234.5678, 3)).toBe("$1.23K"); // Still abbreviated
      expect(formatCurrency(100, 0)).toBe("$100");
    });
  });

  describe("formatPercentage", () => {
    it("formats basic percentage values", () => {
      expect(formatPercentage(15.25)).toBe("15.25%");
      expect(formatPercentage(0)).toBe("0.00%");
      expect(formatPercentage(100)).toBe("100.00%");
    });

    it("handles negative percentages", () => {
      expect(formatPercentage(-5.75)).toBe("-5.75%");
    });

    it("handles edge cases", () => {
      expect(formatPercentage(null)).toBe("N/A");
      expect(formatPercentage(undefined)).toBe("N/A");
      expect(formatPercentage(NaN)).toBe("N/A");
      expect(formatPercentage("invalid")).toBe("N/A");
    });

    it("respects decimal places parameter", () => {
      expect(formatPercentage(15.2567, 3)).toBe("15.257%");
      expect(formatPercentage(15.2567, 0)).toBe("15%");
    });
  });

  describe("formatNumber", () => {
    it("formats large numbers with abbreviations", () => {
      expect(formatNumber(1234567)).toBe("1.23M");
      expect(formatNumber(1000)).toBe("1.00K");
      expect(formatNumber(100)).toBe("100.00");
    });

    it("handles decimal numbers", () => {
      expect(formatNumber(1234.56)).toBe("1.23K");
      expect(formatNumber(0.1234)).toBe("0.12");
    });

    it("handles edge cases", () => {
      expect(formatNumber(null)).toBe("N/A");
      expect(formatNumber(undefined)).toBe("N/A");
      expect(formatNumber(NaN)).toBe("N/A");
      expect(formatNumber("invalid")).toBe("N/A");
    });
  });

  describe("formatRatio", () => {
    it("formats ratio values", () => {
      expect(formatRatio(1.5)).toBe("1.50");
      expect(formatRatio(2.567)).toBe("2.57");
      expect(formatRatio(0.123)).toBe("0.12");
    });

    it("handles edge cases", () => {
      expect(formatRatio(null)).toBe("N/A");
      expect(formatRatio(undefined)).toBe("N/A");
      expect(formatRatio(NaN)).toBe("N/A");
    });
  });

  describe("formatPercent", () => {
    it("formats percent values consistently", () => {
      expect(formatPercent(15.25)).toBe("15.25%"); // formatPercent is same as formatPercentage
      expect(formatPercent(100)).toBe("100.00%");
      expect(formatPercent(-5.75)).toBe("-5.75%");
    });

    it("handles edge cases", () => {
      expect(formatPercent(null)).toBe("N/A");
      expect(formatPercent(undefined)).toBe("N/A");
      expect(formatPercent(NaN)).toBe("N/A");
    });
  });

  describe("getChangeColor", () => {
    it("returns correct colors for different values", () => {
      expect(getChangeColor(5.0)).toBe("#2e7d32"); // positive - green
      expect(getChangeColor(-2.5)).toBe("#d32f2f"); // negative - red
      expect(getChangeColor(0)).toBe("#666"); // neutral - gray
      expect(getChangeColor(null)).toBe("#666");
    });
  });

  describe("getMarketCapCategory", () => {
    it("categorizes market caps correctly", () => {
      expect(getMarketCapCategory(300000000000)).toBe("Mega Cap"); // 300B
      expect(getMarketCapCategory(50000000000)).toBe("Large Cap"); // 50B
      expect(getMarketCapCategory(5000000000)).toBe("Mid Cap"); // 5B
      expect(getMarketCapCategory(1000000000)).toBe("Small Cap"); // 1B
      expect(getMarketCapCategory(100000000)).toBe("Micro Cap"); // 100M
      expect(getMarketCapCategory(10000000)).toBe("Nano Cap"); // 10M
      expect(getMarketCapCategory(null)).toBe("Unknown");
    });
  });

  describe("getChangeIcon", () => {
    it("returns correct icons for different values", () => {
      expect(getChangeIcon(5)).toBe("↗");
      expect(getChangeIcon(-3)).toBe("↘");
      expect(getChangeIcon(0)).toBe("→");
      expect(getChangeIcon(null)).toBe("");
      expect(getChangeIcon(undefined)).toBe("");
    });
  });

  describe("formatDate", () => {
    it("formats date strings correctly", () => {
      // Account for timezone differences - dates may shift by a day
      expect(formatDate("2024-01-15")).toMatch(/Jan 1[45], 2024/);
      expect(formatDate("2024-12-25")).toMatch(/Dec 2[45], 2024/);
    });

    it("handles invalid dates", () => {
      expect(formatDate("invalid")).toBe("Invalid Date"); // Invalid Date string
      expect(formatDate(null)).toBe("N/A");
      expect(formatDate(undefined)).toBe("N/A");
    });

    it("handles Date objects", () => {
      const date = new Date("2024-06-15");
      expect(formatDate(date)).toMatch(/Jun 1[45], 2024/); // Account for timezone
    });
  });

  describe("formatDateTime", () => {
    it("formats datetime strings correctly", () => {
      const result = formatDateTime("2024-01-15T14:30:00Z");
      expect(result).toMatch(/Jan 1[45], 2024.*AM|PM/); // Account for timezone differences
    });

    it("handles invalid datetimes", () => {
      expect(formatDateTime("invalid")).toBe("Invalid Date"); // Invalid Date string
      expect(formatDateTime(null)).toBe("N/A");
    });

    it("handles Date objects", () => {
      const date = new Date("2024-06-15T10:30:00Z");
      const result = formatDateTime(date);
      expect(result).toMatch(/Jun 1[45], 2024/);
    });
  });

  describe("debounce", () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it("debounces function calls", () => {
      const mockFn = vi.fn();
      const debouncedFn = debounce(mockFn, 1000);

      debouncedFn("test1");
      debouncedFn("test2");
      debouncedFn("test3");

      expect(mockFn).not.toHaveBeenCalled();

      vi.advanceTimersByTime(1000);
      expect(mockFn).toHaveBeenCalledOnce();
      expect(mockFn).toHaveBeenCalledWith("test3");
    });

    it("resets timer on subsequent calls", () => {
      const mockFn = vi.fn();
      const debouncedFn = debounce(mockFn, 1000);

      debouncedFn("test1");
      vi.advanceTimersByTime(500);
      debouncedFn("test2");
      vi.advanceTimersByTime(500);

      expect(mockFn).not.toHaveBeenCalled();

      vi.advanceTimersByTime(500);
      expect(mockFn).toHaveBeenCalledOnce();
      expect(mockFn).toHaveBeenCalledWith("test2");
    });
  });

  describe("getFinancialHealthScore", () => {
    it("calculates financial health scores correctly", () => {
      const goodMetrics = {
        trailing_pe: 12, // <15 = 20 points
        debt_to_equity: 0.2, // <0.3 = 20 points
        current_ratio: 2.5, // >2 = 20 points
        return_on_equity_pct: 18, // >15 = 15 points
        revenue_growth_pct: 12, // >10 = 15 points
      };
      // Total: 90 points / 5 factors = 18 average score

      const result = getFinancialHealthScore(goodMetrics);
      expect(result.score).toBeGreaterThanOrEqual(18);
      expect(result.grade).toBe("A");
      expect(result.color).toBe("#2e7d32");
    });

    it("handles poor financial metrics", () => {
      const poorMetrics = {
        trailing_pe: 45, // >=35 = 5 points
        debt_to_equity: 3.0, // >=1.0 = 5 points
        current_ratio: 0.8, // <=1 = 5 points
        return_on_equity_pct: -5, // <=5 = 0 points (no condition matches)
        revenue_growth_pct: -8, // <=0 = 0 points (no condition matches)
      };
      // Total: 15 points / 5 factors = 3 average score

      const result = getFinancialHealthScore(poorMetrics);
      expect(result.score).toBeLessThan(8);
      expect(result.grade).toBe("F");
      expect(result.color).toBe("#d32f2f");
    });

    it("handles missing metrics", () => {
      const incompleteMetrics = {
        current_ratio: 2.0,
        debt_to_equity: null,
      };

      const result = getFinancialHealthScore(incompleteMetrics);
      expect(result.score).toBeGreaterThanOrEqual(0);
      expect(result.grade).toBeDefined();
    });

    it("handles empty metrics object", () => {
      const result = getFinancialHealthScore({});
      expect(result.score).toBe(0);
      expect(result.grade).toBe("F");
    });

    it("assigns correct grades for different score ranges", () => {
      // Test with medium scoring metrics (C grade)
      const mediumMetrics = {
        trailing_pe: 18, // 15-25 = 15 points
        debt_to_equity: 0.5, // 0.3-0.6 = 15 points
        current_ratio: 1.8, // 1.5-2 = 15 points
        return_on_equity_pct: 12, // 10-15 = 10 points
        revenue_growth_pct: 6, // 5-10 = 10 points
      };
      // Total: 65 points / 5 factors = 13 average score (C grade)
      const resultC = getFinancialHealthScore(mediumMetrics);
      expect(resultC.score).toBeGreaterThan(10);
      expect(resultC.grade).toBe("C");

      // Test with D grade metrics (score 8-11)
      const dGradeMetrics = {
        trailing_pe: 28, // 25-35 = 10 points
        debt_to_equity: 0.8, // 0.6-1.0 = 10 points
        current_ratio: 1.2, // 1-1.5 = 10 points
        return_on_equity_pct: 7, // 5-10 = 5 points
        revenue_growth_pct: 3, // 0-5 = 5 points
      };
      // Total: 40 points / 5 factors = 8 average score (D grade)
      const resultD = getFinancialHealthScore(dGradeMetrics);
      expect(resultD.score).toBe(8);
      expect(resultD.grade).toBe("D");
    });
  });

  describe("getTechStatus", () => {
    it("handles RSI indicator correctly", () => {
      expect(getTechStatus("rsi", 80)).toEqual({
        icon: "up",
        color: "error.main",
        label: "Overbought",
      });

      expect(getTechStatus("rsi", 20)).toEqual({
        icon: "down",
        color: "primary.main",
        label: "Oversold",
      });

      expect(getTechStatus("rsi", 50)).toEqual({
        icon: "neutral",
        color: "success.main",
        label: "Neutral",
      });
    });

    it("handles MACD indicator correctly", () => {
      expect(getTechStatus("macd", 1.5)).toEqual({
        icon: "up",
        color: "success.main",
        label: "Bullish",
      });

      expect(getTechStatus("macd", -0.8)).toEqual({
        icon: "down",
        color: "error.main",
        label: "Bearish",
      });

      expect(getTechStatus("macd", 0)).toEqual({
        icon: "flat",
        color: "warning.main",
        label: "Flat",
      });
    });

    it("handles ADX indicator correctly", () => {
      expect(getTechStatus("adx", 30)).toEqual({
        icon: "up",
        color: "success.main",
        label: "Trending",
      });

      expect(getTechStatus("adx", 20)).toEqual({
        icon: "flat",
        color: "info.main",
        label: "Weak",
      });
    });

    it("handles ATR indicator correctly", () => {
      expect(getTechStatus("atr", 3.5)).toEqual({
        icon: "up",
        color: "warning.main",
        label: "High Volatility",
      });

      expect(getTechStatus("atr", 1.2)).toEqual({
        icon: "flat",
        color: "info.main",
        label: "Low Volatility",
      });
    });

    it("handles MFI indicator correctly", () => {
      expect(getTechStatus("mfi", 85)).toEqual({
        icon: "up",
        color: "error.main",
        label: "Overbought",
      });

      expect(getTechStatus("mfi", 15)).toEqual({
        icon: "down",
        color: "primary.main",
        label: "Oversold",
      });

      expect(getTechStatus("mfi", 50)).toEqual({
        icon: "neutral",
        color: "success.main",
        label: "Neutral",
      });
    });

    it("handles ROC and MOM indicators correctly", () => {
      expect(getTechStatus("roc", 5.2)).toEqual({
        icon: "up",
        color: "success.main",
        label: "Positive",
      });

      expect(getTechStatus("mom", -2.1)).toEqual({
        icon: "down",
        color: "error.main",
        label: "Negative",
      });

      expect(getTechStatus("roc", 0)).toEqual({
        icon: "flat",
        color: "info.main",
        label: "Flat",
      });
    });

    it("handles Bollinger Band indicators correctly", () => {
      expect(getTechStatus("bbands_upper", 150)).toEqual({
        icon: "neutral",
        color: "info.main",
        label: "",
      });

      expect(getTechStatus("bbands_middle", 145)).toEqual({
        icon: "neutral",
        color: "info.main",
        label: "",
      });

      expect(getTechStatus("bbands_lower", 140)).toEqual({
        icon: "neutral",
        color: "info.main",
        label: "",
      });
    });

    it("handles pivot indicators correctly", () => {
      expect(getTechStatus("pivot_high", true)).toEqual({
        icon: "up",
        color: "success.main",
        label: "Pivot High",
      });

      expect(getTechStatus("pivot_high", false)).toEqual({
        icon: "neutral",
        color: "info.main",
        label: "",
      });

      expect(getTechStatus("pivot_low", true)).toEqual({
        icon: "down",
        color: "primary.main",
        label: "Pivot Low",
      });

      expect(getTechStatus("pivot_low", false)).toEqual({
        icon: "neutral",
        color: "info.main",
        label: "",
      });
    });

    it("handles SMA and EMA indicators correctly", () => {
      expect(getTechStatus("sma_10", 100)).toEqual({
        icon: "neutral",
        color: "secondary.main",
        label: "",
      });

      expect(getTechStatus("sma_20", 105)).toEqual({
        icon: "neutral",
        color: "secondary.main",
        label: "",
      });

      expect(getTechStatus("ema_4", 98)).toEqual({
        icon: "neutral",
        color: "secondary.main",
        label: "",
      });

      expect(getTechStatus("ema_21", 102)).toEqual({
        icon: "neutral",
        color: "secondary.main",
        label: "",
      });
    });

    it("handles null and undefined values", () => {
      expect(getTechStatus("rsi", null)).toEqual({
        icon: "info",
        color: "text.secondary",
        label: "N/A",
      });

      expect(getTechStatus("macd", undefined)).toEqual({
        icon: "info",
        color: "text.secondary",
        label: "N/A",
      });
    });

    it("handles unknown indicators with default case", () => {
      expect(getTechStatus("unknown_indicator", 50)).toEqual({
        icon: "info",
        color: "text.secondary",
        label: "",
      });
    });
  });
});
