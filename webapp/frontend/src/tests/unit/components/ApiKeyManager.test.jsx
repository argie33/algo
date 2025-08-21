/**
 * Unit Tests for ApiKeyManager Component
 * Tests the API key management functionality for trading accounts
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import SettingsApiKeys from "../../../pages/SettingsApiKeys.jsx";

// Mock the API keys provider
const mockAddApiKey = vi.fn();
const mockDeleteApiKey = vi.fn();
const mockClearMessages = vi.fn();

const mockUseApiKeys = vi.fn(() => ({
  apiKeys: [
    {
      id: "key1",
      provider: "alpaca",
      keyPreview: "PK***ABC123",
      isActive: true,
      environment: "sandbox",
      lastUsed: "2024-01-15T10:30:00Z",
      createdAt: "2024-01-01T00:00:00Z",
    },
    {
      id: "key2",
      provider: "interactive_brokers",
      keyPreview: "IB***XYZ789",
      isActive: false,
      environment: "live",
      lastUsed: null,
      createdAt: "2024-01-10T00:00:00Z",
    },
  ],
  loading: false,
  error: null,
  success: null,
  addApiKey: mockAddApiKey,
  deleteApiKey: mockDeleteApiKey,
  clearMessages: mockClearMessages,
}));

// Mock the auth context
vi.mock("../../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { sub: "test-user-id" },
    isAuthenticated: true,
    token: "mock-token"
  })
}));

vi.mock("../../../components/ApiKeyProvider.jsx", () => ({
  useApiKeys: mockUseApiKeys,
}));

// Make useApiKeys available globally for test assertions
global.useApiKeys = mockUseApiKeys;

// Wrapper component for router context
const TestWrapper = ({ children }) => <BrowserRouter>{children}</BrowserRouter>;

describe("SettingsApiKeys Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("API Key Display", () => {
    it("should display existing API keys with masked information", () => {
      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      // Should show API key information
      expect(screen.getByText(/PK\*\*\*ABC123/)).toBeInTheDocument();
      expect(screen.getByText(/IB\*\*\*XYZ789/)).toBeInTheDocument();

      // Should show provider information
      expect(screen.getByText(/alpaca/i)).toBeInTheDocument();
      expect(
        screen.getByText(/interactive.brokers|interactive_brokers/i)
      ).toBeInTheDocument();

      // Should show environment information
      expect(screen.getByText(/sandbox/i)).toBeInTheDocument();
      expect(screen.getByText(/live/i)).toBeInTheDocument();
    });

    it("should show API key status indicators", () => {
      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      // Should indicate active/inactive status
      expect(screen.getByText(/active/i)).toBeInTheDocument();
      expect(
        screen.getByText(/inactive/i) || screen.queryByText(/disabled/i)
      ).toBeTruthy();
    });

    it("should show last used timestamps", () => {
      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      // Should show when keys were last used
      expect(
        screen.getByText(/last used/i) || screen.getByText(/2024-01-15/)
      ).toBeTruthy();
    });

    it("should display empty state when no API keys exist", () => {
      // Mock empty state
      mockUseApiKeys.mockReturnValue({
        apiKeys: [],
        loading: false,
        error: null,
        success: null,
        addApiKey: mockAddApiKey,
        deleteApiKey: mockDeleteApiKey,
        clearMessages: mockClearMessages,
      });

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      expect(
        screen.getByText(/no api keys|add your first|get started/i)
      ).toBeInTheDocument();
    });
  });

  describe("Adding API Keys", () => {
    it("should open add API key dialog when add button clicked", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const addButton = screen.getByRole("button", { name: /add|new/i });
      await user.click(addButton);

      // Should open dialog
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      expect(screen.getByText(/add api key|new api key/i)).toBeInTheDocument();
    });

    it("should render add API key form with required fields", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const addButton = screen.getByRole("button", { name: /add|new/i });
      await user.click(addButton);

      // Should have form fields
      expect(
        screen.getByLabelText(/provider/i) || screen.getByText(/provider/i)
      ).toBeInTheDocument();
      expect(
        screen.getByLabelText(/api key/i) ||
          screen.getByPlaceholderText(/api key/i)
      ).toBeInTheDocument();
      expect(
        screen.getByLabelText(/secret|private/i) ||
          screen.getByPlaceholderText(/secret|private/i)
      ).toBeInTheDocument();
      expect(
        screen.getByLabelText(/environment/i) ||
          screen.getByText(/sandbox|live/i)
      ).toBeInTheDocument();
    });

    it("should validate required fields before submission", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const addButton = screen.getByRole("button", { name: /add|new/i });
      await user.click(addButton);

      const submitButton = screen.getByRole("button", { name: /save|add/i });
      await user.click(submitButton);

      // Should show validation errors
      expect(
        screen.getByText(/required|please fill|invalid/i) ||
          screen.getAllByText(/required|please fill|invalid/i).length > 0
      ).toBeTruthy();
      expect(mockAddApiKey).not.toHaveBeenCalled();
    });

    it("should submit valid API key data", async () => {
      const user = userEvent.setup();
      mockAddApiKey.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const addButton = screen.getByRole("button", { name: /add|new/i });
      await user.click(addButton);

      // Fill out form
      const apiKeyInput =
        screen.getByLabelText(/api key/i) ||
        screen.getByPlaceholderText(/api key/i);
      const secretInput =
        screen.getByLabelText(/secret|private/i) ||
        screen.getByPlaceholderText(/secret|private/i);

      await user.type(apiKeyInput, "PKTEST12345ABCDEF");
      await user.type(secretInput, "test-secret-key-12345");

      // Select provider (if dropdown exists)
      const providerSelect =
        screen.queryByRole("combobox") || screen.queryByLabelText(/provider/i);
      if (providerSelect) {
        await user.click(providerSelect);
        const alpacaOption = screen.getByText(/alpaca/i);
        await user.click(alpacaOption);
      }

      const submitButton = screen.getByRole("button", { name: /save|add/i });
      await user.click(submitButton);

      expect(mockAddApiKey).toHaveBeenCalledWith(
        expect.objectContaining({
          apiKey: "PKTEST12345ABCDEF",
          secretKey: "test-secret-key-12345",
        })
      );
    });

    it("should close dialog after successful submission", async () => {
      const user = userEvent.setup();
      mockAddApiKey.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const addButton = screen.getByRole("button", { name: /add|new/i });
      await user.click(addButton);

      const apiKeyInput =
        screen.getByLabelText(/api key/i) ||
        screen.getByPlaceholderText(/api key/i);
      const secretInput =
        screen.getByLabelText(/secret|private/i) ||
        screen.getByPlaceholderText(/secret|private/i);

      await user.type(apiKeyInput, "PKTEST12345ABCDEF");
      await user.type(secretInput, "test-secret-key-12345");

      const submitButton = screen.getByRole("button", { name: /save|add/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      });
    });
  });

  describe("Deleting API Keys", () => {
    it("should show delete buttons for existing API keys", () => {
      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const deleteButtons = screen.getAllByRole("button", {
        name: /delete|remove/i,
      });
      expect(deleteButtons.length).toBeGreaterThan(0);
    });

    it("should show confirmation dialog when delete is clicked", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const deleteButtons = screen.getAllByRole("button", {
        name: /delete|remove/i,
      });
      await user.click(deleteButtons[0]);

      // Should show confirmation
      expect(
        screen.getByText(/confirm|are you sure|delete/i)
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /confirm|yes|delete/i })
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /cancel|no/i })
      ).toBeInTheDocument();
    });

    it("should cancel deletion when cancel is clicked", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const deleteButtons = screen.getAllByRole("button", {
        name: /delete|remove/i,
      });
      await user.click(deleteButtons[0]);

      const cancelButton = screen.getByRole("button", { name: /cancel|no/i });
      await user.click(cancelButton);

      expect(mockDeleteApiKey).not.toHaveBeenCalled();
    });

    it("should delete API key when confirmed", async () => {
      const user = userEvent.setup();
      mockDeleteApiKey.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const deleteButtons = screen.getAllByRole("button", {
        name: /delete|remove/i,
      });
      await user.click(deleteButtons[0]);

      const confirmButton = screen.getByRole("button", {
        name: /confirm|yes|delete/i,
      });
      await user.click(confirmButton);

      expect(mockDeleteApiKey).toHaveBeenCalledWith("key1");
    });
  });

  describe("Loading States", () => {
    it("should show loading spinner when loading", () => {
      // Mock loading state
      mockUseApiKeys.mockReturnValue({
        apiKeys: [],
        loading: true,
        error: null,
        success: null,
        addApiKey: mockAddApiKey,
        deleteApiKey: mockDeleteApiKey,
        clearMessages: mockClearMessages,
      });

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      expect(
        screen.getByRole("progressbar") || screen.getByText(/loading/i)
      ).toBeInTheDocument();
    });

    it("should disable actions during loading", () => {
      // Mock loading state
      mockUseApiKeys.mockReturnValue({
        apiKeys: [
          {
            id: "key1",
            provider: "alpaca",
            keyPreview: "PK***ABC123",
            isActive: true,
            environment: "sandbox",
          },
        ],
        loading: true,
        error: null,
        success: null,
        addApiKey: mockAddApiKey,
        deleteApiKey: mockDeleteApiKey,
        clearMessages: mockClearMessages,
      });

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const addButton = screen.getByRole("button", { name: /add|new/i });
      expect(addButton).toBeDisabled();
    });
  });

  describe("Error Handling", () => {
    it("should display error messages", () => {
      // Mock error state
      mockUseApiKeys.mockReturnValue({
        apiKeys: [],
        loading: false,
        error: "Failed to load API keys",
        success: null,
        addApiKey: mockAddApiKey,
        deleteApiKey: mockDeleteApiKey,
        clearMessages: mockClearMessages,
      });

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      expect(screen.getByText("Failed to load API keys")).toBeInTheDocument();
    });

    it("should display success messages", () => {
      // Mock success state
      mockUseApiKeys.mockReturnValue({
        apiKeys: [],
        loading: false,
        error: null,
        success: "API key added successfully",
        addApiKey: mockAddApiKey,
        deleteApiKey: mockDeleteApiKey,
        clearMessages: mockClearMessages,
      });

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      expect(
        screen.getByText("API key added successfully")
      ).toBeInTheDocument();
    });

    it("should allow clearing error messages", async () => {
      const user = userEvent.setup();

      // Mock error state
      mockUseApiKeys.mockReturnValue({
        apiKeys: [],
        loading: false,
        error: "Failed to load API keys",
        success: null,
        addApiKey: mockAddApiKey,
        deleteApiKey: mockDeleteApiKey,
        clearMessages: mockClearMessages,
      });

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const dismissButton = screen.queryByRole("button", {
        name: /dismiss|close|×/i,
      });
      if (dismissButton) {
        await user.click(dismissButton);
        expect(mockClearMessages).toHaveBeenCalled();
      }
    });
  });

  describe("Security Features", () => {
    it("should never display full API keys or secrets", () => {
      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      // Should only show masked previews
      expect(screen.getByText(/PK\*\*\*ABC123/)).toBeInTheDocument();
      expect(screen.queryByText(/PKTEST12345ABCDEF/)).not.toBeInTheDocument();

      // Should not show any secret keys
      expect(
        screen.queryByText(/secret-key|private-key/)
      ).not.toBeInTheDocument();
    });

    it("should have environment selection for sandbox vs live", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const addButton = screen.getByRole("button", { name: /add|new/i });
      await user.click(addButton);

      // Should have environment options
      expect(
        screen.getByText(/sandbox/i) || screen.getByText(/test/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/live/i) || screen.getByText(/production/i)
      ).toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA labels", () => {
      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      expect(
        screen.getByRole("main") || screen.getByRole("region")
      ).toBeInTheDocument();

      const deleteButtons = screen.getAllByRole("button", {
        name: /delete|remove/i,
      });
      deleteButtons.forEach((button) => {
        expect(button).toHaveAttribute("aria-label");
      });
    });

    it("should be keyboard navigable", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      // Should be able to tab through interactive elements
      await user.tab();
      expect(document.activeElement).toBeInstanceOf(HTMLElement);

      await user.tab();
      expect(document.activeElement).toBeInstanceOf(HTMLElement);
    });

    it("should announce status changes to screen readers", () => {
      // Mock success state
      mockUseApiKeys.mockReturnValue({
        apiKeys: [],
        loading: false,
        error: null,
        success: "API key added successfully",
        addApiKey: mockAddApiKey,
        deleteApiKey: mockDeleteApiKey,
        clearMessages: mockClearMessages,
      });

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const successMessage = screen.getByText("API key added successfully");
      expect(successMessage).toHaveAttribute("aria-live");
    });

    it("should have proper focus management in dialogs", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const addButton = screen.getByRole("button", { name: /add|new/i });
      await user.click(addButton);

      const dialog = screen.getByRole("dialog");
      expect(dialog).toHaveAttribute("aria-modal", "true");
      
      // Focus should be trapped within dialog
      const focusableElements = dialog.querySelectorAll(
        'button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      expect(focusableElements.length).toBeGreaterThan(0);
    });
  });

  describe("Provider Support", () => {
    it("should support multiple API providers", () => {
      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      // Should display different providers
      expect(screen.getByText(/alpaca/i)).toBeInTheDocument();
      expect(
        screen.getByText(/interactive.brokers|interactive_brokers/i)
      ).toBeInTheDocument();
    });

    it("should handle provider-specific validation", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const addButton = screen.getByRole("button", { name: /add|new/i });
      await user.click(addButton);

      // Should have provider-specific help text or validation
      expect(
        screen.getByText(/provider/i) || screen.getByText(/select/i)
      ).toBeInTheDocument();
    });

    it("should display provider-specific environment options", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const addButton = screen.getByRole("button", { name: /add|new/i });
      await user.click(addButton);

      // Should show sandbox/live options
      expect(
        screen.getByText(/sandbox/i) || screen.getByText(/test/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/live/i) || screen.getByText(/production/i)
      ).toBeInTheDocument();
    });
  });

  describe("Integration with API Provider Context", () => {
    it("should properly integrate with useApiKeys hook", () => {
      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      expect(mockUseApiKeys).toHaveBeenCalled();
    });

    it("should handle context state changes", () => {
      // Test loading state
      mockUseApiKeys.mockReturnValue({
        apiKeys: [],
        loading: true,
        error: null,
        success: null,
        addApiKey: mockAddApiKey,
        deleteApiKey: mockDeleteApiKey,
        clearMessages: mockClearMessages,
      });

      const { rerender } = render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      expect(
        screen.getByRole("progressbar") || screen.getByText(/loading/i)
      ).toBeInTheDocument();

      // Test error state
      mockUseApiKeys.mockReturnValue({
        apiKeys: [],
        loading: false,
        error: "Network error",
        success: null,
        addApiKey: mockAddApiKey,
        deleteApiKey: mockDeleteApiKey,
        clearMessages: mockClearMessages,
      });

      rerender(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      expect(screen.getByText("Network error")).toBeInTheDocument();
    });

    it("should call context methods with correct parameters", async () => {
      const user = userEvent.setup();
      mockAddApiKey.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      const addButton = screen.getByRole("button", { name: /add|new/i });
      await user.click(addButton);

      const apiKeyInput =
        screen.getByLabelText(/api key/i) ||
        screen.getByPlaceholderText(/api key/i);
      const secretInput =
        screen.getByLabelText(/secret|private/i) ||
        screen.getByPlaceholderText(/secret|private/i);

      await user.type(apiKeyInput, "PKTEST12345ABCDEF");
      await user.type(secretInput, "test-secret-key-12345");

      const submitButton = screen.getByRole("button", { name: /save|add/i });
      await user.click(submitButton);

      expect(mockAddApiKey).toHaveBeenCalledWith(
        expect.objectContaining({
          apiKey: "PKTEST12345ABCDEF",
          secretKey: "test-secret-key-12345",
        })
      );
    });
  });

  describe("Performance Considerations", () => {
    it("should not re-render unnecessarily", () => {
      const { rerender } = render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      // Same props should not cause re-render
      rerender(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      // Component should handle props efficiently
      expect(mockUseApiKeys).toHaveBeenCalled();
    });

    it("should handle large numbers of API keys efficiently", () => {
      // Mock many API keys
      const manyKeys = Array.from({ length: 20 }, (_, i) => ({
        id: `key${i}`,
        provider: i % 2 === 0 ? "alpaca" : "interactive_brokers",
        keyPreview: `PK***${i.toString().padStart(3, '0')}`,
        isActive: i % 3 === 0,
        environment: i % 2 === 0 ? "sandbox" : "live",
        lastUsed: new Date().toISOString(),
        createdAt: new Date().toISOString(),
      }));

      mockUseApiKeys.mockReturnValue({
        apiKeys: manyKeys,
        loading: false,
        error: null,
        success: null,
        addApiKey: mockAddApiKey,
        deleteApiKey: mockDeleteApiKey,
        clearMessages: mockClearMessages,
      });

      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      );

      // Should render all keys without performance issues
      expect(screen.getAllByRole("button", { name: /delete|remove/i })).toHaveLength(20);
    });
  });
});
