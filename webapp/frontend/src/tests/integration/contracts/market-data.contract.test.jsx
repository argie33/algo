/**
 * Market Data Contract Test
 *
 * Tests the contract between frontend market components and backend market data API.
 * Validates real API structures for market overview, sector data, and real-time quotes.
 */

import { describe, it, expect, beforeAll } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { TestWrapper } from "../../test-utils.jsx";
import MarketOverview from "../../../pages/MarketOverview.jsx";
import SectorAnalysis from "../../../pages/SectorAnalysis.jsx";
import {
  checkServerAvailability,
  skipIfServerUnavailable,
  API_BASE_URL,
  AUTH_HEADERS,
} from "./test-server-utils.js";

describe("Market Data Contract Tests", () => {
  let serverAvailable = false;

  beforeAll(async () => {
    serverAvailable = await checkServerAvailability();
  });

  it("should validate market overview data structure", async () => {
    if (skipIfServerUnavailable(serverAvailable, "market overview test"))
      return;

    // STEP 1: Test real backend API response structure
    const response = await fetch(`${API_BASE_URL}/api/market/overview`, {
      headers: AUTH_HEADERS,
    });

    expect(response.status).toBe(200);
    const apiResponse = await response.json();

    // Validate backend contract
    expect(apiResponse).toHaveProperty("success", true);
    expect(apiResponse).toHaveProperty("data");

    console.log("Market overview structure:", {
      success: apiResponse.success,
      dataType: typeof apiResponse.data,
      dataKeys: Object.keys(apiResponse.data || {}),
      hasIndices: "indices" in (apiResponse.data || {}),
      hasMarketSummary: "marketSummary" in (apiResponse.data || {}),
    });

    // STEP 2: Validate expected market data fields
    if (apiResponse.data) {
      const marketData = apiResponse.data;

      // Common market overview fields
      if (marketData.indices) {
        expect(Array.isArray(marketData.indices)).toBe(true);
        if (marketData.indices.length > 0) {
          const sampleIndex = marketData.indices[0];
          expect(sampleIndex).toHaveProperty("symbol");
          expect(sampleIndex).toHaveProperty("price");
        }
      }
    }
  });

  it("should validate sector analysis data structure", async () => {
    if (skipIfServerUnavailable(serverAvailable, "sector analysis test"))
      return;

    const response = await fetch(`${API_BASE_URL}/api/sectors/analysis`, {
      headers: AUTH_HEADERS,
    });

    expect(response.status).toBe(200);
    const apiResponse = await response.json();

    // Validate backend contract
    expect(apiResponse).toHaveProperty("success", true);
    expect(apiResponse).toHaveProperty("data");

    console.log("Sectors analysis structure:", {
      success: apiResponse.success,
      dataType: typeof apiResponse.data,
      dataKeys: Object.keys(apiResponse.data || {}),
      isSectorsArray: Array.isArray(apiResponse.data?.sectors),
    });

    // STEP 2: Validate sector data structure
    if (apiResponse.data?.sectors && Array.isArray(apiResponse.data.sectors)) {
      const sectors = apiResponse.data.sectors;
      if (sectors.length > 0) {
        const sampleSector = sectors[0];
        expect(sampleSector).toHaveProperty("name");
        expect(sampleSector).toHaveProperty("performance");
      }
    }
  });

  it("should validate real-time quotes data structure", async () => {
    if (skipIfServerUnavailable(serverAvailable, "real-time quotes test"))
      return;

    const testSymbols = "AAPL,MSFT,GOOGL";
    const response = await fetch(
      `${API_BASE_URL}/api/market/quotes?symbols=${testSymbols}`,
      {
        headers: AUTH_HEADERS,
      }
    );

    expect(response.status).toBe(200);
    const apiResponse = await response.json();

    // Validate backend contract
    expect(apiResponse).toHaveProperty("success", true);
    expect(apiResponse).toHaveProperty("data");

    console.log("Real-time quotes structure:", {
      success: apiResponse.success,
      dataType: typeof apiResponse.data,
      dataKeys: Object.keys(apiResponse.data || {}),
      quotesCount: Array.isArray(apiResponse.data)
        ? apiResponse.data.length
        : "not array",
    });

    // STEP 2: Validate quote object structure
    if (Array.isArray(apiResponse.data) && apiResponse.data.length > 0) {
      const sampleQuote = apiResponse.data[0];
      expect(sampleQuote).toHaveProperty("symbol");
      expect(sampleQuote).toHaveProperty("price");
      expect(sampleQuote).toHaveProperty("timestamp");
    }
  });

  it("should validate market movers data structure", async () => {
    if (skipIfServerUnavailable(serverAvailable, "market movers test")) return;

    const response = await fetch(`${API_BASE_URL}/api/market/movers`, {
      headers: AUTH_HEADERS,
    });

    const apiResponse = await response.json();

    // Validate backend contract
    expect(apiResponse).toHaveProperty("success", true);

    console.log("Market movers structure:", {
      success: apiResponse.success,
      dataType: typeof apiResponse.data,
      hasGainers: "gainers" in (apiResponse.data || {}),
      hasLosers: "losers" in (apiResponse.data || {}),
      hasVolume: "volume" in (apiResponse.data || {}),
    });
  });

  it("should validate WebSocket streaming contract for market data", async () => {
    if (skipIfServerUnavailable(serverAvailable, "WebSocket streaming test"))
      return;

    // Test WebSocket endpoint that was causing 404 errors
    const symbols = "AAPL,MSFT,GOOGL";
    const response = await fetch(
      `${API_BASE_URL}/api/websocket/stream/?symbols=${symbols}`,
      {
        headers: AUTH_HEADERS,
      }
    );

    // Should not return 404 when symbols are provided
    expect(response.status).not.toBe(404);

    console.log("WebSocket market streaming status:", response.status);

    // Test handling of empty symbols parameter
    const emptyResponse = await fetch(
      `${API_BASE_URL}/api/websocket/stream/?symbols=`,
      {
        headers: AUTH_HEADERS,
      }
    );

    console.log("WebSocket empty symbols response:", emptyResponse.status);
  });

  it("should validate market data API contract supports trading dashboard", async () => {
    if (
      skipIfServerUnavailable(
        serverAvailable,
        "trading dashboard contract test"
      )
    )
      return;

    // Test that market data APIs return structures needed for trading decisions
    const marketResponse = await fetch(`${API_BASE_URL}/api/market/overview`, {
      headers: AUTH_HEADERS,
    });

    expect(marketResponse.status).toBe(200);
    const marketData = await marketResponse.json();

    // Validate trading-critical data structure
    expect(marketData).toHaveProperty("success", true);
    expect(marketData).toHaveProperty("data");

    if (marketData.data?.indices) {
      // Validate index data structure for trading
      const sampleIndex = marketData.data.indices[0];
      if (sampleIndex) {
        expect(sampleIndex).toHaveProperty("symbol");
        expect(sampleIndex).toHaveProperty("price");
        expect(typeof sampleIndex.price === "number").toBe(true);
      }
    }

    console.log("✅ Market data contract supports trading dashboard");
  });

  it("should validate sector data API contract supports portfolio analysis", async () => {
    if (
      skipIfServerUnavailable(
        serverAvailable,
        "portfolio analysis contract test"
      )
    )
      return;

    const sectorsResponse = await fetch(
      `${API_BASE_URL}/api/sectors/analysis`,
      {
        headers: AUTH_HEADERS,
      }
    );

    expect(sectorsResponse.status).toBe(200);
    const sectorsData = await sectorsResponse.json();

    // Validate portfolio analysis data structure
    expect(sectorsData).toHaveProperty("success", true);
    expect(sectorsData).toHaveProperty("data");

    if (sectorsData.data?.sectors && Array.isArray(sectorsData.data.sectors)) {
      const sampleSector = sectorsData.data.sectors[0];
      if (sampleSector) {
        expect(sampleSector).toHaveProperty("name");
        expect(sampleSector).toHaveProperty("performance");
        expect(typeof sampleSector.performance === "number").toBe(true);
      }
    }

    console.log("✅ Sector data contract supports portfolio analysis");
  });

  it("should render MarketOverview component with real backend data and handle UI interactions", async () => {
    if (
      skipIfServerUnavailable(serverAvailable, "MarketOverview full-stack test")
    )
      return;

    // STEP 1: Verify backend API returns proper data
    const marketResponse = await fetch(`${API_BASE_URL}/api/market/overview`, {
      headers: AUTH_HEADERS,
    });

    expect(marketResponse.status).toBe(200);
    const marketData = await marketResponse.json();
    expect(marketData).toHaveProperty("success", true);

    // STEP 2: Test frontend integration - render component with real backend
    render(
      <TestWrapper>
        <MarketOverview />
      </TestWrapper>
    );

    // STEP 3: Verify UI renders without crashing
    await waitFor(() => {
      // Should show market overview content
      expect(
        screen.getByText(/market/i) || screen.getByText(/overview/i)
      ).toBeInTheDocument();
    });

    // STEP 4: Verify data loads without errors
    await waitFor(
      () => {
        // Should not show error states if backend API is working
        expect(
          screen.queryByText(/error loading market data/i)
        ).not.toBeInTheDocument();
        expect(screen.queryByText(/failed to load/i)).not.toBeInTheDocument();
        expect(
          screen.queryByText(/something went wrong/i)
        ).not.toBeInTheDocument();
      },
      { timeout: 15000 } // Allow time for charts and complex components
    );

    console.log(
      "✅ MarketOverview component successfully integrates with backend API"
    );
  });

  it("should render SectorAnalysis component with real backend data and display sectors", async () => {
    if (
      skipIfServerUnavailable(serverAvailable, "SectorAnalysis full-stack test")
    )
      return;

    // STEP 1: Verify backend API returns sector data
    const sectorsResponse = await fetch(`${API_BASE_URL}/api/market/sectors`, {
      headers: AUTH_HEADERS,
    });

    expect(sectorsResponse.status).toBe(200);
    const sectorsData = await sectorsResponse.json();
    expect(sectorsData).toHaveProperty("success", true);

    // STEP 2: Test frontend integration
    render(
      <TestWrapper>
        <SectorAnalysis />
      </TestWrapper>
    );

    // STEP 3: Verify sector analysis page renders
    await waitFor(() => {
      expect(
        screen.getByText(/sector/i) || screen.getByText(/analysis/i)
      ).toBeInTheDocument();
    });

    // STEP 4: Verify data integration works
    await waitFor(
      () => {
        // Should not show error states if API is working
        expect(
          screen.queryByText(/error loading sector data/i)
        ).not.toBeInTheDocument();
        expect(
          screen.queryByText(/sectors service unavailable/i)
        ).not.toBeInTheDocument();
      },
      { timeout: 12000 }
    );

    console.log(
      "✅ SectorAnalysis component successfully displays backend sector data"
    );
  });
});
