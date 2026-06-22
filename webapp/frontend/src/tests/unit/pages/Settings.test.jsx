/**
 * Settings Page Unit Tests
 * Component has 3 plain <button> tabs: "General Settings", "Preferences", "Account"
 * Uses named exports getSettings/updateSettings from api.js
 * Loading state: "Loading settings..."
 * Success: "Settings saved successfully!"
 * Errors: "Failed to save settings" / "Failed to load settings"
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

vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: ({ children }) => children,
}));

vi.mock("../../../services/api.js", () => ({
  default: { get: vi.fn(), post: vi.fn() },
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
}));

describe("Settings Page", () => {
  let getSettings;
  let updateSettings;

  beforeEach(async () => {
    vi.clearAllMocks();
    const apiModule = await import("../../../services/api.js");
    getSettings = apiModule.getSettings;
    updateSettings = apiModule.updateSettings;

    getSettings.mockResolvedValue({
      data: {
        notifications: { email: true, push: false, alerts: false },
        profile: {
          firstName: "Test",
          lastName: "User",
          email: "test@example.com",
        },
        theme: "dark",
        defaultView: "market",
      },
    });
    updateSettings.mockResolvedValue({ ok: true, success: true });
  });

  describe("Settings Page Layout", () => {
    it("should render the Settings heading", async () => {
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(screen.getByText("Settings")).toBeInTheDocument();
      });
    });

    it("should display three tab buttons", async () => {
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: "General Settings" })
        ).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: "Preferences" })
        ).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: "Account" })
        ).toBeInTheDocument();
      });
    });

    it("should call getSettings on mount", async () => {
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(getSettings).toHaveBeenCalled();
      });
    });

    it("should show loading state before settings resolve", () => {
      getSettings.mockImplementation(() => new Promise(() => {}));
      renderWithProviders(<Settings />);
      expect(screen.getByText(/Loading settings/i)).toBeInTheDocument();
    });
  });

  describe("General Settings Tab (default)", () => {
    it("should display Theme label on default tab", async () => {
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(screen.getByText("Theme")).toBeInTheDocument();
      });
    });

    it("should display Default View label", async () => {
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(screen.getByText("Default View")).toBeInTheDocument();
      });
    });

    it("should have Save Settings button", async () => {
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /Save Settings/i })
        ).toBeInTheDocument();
      });
    });

    it("should call updateSettings on Save Settings click", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /Save Settings/i })
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /Save Settings/i }));
      await waitFor(() => {
        expect(updateSettings).toHaveBeenCalled();
      });
    });

    it("should show success message after saving", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /Save Settings/i })
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /Save Settings/i }));
      await waitFor(() => {
        expect(
          screen.getByText(/Settings saved successfully/i)
        ).toBeInTheDocument();
      });
    });
  });

  describe("Preferences Tab", () => {
    it("should show Email Notifications label", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: "Preferences" })
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: "Preferences" }));
      await waitFor(() => {
        expect(screen.getByText(/Email Notifications/i)).toBeInTheDocument();
      });
    });

    it("should show Push Notifications label", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: "Preferences" })
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: "Preferences" }));
      // Use getAllByText since "push" appears in both the label and subtitle text
      await waitFor(() => {
        expect(
          screen.getAllByText(/Push Notifications/i).length
        ).toBeGreaterThan(0);
      });
    });

    it("should show Trading Alerts label", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: "Preferences" })
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: "Preferences" }));
      await waitFor(() => {
        expect(screen.getByText(/Trading Alerts/i)).toBeInTheDocument();
      });
    });

    it("should show auto-save note", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: "Preferences" })
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: "Preferences" }));
      await waitFor(() => {
        expect(screen.getByText(/automatically saved/i)).toBeInTheDocument();
      });
    });
  });

  describe("Account Tab", () => {
    it("should show First Name field", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: "Account" })
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: "Account" }));
      await waitFor(() => {
        expect(screen.getByText("First Name")).toBeInTheDocument();
      });
    });

    it("should show Last Name field", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: "Account" })
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: "Account" }));
      await waitFor(() => {
        expect(screen.getByText("Last Name")).toBeInTheDocument();
      });
    });

    it("should show Email field", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: "Account" })
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: "Account" }));
      await waitFor(() => {
        expect(screen.getByText("Email")).toBeInTheDocument();
      });
    });

    it("should show Save Profile button", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: "Account" })
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: "Account" }));
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /Save Profile/i })
        ).toBeInTheDocument();
      });
    });

    it("should show email cannot be changed note", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: "Account" })
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: "Account" }));
      await waitFor(() => {
        expect(
          screen.getByText(/Email cannot be changed/i)
        ).toBeInTheDocument();
      });
    });
  });

  describe("Error Handling", () => {
    it("should show error when settings fail to load", async () => {
      getSettings.mockRejectedValue(new Error("Settings unavailable"));
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(
          screen.getByText(/Failed to load settings/i)
        ).toBeInTheDocument();
      });
    });

    it("should show error when save fails", async () => {
      const user = userEvent.setup();
      updateSettings.mockRejectedValue(new Error("Save failed"));
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /Save Settings/i })
        ).toBeInTheDocument();
      });
      await user.click(screen.getByRole("button", { name: /Save Settings/i }));
      await waitFor(() => {
        expect(
          screen.getByText(/Failed to save settings/i)
        ).toBeInTheDocument();
      });
    });

    it("should not crash on settings error", async () => {
      getSettings.mockRejectedValue(new Error("error"));
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(document.body).toBeTruthy();
      });
    });
  });

  describe("Accessibility", () => {
    it("should have select controls on General Settings tab", async () => {
      renderWithProviders(<Settings />);
      await waitFor(() => {
        const selects = screen.queryAllByRole("combobox");
        expect(selects.length).toBeGreaterThan(0);
      });
    });

    it("should be keyboard navigable", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(screen.getByText("Settings")).toBeInTheDocument();
      });
      await user.tab();
      const focused = document.activeElement;
      expect(focused).toBeTruthy();
      expect(focused?.tagName).toMatch(/BUTTON|INPUT|SELECT/i);
    });
  });

  describe("Responsive Design", () => {
    it("should render on mobile viewport", async () => {
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 375,
      });
      renderWithProviders(<Settings />);
      await waitFor(() => {
        expect(document.body).toBeTruthy();
      });
    });
  });
});
