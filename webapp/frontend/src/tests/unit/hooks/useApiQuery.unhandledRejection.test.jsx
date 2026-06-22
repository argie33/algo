import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useApiQuery, useApiPaginatedQuery } from "../../../hooks/useApiQuery";
import * as dataCache from "../../../services/dataCache";
import React from "react";

// Mock the dataCache module
vi.mock("../../../services/dataCache", () => ({
  default: {
    get: vi.fn(),
    set: vi.fn(),
    delete: vi.fn(),
    clear: vi.fn(),
    getMarketData: vi.fn(),
    setMarketData: vi.fn(),
    cleanup: vi.fn(),
    getMetadata: vi.fn(),
  },
  get: vi.fn(),
  set: vi.fn(),
}));

describe("useApiQuery - Unhandled Promise Rejections Fix", () => {
  let queryClient;
  let unhandledRejections = [];

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: 0 }, // Disable retries for testing
      },
    });

    unhandledRejections = [];

    // Capture unhandled rejections
    const handleRejection = (e) => {
      unhandledRejections.push(e.reason || e);
    };

    window.addEventListener("unhandledrejection", handleRejection);

    // Cleanup after each test
    return () => {
      window.removeEventListener("unhandledrejection", handleRejection);
    };
  });

  afterEach(() => {
    vi.clearAllMocks();
    unhandledRejections = [];
  });

  const wrapper = ({ children }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);

  it("should catch API errors without unhandled rejections", async () => {
    const mockError = new Error("API failed");
    const queryFn = vi.fn().mockRejectedValue(mockError);

    const { result } = renderHook(() => useApiQuery(["test-key"], queryFn), {
      wrapper,
    });

    await waitFor(() => {
      expect(result.current.error).toBeDefined();
    });

    // Should not have any unhandled rejections
    await waitFor(
      () => {
        expect(unhandledRejections.length).toBe(0);
      },
      { timeout: 1000 }
    );

    expect(result.current.error?.message).toContain("API failed");
  });

  it("should handle cache failures gracefully", async () => {
    const mockData = { test: "data" };
    const queryFn = vi.fn().mockResolvedValue({
      data: { success: true, data: mockData },
    });

    // Mock cache.set to throw
    dataCache.set.mockRejectedValue(new Error("Cache write failed"));
    dataCache.get.mockResolvedValue(null);

    const { result } = renderHook(() => useApiQuery(["test-key"], queryFn), {
      wrapper,
    });

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    // Cache failure should not cause unhandled rejection
    expect(unhandledRejections.length).toBe(0);
    // Data includes metadata added by addMetadata()
    expect(result.current.data.test).toBe("data");
    expect(result.current.data._fetchedAt).toBeDefined();
    expect(result.current.data._age).toBeDefined();
  });

  it("should return cached fallback without unhandled rejections", async () => {
    const mockError = new Error("Network error");
    const cachedData = { cached: true };
    const queryFn = vi.fn().mockRejectedValue(mockError);

    // Mock cache retrieval (hook uses default export)
    dataCache.default.get.mockResolvedValue(cachedData);
    dataCache.default.getMetadata.mockResolvedValue({ fetchedAt: Date.now() });

    const { result } = renderHook(() => useApiQuery(["test-key"], queryFn), {
      wrapper,
    });

    // Network errors trigger retries; wait long enough for all retries to complete
    await waitFor(
      () => {
        expect(result.current.data).toBeDefined();
      },
      { timeout: 5000 }
    );

    // Should return cached data without unhandled rejections
    expect(unhandledRejections.length).toBe(0);
    // Cached data gets metadata added too
    expect(result.current.data).toHaveProperty("cached", true);
    expect(result.current.data._fromCache).toBe(true);
  });

  it("should handle cache retrieval failures", async () => {
    const mockError = new Error("Network error");
    const queryFn = vi.fn().mockRejectedValue(mockError);

    // Mock cache retrieval to fail (hook uses default export, not named export)
    dataCache.default.get.mockRejectedValue(new Error("Cache read failed"));

    const { result } = renderHook(() => useApiQuery(["test-key"], queryFn), {
      wrapper,
    });

    // 'Network error' triggers retries (200+400+800ms); wait long enough
    await waitFor(
      () => {
        expect(result.current.error).not.toBeNull();
      },
      { timeout: 5000 }
    );

    // Both cache read and API call failed, but no unhandled rejections
    expect(unhandledRejections.length).toBe(0);
    expect(result.current.error?.message).toContain("Network error");
  });

  it("should properly log errors without throwing", async () => {
    const consoleWarnSpy = vi
      .spyOn(console, "warn")
      .mockImplementation(() => {});
    const mockError = new Error("Test error");
    const queryFn = vi.fn().mockRejectedValue(mockError);

    dataCache.get.mockResolvedValue(null);

    renderHook(() => useApiQuery(["test-key"], queryFn), { wrapper });

    await waitFor(() => {
      expect(consoleWarnSpy).toHaveBeenCalledWith(
        expect.stringContaining("[useApiQuery] Query failed"),
        expect.anything()
      );
    });

    expect(unhandledRejections.length).toBe(0);
    consoleWarnSpy.mockRestore();
  });

  it("should format decimal fields for financial precision", async () => {
    const mockData = {
      position_value: 12345.6789,
      unrealized_pnl_dollars: 123.456789,
      avg_entry_price: 99.99999,
      current_price: 100.0001,
    };
    const queryFn = vi.fn().mockResolvedValue({
      data: { success: true, data: mockData },
    });

    dataCache.set.mockResolvedValue(undefined);
    dataCache.get.mockResolvedValue(null);

    const { result } = renderHook(
      () => useApiQuery(["algo-positions"], queryFn),
      { wrapper }
    );

    await waitFor(() => {
      expect(result.current.data).toBeDefined();
    });

    // All float values should be formatted to 2 decimal places for financial precision
    expect(result.current.data.position_value).toBe(12345.68);
    expect(result.current.data.unrealized_pnl_dollars).toBe(123.46);
    expect(result.current.data.avg_entry_price).toBe(100.0);
    expect(result.current.data.current_price).toBe(100.0);
  });
});

describe("useApiPaginatedQuery - Unhandled Promise Rejections Fix", () => {
  let queryClient;
  let unhandledRejections = [];

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: 0 },
      },
    });

    unhandledRejections = [];

    const handleRejection = (e) => {
      unhandledRejections.push(e.reason || e);
    };

    window.addEventListener("unhandledrejection", handleRejection);

    return () => {
      window.removeEventListener("unhandledrejection", handleRejection);
    };
  });

  afterEach(() => {
    vi.clearAllMocks();
    unhandledRejections = [];
  });

  const wrapper = ({ children }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);

  it("should handle paginated query errors without unhandled rejections", async () => {
    const mockError = new Error("Paginated API failed");
    const queryFn = vi.fn().mockRejectedValue(mockError);

    dataCache.default.get.mockResolvedValue(null);

    const { result } = renderHook(
      () => useApiPaginatedQuery(["test-paginated"], queryFn),
      { wrapper }
    );

    // toBeDefined() passes for null; use not.toBeNull() to wait for actual error
    await waitFor(() => {
      expect(result.current.error).not.toBeNull();
    });

    expect(unhandledRejections.length).toBe(0);
    expect(result.current.error?.message).toContain("Paginated API failed");
  });

  it("should return empty items array on error", async () => {
    const queryFn = vi.fn().mockRejectedValue(new Error("API error"));
    dataCache.get.mockResolvedValue(null);

    const { result } = renderHook(
      () => useApiPaginatedQuery(["test-paginated"], queryFn),
      { wrapper }
    );

    await waitFor(() => {
      expect(result.current.error).toBeDefined();
    });

    expect(result.current.items).toEqual([]);
    expect(unhandledRejections.length).toBe(0);
  });

  it("should handle API response without items property (Issue #9)", async () => {
    const queryFn = vi.fn().mockResolvedValue({
      data: { statusCode: 200, data: {} }, // No items property
    });

    dataCache.set.mockResolvedValue(undefined);
    dataCache.get.mockResolvedValue(null);

    const { result } = renderHook(
      () => useApiPaginatedQuery(["test-no-items"], queryFn),
      { wrapper }
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    // Should return empty items array without errors
    expect(result.current.items).toEqual([]);
    expect(result.current.error).toBeNull();
    expect(unhandledRejections.length).toBe(0);
  });

  it("should handle API response with undefined items property", async () => {
    const queryFn = vi.fn().mockResolvedValue({
      data: { statusCode: 200, data: { items: undefined } },
    });

    dataCache.set.mockResolvedValue(undefined);
    dataCache.get.mockResolvedValue(null);

    const { result } = renderHook(
      () => useApiPaginatedQuery(["test-undefined-items"], queryFn),
      { wrapper }
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.items).toEqual([]);
    expect(result.current.error).toBeNull();
    expect(unhandledRejections.length).toBe(0);
  });

  it("should handle API response with null items property", async () => {
    const queryFn = vi.fn().mockResolvedValue({
      data: { statusCode: 200, data: { items: null } },
    });

    dataCache.set.mockResolvedValue(undefined);
    dataCache.get.mockResolvedValue(null);

    const { result } = renderHook(
      () => useApiPaginatedQuery(["test-null-items"], queryFn),
      { wrapper }
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.items).toEqual([]);
    expect(result.current.error).toBeNull();
    expect(unhandledRejections.length).toBe(0);
  });
});
