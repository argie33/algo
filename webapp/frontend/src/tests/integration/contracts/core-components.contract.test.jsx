/**
 * Core Components Contract Test
 * 
 * Tests critical frontend components that consume backend APIs.
 * Ensures component-API integration works correctly.
 */

import { describe, it, expect, beforeAll, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { TestWrapper } from "../../test-utils.jsx";
import Watchlist from "../../../pages/Watchlist.jsx";
import TechnicalAnalysis from "../../../pages/TechnicalAnalysis.jsx";
import StockExplorer from "../../../pages/StockExplorer.jsx";
import NewsAnalysis from "../../../pages/NewsAnalysis.jsx";
import { 
  checkServerAvailability, 
  skipIfServerUnavailable, 
  API_BASE_URL,
  AUTH_HEADERS,
  createMockFetch 
} from "./test-server-utils.js";

describe("Core Components Contract Tests", () => {
  let serverAvailable = false;

  beforeAll(async () => {
    serverAvailable = await checkServerAvailability();
  });

  it("should validate Watchlist component consumes watchlist API correctly", async () => {
    if (skipIfServerUnavailable(serverAvailable, "Watchlist component test")) return;

    // Mock the watchlist API response structure
    const mockWatchlistResponse = {
      success: true,
      data: {
        watchlist: [
          {
            symbol: 'AAPL',
            name: 'Apple Inc.',
            price: 175.50,
            change: 2.30,
            changePercent: 1.33
          },
          {
            symbol: 'MSFT', 
            name: 'Microsoft Corporation',
            price: 350.25,
            change: -1.75,
            changePercent: -0.50
          }
        ],
        count: 2
      }
    };

    const { cleanup } = createMockFetch(mockWatchlistResponse);
    
    // Cleanup
    afterEach(() => {
      cleanup();
    });

    // Render the Watchlist component
    render(
      <TestWrapper>
        <Watchlist />
      </TestWrapper>
    );

    // Verify component can consume the API structure
    await waitFor(() => {
      // Should not show error states if API contract is correct
      expect(screen.queryByText(/error loading watchlist/i)).not.toBeInTheDocument();
    }, { timeout: 10000 });
  });

  it("should validate TechnicalAnalysis component consumes technical API correctly", async () => {
    if (skipIfServerUnavailable(serverAvailable, "TechnicalAnalysis component test")) return;

    // Mock the technical analysis API response structure
    const mockTechnicalResponse = {
      success: true,
      data: {
        symbol: 'AAPL',
        indicators: {
          rsi: 65.4,
          macd: 1.23,
          bb: {
            upper: 180.0,
            middle: 175.0,
            lower: 170.0
          }
        },
        signals: [
          {
            type: 'buy',
            confidence: 0.75,
            reason: 'RSI oversold'
          }
        ]
      }
    };

    const { cleanup } = createMockFetch(mockTechnicalResponse);
    
    afterEach(() => {
      cleanup();
    });

    render(
      <TestWrapper>
        <TechnicalAnalysis />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.queryByText(/error loading technical data/i)).not.toBeInTheDocument();
    }, { timeout: 10000 });
  });

  it("should validate StockExplorer component consumes stock API correctly", async () => {
    if (skipIfServerUnavailable(serverAvailable, "StockExplorer component test")) return;

    const mockStockResponse = {
      success: true,
      data: {
        stocks: [
          {
            symbol: 'AAPL',
            name: 'Apple Inc.',
            sector: 'Technology',
            marketCap: 2800000000000,
            price: 175.50
          }
        ],
        pagination: {
          total: 100,
          page: 1,
          limit: 20
        }
      }
    };

    const { cleanup } = createMockFetch(mockStockResponse);
    
    afterEach(() => {
      cleanup();
    });

    render(
      <TestWrapper>
        <StockExplorer />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.queryByText(/error loading stocks/i)).not.toBeInTheDocument();
    }, { timeout: 10000 });
  });

  it("should validate NewsAnalysis component consumes news API correctly", async () => {
    if (skipIfServerUnavailable(serverAvailable, "NewsAnalysis component test")) return;

    const mockNewsResponse = {
      success: true,
      data: {
        articles: [
          {
            id: '1',
            title: 'Apple Reports Strong Q4 Earnings',
            summary: 'Apple exceeded expectations with strong iPhone sales',
            sentiment: 'positive',
            publishedAt: '2024-01-15T10:30:00Z',
            source: 'Reuters'
          }
        ],
        sentiment: {
          overall: 'positive',
          score: 0.75
        }
      }
    };

    const { cleanup } = createMockFetch(mockNewsResponse);
    
    afterEach(() => {
      cleanup();
    });

    render(
      <TestWrapper>
        <NewsAnalysis />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.queryByText(/error loading news/i)).not.toBeInTheDocument();
    }, { timeout: 10000 });
  });

  describe("API Integration Validation", () => {
    it("should validate watchlist API endpoint structure", async () => {
      if (skipIfServerUnavailable(serverAvailable, "watchlist API test")) return;

      const response = await fetch(`${API_BASE_URL}/api/watchlist`, {
        headers: AUTH_HEADERS
      });
      
      const apiResponse = await response.json();
      
      // Validate backend contract
      expect(apiResponse).toHaveProperty('success');
      
      console.log('Watchlist API structure:', {
        success: apiResponse.success,
        hasData: 'data' in apiResponse,
        dataType: typeof apiResponse.data
      });
    });

    it("should validate technical analysis API endpoint structure", async () => {
      if (skipIfServerUnavailable(serverAvailable, "technical API test")) return;

      const response = await fetch(`${API_BASE_URL}/api/technical/daily/AAPL`, {
        headers: AUTH_HEADERS
      });
      
      const apiResponse = await response.json();
      
      expect(apiResponse).toHaveProperty('success');
      
      console.log('Technical API structure:', {
        success: apiResponse.success,
        hasData: 'data' in apiResponse,
        dataType: typeof apiResponse.data
      });
    });

    it("should validate news API endpoint structure", async () => {
      if (skipIfServerUnavailable(serverAvailable, "news API test")) return;

      const response = await fetch(`${API_BASE_URL}/api/news/latest`, {
        headers: AUTH_HEADERS
      });
      
      const apiResponse = await response.json();
      
      expect(apiResponse).toHaveProperty('success');
      
      console.log('News API structure:', {
        success: apiResponse.success,
        hasData: 'data' in apiResponse,
        dataType: typeof apiResponse.data
      });
    });
  });
});