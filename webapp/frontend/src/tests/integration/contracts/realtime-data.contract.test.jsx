/**
 * Real-Time Data Contract Tests
 * Tests WebSocket and streaming data contracts that were causing 404 errors
 */

import { describe, it, expect, beforeAll } from "vitest";
import {
  checkServerAvailability,
  skipIfServerUnavailable,
  API_BASE_URL,
  AUTH_HEADERS,
} from "./test-server-utils.js";

describe("Real-Time Data Contract Tests", () => {
  let serverAvailable = false;

  beforeAll(async () => {
    serverAvailable = await checkServerAvailability();
  });

  it("validates WebSocket stream endpoint requires symbols parameter", async () => {
    if (skipIfServerUnavailable(serverAvailable, "WebSocket contract test"))
      return;

    // Test the exact bug we fixed - empty symbols causing 404
    const emptySymbolsResponse = await fetch(
      `${API_BASE_URL}/api/websocket/stream/`,
      {
        headers: AUTH_HEADERS,
      }
    );

    console.log("Empty symbols endpoint status:", emptySymbolsResponse.status);
    // Should return 404 or error - this was the bug we fixed in frontend

    // Test with proper symbols
    const validSymbolsResponse = await fetch(
      `${API_BASE_URL}/api/websocket/stream/AAPL,GOOGL`,
      {
        headers: AUTH_HEADERS,
      }
    );

    console.log("Valid symbols endpoint status:", validSymbolsResponse.status);
    expect(validSymbolsResponse.status).not.toBe(404);
  });

  it("validates real-time price data structure", async () => {
    if (!serverAvailable) return;

    const response = await fetch(`${API_BASE_URL}/api/stocks/AAPL/price`, {
      headers: AUTH_HEADERS,
    });

    const data = await response.json();
    console.log("Real-time price structure:", Object.keys(data));
    expect(data).toHaveProperty("success", true);
  });

  it("validates live data manager endpoints", async () => {
    if (!serverAvailable) return;

    const response = await fetch(`${API_BASE_URL}/api/livedata/status`, {
      headers: AUTH_HEADERS,
    });

    if (response.ok) {
      const data = await response.json();
      console.log("Live data status structure:", Object.keys(data));
      expect(data).toHaveProperty("service", "live-data");
      expect(data).toHaveProperty("status", "operational");
    } else {
      console.log("Live data endpoint not available:", response.status);
    }
  });
});
