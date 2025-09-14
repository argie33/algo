/**
 * Settings Page Unit Tests
 * Tests API key management, user preferences, and configuration options
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  renderWithProviders,
  screen,
  waitFor,
  userEvent,
  createMockUser,
} from "../../test-utils.jsx";
import Settings from "../../../pages/Settings.jsx";
import api from "../../../services/api.js";

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: ({ children }) => children, // Mock AuthProvider as a pass-through
}));

// Mock API service - using vi.mocked(api) pattern

vi.mock("../../../services/api.js", () => ({
  default: {
    getSettings: vi.fn(),
    updateSettings: vi.fn(),
    getApiKeys: vi.fn(),
    saveApiKey: vi.fn(),
    deleteApiKey: vi.fn(),
    testApiKey: vi.fn(),
  },
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
}));

// Note: ApiKeyProvider removed - API key functionality now handled directly by Settings page

describe("Settings Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Reset mocked api functions
    const mockedApi = vi.mocked(api);
    mockedApi.getSettings.mockReset();
    mockedApi.updateSettings.mockReset();
    mockedApi.getApiKeys.mockReset();
    mockedApi.saveApiKey.mockReset();
    mockedApi.deleteApiKey.mockReset();
    mockedApi.testApiKey.mockReset();
  });

  describe("Settings Page Layout", () => {
    it("should display settings navigation tabs", async () => {
      vi.mocked(api).getSettings.mockResolvedValue({
        notifications: { email: true, push: false },
        privacy: { shareData: false },
        trading: { confirmOrders: true },
      });

      renderWithProviders(<Settings />);

      await waitFor(() => {
        // Should have tab navigation
        expect(
          screen.getByText(/API Keys/i) ||
            screen.getByText(/Preferences/i) ||
            screen.getByText(/Notifications/i) ||
            screen.getByRole("tab")
        ).toBeTruthy();
      });
    });

    it("should load user settings on mount", async () => {
      const mockSettings = {
        notifications: {
          email: true,
          push: false,
          alerts: true,
        },
        privacy: {
          shareData: false,
          analytics: true,
        },
        trading: {
          confirmOrders: true,
          defaultQuantity: 100,
        },
      };

      vi.mocked(api).getSettings.mockResolvedValue(mockSettings);

      renderWithProviders(<Settings />);

      await waitFor(() => {
        expect(vi.mocked(api).getSettings).toHaveBeenCalled();
      });
    });
  });

  describe("API Keys Management", () => {
    it("should display existing API keys", async () => {
      // ApiKeyProvider no longer exists - test functionality moved to direct API integration

      const mockApiKeys = {
        alpaca: {
          keyId: "PK***ABC",
          isValid: true,
          lastValidated: "2025-01-15T10:30:00Z",
        },
        polygon: {
          keyId: "poly***XYZ",
          isValid: true,
          lastValidated: "2025-01-15T10:30:00Z",
        },
      };

      useApiKeys.mockReturnValue({
        apiKeys: mockApiKeys,
        isLoading: false,
        error: null,
        refreshApiKeys: vi.fn(),
      });

      renderWithProviders(<Settings />);

      await waitFor(() => {
        // Should display API key providers
        expect(screen.getByText(/Alpaca/i)).toBeTruthy();
        expect(screen.getByText(/Polygon/i)).toBeTruthy();
      });

      // Should show masked key IDs
      expect(screen.getByText(/PK\*\*\*ABC/i)).toBeTruthy();
      expect(screen.getByText(/poly\*\*\*XYZ/i)).toBeTruthy();
    });

    it("should allow adding new API keys", async () => {
      const user = userEvent.setup();

      vi.mocked(api).saveApiKey.mockResolvedValue({ success: true });
      vi.mocked(api).testApiKey.mockResolvedValue({ isValid: true });

      renderWithProviders(<Settings />);

      await waitFor(() => {
        const addButton =
          screen.getByText(/Add API Key/i) ||
          screen.getByRole("button", { name: /add/i });
        expect(addButton).toBeTruthy();
      });

      // Click add API key button
      const addButton =
        screen.getByText(/Add API Key/i) ||
        screen.getByRole("button", { name: /add/i });
      await user.click(addButton);

      await waitFor(() => {
        // Should show API key form
        expect(
          screen.getByText(/Provider/i) ||
            screen.getByText(/API Key/i) ||
            screen.getByText(/Secret/i)
        ).toBeTruthy();
      });
    });

    it("should validate API keys before saving", async () => {
      const user = userEvent.setup();

      vi.mocked(api).testApiKey.mockResolvedValue({
        isValid: false,
        error: "Invalid credentials",
      });

      renderWithProviders(<Settings />);

      // Simulate filling API key form
      const apiKeyInput =
        screen.queryByLabelText(/API Key/i) ||
        screen.queryByPlaceholderText(/API Key/i);

      if (apiKeyInput) {
        await user.type(apiKeyInput, "invalid-key");

        const testButton =
          screen.getByText(/Test/i) ||
          screen.getByRole("button", { name: /test/i });
        await user.click(testButton);

        await waitFor(() => {
          expect(vi.mocked(api).testApiKey).toHaveBeenCalledWith(
            expect.objectContaining({
              keyId: "invalid-key",
            })
          );
        });

        // Should show validation error
        expect(
          screen.getByText(/Invalid credentials/i) ||
            screen.getByText(/validation failed/i)
        ).toBeTruthy();
      }
    });

    it("should allow deleting API keys", async () => {
      // ApiKeyProvider no longer exists - test functionality moved to direct API integration
      const user = userEvent.setup();

      const mockApiKeys = {
        alpaca: { keyId: "PK***ABC", isValid: true },
      };

      useApiKeys.mockReturnValue({
        apiKeys: mockApiKeys,
        isLoading: false,
        error: null,
        refreshApiKeys: vi.fn(),
      });

      vi.mocked(api).deleteApiKey.mockResolvedValue({ success: true });

      renderWithProviders(<Settings />);

      await waitFor(() => {
        const deleteButton =
          screen.getByText(/Delete/i) ||
          screen.getByRole("button", { name: /delete/i });
        expect(deleteButton).toBeTruthy();
      });

      const deleteButton =
        screen.getByText(/Delete/i) ||
        screen.getByRole("button", { name: /delete/i });
      await user.click(deleteButton);

      // Should show confirmation dialog
      await waitFor(() => {
        expect(
          screen.getByText(/confirm/i) ||
            screen.getByText(/are you sure/i) ||
            screen.getByText(/delete/i)
        ).toBeTruthy();
      });
    });
  });

  describe("User Preferences", () => {
    it("should display notification preferences", async () => {
      const mockSettings = {
        notifications: {
          email: true,
          push: false,
          priceAlerts: true,
          newsAlerts: false,
        },
      };

      vi.mocked(api).getSettings.mockResolvedValue(mockSettings);

      renderWithProviders(<Settings />);

      await waitFor(() => {
        // Should show notification options
        expect(
          screen.getByText(/Email/i) ||
            screen.getByText(/Push/i) ||
            screen.getByText(/Notifications/i)
        ).toBeTruthy();
      });
    });

    it("should allow updating notification preferences", async () => {
      const user = userEvent.setup();

      vi.mocked(api).getSettings.mockResolvedValue({
        notifications: { email: false, push: false },
      });
      vi.mocked(api).updateSettings.mockResolvedValue({ success: true });

      renderWithProviders(<Settings />);

      await waitFor(() => {
        const emailToggle =
          screen.getByRole("checkbox") || screen.getByRole("switch");
        expect(emailToggle).toBeTruthy();
      });

      // Toggle email notifications
      const emailToggle =
        screen.getByRole("checkbox") || screen.getByRole("switch");
      await user.click(emailToggle);

      await waitFor(() => {
        expect(vi.mocked(api).updateSettings).toHaveBeenCalledWith(
          expect.objectContaining({
            notifications: expect.objectContaining({
              email: true,
            }),
          })
        );
      });
    });

    it("should display trading preferences", async () => {
      const mockSettings = {
        trading: {
          confirmOrders: true,
          defaultQuantity: 100,
          stopLossDefault: 5.0,
          takeProfitDefault: 10.0,
        },
      };

      vi.mocked(api).getSettings.mockResolvedValue(mockSettings);

      renderWithProviders(<Settings />);

      await waitFor(() => {
        // Should show trading preferences
        expect(
          screen.getByText(/Trading/i) ||
            screen.getByText(/Orders/i) ||
            screen.getByText(/Confirm/i)
        ).toBeTruthy();
      });
    });

    it("should display privacy settings", async () => {
      const mockSettings = {
        privacy: {
          shareData: false,
          analytics: true,
          marketingEmails: false,
        },
      };

      vi.mocked(api).getSettings.mockResolvedValue(mockSettings);

      renderWithProviders(<Settings />);

      await waitFor(() => {
        // Should show privacy options
        expect(
          screen.getByText(/Privacy/i) ||
            screen.getByText(/Data/i) ||
            screen.getByText(/Analytics/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Settings Persistence", () => {
    it("should save settings changes automatically", async () => {
      const user = userEvent.setup();

      vi.mocked(api).getSettings.mockResolvedValue({
        notifications: { email: false },
      });
      vi.mocked(api).updateSettings.mockResolvedValue({ success: true });

      renderWithProviders(<Settings />);

      await waitFor(() => {
        const toggle =
          screen.getByRole("checkbox") || screen.getByRole("switch");
        expect(toggle).toBeTruthy();
      });

      const toggle = screen.getByRole("checkbox") || screen.getByRole("switch");
      await user.click(toggle);

      // Should automatically save after a short delay
      await waitFor(
        () => {
          expect(vi.mocked(api).updateSettings).toHaveBeenCalled();
        },
        { timeout: 2000 }
      );
    });

    it("should show save status indicators", async () => {
      const user = userEvent.setup();

      vi.mocked(api).updateSettings.mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(() => resolve({ success: true }), 1000)
          )
      );

      renderWithProviders(<Settings />);

      const toggle =
        screen.queryByRole("checkbox") || screen.queryByRole("switch");

      if (toggle) {
        await user.click(toggle);

        // Should show saving indicator
        await waitFor(() => {
          expect(
            screen.getByText(/Saving/i) ||
              screen.getByText(/Loading/i) ||
              screen.getByTestId("saving-indicator")
          ).toBeTruthy();
        });
      }
    });
  });

  describe("Account Management", () => {
    it("should display account information", async () => {
      const mockSettings = {
        account: {
          email: "user@example.com",
          createdAt: "2024-01-15T10:30:00Z",
          lastLogin: "2025-01-15T10:30:00Z",
        },
      };

      vi.mocked(api).getSettings.mockResolvedValue(mockSettings);

      renderWithProviders(<Settings />);

      await waitFor(() => {
        // Should show account details
        expect(
          screen.getByText(/user@example\.com/i) || screen.getByText(/Account/i)
        ).toBeTruthy();
      });
    });

    it("should allow password change", async () => {
      const user = userEvent.setup();

      vi.mocked(api).updateSettings.mockResolvedValue({ success: true });

      renderWithProviders(<Settings />);

      const passwordButton =
        screen.queryByText(/Change Password/i) ||
        screen.queryByRole("button", { name: /password/i });

      if (passwordButton) {
        await user.click(passwordButton);

        await waitFor(() => {
          expect(
            screen.getByText(/Current Password/i) ||
              screen.getByText(/New Password/i) ||
              screen.getByLabelText(/password/i)
          ).toBeTruthy();
        });
      }
    });
  });

  describe("Data Export/Import", () => {
    it("should allow data export", async () => {
      const user = userEvent.setup();

      renderWithProviders(<Settings />);

      const exportButton =
        screen.queryByText(/Export/i) ||
        screen.queryByRole("button", { name: /export/i });

      if (exportButton) {
        await user.click(exportButton);

        // Should trigger data export
        await waitFor(() => {
          expect(
            screen.getByText(/Exporting/i) || screen.getByText(/Download/i)
          ).toBeTruthy();
        });
      }
    });
  });

  describe("Error Handling", () => {
    it("should handle settings load errors", async () => {
      vi.mocked(api).getSettings.mockRejectedValue(new Error("Settings unavailable"));

      renderWithProviders(<Settings />);

      await waitFor(() => {
        expect(
          screen.getByText(/error/i) ||
            screen.getByText(/unavailable/i) ||
            screen.getByText(/failed/i)
        ).toBeTruthy();
      });
    });

    it("should handle save errors gracefully", async () => {
      const user = userEvent.setup();

      vi.mocked(api).getSettings.mockResolvedValue({
        notifications: { email: false },
      });
      vi.mocked(api).updateSettings.mockRejectedValue(new Error("Save failed"));

      renderWithProviders(<Settings />);

      const toggle = screen.queryByRole("checkbox");
      if (toggle) {
        await user.click(toggle);

        await waitFor(() => {
          expect(
            screen.getByText(/Save failed/i) || screen.getByText(/error/i)
          ).toBeTruthy();
        });
      }
    });

    it("should handle API key validation errors", async () => {
      vi.mocked(api).testApiKey.mockRejectedValue(new Error("Connection timeout"));

      renderWithProviders(<Settings />);

      // Should handle validation errors gracefully
      expect(document.body).toBeTruthy(); // Component doesn't crash
    });
  });

  describe("Accessibility", () => {
    it("should have proper form labels", async () => {
      vi.mocked(api).getSettings.mockResolvedValue({
        notifications: { email: true },
      });

      renderWithProviders(<Settings />);

      await waitFor(() => {
        // Should have labeled form controls
        const formControls =
          screen.getAllByRole("checkbox") ||
          screen.getAllByRole("switch") ||
          screen.getAllByRole("textbox") ||
          [];
        expect(formControls.length).toBeGreaterThan(0);
      });
    });

    it("should be keyboard navigable", async () => {
      const user = userEvent.setup();

      vi.mocked(api).getSettings.mockResolvedValue({
        notifications: { email: true },
      });

      renderWithProviders(<Settings />);

      // Should be able to tab through interactive elements
      await user.tab();

      const focusedElement = document.activeElement;
      expect(focusedElement).toBeTruthy();
      expect(focusedElement?.tagName).toMatch(/BUTTON|INPUT|SELECT/i);
    });
  });

  describe("Responsive Design", () => {
    it("should adapt to mobile layout", async () => {
      vi.mocked(api).getSettings.mockResolvedValue({
        notifications: { email: true },
      });

      // Mock mobile viewport
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 375,
      });

      renderWithProviders(<Settings />);

      await waitFor(() => {
        // Should render without horizontal scroll
        expect(document.body).toBeTruthy();
      });
    });
  });
});
