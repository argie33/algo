import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import ApiKeysTab from "../../../components/settings/ApiKeysTab.jsx";
import { useAuth } from "../../../contexts/AuthContext.jsx";

// Mock the API config
vi.mock("../../../services/api.js", () => ({
  getApiConfig: () => ({
    apiUrl: "http://localhost:3001",
  }),
}));

// Mock AuthContext - This is the key fix!
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(),
}));

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock window.confirm
global.confirm = vi.fn();

describe("ApiKeysTab - Fixed Authentication Tests", () => {
  const mockApiKeys = [
    {
      id: "alpaca-123",
      provider: "alpaca",
      keyId: "PKTEST123456",
      apiKey: "PKTEST123456",
      isActive: true,
      isSandbox: true,
    },
  ];

  const mockAuthenticatedUser = {
    user: {
      id: "user-123",
      username: "testuser",
      email: "test@example.com",
    },
    tokens: {
      accessToken: "valid-cognito-jwt-token",
      idToken: "valid-id-token",
    },
  };

  const mockUnauthenticatedUser = {
    user: null,
    tokens: null,
  };

  beforeEach(() => {
    mockFetch.mockClear();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  const renderApiKeysTab = () => {
    return render(
      <BrowserRouter>
        <ApiKeysTab />
      </BrowserRouter>
    );
  };

  describe("Authentication Integration - AuthContext", () => {
    it("should include Authorization header when user is authenticated via AuthContext", async () => {
      // Mock authenticated user with AuthContext
      vi.mocked(useAuth).mockReturnValue(mockAuthenticatedUser);

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: [] }),
      });

      renderApiKeysTab();

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:3001/api/settings/api-keys",
          expect.objectContaining({
            headers: expect.objectContaining({
              "Content-Type": "application/json",
              Authorization: "Bearer valid-cognito-jwt-token",
            }),
          })
        );
      });
    });

    it("should NOT include Authorization header when user is not authenticated", async () => {
      // Mock unauthenticated user
      vi.mocked(useAuth).mockReturnValue(mockUnauthenticatedUser);

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: [] }),
      });

      renderApiKeysTab();

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:3001/api/settings/api-keys",
          expect.objectContaining({
            headers: expect.objectContaining({
              "Content-Type": "application/json",
            }),
          })
        );

        // Verify NO Authorization header
        const fetchCall = mockFetch.mock.calls[0];
        expect(fetchCall[1].headers).not.toHaveProperty("Authorization");
      });
    });

    it("should handle missing tokens gracefully (user logged in but tokens expired)", async () => {
      // User exists but tokens are missing/expired
      vi.mocked(useAuth).mockReturnValue({
        user: mockAuthenticatedUser.user,
        tokens: null,
      });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: [] }),
      });

      renderApiKeysTab();

      await waitFor(() => {
        const fetchCall = mockFetch.mock.calls[0];
        expect(fetchCall[1].headers).not.toHaveProperty("Authorization");
      });
    });
  });

  describe("API Operations with Authentication", () => {
    beforeEach(() => {
      // Default to authenticated user for API operation tests
      vi.mocked(useAuth).mockReturnValue(mockAuthenticatedUser);
    });

    it("should include auth token when adding API key", async () => {
      // Initial load
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: [] }),
      });

      renderApiKeysTab();

      await waitFor(() => {
        expect(screen.getByText("Add API Key")).toBeInTheDocument();
      });

      // Open add dialog (click the first Add API Key button)
      fireEvent.click(screen.getAllByText("Add API Key")[0]);

      // Fill form
      fireEvent.change(screen.getByLabelText("API Key"), {
        target: { value: "new-api-key-123" },
      });

      // Handle MUI Select for Provider
      const providerSelect = screen.getByRole("combobox");
      fireEvent.mouseDown(providerSelect);
      fireEvent.click(screen.getByText("Alpaca Trading"));

      fireEvent.change(screen.getByLabelText("API Secret"), {
        target: { value: "new-secret-123" },
      });

      // Mock add API response
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      // Submit
      fireEvent.click(screen.getByRole("button", { name: "Add API Key" }));

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:3001/api/settings/api-keys",
          expect.objectContaining({
            method: "POST",
            headers: expect.objectContaining({
              "Content-Type": "application/json",
              Authorization: "Bearer valid-cognito-jwt-token",
            }),
            body: JSON.stringify({
              provider: "alpaca",
              apiKey: "new-api-key-123",
              apiSecret: "new-secret-123",
              isSandbox: true,
              isActive: true,
            }),
          })
        );
      });
    });

    it("should include auth token when updating API key", async () => {
      // Load existing API keys
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: mockApiKeys }),
      });

      renderApiKeysTab();

      await waitFor(() => {
        expect(screen.getByText("alpaca")).toBeInTheDocument();
      });

      // Open edit dialog
      const editButtons = screen.getAllByTitle("Edit");
      fireEvent.click(editButtons[0]);

      // Mock update response
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      // Submit update
      fireEvent.click(screen.getByRole("button", { name: "Update API Key" }));

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:3001/api/settings/api-keys/alpaca-123",
          expect.objectContaining({
            method: "PUT",
            headers: expect.objectContaining({
              "Content-Type": "application/json",
              Authorization: "Bearer valid-cognito-jwt-token",
            }),
          })
        );
      });
    });

    it("should include auth token when deleting API key", async () => {
      global.confirm.mockReturnValue(true);

      // Load existing API keys
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: mockApiKeys }),
      });

      renderApiKeysTab();

      await waitFor(() => {
        expect(screen.getByText("alpaca")).toBeInTheDocument();
      });

      // Mock delete response
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true }),
      });

      // Click delete
      const deleteButtons = screen.getAllByTitle("Delete");
      fireEvent.click(deleteButtons[0]);

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:3001/api/settings/api-keys/alpaca-123",
          expect.objectContaining({
            method: "DELETE",
            headers: expect.objectContaining({
              "Content-Type": "application/json",
              Authorization: "Bearer valid-cognito-jwt-token",
            }),
          })
        );
      });
    });

    it("should include auth token when testing connection", async () => {
      // Load existing API keys
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data: mockApiKeys }),
      });

      renderApiKeysTab();

      await waitFor(() => {
        expect(screen.getByText("alpaca")).toBeInTheDocument();
      });

      // Mock test connection response
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ message: "Connection successful" }),
      });

      // Click test connection
      const testButtons = screen.getAllByTitle("Test Connection");
      fireEvent.click(testButtons[0]);

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          "http://localhost:3001/api/settings/test-connection/alpaca-123",
          expect.objectContaining({
            method: "POST",
            headers: expect.objectContaining({
              "Content-Type": "application/json",
              Authorization: "Bearer valid-cognito-jwt-token",
            }),
          })
        );
      });
    });
  });

  describe("Error Scenarios", () => {
    it("should handle 401 Unauthorized properly", async () => {
      vi.mocked(useAuth).mockReturnValue(mockAuthenticatedUser);

      // Mock 401 response
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ error: "Unauthorized" }),
      });

      renderApiKeysTab();

      await waitFor(() => {
        expect(screen.getByText("Unauthorized")).toBeInTheDocument();
      });
    });

    it("should show helpful message when not authenticated", async () => {
      vi.mocked(useAuth).mockReturnValue(mockUnauthenticatedUser);

      // Component should still work but without auth headers
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ error: "Authentication required" }),
      });

      renderApiKeysTab();

      await waitFor(() => {
        expect(screen.getByText("Authentication required")).toBeInTheDocument();
      });
    });
  });
});
