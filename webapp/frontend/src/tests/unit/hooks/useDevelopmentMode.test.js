/**
 * useDevelopmentMode Hook Unit Tests
 * Tests development mode detection and API availability checking
 * 
 * This hook is crucial for our site because it:
 * - Determines when to show dev-only features
 * - Checks if our backend API is available
 * - Enables/disables real-time queries based on environment
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useDevelopmentMode } from "../../../hooks/useDevelopmentMode.js";

// Mock window location
const mockLocation = {
  hostname: 'localhost',
  port: '5173'
};
Object.defineProperty(window, 'location', {
  value: mockLocation,
  writable: true
});

describe("useDevelopmentMode Hook", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLocation.hostname = 'localhost';
    mockLocation.port = '5173';
    delete window.__CONFIG__;

    // Simple mocks that don't cause recursion
    global.fetch = vi.fn();
    global.AbortController = vi.fn(() => ({
      abort: vi.fn(),
      signal: {}
    }));
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("detects localhost as development mode", async () => {
    mockLocation.hostname = 'localhost';
    global.fetch.mockResolvedValue({ ok: true });

    const { result } = renderHook(() => useDevelopmentMode());

    expect(result.current.isDevelopment).toBe(true);
    
    await waitFor(() => {
      expect(result.current.apiAvailable).toBe(true);
    });
  });

  it("detects 127.0.0.1 as development mode", async () => {
    mockLocation.hostname = '127.0.0.1';
    global.fetch.mockResolvedValue({ ok: true });

    const { result } = renderHook(() => useDevelopmentMode());

    expect(result.current.isDevelopment).toBe(true);
  });

  it("detects port 5173 as development mode", async () => {
    mockLocation.hostname = 'example.com';
    mockLocation.port = '5173';
    global.fetch.mockResolvedValue({ ok: true });

    const { result } = renderHook(() => useDevelopmentMode());

    expect(result.current.isDevelopment).toBe(true);
  });

  it("detects production mode correctly", () => {
    mockLocation.hostname = 'production.example.com';
    mockLocation.port = '443';

    const { result } = renderHook(() => useDevelopmentMode());

    expect(result.current.isDevelopment).toBe(false);
    // In production, API is assumed available according to the hook
    expect(result.current.apiAvailable).toBe(true);
  });

  it("checks API availability in development mode", async () => {
    mockLocation.hostname = 'localhost';
    global.fetch.mockResolvedValue({ ok: true });

    const { result } = renderHook(() => useDevelopmentMode());

    await waitFor(() => {
      expect(result.current.apiAvailable).toBe(true);
    });

    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:3001/api/health',
      expect.objectContaining({
        headers: { 'Accept': 'application/json' }
      })
    );
  });

  it("handles API unavailable in development mode", async () => {
    mockLocation.hostname = 'localhost';
    global.fetch.mockResolvedValue({ ok: false });

    const { result } = renderHook(() => useDevelopmentMode());

    await waitFor(() => {
      expect(result.current.apiAvailable).toBe(false);
    });
  });

  it("handles API fetch error gracefully", async () => {
    mockLocation.hostname = 'localhost';
    global.fetch.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useDevelopmentMode());

    await waitFor(() => {
      expect(result.current.apiAvailable).toBe(false);
    });
  });

  it("uses custom API URL from window.__CONFIG__", async () => {
    window.__CONFIG__ = { API_URL: 'http://custom-api:3002' };
    mockLocation.hostname = 'localhost';
    global.fetch.mockResolvedValue({ ok: true });

    renderHook(() => useDevelopmentMode());

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        'http://custom-api:3002/api/health',
        expect.any(Object)
      );
    });
  });

  it("handles network errors gracefully (critical for site reliability)", async () => {
    mockLocation.hostname = 'localhost';
    global.fetch.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useDevelopmentMode());

    // Should detect development but handle API failure gracefully
    expect(result.current.isDevelopment).toBe(true);
    
    await waitFor(() => {
      expect(result.current.apiAvailable).toBe(false);
    });
  });

  it("returns consistent state structure", () => {
    const { result } = renderHook(() => useDevelopmentMode());

    expect(result.current).toHaveProperty('isDevelopment');
    expect(result.current).toHaveProperty('apiAvailable');
    expect(typeof result.current.isDevelopment).toBe('boolean');
    expect(typeof result.current.apiAvailable).toBe('boolean');
  });

  it("does not check API in production mode (improves performance)", () => {
    mockLocation.hostname = 'production.example.com';
    mockLocation.port = '443';

    const { result } = renderHook(() => useDevelopmentMode());

    expect(result.current.isDevelopment).toBe(false);
    // In production mode, API is assumed available for performance
    expect(result.current.apiAvailable).toBe(true);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("correctly identifies different development environments", () => {
    const testCases = [
      { hostname: 'localhost', port: '5173', expected: true, desc: 'Vite dev server' },
      { hostname: '127.0.0.1', port: '3000', expected: true, desc: 'Local IP' },
      { hostname: 'production.com', port: '5173', expected: true, desc: 'Vite port anywhere' },
      { hostname: 'production.com', port: '80', expected: false, desc: 'Production' },
      { hostname: 'staging.com', port: '443', expected: false, desc: 'Staging' }
    ];

    testCases.forEach(({ hostname, port = '80', expected }) => {
      mockLocation.hostname = hostname;
      mockLocation.port = port;

      const { result, unmount } = renderHook(() => useDevelopmentMode());
      
      expect(result.current.isDevelopment).toBe(expected);
      
      unmount();
    });
  });

  it("provides shouldEnableQueries helper for conditional data fetching", () => {
    mockLocation.hostname = 'localhost';
    global.fetch.mockResolvedValue({ ok: true });

    const { result } = renderHook(() => useDevelopmentMode());

    // Should have the helper property for enabling/disabling queries
    expect(result.current).toHaveProperty('shouldEnableQueries');
    expect(typeof result.current.shouldEnableQueries).toBe('boolean');
  });
});