import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { BrowserRouter } from "react-router-dom";
import SettingsManager from "../../components/SettingsManager";

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

const renderWithRouter = (component) => {
  return render(<BrowserRouter>{component}</BrowserRouter>);
};

describe("SettingsManager Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Default API responses
    api.get.mockResolvedValue({
      data: {
        success: true,
        data: {
          profile: {
            name: "Test User",
            email: "test@example.com",
            preferences: {},
          },
          apiKeys: [],
          notifications: {
            email: true,
            push: false,
          },
        },
      },
    });
  });

  describe("Settings Tabs Navigation", () => {
    it("should render all settings tabs", async () => {
      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(screen.getByText(/Profile/i)).toBeInTheDocument();
        expect(screen.getByText(/API Keys/i)).toBeInTheDocument();
        expect(screen.getByText(/Notifications/i)).toBeInTheDocument();
        expect(screen.getByText(/Preferences/i)).toBeInTheDocument();
      });
    });

    it("should switch between tabs when clicked", async () => {
      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(screen.getByText(/Profile/i)).toBeInTheDocument();
      });

      // Click API Keys tab
      fireEvent.click(screen.getByText(/API Keys/i));

      await waitFor(() => {
        expect(screen.getByText(/Manage your API keys/i)).toBeInTheDocument();
      });

      // Click Notifications tab
      fireEvent.click(screen.getByText(/Notifications/i));

      await waitFor(() => {
        expect(
          screen.getByText(/Notification preferences/i)
        ).toBeInTheDocument();
      });
    });
  });

  describe("Profile Settings", () => {
    it("should display user profile information", async () => {
      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(screen.getByDisplayValue("Test User")).toBeInTheDocument();
        expect(
          screen.getByDisplayValue("test@example.com")
        ).toBeInTheDocument();
      });
    });

    it("should update profile when form is submitted", async () => {
      api.put.mockResolvedValue({
        data: {
          success: true,
          message: "Profile updated successfully",
        },
      });

      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(screen.getByDisplayValue("Test User")).toBeInTheDocument();
      });

      // Update name
      const nameField = screen.getByDisplayValue("Test User");
      fireEvent.change(nameField, { target: { value: "Updated Name" } });

      // Submit form
      fireEvent.click(screen.getByText(/Save Profile/i));

      await waitFor(() => {
        expect(api.put).toHaveBeenCalledWith("/api/settings/profile", {
          name: "Updated Name",
          email: "test@example.com",
        });
      });

      await waitFor(() => {
        expect(
          screen.getByText(/Profile updated successfully/i)
        ).toBeInTheDocument();
      });
    });

    it("should validate profile form fields", async () => {
      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(screen.getByDisplayValue("Test User")).toBeInTheDocument();
      });

      // Clear required field
      const nameField = screen.getByDisplayValue("Test User");
      fireEvent.change(nameField, { target: { value: "" } });

      fireEvent.click(screen.getByText(/Save Profile/i));

      await waitFor(() => {
        expect(screen.getByText(/Name is required/i)).toBeInTheDocument();
      });

      expect(api.put).not.toHaveBeenCalled();
    });
  });

  describe("Notification Settings", () => {
    it("should display notification preferences", async () => {
      renderWithRouter(<SettingsManager />);

      fireEvent.click(screen.getByText(/Notifications/i));

      await waitFor(() => {
        expect(
          screen.getByLabelText(/Email notifications/i)
        ).toBeInTheDocument();
        expect(
          screen.getByLabelText(/Push notifications/i)
        ).toBeInTheDocument();
      });

      // Check initial states
      expect(screen.getByLabelText(/Email notifications/i)).toBeChecked();
      expect(screen.getByLabelText(/Push notifications/i)).not.toBeChecked();
    });

    it("should update notification preferences", async () => {
      api.put.mockResolvedValue({
        data: {
          success: true,
          message: "Notifications updated",
        },
      });

      renderWithRouter(<SettingsManager />);

      fireEvent.click(screen.getByText(/Notifications/i));

      await waitFor(() => {
        expect(
          screen.getByLabelText(/Email notifications/i)
        ).toBeInTheDocument();
      });

      // Toggle push notifications
      fireEvent.click(screen.getByLabelText(/Push notifications/i));

      // Save changes
      fireEvent.click(screen.getByText(/Save Notifications/i));

      await waitFor(() => {
        expect(api.put).toHaveBeenCalledWith("/api/settings/notifications", {
          email: true,
          push: true,
        });
      });
    });
  });

  describe("User Preferences", () => {
    it("should display theme and language preferences", async () => {
      renderWithRouter(<SettingsManager />);

      fireEvent.click(screen.getByText(/Preferences/i));

      await waitFor(() => {
        expect(screen.getByLabelText(/Theme/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/Language/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/Currency/i)).toBeInTheDocument();
      });
    });

    it("should update user preferences", async () => {
      api.put.mockResolvedValue({
        data: {
          success: true,
          message: "Preferences updated",
        },
      });

      renderWithRouter(<SettingsManager />);

      fireEvent.click(screen.getByText(/Preferences/i));

      await waitFor(() => {
        expect(screen.getByLabelText(/Theme/i)).toBeInTheDocument();
      });

      // Change theme
      fireEvent.change(screen.getByLabelText(/Theme/i), {
        target: { value: "dark" },
      });

      // Change currency
      fireEvent.change(screen.getByLabelText(/Currency/i), {
        target: { value: "EUR" },
      });

      fireEvent.click(screen.getByText(/Save Preferences/i));

      await waitFor(() => {
        expect(api.put).toHaveBeenCalledWith("/api/settings/preferences", {
          theme: "dark",
          language: "en",
          currency: "EUR",
        });
      });
    });
  });

  describe("Settings Integration", () => {
    it("should load all settings data on component mount", async () => {
      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith("/api/settings/profile");
        expect(api.get).toHaveBeenCalledWith("/api/settings/api-keys");
        expect(api.get).toHaveBeenCalledWith("/api/settings/notifications");
        expect(api.get).toHaveBeenCalledWith("/api/settings/preferences");
      });
    });

    it("should handle loading errors gracefully", async () => {
      api.get.mockRejectedValue({
        response: {
          data: {
            success: false,
            error: "Failed to load settings",
          },
        },
      });

      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(
          screen.getByText(/Failed to load settings/i)
        ).toBeInTheDocument();
      });
    });

    it("should provide refresh functionality", async () => {
      api.get
        .mockRejectedValueOnce(new Error("Network error"))
        .mockResolvedValue({
          data: { success: true, data: { profile: {}, apiKeys: [] } },
        });

      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(
          screen.getByText(/Failed to load settings/i)
        ).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText(/Refresh/i));

      await waitFor(() => {
        expect(screen.getByText(/Profile/i)).toBeInTheDocument();
      });

      expect(api.get).toHaveBeenCalledTimes(8); // 4 initial + 4 retry calls
    });
  });

  describe("Form Validation", () => {
    it("should validate email format in profile", async () => {
      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(
          screen.getByDisplayValue("test@example.com")
        ).toBeInTheDocument();
      });

      // Enter invalid email
      const emailField = screen.getByDisplayValue("test@example.com");
      fireEvent.change(emailField, { target: { value: "invalid-email" } });

      fireEvent.click(screen.getByText(/Save Profile/i));

      await waitFor(() => {
        expect(
          screen.getByText(/Please enter a valid email/i)
        ).toBeInTheDocument();
      });

      expect(api.put).not.toHaveBeenCalled();
    });

    it("should prevent submission with empty required fields", async () => {
      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(screen.getByDisplayValue("Test User")).toBeInTheDocument();
      });

      // Clear all required fields
      const nameField = screen.getByDisplayValue("Test User");
      const emailField = screen.getByDisplayValue("test@example.com");

      fireEvent.change(nameField, { target: { value: "" } });
      fireEvent.change(emailField, { target: { value: "" } });

      fireEvent.click(screen.getByText(/Save Profile/i));

      await waitFor(() => {
        expect(screen.getByText(/Name is required/i)).toBeInTheDocument();
        expect(screen.getByText(/Email is required/i)).toBeInTheDocument();
      });

      expect(api.put).not.toHaveBeenCalled();
    });
  });

  describe("Loading States", () => {
    it("should show loading spinner while fetching settings", async () => {
      api.get.mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  data: { success: true, data: {} },
                }),
              100
            )
          )
      );

      renderWithRouter(<SettingsManager />);

      expect(screen.getByText(/Loading settings/i)).toBeInTheDocument();

      await waitFor(
        () => {
          expect(
            screen.queryByText(/Loading settings/i)
          ).not.toBeInTheDocument();
        },
        { timeout: 200 }
      );
    });

    it("should show loading state while saving", async () => {
      api.put.mockImplementation(
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

      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(screen.getByDisplayValue("Test User")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText(/Save Profile/i));

      expect(screen.getByText(/Saving/i)).toBeInTheDocument();

      await waitFor(
        () => {
          expect(screen.queryByText(/Saving/i)).not.toBeInTheDocument();
        },
        { timeout: 200 }
      );
    });
  });

  describe("Success and Error Messages", () => {
    it("should show success message after successful update", async () => {
      api.put.mockResolvedValue({
        data: {
          success: true,
          message: "Profile updated successfully",
        },
      });

      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(screen.getByDisplayValue("Test User")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText(/Save Profile/i));

      await waitFor(() => {
        expect(
          screen.getByText(/Profile updated successfully/i)
        ).toBeInTheDocument();
      });
    });

    it("should show error message when update fails", async () => {
      api.put.mockRejectedValue({
        response: {
          data: {
            success: false,
            error: "Update failed",
          },
        },
      });

      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(screen.getByDisplayValue("Test User")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText(/Save Profile/i));

      await waitFor(() => {
        expect(screen.getByText(/Update failed/i)).toBeInTheDocument();
      });
    });

    it("should auto-dismiss success messages", async () => {
      vi.useFakeTimers();

      api.put.mockResolvedValue({
        data: {
          success: true,
          message: "Profile updated successfully",
        },
      });

      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(screen.getByDisplayValue("Test User")).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText(/Save Profile/i));

      await waitFor(() => {
        expect(
          screen.getByText(/Profile updated successfully/i)
        ).toBeInTheDocument();
      });

      // Fast forward 5 seconds
      vi.advanceTimersByTime(5000);

      await waitFor(() => {
        expect(
          screen.queryByText(/Profile updated successfully/i)
        ).not.toBeInTheDocument();
      });

      vi.useRealTimers();
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA labels for tabs", async () => {
      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(screen.getByRole("tablist")).toBeInTheDocument();
        expect(
          screen.getByRole("tab", { name: /Profile/i })
        ).toBeInTheDocument();
        expect(
          screen.getByRole("tab", { name: /API Keys/i })
        ).toBeInTheDocument();
      });
    });

    it("should have proper form labels", async () => {
      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(screen.getByLabelText(/Name/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/Email/i)).toBeInTheDocument();
      });

      // Check ARIA attributes
      expect(screen.getByLabelText(/Name/i)).toHaveAttribute(
        "aria-required",
        "true"
      );
      expect(screen.getByLabelText(/Email/i)).toHaveAttribute(
        "aria-required",
        "true"
      );
    });

    it("should be keyboard navigable", async () => {
      renderWithRouter(<SettingsManager />);

      await waitFor(() => {
        expect(screen.getByText(/Profile/i)).toBeInTheDocument();
      });

      // Tab navigation
      const profileTab = screen.getByRole("tab", { name: /Profile/i });
      const apiKeysTab = screen.getByRole("tab", { name: /API Keys/i });

      profileTab.focus();
      expect(profileTab).toHaveFocus();

      // Arrow key navigation
      fireEvent.keyDown(profileTab, { key: "ArrowRight" });
      expect(apiKeysTab).toHaveFocus();

      fireEvent.keyDown(apiKeysTab, { key: "ArrowLeft" });
      expect(profileTab).toHaveFocus();
    });
  });
});
