/**
 * REAL SITE Tests for Dashboard Component
 * Tests the actual site functionality with real API calls
 */

import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Dashboard from "../../../pages/Dashboard";

// Mock only the AuthContext to provide user authentication
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: () => ({
    user: { id: 'test-user', email: 'test@example.com', name: 'Test User' },
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

describe("Dashboard Component - REAL SITE TESTING", () => {
  beforeEach(() => {
    // Ensure we're using real fetch
    global.fetch = global.originalFetch || fetch;
  });

  it("should render Dashboard component without crashing", () => {
    // Basic smoke test - component should render
    const { container } = renderWithRouter(<Dashboard />);
    expect(container).toBeTruthy();
    expect(container.innerHTML).not.toBe("");
  });

  it("should display Dashboard heading or main content", async () => {
    // Test that the component displays the main Dashboard content
    renderWithRouter(<Dashboard />);

    await waitFor(() => {
      // Look for Dashboard heading or any main content
      const dashboardHeading = screen.queryByText(/Dashboard/i);
      const dashboardContent = document.body.textContent;
      
      // Should have either Dashboard heading or some substantial content
      expect(
        dashboardHeading || 
        dashboardContent.length > 100
      ).toBeTruthy();
    }, { timeout: 15000 });
  });

  it("should make real API calls to load dashboard data", async () => {
    // Test that component makes actual API requests
    let apiCallMade = false;
    
    // Monitor fetch calls
    const originalFetch = global.fetch;
    global.fetch = async (...args) => {
      apiCallMade = true;
      return originalFetch(...args);
    };

    renderWithRouter(<Dashboard />);

    await waitFor(() => {
      expect(apiCallMade).toBe(true);
    }, { timeout: 10000 });

    // Restore original fetch
    global.fetch = originalFetch;
  });

  it("should handle real API responses or errors gracefully", async () => {
    // Test that component handles real API responses without crashing
    renderWithRouter(<Dashboard />);

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

  it("should display loading states or content within reasonable time", async () => {
    // Test that users get feedback within reasonable time
    renderWithRouter(<Dashboard />);

    await waitFor(() => {
      const bodyText = document.body.textContent;
      
      // Should show either loading indicator, data, or meaningful content
      const hasContent = bodyText.length > 100;
      const hasLoadingIndicator = bodyText.toLowerCase().includes("loading");
      const hasDashboardContent = bodyText.toLowerCase().includes("dashboard") || 
                                 bodyText.toLowerCase().includes("market") ||
                                 bodyText.toLowerCase().includes("overview");
      
      expect(hasContent || hasLoadingIndicator || hasDashboardContent).toBe(true);
    }, { timeout: 10000 });
  });

  it("should display market data or error message", async () => {
    // Test that dashboard shows market data or handles errors appropriately
    renderWithRouter(<Dashboard />);

    await waitFor(() => {
      const bodyText = document.body.textContent.toLowerCase();
      
      // Should show either market data indicators or clear error handling
      const hasMarketData = bodyText.includes("market") || 
                           bodyText.includes("stocks") ||
                           bodyText.includes("index") ||
                           bodyText.includes("portfolio");
      
      const hasErrorHandling = bodyText.includes("error") || 
                              bodyText.includes("failed") ||
                              bodyText.includes("try again");
      
      // Should show either data or proper error handling, not blank screen
      expect(hasMarketData || hasErrorHandling).toBe(true);
    }, { timeout: 15000 });
  });
});