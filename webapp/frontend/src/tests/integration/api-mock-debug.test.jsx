/**
 * API Mock Debug Test
 * Simple test to isolate the mocking issue without complex components
 */

// Mock API service at the top level (hoisted)
vi.mock("../../services/api", () => ({
  getStockPrices: vi.fn((_symbol, _timeframe, _limit) => 
    Promise.resolve({
      data: [
        { date: "2025-06-30", close: 190.5, volume: 1000000 },
      ]
    })
  ),
  getStockMetrics: vi.fn((_symbol) => 
    Promise.resolve({
      data: {
        beta: 1.2,
        volatility: 0.28,
      }
    })
  ),
  default: {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
  }
}));

import { describe, it, expect, vi } from "vitest";

describe("API Mock Debug Test", () => {
  it("should have working API mocks", async () => {
    // Dynamic import to test the mock
    const api = await import("../../services/api");
    
    console.log("Available API exports:", Object.keys(api));
    console.log("getStockPrices type:", typeof api.getStockPrices);
    console.log("getStockMetrics type:", typeof api.getStockMetrics);
    
    // Test the mocked functions directly
    expect(api.getStockPrices).toBeDefined();
    expect(api.getStockMetrics).toBeDefined();
    
    // Call the functions
    const pricesResult = await api.getStockPrices("AAPL", "daily", 30);
    const metricsResult = await api.getStockMetrics("AAPL");
    
    expect(pricesResult.data).toHaveLength(1);
    expect(metricsResult.data.beta).toBe(1.2);
  });
  
  it("should allow named imports", async () => {
    // Test destructured import
    const { getStockPrices, getStockMetrics } = await import("../../services/api");
    
    expect(getStockPrices).toBeDefined();
    expect(getStockMetrics).toBeDefined();
    
    const pricesResult = await getStockPrices("AAPL", "daily", 30);
    const metricsResult = await getStockMetrics("AAPL");
    
    expect(pricesResult.data).toHaveLength(1);
    expect(metricsResult.data.beta).toBe(1.2);
  });
});