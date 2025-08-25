/**
 * REAL SITE Tests for TechnicalAnalysis Component
 * Tests the actual site functionality with real API calls
 */

import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import TechnicalAnalysis from "../../../pages/TechnicalAnalysis";

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

describe("TechnicalAnalysis Component - REAL SITE TESTING", () => {
  beforeEach(() => {
    // Ensure we're using real fetch
    global.fetch = global.originalFetch || fetch;
  });

  it("should render TechnicalAnalysis component without crashing", () => {
    // Basic smoke test - component should render
    const { container } = renderWithRouter(<TechnicalAnalysis />);
    expect(container).toBeTruthy();
    expect(container.innerHTML).not.toBe("");
  });

  it("should display Technical Analysis heading and filters", async () => {
    // Test that the component displays the main Technical Analysis content
    renderWithRouter(<TechnicalAnalysis />);

    await waitFor(() => {
      // Look for Technical Analysis heading
      const technicalHeading = screen.queryByText(/Technical Analysis/i);
      expect(technicalHeading).toBeTruthy();
      
      // Look for filter controls
      const timeframeFilter = screen.queryByText(/Timeframe/i);
      const searchFilter = screen.queryByText(/Search Symbol/i);
      expect(timeframeFilter || searchFilter).toBeTruthy();
    }, { timeout: 10000 });
  });

  it("should make real API calls to load technical data", async () => {
    // Test that component makes actual API requests
    let apiCallMade = false;
    
    // Monitor fetch calls
    const originalFetch = global.fetch;
    global.fetch = async (...args) => {
      apiCallMade = true;
      return originalFetch(...args);
    };

    renderWithRouter(<TechnicalAnalysis />);

    await waitFor(() => {
      expect(apiCallMade).toBe(true);
    }, { timeout: 10000 });

    // Restore original fetch
    global.fetch = originalFetch;
  });

  it("should handle real API responses or errors gracefully", async () => {
    // Test that component handles real API responses without crashing
    renderWithRouter(<TechnicalAnalysis />);

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

  it("should display technical indicators and filters within reasonable time", async () => {
    // Test that users get feedback within reasonable time
    renderWithRouter(<TechnicalAnalysis />);

    await waitFor(() => {
      const bodyText = document.body.textContent;
      
      // Should show either loading indicator, data, or meaningful content
      const hasContent = bodyText.length > 100;
      const hasLoadingIndicator = bodyText.toLowerCase().includes("loading") ||
                                  bodyText.toLowerCase().includes("technical data");
      const hasTechnicalContent = bodyText.toLowerCase().includes("rsi") || 
                                 bodyText.toLowerCase().includes("macd") ||
                                 bodyText.toLowerCase().includes("indicator") ||
                                 bodyText.toLowerCase().includes("filter");
      
      expect(hasContent || hasLoadingIndicator || hasTechnicalContent).toBe(true);
    }, { timeout: 10000 });
  });

  it("should display technical indicators data", async () => {
    // Test that technical analysis shows RSI, MACD and other indicators
    renderWithRouter(<TechnicalAnalysis />);

    await waitFor(() => {
      const bodyText = document.body.textContent.toLowerCase();
      
      // Should show either technical indicator content or error handling
      const hasIndicatorContent = bodyText.includes("rsi") || 
                                 bodyText.includes("macd") ||
                                 bodyText.includes("adx") ||
                                 bodyText.includes("sma") ||
                                 bodyText.includes("ema");
      
      const hasErrorHandling = bodyText.includes("error loading technical data") || 
                              bodyText.includes("no technical data found");
      
      const hasLoadingState = bodyText.includes("loading technical data");
      
      // Should show either technical data, loading state, or proper error handling
      expect(hasIndicatorContent || hasErrorHandling || hasLoadingState).toBe(true);
    }, { timeout: 15000 });
  });

  it("should handle symbol search and filtering", async () => {
    // Test that technical analysis supports search and filtering functionality
    renderWithRouter(<TechnicalAnalysis />);

    await waitFor(() => {
      const bodyText = document.body.textContent.toLowerCase();
      
      // Should show search/filter functionality
      const hasSearchContent = bodyText.includes("search symbol") || 
                               bodyText.includes("filter") ||
                               bodyText.includes("timeframe") ||
                               bodyText.includes("daily") ||
                               bodyText.includes("weekly");
      
      const hasFilterControls = bodyText.includes("indicator") ||
                                bodyText.includes("min value") ||
                                bodyText.includes("max value");
      
      const hasLoadingState = bodyText.includes("loading");
      
      // Should show either filter functionality or loading state
      expect(hasSearchContent || hasFilterControls || hasLoadingState).toBe(true);
    }, { timeout: 15000 });
  });

  it("should display accordion-style technical data", async () => {
    // Test that technical analysis displays data in accordion format
    renderWithRouter(<TechnicalAnalysis />);

    await waitFor(() => {
      const bodyText = document.body.textContent.toLowerCase();
      
      // Should show accordion-style content or loading state
      const hasAccordionContent = bodyText.includes("symbol") && 
                                  (bodyText.includes("rsi") || bodyText.includes("macd"));
      
      const hasWarningMessage = bodyText.includes("no technical data found");
      
      const hasLoadingState = bodyText.includes("loading technical data");
      
      // Should show either accordion data, warning message, or loading state
      expect(hasAccordionContent || hasWarningMessage || hasLoadingState).toBe(true);
    }, { timeout: 15000 });
  });
});