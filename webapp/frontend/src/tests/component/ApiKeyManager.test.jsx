import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ApiKeyProvider } from "../../components/ApiKeyProvider";
import ApiKeyManager from "../../components/ApiKeyManager";

// Mock the API service
vi.mock("../../services/api", () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}));

// Mock AuthContext
const mockAuthContext = {
  user: { sub: "test-user", email: "test@example.com" },
  token: "mock-jwt-token",
  isAuthenticated: true,
};

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => mockAuthContext,
}));

// Import after mocking
import api from "../../services/api";

const renderWithProviders = (component) => {
  return render(<ApiKeyProvider>{component}</ApiKeyProvider>);
};

describe("ApiKeyManager Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Default API responses
    api.get.mockResolvedValue({
      data: {
        success: true,
        apiKeys: [],
      },
    });
  });

  describe("Initial Load", () => {
    it("should render the API key manager interface", async () => {
      renderWithProviders(<ApiKeyManager />);

      expect(screen.getByText(/API Keys/i)).toBeInTheDocument();
      expect(screen.getByText(/Add API Key/i)).toBeInTheDocument();
    });

    it("should load existing API keys on mount", async () => {
      const mockApiKeys = [
        {
          provider: "alpaca",
          hasApiKey: true,
          lastValidated: "2023-01-01T00:00:00Z",
          connectionStatus: "connected",
        },
      ];

      api.get.mockResolvedValue({
        data: {
          success: true,
          apiKeys: mockApiKeys,
        },
      });

      renderWithProviders(<ApiKeyManager />);

      await waitFor(() => {
        expect(screen.getByText(/alpaca/i)).toBeInTheDocument();
        expect(screen.getByText(/connected/i)).toBeInTheDocument();
      });

      expect(api.get).toHaveBeenCalledWith("/api/settings/api-keys");
    });
  });

  describe("Adding API Keys", () => {
    it("should show add API key form when Add button is clicked", async () => {
      renderWithProviders(<ApiKeyManager />);

      fireEvent.click(screen.getByText(/Add API Key/i));

      await waitFor(() => {
        expect(screen.getByLabelText(/Provider/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/API Key/i)).toBeInTheDocument();
      });
    });

    it("should successfully add a new API key", async () => {
      api.post.mockResolvedValue({
        data: {
          success: true,
          message: "API key stored successfully",
        },
      });

      renderWithProviders(<ApiKeyManager />);

      // Open add form
      fireEvent.click(screen.getByText(/Add API Key/i));

      await waitFor(() => {
        expect(screen.getByLabelText(/Provider/i)).toBeInTheDocument();
      });

      // Fill form
      fireEvent.change(screen.getByLabelText(/Provider/i), {
        target: { value: "alpaca" },
      });
      fireEvent.change(screen.getByLabelText(/API Key/i), {
        target: { value: "PKTEST_123" },
      });
      fireEvent.change(screen.getByLabelText(/API Secret/i), {
        target: { value: "secret123" },
      });

      // Submit form
      fireEvent.click(screen.getByText(/Save/i));

      await waitFor(() => {
        expect(api.post).toHaveBeenCalledWith("/api/settings/api-keys", {
          provider: "alpaca",
          apiKey: "PKTEST_123",
          apiSecret: "secret123",
          isSandbox: true,
        });
      });
    });

    it("should validate required fields", async () => {
      renderWithProviders(<ApiKeyManager />);

      fireEvent.click(screen.getByText(/Add API Key/i));

      await waitFor(() => {
        expect(screen.getByLabelText(/Provider/i)).toBeInTheDocument();
      });

      // Try to submit without required fields
      fireEvent.click(screen.getByText(/Save/i));

      await waitFor(() => {
        expect(screen.getByText(/Provider is required/i)).toBeInTheDocument();
        expect(screen.getByText(/API Key is required/i)).toBeInTheDocument();
      });

      expect(api.post).not.toHaveBeenCalled();
    });

    it("should handle API key storage errors", async () => {
      api.post.mockRejectedValue({
        response: {
          data: {
            success: false,
            error: "Invalid API key",
          },
        },
      });

      renderWithProviders(<ApiKeyManager />);

      fireEvent.click(screen.getByText(/Add API Key/i));

      await waitFor(() => {
        expect(screen.getByLabelText(/Provider/i)).toBeInTheDocument();
      });

      // Fill and submit form
      fireEvent.change(screen.getByLabelText(/Provider/i), {
        target: { value: "alpaca" },
      });
      fireEvent.change(screen.getByLabelText(/API Key/i), {
        target: { value: "INVALID_KEY" },
      });

      fireEvent.click(screen.getByText(/Save/i));

      await waitFor(() => {
        expect(screen.getByText(/Invalid API key/i)).toBeInTheDocument();
      });
    });
  });

  describe("API Key Validation", () => {
    it("should validate API key connection", async () => {
      const mockApiKeys = [
        {
          provider: "alpaca",
          hasApiKey: true,
          connectionStatus: "disconnected",
        },
      ];

      api.get.mockResolvedValue({
        data: { success: true, apiKeys: mockApiKeys },
      });

      api.post.mockResolvedValue({
        data: {
          success: true,
          data: { valid: true, account_id: "test-account" },
        },
      });

      renderWithProviders(<ApiKeyManager />);

      await waitFor(() => {
        expect(screen.getByText(/alpaca/i)).toBeInTheDocument();
      });

      // Click validate button
      fireEvent.click(screen.getByText(/Test Connection/i));

      await waitFor(() => {
        expect(api.post).toHaveBeenCalledWith(
          "/api/settings/api-keys/alpaca/validate"
        );
      });

      await waitFor(() => {
        expect(screen.getByText(/Connection successful/i)).toBeInTheDocument();
      });
    });

    it("should handle validation failures", async () => {
      const mockApiKeys = [
        {
          provider: "alpaca",
          hasApiKey: true,
          connectionStatus: "disconnected",
        },
      ];

      api.get.mockResolvedValue({
        data: { success: true, apiKeys: mockApiKeys },
      });

      api.post.mockRejectedValue({
        response: {
          data: {
            success: false,
            error: "Invalid credentials",
          },
        },
      });

      renderWithProviders(<ApiKeyManager />);

      await waitFor(() => {
        expect(screen.getByText(/alpaca/i)).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText(/Test Connection/i));

      await waitFor(() => {
        expect(screen.getByText(/Invalid credentials/i)).toBeInTheDocument();
      });
    });
  });

  describe("Deleting API Keys", () => {
    it("should delete API key when delete button is clicked", async () => {
      const mockApiKeys = [
        {
          provider: "alpaca",
          hasApiKey: true,
          connectionStatus: "connected",
        },
      ];

      api.get.mockResolvedValue({
        data: { success: true, apiKeys: mockApiKeys },
      });

      api.delete.mockResolvedValue({
        data: { success: true, message: "API key deleted" },
      });

      renderWithProviders(<ApiKeyManager />);

      await waitFor(() => {
        expect(screen.getByText(/alpaca/i)).toBeInTheDocument();
      });

      // Click delete button
      fireEvent.click(screen.getByText(/Delete/i));

      // Confirm deletion
      await waitFor(() => {
        expect(screen.getByText(/Are you sure/i)).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText(/Confirm/i));

      await waitFor(() => {
        expect(api.delete).toHaveBeenCalledWith(
          "/api/settings/api-keys/alpaca"
        );
      });
    });

    it("should handle delete errors gracefully", async () => {
      const mockApiKeys = [
        {
          provider: "alpaca",
          hasApiKey: true,
          connectionStatus: "connected",
        },
      ];

      api.get.mockResolvedValue({
        data: { success: true, apiKeys: mockApiKeys },
      });

      api.delete.mockRejectedValue({
        response: {
          data: {
            success: false,
            error: "Delete failed",
          },
        },
      });

      renderWithProviders(<ApiKeyManager />);

      await waitFor(() => {
        expect(screen.getByText(/alpaca/i)).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText(/Delete/i));

      await waitFor(() => {
        expect(screen.getByText(/Are you sure/i)).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText(/Confirm/i));

      await waitFor(() => {
        expect(screen.getByText(/Delete failed/i)).toBeInTheDocument();
      });
    });
  });

  describe("Provider Selection", () => {
    it("should support all major financial data providers", async () => {
      renderWithProviders(<ApiKeyManager />);

      fireEvent.click(screen.getByText(/Add API Key/i));

      await waitFor(() => {
        expect(screen.getByLabelText(/Provider/i)).toBeInTheDocument();
      });

      const _providerSelect = screen.getByLabelText(/Provider/i);

      // Check that major providers are available
      expect(screen.getByDisplayValue("alpaca")).toBeInTheDocument();
      expect(screen.getByDisplayValue("polygon")).toBeInTheDocument();
      expect(screen.getByDisplayValue("finnhub")).toBeInTheDocument();
    });

    it("should show provider-specific fields", async () => {
      renderWithProviders(<ApiKeyManager />);

      fireEvent.click(screen.getByText(/Add API Key/i));

      await waitFor(() => {
        expect(screen.getByLabelText(/Provider/i)).toBeInTheDocument();
      });

      // Select Alpaca
      fireEvent.change(screen.getByLabelText(/Provider/i), {
        target: { value: "alpaca" },
      });

      await waitFor(() => {
        expect(screen.getByText(/Sandbox Mode/i)).toBeInTheDocument();
      });
    });
  });

  describe("Loading States", () => {
    it("should show loading state while fetching API keys", async () => {
      // Mock delayed response
      api.get.mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  data: { success: true, apiKeys: [] },
                }),
              100
            )
          )
      );

      renderWithProviders(<ApiKeyManager />);

      expect(screen.getByText(/Loading/i)).toBeInTheDocument();

      await waitFor(
        () => {
          expect(screen.queryByText(/Loading/i)).not.toBeInTheDocument();
        },
        { timeout: 200 }
      );
    });

    it("should show loading state while saving API key", async () => {
      api.post.mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  data: { success: true, message: "Saved" },
                }),
              100
            )
          )
      );

      renderWithProviders(<ApiKeyManager />);

      fireEvent.click(screen.getByText(/Add API Key/i));

      await waitFor(() => {
        expect(screen.getByLabelText(/Provider/i)).toBeInTheDocument();
      });

      fireEvent.change(screen.getByLabelText(/Provider/i), {
        target: { value: "alpaca" },
      });
      fireEvent.change(screen.getByLabelText(/API Key/i), {
        target: { value: "TEST123" },
      });

      fireEvent.click(screen.getByText(/Save/i));

      expect(screen.getByText(/Saving/i)).toBeInTheDocument();

      await waitFor(
        () => {
          expect(screen.queryByText(/Saving/i)).not.toBeInTheDocument();
        },
        { timeout: 200 }
      );
    });
  });

  describe("Error Handling", () => {
    it("should handle network errors gracefully", async () => {
      api.get.mockRejectedValue(new Error("Network error"));

      renderWithProviders(<ApiKeyManager />);

      await waitFor(() => {
        expect(
          screen.getByText(/Failed to load API keys/i)
        ).toBeInTheDocument();
      });
    });

    it("should provide retry functionality", async () => {
      api.get
        .mockRejectedValueOnce(new Error("Network error"))
        .mockResolvedValue({
          data: { success: true, apiKeys: [] },
        });

      renderWithProviders(<ApiKeyManager />);

      await waitFor(() => {
        expect(
          screen.getByText(/Failed to load API keys/i)
        ).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText(/Retry/i));

      await waitFor(() => {
        expect(screen.getByText(/Add API Key/i)).toBeInTheDocument();
      });

      expect(api.get).toHaveBeenCalledTimes(2);
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA labels", async () => {
      renderWithProviders(<ApiKeyManager />);

      fireEvent.click(screen.getByText(/Add API Key/i));

      await waitFor(() => {
        expect(screen.getByLabelText(/Provider/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/API Key/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/API Secret/i)).toBeInTheDocument();
      });

      // Check ARIA attributes
      expect(screen.getByLabelText(/Provider/i)).toHaveAttribute(
        "aria-required",
        "true"
      );
      expect(screen.getByLabelText(/API Key/i)).toHaveAttribute(
        "aria-required",
        "true"
      );
    });

    it("should be keyboard navigable", async () => {
      renderWithProviders(<ApiKeyManager />);

      // Focus the add button
      screen.getByText(/Add API Key/i).focus();
      expect(screen.getByText(/Add API Key/i)).toHaveFocus();

      // Press Enter to activate
      fireEvent.keyDown(screen.getByText(/Add API Key/i), { key: "Enter" });

      await waitFor(() => {
        expect(screen.getByLabelText(/Provider/i)).toBeInTheDocument();
      });
    });
  });
});
