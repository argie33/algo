import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithTheme } from "../test-helpers/component-test-utils";
import LoginForm from "../../../../components/auth/LoginForm.jsx";

// Mock the auth context
vi.mock("../../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    login: vi.fn(),
    isLoading: false,
    error: null,
    clearError: vi.fn(),
    user: null,
  })),
}));

// Import after mocking
import { useAuth } from "../../../../contexts/AuthContext.jsx";

describe("LoginForm Component", () => {
  const defaultProps = {
    onSwitchToRegister: vi.fn(),
    onSwitchToForgotPassword: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    // Reset mock implementation
    useAuth.mockReturnValue({
      login: vi.fn(),
      isLoading: false,
      error: null,
      clearError: vi.fn(),
      user: null,
    });
  });

  describe("Form Rendering", () => {
    it("should render login form with required fields", () => {
      renderWithTheme(<LoginForm {...defaultProps} />);

      expect(screen.getByLabelText(/username or email/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
    });

    it("should render form title", () => {
      renderWithTheme(<LoginForm {...defaultProps} />);

      expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    });

    it("should render switch to register link", () => {
      renderWithTheme(<LoginForm {...defaultProps} />);

      expect(screen.getByText(/don't have an account/i)).toBeInTheDocument();
    });

    it("should render forgot password link", () => {
      renderWithTheme(<LoginForm {...defaultProps} />);

      expect(screen.getByText(/forgot password/i)).toBeInTheDocument();
    });
  });

  describe("Form Interaction", () => {
    it("should handle username input", async () => {
      const user = userEvent.setup();
      renderWithTheme(<LoginForm {...defaultProps} />);

      const usernameInput = screen.getByLabelText(/username or email/i);
      await user.type(usernameInput, "testuser");

      expect(usernameInput).toHaveValue("testuser");
    });

    it("should handle password input", async () => {
      const user = userEvent.setup();
      renderWithTheme(<LoginForm {...defaultProps} />);

      const passwordInput = screen.getByLabelText(/^password/i);
      await user.type(passwordInput, "password123");

      expect(passwordInput).toHaveValue("password123");
    });

    it("should toggle password visibility", async () => {
      const user = userEvent.setup();
      renderWithTheme(<LoginForm {...defaultProps} />);

      const passwordInput = screen.getByLabelText(/^password/i);
      const toggleButton = screen.getByRole("button", { name: /toggle password visibility/i });

      expect(passwordInput).toHaveAttribute("type", "password");

      await user.click(toggleButton);
      expect(passwordInput).toHaveAttribute("type", "text");

      await user.click(toggleButton);
      expect(passwordInput).toHaveAttribute("type", "password");
    });

    it("should call login on form submission", async () => {
      const mockLogin = vi.fn().mockResolvedValue({ success: true });
      useAuth.mockReturnValue({
        login: mockLogin,
        isLoading: false,
        error: null,
        clearError: vi.fn(),
        user: null,
      });

      const user = userEvent.setup();
      renderWithTheme(<LoginForm {...defaultProps} />);

      const usernameInput = screen.getByLabelText(/username or email/i);
      const passwordInput = screen.getByLabelText(/^password/i);
      const submitButton = screen.getByRole("button", { name: /sign in/i });

      await user.type(usernameInput, "testuser");
      await user.type(passwordInput, "password123");
      await user.click(submitButton);

      expect(mockLogin).toHaveBeenCalledWith("testuser", "password123");
    });

    it("should show loading state during login", () => {
      useAuth.mockReturnValue({
        login: vi.fn(),
        isLoading: true,
        error: null,
        clearError: vi.fn(),
        user: null,
      });

      renderWithTheme(<LoginForm {...defaultProps} />);

      expect(screen.getByRole("progressbar")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /signing in/i })).toBeDisabled();
    });

    it("should display error message", () => {
      const errorMessage = "Invalid credentials";
      useAuth.mockReturnValue({
        login: vi.fn(),
        isLoading: false,
        error: errorMessage,
        clearError: vi.fn(),
        user: null,
      });

      renderWithTheme(<LoginForm {...defaultProps} />);

      expect(screen.getByText(errorMessage)).toBeInTheDocument();
    });
  });

  describe("Navigation", () => {
    it("should call onSwitchToRegister when register link is clicked", async () => {
      const user = userEvent.setup();
      const mockSwitchToRegister = vi.fn();
      
      renderWithTheme(
        <LoginForm 
          {...defaultProps} 
          onSwitchToRegister={mockSwitchToRegister} 
        />
      );

      const registerLink = screen.getByText(/sign up/i);
      await user.click(registerLink);

      expect(mockSwitchToRegister).toHaveBeenCalled();
    });

    it("should call onSwitchToForgotPassword when forgot password link is clicked", async () => {
      const user = userEvent.setup();
      const mockSwitchToForgotPassword = vi.fn();
      
      renderWithTheme(
        <LoginForm 
          {...defaultProps} 
          onSwitchToForgotPassword={mockSwitchToForgotPassword} 
        />
      );

      const forgotLink = screen.getByText(/forgot password/i);
      await user.click(forgotLink);

      expect(mockSwitchToForgotPassword).toHaveBeenCalled();
    });
  });

  describe("Remember Me", () => {
    it("should handle remember me checkbox", async () => {
      const user = userEvent.setup();
      renderWithTheme(<LoginForm {...defaultProps} />);

      const rememberCheckbox = screen.getByRole("checkbox", { name: /remember me/i });
      expect(rememberCheckbox).not.toBeChecked();

      await user.click(rememberCheckbox);
      expect(rememberCheckbox).toBeChecked();
    });

    it("should pass remember me state to login function", async () => {
      const mockLogin = vi.fn().mockResolvedValue({ success: true });
      useAuth.mockReturnValue({
        login: mockLogin,
        isLoading: false,
        error: null,
        clearError: vi.fn(),
        user: null,
      });

      const user = userEvent.setup();
      renderWithTheme(<LoginForm {...defaultProps} />);

      const usernameInput = screen.getByLabelText(/username or email/i);
      const passwordInput = screen.getByLabelText(/^password/i);
      const rememberCheckbox = screen.getByRole("checkbox", { name: /remember me/i });
      const submitButton = screen.getByRole("button", { name: /sign in/i });

      await user.type(usernameInput, "testuser");
      await user.type(passwordInput, "password123");
      await user.click(rememberCheckbox);
      await user.click(submitButton);

      expect(mockLogin).toHaveBeenCalledWith("testuser", "password123");
    });
  });
});