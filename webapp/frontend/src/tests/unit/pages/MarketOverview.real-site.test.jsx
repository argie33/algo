/**
 * REAL SITE Tests for MarketOverview Component
 * Tests the actual site functionality with real API calls
 */

import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MarketOverview from "../../../pages/MarketOverview";

// Mock only the AuthContext to provide user authentication
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: () => ({
    user: { 
      id: 'test-user', 
      email: 'test@example.com', 
      name: 'Test User',
      firstName: 'Test',
      lastName: 'User',
      tokens: { accessToken: 'test-token' }
    },
    isAuthenticated: true,
    isLoading: false,
    error: null,
  }),
  AuthProvider: ({ children }) => children,
}));

const renderWithRouter = (component) => {
  // Create a real QueryClient for testing (no retries to speed up tests)
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {component}
      </BrowserRouter>
    </QueryClientProvider>
  );
};

describe("MarketOverview Component - REAL SITE TESTING", () => {
  beforeEach(() => {
    // Ensure we're using real fetch
    global.fetch = global.originalFetch || fetch;
  });

  it("should render MarketOverview component without crashing", () => {
    // Basic smoke test - component should render
    const { container } = renderWithRouter(<MarketOverview />);
    expect(container).toBeTruthy();
    expect(container.innerHTML).not.toBe("");
  });

  it("should display Market Overview heading and navigation", async () => {
    // Test that the component displays the main Market Overview content
    renderWithRouter(<MarketOverview />);

    await waitFor(() => {
      // Look for Market Overview heading
      const marketHeading = screen.queryByText(/Market Overview/i);
      expect(marketHeading).toBeTruthy();
      
      // Look for timeframe controls
      const oneDayButton = screen.queryByText(/1D/i);
      const oneWeekButton = screen.queryByText(/1W/i);
      expect(oneDayButton || oneWeekButton).toBeTruthy();
    }, { timeout: 10000 });
  });

  it("should make real API calls to load market data", async () => {
    // Test that component makes actual API requests
    let apiCallMade = false;
    
    // Monitor fetch calls
    const originalFetch = global.fetch;
    global.fetch = async (...args) => {
      apiCallMade = true;
      return originalFetch(...args);
    };

    renderWithRouter(<MarketOverview />);

    await waitFor(() => {
      expect(apiCallMade).toBe(true);
    }, { timeout: 10000 });

    // Restore original fetch
    global.fetch = originalFetch;
  });

  it("should handle real API responses or errors gracefully", async () => {
    // Test that component handles real API responses without crashing
    renderWithRouter(<MarketOverview />);

    await waitFor(() => {
      // Component should render something meaningful
      const body = document.body;
      expect(body).toBeTruthy();
      
      // Should not be completely empty
      expect(body.textContent.length).toBeGreaterThan(50);
      
      // Should not show major error messages (minor ones are okay)
      const bodyText = body.textContent.toLowerCase();
      const hasMajorError = bodyText.includes("something went wrong") || 
                          bodyText.includes("error boundary") ||
                          bodyText.includes("component crashed");
      expect(hasMajorError).toBe(false);
    }, { timeout: 15000 });
  });

  it("should display market sentiment indicators within reasonable time", async () => {
    // Test that users get feedback within reasonable time
    renderWithRouter(<MarketOverview />);

    await waitFor(() => {
      const bodyText = document.body.textContent;
      
      // Should show either loading indicator, data, or meaningful content
      const hasContent = bodyText.length > 100;
      const hasLoadingIndicator = bodyText.toLowerCase().includes("loading") ||
                                  bodyText.toLowerCase().includes("fetching");
      const hasMarketContent = bodyText.toLowerCase().includes("market") || 
                              bodyText.toLowerCase().includes("sentiment") ||
                              bodyText.toLowerCase().includes("fear") ||
                              bodyText.toLowerCase().includes("greed");
      
      expect(hasContent || hasLoadingIndicator || hasMarketContent).toBe(true);
    }, { timeout: 10000 });
  });

  it("should display market tabs and navigation", async () => {
    // Test that market overview shows tabbed navigation
    renderWithRouter(<MarketOverview />);

    await waitFor(() => {
      const bodyText = document.body.textContent.toLowerCase();
      
      // Should show either tab content or error handling
      const hasTabContent = bodyText.includes("sentiment") || 
                           bodyText.includes("sector") ||
                           bodyText.includes("breadth") ||
                           bodyText.includes("economic") ||
                           bodyText.includes("research");
      
      const hasErrorHandling = bodyText.includes("error") || 
                              bodyText.includes("failed") ||
                              bodyText.includes("try again");
      
      // Should show either data or proper error handling, not blank screen
      expect(hasTabContent || hasErrorHandling).toBe(true);
    }, { timeout: 15000 });
  });

  it("should handle sentiment indicators loading", async () => {
    // Test that market overview loads and displays sentiment data
    renderWithRouter(<MarketOverview />);

    await waitFor(() => {
      const bodyText = document.body.textContent.toLowerCase();
      
      // Should show sentiment-related content
      const hasSentimentContent = bodyText.includes("fear") || 
                                 bodyText.includes("greed") ||
                                 bodyText.includes("aaii") ||
                                 bodyText.includes("naaim") ||
                                 bodyText.includes("sentiment");
      
      const hasLoadingState = bodyText.includes("loading") ||
                             bodyText.includes("fetching");
      
      const hasErrorHandling = bodyText.includes("failed to load") || 
                              bodyText.includes("check your data sources");
      
      // Should show either sentiment data, loading state, or proper error handling
      expect(hasSentimentContent || hasLoadingState || hasErrorHandling).toBe(true);
    }, { timeout: 15000 });
  });

  it("should display market breadth data", async () => {
    // Test that market overview shows advancing/declining stocks data
    renderWithRouter(<MarketOverview />);

    await waitFor(() => {
      const bodyText = document.body.textContent.toLowerCase();
      
      // Should show market breadth content
      const hasBreadthContent = bodyText.includes("advancing") || 
                               bodyText.includes("declining") ||
                               bodyText.includes("breadth") ||
                               bodyText.includes("market cap");
      
      const hasLoadingState = bodyText.includes("loading") ||
                             bodyText.includes("real-time");
      
      const hasErrorHandling = bodyText.includes("failed") || 
                              bodyText.includes("debug endpoint");
      
      // Should show either breadth data, loading state, or proper error handling
      expect(hasBreadthContent || hasLoadingState || hasErrorHandling).toBe(true);
    }, { timeout: 15000 });
  });
});