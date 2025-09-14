/**
 * API Key and Portfolio Import Integration Tests
 * Tests the complete workflow from API key management to portfolio import
 */

import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
} from "@testing-library/react";
import { vi, describe, test, expect, beforeEach, afterEach } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import Settings from "../../pages/Settings";
import Portfolio from "../../pages/Portfolio";
import * as api from "../../services/api";

// Mock the API functions
vi.mock("../../services/api", () => ({
  getApiConfig: vi.fn(() => ({
    baseURL: "http://localhost:3001",
    apiUrl: "http://localhost:3001",
    isDevelopment: true,
  })),
  getApiKeys: vi.fn(),
  testApiConnection: vi.fn(),
  importPortfolioFromBroker: vi.fn(),
}));

// Mock useAuth hook
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: "test-user",
      email: "test@example.com",
      firstName: "Test",
      lastName: "User",
      tokens: { accessToken: "test-token" },
    },
    isAuthenticated: true,
    isLoading: false,
    logout: vi.fn(),
    checkAuthState: vi.fn(),
  }),
}));

// Mock fetch for Settings API calls
global.fetch = vi.fn();

const TestWrapper = ({ children }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

  return (
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </BrowserRouter>
  );
};

describe("API Key and Portfolio Import Integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Mock successful API responses by default with immediate resolution
    global.fetch.mockImplementation(async (url) => {
      // Handle different API endpoints
      if (url.includes("/api/portfolio/api-keys")) {
        return {
          ok: true,
          json: async () => ({ data: [] }),
        };
      }
      if (url.includes("/api/portfolio/holdings")) {
        return {
          ok: true,
          json: async () => ({
            data: {
              holdings: [],
              summary: {
                totalValue: 0,
                totalPnL: 0,
                totalPnLPercent: 0,
              },
            },
          }),
        };
      }
      // Default response for any other API calls
      return {
        ok: true,
        json: async () => ({ data: [] }),
      };
    });
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  describe("API Key Management Workflow", () => {
    test("should add API key and display it in settings", async () => {
      // Mock API key creation and retrieval
      global.fetch
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ success: true }),
        }) // POST /api/portfolio/api-keys
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            data: [
              {
                brokerName: "alpaca",
                createdAt: "2025-01-15T00:00:00Z",
                status: "active",
                sandbox: true,
              },
            ],
          }),
        }); // GET /api/portfolio/api-keys

      await act(async () => {
        render(
          <TestWrapper>
            <Settings />
          </TestWrapper>
        );
      });

      // Wait for the component to finish loading and render the UI
      await waitFor(
        () => {
          expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
        },
        { timeout: 5000 }
      );

      // Wait for the API Keys tab to be available
      await waitFor(() => {
        expect(screen.getByTestId("api-keys-tab")).toBeInTheDocument();
      });

      // Navigate to API Keys tab
      fireEvent.click(screen.getByTestId("api-keys-tab"));

      // Add API key
      fireEvent.click(screen.getByTestId("add-api-key-button"));

      // Wait for the add API key dialog to open
      await waitFor(() => {
        expect(screen.getByText("Add Broker API Key")).toBeInTheDocument();
      });

      // Fill in API key form
      // For MUI Select, we need to click to open the dropdown and then select the option
      const brokerSelect = screen.getByLabelText(/broker/i);
      fireEvent.mouseDown(brokerSelect);

      // Wait for the dropdown to open and click on Alpaca option
      await waitFor(() => {
        const alpacaOption = screen.getByRole("option", { name: /alpaca/i });
        expect(alpacaOption).toBeInTheDocument();
        fireEvent.click(alpacaOption);
      });

      // Fill in text fields normally
      fireEvent.change(screen.getByTestId("api-key-input"), {
        target: { value: "test-api-key" },
      });
      fireEvent.change(screen.getByLabelText(/api secret/i), {
        target: { value: "test-secret" },
      });

      // Submit the form
      fireEvent.click(screen.getByLabelText("Add new API key"));

      // Wait for success message
      await waitFor(() => {
        expect(
          screen.getByText(/api key added successfully/i)
        ).toBeInTheDocument();
      });

      // Verify API key appears in the list
      await waitFor(() => {
        expect(screen.getByText("Alpaca")).toBeInTheDocument();
        expect(screen.getByText(/Added: 1\/15\/2025/)).toBeInTheDocument();
      });
    });

    test("should handle API key creation errors", async () => {
      // Mock API error
      global.fetch.mockResolvedValueOnce({
        ok: false,
        json: async () => ({ error: "Invalid API credentials" }),
      });

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      fireEvent.click(screen.getByTestId("api-keys-tab"));
      fireEvent.click(screen.getByTestId("add-api-key-button"));

      // Fill minimal form
      fireEvent.change(screen.getByLabelText(/broker/i), {
        target: { value: "alpaca" },
      });
      fireEvent.change(screen.getByTestId("api-key-input"), {
        target: { value: "invalid-key" },
      });

      fireEvent.click(screen.getByLabelText("Add new API key"));

      await waitFor(() => {
        expect(
          screen.getByText(/invalid api credentials/i)
        ).toBeInTheDocument();
      });
    });
  });

  describe("Portfolio Import Integration", () => {
    test("should show available API keys in portfolio import dialog", async () => {
      // Mock API keys response
      api.getApiKeys.mockResolvedValue({
        apiKeys: [
          {
            brokerName: "alpaca",
            createdAt: "2025-01-15T00:00:00Z",
            status: "active",
            sandbox: true,
          },
        ],
      });

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Open portfolio import dialog
      const importButton = screen.getByText(/import portfolio/i);
      fireEvent.click(importButton);

      // Wait for API keys to load
      await waitFor(() => {
        expect(screen.getByText("Alpaca")).toBeInTheDocument();
        expect(screen.getByText(/Paper/)).toBeInTheDocument(); // Sandbox mode
      });

      // Verify test and import buttons are present
      expect(screen.getByText("Test")).toBeInTheDocument();
      expect(screen.getByText("Import")).toBeInTheDocument();
    });

    test("should handle API connection testing", async () => {
      // Mock API keys and test connection
      api.getApiKeys.mockResolvedValue({
        apiKeys: [
          {
            brokerName: "alpaca",
            createdAt: "2025-01-15T00:00:00Z",
            status: "active",
            sandbox: true,
          },
        ],
      });

      api.testApiConnection.mockResolvedValue({
        success: true,
        connection: {
          valid: true,
          accountInfo: {
            accountId: "TEST123",
            portfolioValue: 10000,
            environment: "paper",
          },
        },
      });

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      fireEvent.click(screen.getByText(/import portfolio/i));

      await waitFor(() => {
        expect(screen.getByText("Alpaca")).toBeInTheDocument();
      });

      // Test connection
      fireEvent.click(screen.getByText("Test"));

      await waitFor(() => {
        expect(screen.getByText(/connection successful/i)).toBeInTheDocument();
        expect(screen.getByText(/TEST123/)).toBeInTheDocument();
        expect(screen.getByText(/\$10,000/)).toBeInTheDocument();
      });
    });

    test("should handle portfolio import", async () => {
      // Mock API keys and import
      api.getApiKeys.mockResolvedValue({
        apiKeys: [
          {
            brokerName: "alpaca",
            createdAt: "2025-01-15T00:00:00Z",
            status: "active",
            sandbox: true,
          },
        ],
      });

      api.importPortfolioFromBroker.mockResolvedValue({
        success: true,
        data: {
          summary: {
            positions: 5,
            totalValue: 25000,
            totalPnL: 2500,
            totalPnLPercent: 11.11,
          },
        },
      });

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      fireEvent.click(screen.getByText(/import portfolio/i));

      await waitFor(() => {
        expect(screen.getByText("Alpaca")).toBeInTheDocument();
      });

      // Import portfolio
      fireEvent.click(screen.getByText("Import"));

      await waitFor(() => {
        expect(
          screen.getByText(/portfolio imported successfully/i)
        ).toBeInTheDocument();
        expect(screen.getByText(/5 positions/)).toBeInTheDocument();
        expect(screen.getByText(/\$25,000/)).toBeInTheDocument();
      });
    });

    test("should show no connections message when no API keys exist", async () => {
      // Mock empty API keys response
      api.getApiKeys.mockResolvedValue({
        apiKeys: [],
      });

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      fireEvent.click(screen.getByText(/import portfolio/i));

      await waitFor(() => {
        expect(
          screen.getByText(/no broker connections found/i)
        ).toBeInTheDocument();
        expect(screen.getByText(/go to settings/i)).toBeInTheDocument();
      });
    });

    test("should filter to only show supported brokers", async () => {
      // Mock API keys with mixed brokers
      api.getApiKeys.mockResolvedValue({
        apiKeys: [
          { brokerName: "alpaca", status: "active" },
          { brokerName: "robinhood", status: "active" },
          { brokerName: "unsupported-broker", status: "active" },
        ],
      });

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      fireEvent.click(screen.getByText(/import portfolio/i));

      await waitFor(() => {
        expect(screen.getByText("Alpaca")).toBeInTheDocument();
        expect(screen.getByText("Robinhood")).toBeInTheDocument();
        expect(
          screen.queryByText("Unsupported-broker")
        ).not.toBeInTheDocument();
      });
    });
  });

  describe("End-to-End Integration", () => {
    test("should complete full workflow: add API key → test connection → import portfolio", async () => {
      // Mock API responses for the complete workflow

      global.fetch
        .mockImplementationOnce(async () => ({
          // Initial load - empty
          ok: true,
          json: async () => ({ data: [] }),
        }))
        .mockImplementationOnce(async () => ({
          // Add API key
          ok: true,
          json: async () => ({ success: true }),
        }))
        .mockImplementationOnce(async () => ({
          // Reload after add
          ok: true,
          json: async () => ({
            data: [
              {
                brokerName: "alpaca",
                createdAt: "2025-01-15T00:00:00Z",
                status: "active",
                sandbox: true,
              },
            ],
          }),
        }));

      api.getApiKeys.mockResolvedValue({
        apiKeys: [
          {
            brokerName: "alpaca",
            createdAt: "2025-01-15T00:00:00Z",
            status: "active",
            sandbox: true,
          },
        ],
      });

      api.testApiConnection.mockResolvedValue({
        success: true,
        connection: { valid: true, accountInfo: { accountId: "TEST123" } },
      });

      api.importPortfolioFromBroker.mockResolvedValue({
        success: true,
        data: { summary: { positions: 3, totalValue: 15000 } },
      });

      // Start with Settings page
      const { rerender } = render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      // Add API key
      fireEvent.click(screen.getByTestId("api-keys-tab"));
      fireEvent.click(screen.getByTestId("add-api-key-button"));

      fireEvent.change(screen.getByLabelText(/broker/i), {
        target: { value: "alpaca" },
      });
      fireEvent.change(screen.getByTestId("api-key-input"), {
        target: { value: "test-key" },
      });
      fireEvent.change(screen.getByLabelText(/api secret/i), {
        target: { value: "test-secret" },
      });

      fireEvent.click(screen.getByLabelText("Add new API key"));

      await waitFor(() => {
        expect(
          screen.getByText(/api key added successfully/i)
        ).toBeInTheDocument();
      });

      // Switch to Portfolio page
      rerender(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Open import dialog
      fireEvent.click(screen.getByText(/import portfolio/i));

      await waitFor(() => {
        expect(screen.getByText("Alpaca")).toBeInTheDocument();
      });

      // Test connection
      fireEvent.click(screen.getByText("Test"));

      await waitFor(() => {
        expect(screen.getByText(/connection successful/i)).toBeInTheDocument();
      });

      // Import portfolio
      fireEvent.click(screen.getByText("Import"));

      await waitFor(() => {
        expect(
          screen.getByText(/portfolio imported successfully/i)
        ).toBeInTheDocument();
      });
    });
  });
});
