/**
 * Unit Tests for RegisterForm Component
 * Tests registration form validation, submission, and user interactions
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithTheme } from "../test-helpers/component-test-utils.jsx";
import RegisterForm from "../../../../components/auth/RegisterForm.jsx";
import * as AuthContext from "../../../../contexts/AuthContext";

// Mock AuthContext
const mockRegister = vi.fn();
const mockClearError = vi.fn();

vi.mock("../../../../contexts/AuthContext", () => ({
  useAuth: vi.fn(),
}));

describe("RegisterForm Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    AuthContext.useAuth.mockReturnValue({
      register: mockRegister,
      isLoading: false,
      error: null,
      clearError: mockClearError,
    });
    mockRegister.mockResolvedValue({ success: true });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("Form Rendering", () => {
    it("should render registration form with all elements", () => {
      renderWithTheme(<RegisterForm />);

      expect(screen.getByText("Sign Up")).toBeInTheDocument();
      expect(screen.getByText("Create your Financial Dashboard account")).toBeInTheDocument();
      expect(screen.getByRole("textbox", { name: /first name/i })).toBeInTheDocument();
      expect(screen.getByRole("textbox", { name: /last name/i })).toBeInTheDocument();
      expect(screen.getByRole("textbox", { name: /username/i })).toBeInTheDocument();
      expect(screen.getByRole("textbox", { name: /email address/i })).toBeInTheDocument();
      expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/^confirm password/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /create account/i })).toBeInTheDocument();
    });

    it("should have proper form structure", () => {
      const { container } = renderWithTheme(<RegisterForm />);

      const form = container.querySelector("form");
      expect(form).toBeInTheDocument();
      expect(form).toHaveAttribute("novalidate");
    });

    it("should display registration icon and branding", () => {
      renderWithTheme(<RegisterForm />);

      expect(screen.getByText("Sign Up")).toBeInTheDocument();
      expect(screen.getAllByTestId("PersonAddIcon")).toHaveLength(2); // Icon appears in header and button
    });

    it("should show helper texts for fields", () => {
      renderWithTheme(<RegisterForm />);

      expect(screen.getByText("This will be your unique identifier for signing in")).toBeInTheDocument();
      expect(screen.getByText("We'll send verification instructions to this email")).toBeInTheDocument();
      expect(screen.getByText("Must be at least 8 characters long")).toBeInTheDocument();
    });

    it("should render navigation link to login", () => {
      renderWithTheme(<RegisterForm />);

      expect(screen.getByText("Already have an account?")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /sign in here/i })).toBeInTheDocument();
    });
  });

  describe("Form Validation", () => {
    it("should show validation error for empty required fields", async () => {
      const user = userEvent.setup();
      renderWithTheme(<RegisterForm />);

      const submitButton = screen.getByRole("button", { name: /create account/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Please fill in all required fields")).toBeInTheDocument();
      });
    });

    it("should validate password mismatch", async () => {
      const user = userEvent.setup();
      renderWithTheme(<RegisterForm />);

      await user.type(screen.getByRole("textbox", { name: /username/i }), "testuser");
      await user.type(screen.getByRole("textbox", { name: /email address/i }), "test@example.com");
      await user.type(screen.getByLabelText(/^password/i), "password123");
      await user.type(screen.getByLabelText(/^confirm password/i), "differentpassword");

      const submitButton = screen.getByRole("button", { name: /create account/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Passwords do not match")).toBeInTheDocument();
      });
    });

    it("should validate minimum password length", async () => {
      const user = userEvent.setup();
      renderWithTheme(<RegisterForm />);

      await user.type(screen.getByRole("textbox", { name: /username/i }), "testuser");
      await user.type(screen.getByRole("textbox", { name: /email address/i }), "test@example.com");
      await user.type(screen.getByLabelText(/^password/i), "short");
      await user.type(screen.getByLabelText(/^confirm password/i), "short");

      const submitButton = screen.getByRole("button", { name: /create account/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Password must be at least 8 characters long")).toBeInTheDocument();
      });
    });

    it("should validate email format", async () => {
      const user = userEvent.setup();
      renderWithTheme(<RegisterForm />);

      await user.type(screen.getByRole("textbox", { name: /username/i }), "testuser");
      await user.type(screen.getByRole("textbox", { name: /email address/i }), "invalid-email");
      await user.type(screen.getByLabelText(/^password/i), "password123");
      await user.type(screen.getByLabelText(/^confirm password/i), "password123");

      const submitButton = screen.getByRole("button", { name: /create account/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Please enter a valid email address")).toBeInTheDocument();
      });
    });

    it("should clear validation errors when user starts typing", async () => {
      const user = userEvent.setup();
      renderWithTheme(<RegisterForm />);

      // Trigger validation error
      const submitButton = screen.getByRole("button", { name: /create account/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Please fill in all required fields")).toBeInTheDocument();
      });

      // Start typing to clear error
      await user.type(screen.getByRole("textbox", { name: /username/i }), "test");

      await waitFor(() => {
        expect(screen.queryByText("Please fill in all required fields")).not.toBeInTheDocument();
      });
    });
  });

  describe("Form Input Handling", () => {
    it("should update form fields on input", async () => {
      const user = userEvent.setup();
      renderWithTheme(<RegisterForm />);

      const firstNameField = screen.getByRole("textbox", { name: /first name/i });
      const lastNameField = screen.getByRole("textbox", { name: /last name/i });
      const usernameField = screen.getByRole("textbox", { name: /username/i });
      const emailField = screen.getByRole("textbox", { name: /email address/i });
      const passwordField = screen.getByLabelText(/^password/i);
      const confirmPasswordField = screen.getByLabelText(/^confirm password/i);

      await user.type(firstNameField, "John");
      await user.type(lastNameField, "Doe");
      await user.type(usernameField, "johndoe");
      await user.type(emailField, "john@example.com");
      await user.type(passwordField, "password123");
      await user.type(confirmPasswordField, "password123");

      expect(firstNameField).toHaveValue("John");
      expect(lastNameField).toHaveValue("Doe");
      expect(usernameField).toHaveValue("johndoe");
      expect(emailField).toHaveValue("john@example.com");
      expect(passwordField).toHaveValue("password123");
      expect(confirmPasswordField).toHaveValue("password123");
    });
  });

  describe("Password Visibility Toggle", () => {
    it("should toggle password visibility", async () => {
      const user = userEvent.setup();
      renderWithTheme(<RegisterForm />);

      const passwordField = screen.getByLabelText(/^password/i);
      const passwordToggle = screen.getByLabelText("toggle password visibility");

      expect(passwordField).toHaveAttribute("type", "password");

      await user.click(passwordToggle);
      expect(passwordField).toHaveAttribute("type", "text");

      await user.click(passwordToggle);
      expect(passwordField).toHaveAttribute("type", "password");
    });

    it("should toggle confirm password visibility", async () => {
      const user = userEvent.setup();
      renderWithTheme(<RegisterForm />);

      const confirmPasswordField = screen.getByLabelText(/^confirm password/i);
      const confirmPasswordToggle = screen.getByLabelText("toggle confirm password visibility");

      expect(confirmPasswordField).toHaveAttribute("type", "password");

      await user.click(confirmPasswordToggle);
      expect(confirmPasswordField).toHaveAttribute("type", "text");

      await user.click(confirmPasswordToggle);
      expect(confirmPasswordField).toHaveAttribute("type", "password");
    });

    it("should maintain field values when toggling visibility", async () => {
      const user = userEvent.setup();
      renderWithTheme(<RegisterForm />);

      const passwordField = screen.getByLabelText(/^password/i);
      const passwordToggle = screen.getByLabelText("toggle password visibility");

      await user.type(passwordField, "password123");
      await user.click(passwordToggle);

      expect(passwordField).toHaveValue("password123");
    });
  });

  describe("Form Submission", () => {
    it("should submit form with valid data", async () => {
      const user = userEvent.setup();
      const mockOnRegistrationSuccess = vi.fn();
      renderWithTheme(<RegisterForm onRegistrationSuccess={mockOnRegistrationSuccess} />);

      await user.type(screen.getByRole("textbox", { name: /first name/i }), "John");
      await user.type(screen.getByRole("textbox", { name: /last name/i }), "Doe");
      await user.type(screen.getByRole("textbox", { name: /username/i }), "johndoe");
      await user.type(screen.getByRole("textbox", { name: /email address/i }), "john@example.com");
      await user.type(screen.getByLabelText(/^password/i), "password123");
      await user.type(screen.getByLabelText(/^confirm password/i), "password123");

      const submitButton = screen.getByRole("button", { name: /create account/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockRegister).toHaveBeenCalledWith("johndoe", "password123", "john@example.com", "John", "Doe");
        expect(mockOnRegistrationSuccess).toHaveBeenCalledWith("johndoe", undefined);
      });
    });

    it("should handle registration success with next step", async () => {
      const user = userEvent.setup();
      const mockOnRegistrationSuccess = vi.fn();
      const nextStep = "CONFIRM_SIGN_UP";
      mockRegister.mockResolvedValue({ success: true, nextStep });

      renderWithTheme(<RegisterForm onRegistrationSuccess={mockOnRegistrationSuccess} />);

      await user.type(screen.getByRole("textbox", { name: /username/i }), "johndoe");
      await user.type(screen.getByRole("textbox", { name: /email address/i }), "john@example.com");
      await user.type(screen.getByLabelText(/^password/i), "password123");
      await user.type(screen.getByLabelText(/^confirm password/i), "password123");

      const submitButton = screen.getByRole("button", { name: /create account/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockOnRegistrationSuccess).toHaveBeenCalledWith("johndoe", nextStep);
      });
    });

    it("should handle registration failure with error message", async () => {
      const user = userEvent.setup();
      mockRegister.mockResolvedValue({ success: false, error: "Username already exists" });

      renderWithTheme(<RegisterForm />);

      await user.type(screen.getByRole("textbox", { name: /username/i }), "johndoe");
      await user.type(screen.getByRole("textbox", { name: /email address/i }), "john@example.com");
      await user.type(screen.getByLabelText(/^password/i), "password123");
      await user.type(screen.getByLabelText(/^confirm password/i), "password123");

      const submitButton = screen.getByRole("button", { name: /create account/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Username already exists")).toBeInTheDocument();
      });
    });
  });

  describe("Loading State", () => {
    beforeEach(() => {
      AuthContext.useAuth.mockReturnValue({
        register: mockRegister,
        isLoading: true,
        error: null,
        clearError: mockClearError,
      });
    });

    it("should show loading state during registration", () => {
      renderWithTheme(<RegisterForm />);

      expect(screen.getByText("Creating Account...")).toBeInTheDocument();
      expect(screen.getByRole("progressbar")).toBeInTheDocument();
    });

    it("should disable form fields during loading", () => {
      renderWithTheme(<RegisterForm />);

      expect(screen.getByRole("textbox", { name: /first name/i })).toBeDisabled();
      expect(screen.getByRole("textbox", { name: /last name/i })).toBeDisabled();
      expect(screen.getByRole("textbox", { name: /username/i })).toBeDisabled();
      expect(screen.getByRole("textbox", { name: /email address/i })).toBeDisabled();
      expect(screen.getByLabelText(/^password/i)).toBeDisabled();
      expect(screen.getByLabelText(/^confirm password/i)).toBeDisabled();
      expect(screen.getByRole("button", { name: /creating account/i })).toBeDisabled();
    });

    it("should disable password visibility toggles during loading", () => {
      renderWithTheme(<RegisterForm />);

      expect(screen.getByLabelText("toggle password visibility")).toBeDisabled();
      expect(screen.getByLabelText("toggle confirm password visibility")).toBeDisabled();
    });

    it("should disable navigation links during loading", () => {
      renderWithTheme(<RegisterForm />);

      expect(screen.getByRole("button", { name: /sign in here/i })).toBeDisabled();
    });
  });

  describe("Error Handling", () => {
    it("should display auth context error", () => {
      AuthContext.useAuth.mockReturnValue({
        register: mockRegister,
        isLoading: false,
        error: "Network connection failed",
        clearError: mockClearError,
      });

      renderWithTheme(<RegisterForm />);

      expect(screen.getByText("Network connection failed")).toBeInTheDocument();
    });

    it("should clear auth context error when user starts typing", async () => {
      AuthContext.useAuth.mockReturnValue({
        register: mockRegister,
        isLoading: false,
        error: "Network connection failed",
        clearError: mockClearError,
      });

      const user = userEvent.setup();
      renderWithTheme(<RegisterForm />);

      const usernameField = screen.getByRole("textbox", { name: /username/i });
      await user.type(usernameField, "test");

      expect(mockClearError).toHaveBeenCalled();
    });

    it("should display both local and auth errors appropriately", () => {
      AuthContext.useAuth.mockReturnValue({
        register: mockRegister,
        isLoading: false,
        error: "Auth error",
        clearError: mockClearError,
      });

      renderWithTheme(<RegisterForm />);

      // Should show auth error
      expect(screen.getByText("Auth error")).toBeInTheDocument();
    });
  });

  describe("Navigation Links", () => {
    it("should call onSwitchToLogin when sign in link is clicked", async () => {
      const user = userEvent.setup();
      const mockOnSwitchToLogin = vi.fn();
      renderWithTheme(<RegisterForm onSwitchToLogin={mockOnSwitchToLogin} />);

      const signInLink = screen.getByRole("button", { name: /sign in here/i });
      await user.click(signInLink);

      expect(mockOnSwitchToLogin).toHaveBeenCalled();
    });

    it("should handle missing callback props gracefully", () => {
      renderWithTheme(<RegisterForm />);

      expect(screen.getByRole("button", { name: /sign in here/i })).toBeInTheDocument();
    });
  });

  describe("Keyboard Navigation", () => {
    it("should be keyboard navigable", async () => {
      const user = userEvent.setup();
      renderWithTheme(<RegisterForm />);

      const firstField = screen.getByRole("textbox", { name: /first name/i });
      await user.tab();

      expect(firstField).toHaveFocus();
    });

    it("should submit form on Enter key in last field", async () => {
      const user = userEvent.setup();
      const mockOnRegistrationSuccess = vi.fn();
      renderWithTheme(<RegisterForm onRegistrationSuccess={mockOnRegistrationSuccess} />);

      await user.type(screen.getByRole("textbox", { name: /username/i }), "johndoe");
      await user.type(screen.getByRole("textbox", { name: /email address/i }), "john@example.com");
      await user.type(screen.getByLabelText(/^password/i), "password123");

      const confirmPasswordField = screen.getByLabelText(/^confirm password/i);
      await user.type(confirmPasswordField, "password123");
      await user.keyboard("{Enter}");

      await waitFor(() => {
        expect(mockRegister).toHaveBeenCalled();
      });
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA labels", () => {
      renderWithTheme(<RegisterForm />);

      expect(screen.getByLabelText("toggle password visibility")).toBeInTheDocument();
      expect(screen.getByLabelText("toggle confirm password visibility")).toBeInTheDocument();
    });

    it("should have proper form semantics", () => {
      const { container } = renderWithTheme(<RegisterForm />);

      const form = container.querySelector("form");
      expect(form).toBeInTheDocument();

      // Check that form inputs are properly accessible
      expect(screen.getByRole("textbox", { name: /username/i })).toBeInTheDocument();
      expect(screen.getByRole("textbox", { name: /email address/i })).toBeInTheDocument();
      expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/^confirm password/i)).toBeInTheDocument();
    });

    it("should have proper heading hierarchy", () => {
      renderWithTheme(<RegisterForm />);

      const heading = screen.getByRole("heading", { name: "Sign Up" });
      expect(heading).toBeInTheDocument();
      expect(heading).toHaveProperty("tagName", "H1");
    });

    it("should announce errors to screen readers", async () => {
      const user = userEvent.setup();
      renderWithTheme(<RegisterForm />);

      const submitButton = screen.getByRole("button", { name: /create account/i });
      await user.click(submitButton);

      await waitFor(() => {
        const alert = screen.getByRole("alert");
        expect(alert).toBeInTheDocument();
        expect(alert).toHaveTextContent("Please fill in all required fields");
      });
    });
  });

  describe("Edge Cases", () => {
    it("should handle form submission without optional fields", async () => {
      const user = userEvent.setup();
      const mockOnRegistrationSuccess = vi.fn();
      renderWithTheme(<RegisterForm onRegistrationSuccess={mockOnRegistrationSuccess} />);

      // Only fill required fields (not firstName/lastName)
      await user.type(screen.getByRole("textbox", { name: /username/i }), "johndoe");
      await user.type(screen.getByRole("textbox", { name: /email address/i }), "john@example.com");
      await user.type(screen.getByLabelText(/^password/i), "password123");
      await user.type(screen.getByLabelText(/^confirm password/i), "password123");

      const submitButton = screen.getByRole("button", { name: /create account/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockRegister).toHaveBeenCalledWith("johndoe", "password123", "john@example.com", "", "");
      });
    });

    it("should handle registration success without callback", async () => {
      const user = userEvent.setup();
      renderWithTheme(<RegisterForm />);

      await user.type(screen.getByRole("textbox", { name: /username/i }), "johndoe");
      await user.type(screen.getByRole("textbox", { name: /email address/i }), "john@example.com");
      await user.type(screen.getByLabelText(/^password/i), "password123");
      await user.type(screen.getByLabelText(/^confirm password/i), "password123");

      const submitButton = screen.getByRole("button", { name: /create account/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockRegister).toHaveBeenCalled();
      });
    });

    it("should handle form with whitespace input", async () => {
      const user = userEvent.setup();
      renderWithTheme(<RegisterForm />);

      await user.type(screen.getByRole("textbox", { name: /username/i }), "  johndoe  ");
      await user.type(screen.getByRole("textbox", { name: /email address/i }), "  john@example.com  ");

      // Username field should maintain the whitespace during input
      expect(screen.getByRole("textbox", { name: /username/i })).toHaveValue("  johndoe  ");
      // Email field may trim whitespace automatically - check it has the core email
      expect(screen.getByRole("textbox", { name: /email address/i }).value).toContain("john@example.com");
    });

    it("should handle null/undefined auth context values gracefully", () => {
      AuthContext.useAuth.mockReturnValue({
        register: null,
        isLoading: false,
        error: null,
        clearError: null,
      });

      renderWithTheme(<RegisterForm />);

      // Should render without crashing
      expect(screen.getByText("Sign Up")).toBeInTheDocument();
    });
  });
});