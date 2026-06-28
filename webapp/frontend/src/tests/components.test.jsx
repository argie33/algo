import { describe, it, expect } from "vitest";

describe("Utility Functions", () => {
  it("formats currency correctly", async () => {
    const { formatCurrency } = await import("../utils/formatters");

    expect(formatCurrency(1000)).toBe("$1.00K");
    expect(formatCurrency(1000000)).toBe("$1.00M");
    expect(formatCurrency(null)).toBe("N/A");
  });

  it("formats percentage correctly", async () => {
    const { formatPercentage } = await import("../utils/formatters");

    expect(formatPercentage(15)).toBe("15.00%");
    expect(formatPercentage(-5)).toBe("-5.00%");
    expect(formatPercentage(null)).toBe("N/A");
  });

  it("formats numbers correctly", async () => {
    const { formatNumber } = await import("../utils/formatters");

    expect(formatNumber(1234.567, 2)).toBe("1.23K");
    expect(formatNumber(1000000, 0)).toBe("1.00M");
    expect(formatNumber(null)).toBe("N/A");
  });
});
