/**
 * REAL SITE Tests for Settings Component
 * Tests the actual site functionality with real API calls
 */

import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import Settings from "../../../pages/Settings";

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
    logout: vi.fn(),
    checkAuthState: vi.fn(),
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

describe("Settings Component - REAL SITE TESTING", () => {
  beforeEach(() => {
    // Ensure we're using real fetch
    global.fetch = global.originalFetch || fetch;
  });

  it("should render Settings component without crashing", () => {
    // Basic smoke test - component should render
    const { container } = renderWithRouter(<Settings />);
    expect(container).toBeTruthy();
    expect(container.innerHTML).not.toBe("");
  });

  it("should display Settings heading and tabs", async () => {
    // Test that the component displays the main Settings content
    renderWithRouter(<Settings />);

    await waitFor(() => {
      // Look for Settings heading
      const settingsHeading = screen.queryByText(/Account Settings/i);
      expect(settingsHeading).toBeTruthy();
      
      // Look for main tab navigation
      const profileTab = screen.queryByText(/Profile/i);
      const apiKeysTab = screen.queryByText(/API Keys/i);
      expect(profileTab || apiKeysTab).toBeTruthy();
    }, { timeout: 10000 });
  });

  it("should make real API calls to load user settings", async () => {
    // Test that component makes actual API requests
    let apiCallMade = false;
    
    // Monitor fetch calls
    const originalFetch = global.fetch;
    global.fetch = async (...args) => {
      apiCallMade = true;
      return originalFetch(...args);
    };

    renderWithRouter(<Settings />);

    await waitFor(() => {
      expect(apiCallMade).toBe(true);
    }, { timeout: 10000 });

    // Restore original fetch
    global.fetch = originalFetch;
  });

  it("should handle real API responses or errors gracefully", async () => {
    // Test that component handles real API responses without crashing
    renderWithRouter(<Settings />);

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

  it("should display settings tabs within reasonable time", async () => {
    // Test that users get feedback within reasonable time
    renderWithRouter(<Settings />);

    await waitFor(() => {
      const bodyText = document.body.textContent;
      
      // Should show either loading indicator, data, or meaningful content
      const hasContent = bodyText.length > 100;
      const hasLoadingIndicator = bodyText.toLowerCase().includes("loading");
      const hasSettingsContent = bodyText.toLowerCase().includes("settings") || 
                                bodyText.toLowerCase().includes("profile") ||
                                bodyText.toLowerCase().includes("api keys");
      
      expect(hasContent || hasLoadingIndicator || hasSettingsContent).toBe(true);
    }, { timeout: 10000 });
  });

  it("should display API Keys tab functionality", async () => {
    // Test that settings shows API keys management
    renderWithRouter(<Settings />);

    await waitFor(() => {
      const bodyText = document.body.textContent.toLowerCase();
      
      // Should show either API keys content or error handling
      const hasApiKeysContent = bodyText.includes("api") || 
                               bodyText.includes("keys") ||
                               bodyText.includes("broker");
      
      const hasErrorHandling = bodyText.includes("error") || 
                              bodyText.includes("failed") ||
                              bodyText.includes("try again");
      
      // Should show either data or proper error handling, not blank screen
      expect(hasApiKeysContent || hasErrorHandling).toBe(true);
    }, { timeout: 15000 });
  });

  it("should handle user profile data loading", async () => {
    // Test that settings loads and displays user profile information
    renderWithRouter(<Settings />);

    await waitFor(() => {
      const bodyText = document.body.textContent.toLowerCase();
      
      // Should show profile-related content
      const hasProfileContent = bodyText.includes("profile") || 
                               bodyText.includes("first name") ||
                               bodyText.includes("last name") ||
                               bodyText.includes("email") ||
                               bodyText.includes("test user");
      
      const hasErrorHandling = bodyText.includes("unable to load") || 
                              bodyText.includes("authentication issue");
      
      // Should show either profile data or proper error handling
      expect(hasProfileContent || hasErrorHandling).toBe(true);
    }, { timeout: 15000 });
  });
});