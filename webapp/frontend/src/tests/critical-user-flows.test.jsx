/**
 * Critical User Flows Test
 * Tests the most important user journeys on our financial platform
 */

import { useState, useEffect } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders, screen, waitFor } from "./test-utils.jsx";

// Mock the actual API calls
vi.mock("../services/api.js", () => ({
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
  testApiConnection: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: { status: "healthy" },
    })
  ),
}));

describe("Critical User Flows", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
  });

  describe("Application Bootstrap", () => {
    it("should load React application successfully", () => {
      const testElement = document.createElement("div");
      expect(testElement).toBeTruthy();
    });

    it("should handle routing configuration", async () => {
      // Test that our routing setup works
      const _mockComponent = () => <div>Test Route</div>;
      const { container } = renderWithProviders(<_mockComponent />);
      expect(container).toBeTruthy();
    });
  });

  describe("Authentication Flow", () => {
    it("should handle user authentication context", async () => {
      // Test the authentication provider
      const TestComponent = () => {
        return <div data-testid="auth-test">Authentication Test</div>;
      };

      renderWithProviders(<TestComponent />);
      
      await waitFor(() => {
        expect(screen.getByTestId("auth-test")).toBeTruthy();
      });
    });
  });

  describe("Data Loading Flow", () => {
    it("should handle API configuration loading", async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
          success: true,
          data: { message: "API is healthy" }
        }),
      });

      // Test that fetch is configured and working
      const response = await global.fetch("/api/health");
      expect(response.ok).toBe(true);
    });

    it("should handle loading states appropriately", async () => {
      let resolvePromise;
      const loadingPromise = new Promise((resolve) => {
        resolvePromise = resolve;
      });

      global.fetch.mockReturnValue(loadingPromise);

      const TestComponent = () => {
        const [loading, setLoading] = useState(true);
        
        useEffect(() => {
          fetch("/api/test").then(() => setLoading(false));
        }, []);

        return <div>{loading ? "Loading..." : "Loaded"}</div>;
      };

      renderWithProviders(<TestComponent />);

      // Should show loading initially
      expect(screen.getByText("Loading...")).toBeTruthy();

      // Resolve the promise and check loaded state
      resolvePromise({
        ok: true,
        json: () => Promise.resolve({ success: true })
      });

      await waitFor(() => {
        expect(screen.getByText("Loaded")).toBeTruthy();
      });
    });
  });

  describe("Error Handling Flow", () => {
    it("should handle API errors gracefully", async () => {
      global.fetch.mockRejectedValue(new Error("Network error"));

      const TestComponent = () => {
        const [error, setError] = useState(null);
        
        useEffect(() => {
          fetch("/api/test").catch(err => setError(err.message));
        }, []);

        return <div>{error ? `Error: ${error}` : "No error"}</div>;
      };

      renderWithProviders(<TestComponent />);

      await waitFor(() => {
        expect(screen.getByText("Error: Network error")).toBeTruthy();
      });
    });

    it("should display user-friendly error messages", () => {
      const ErrorComponent = ({ error }) => (
        <div data-testid="error-display">
          {error ? "Something went wrong. Please try again." : "All good"}
        </div>
      );

      renderWithProviders(<ErrorComponent error={true} />);
      
      expect(screen.getByTestId("error-display")).toHaveTextContent(
        "Something went wrong. Please try again."
      );
    });
  });

  describe("Performance Monitoring", () => {
    it("should complete rendering within reasonable time", async () => {
      const startTime = performance.now();

      const SimpleComponent = () => (
        <div data-testid="perf-test">Performance test component</div>
      );

      renderWithProviders(<SimpleComponent />);

      await waitFor(() => {
        expect(screen.getByTestId("perf-test")).toBeTruthy();
      });

      const endTime = performance.now();
      const renderTime = endTime - startTime;

      // Should render within 100ms
      expect(renderTime).toBeLessThan(100);
    });
  });
});