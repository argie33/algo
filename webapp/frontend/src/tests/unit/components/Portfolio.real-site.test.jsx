/**
 * REAL SITE Tests for Portfolio Component
 * Tests the actual site functionality with real API calls
 */

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import Portfolio from "../../../pages/Portfolio.jsx";

// Mock only the AuthContext to provide user authentication
import { vi } from "vitest";
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
  return render(
    <BrowserRouter>
      {component}
    </BrowserRouter>
  );
};

describe("Portfolio Component - REAL SITE TESTING", () => {
  beforeEach(() => {
    // Ensure we're using real fetch
    global.fetch = global.originalFetch || fetch;
  });

  it("should render Portfolio component without crashing", () => {
    // Basic smoke test - component should render
    const { container } = renderWithRouter(<Portfolio />);
    expect(container).toBeTruthy();
    expect(container.innerHTML).not.toBe("");
  });

  it("should display Portfolio heading or main content", async () => {
    // Test that the component displays the main Portfolio content
    renderWithRouter(<Portfolio />);

    await waitFor(() => {
      // Look for Portfolio heading or any main content
      const portfolioHeading = screen.queryByText(/Portfolio/i);
      const portfolioContent = document.body.textContent;
      
      // Should have either Portfolio heading or some substantial content
      expect(
        portfolioHeading || 
        portfolioContent.length > 100
      ).toBeTruthy();
    }, { timeout: 15000 });
  });

  it("should make real API calls to load portfolio data", async () => {
    // Test that component makes actual API requests
    let apiCallMade = false;
    
    // Monitor fetch calls
    const originalFetch = global.fetch;
    global.fetch = async (...args) => {
      apiCallMade = true;
      return originalFetch(...args);
    };

    renderWithRouter(<Portfolio />);

    await waitFor(() => {
      expect(apiCallMade).toBe(true);
    }, { timeout: 10000 });

    // Restore original fetch
    global.fetch = originalFetch;
  });

  it("should handle real API responses or errors gracefully", async () => {
    // Test that component handles real API responses without crashing
    renderWithRouter(<Portfolio />);

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
    renderWithRouter(<Portfolio />);

    await waitFor(() => {
      const bodyText = document.body.textContent;
      
      // Should show either loading indicator, data, or meaningful content
      const hasContent = bodyText.length > 100;
      const hasLoadingIndicator = bodyText.toLowerCase().includes("loading");
      const hasPortfolioContent = bodyText.toLowerCase().includes("portfolio");
      
      expect(hasContent || hasLoadingIndicator || hasPortfolioContent).toBe(true);
    }, { timeout: 10000 });
  });
});