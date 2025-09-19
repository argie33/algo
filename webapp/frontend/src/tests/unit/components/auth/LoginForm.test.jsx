import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import LoginForm from "../../../../components/auth/LoginForm";

// Mock API service with standardized pattern
vi.mock("../../../../services/api.js", () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    login: vi.fn().mockResolvedValue({ success: true, data: { token: "mock-token" } }),
    register: vi.fn().mockResolvedValue({ success: true, data: {} }),
    logout: vi.fn().mockResolvedValue({ success: true }),
    resetPassword: vi.fn().mockResolvedValue({ success: true }),
    verifyEmail: vi.fn().mockResolvedValue({ success: true }),
    getTradingSignalsDaily: vi.fn().mockResolvedValue({ success: true, data: [] }),
    getPortfolioAnalytics: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getStockMetrics: vi.fn().mockResolvedValue({ success: true, data: {} }),
  },
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
}));

// Mock localStorage
const mockLocalStorage = {
  setItem: vi.fn(),
  getItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
};
Object.defineProperty(window, "localStorage", {
  value: mockLocalStorage,
});

// Mock AuthContext
const mockLogin = vi.fn();
const mockClearError = vi.fn();

vi.mock("../../../../contexts/AuthContext", () => ({
  useAuth: vi.fn(() => ({
    login: mockLogin,
    isLoading: false,
    error: "",
    clearError: mockClearError,
  })),
}));

describe("LoginForm", () => {
  const defaultProps = {
    onSwitchToRegister: vi.fn(),
    onSwitchToForgotPassword: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockLocalStorage.setItem.mockClear();
    mockLogin.mockResolvedValue({ success: true });
  });

  describe("Basic Rendering", () => {
    test("renders login form with all elements", () => {
      render(<LoginForm {...defaultProps} />);

      expect(
        screen.getByRole("heading", { name: "Sign In" })
      ).toBeInTheDocument();
      expect(
        screen.getByText("Access your Financial Dashboard")
      ).toBeInTheDocument();
      expect(
        screen.getByRole("textbox", { name: /username/i })
      ).toBeInTheDocument();
      expect(screen.getByText("Username or Email")).toBeInTheDocument(); // Label text
      expect(screen.getByText("Password")).toBeInTheDocument(); // Password label
      expect(screen.getByText("Remember me for 30 days")).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /sign in/i })
      ).toBeInTheDocument();
      expect(screen.getByText("Forgot password?")).toBeInTheDocument();
      expect(screen.getByText("Sign up here")).toBeInTheDocument();
    });

    test("renders password field with visibility toggle", () => {
      render(<LoginForm {...defaultProps} />);

      const passwordField = document.querySelector('input[type="password"]');
      const toggleButton =
        document.querySelector('[aria-label*="toggle"]') ||
        screen.queryByRole("button", { name: /toggle/i });

      expect(passwordField).toHaveAttribute("type", "password");
      expect(toggleButton).toBeInTheDocument();
    });

    test("renders remember me checkbox", () => {
      render(<LoginForm {...defaultProps} />);

      const checkbox = screen.getByRole("checkbox");
      expect(checkbox).toBeInTheDocument();
      expect(checkbox).not.toBeChecked();
    });
  });

  describe("Form Interactions", () => {
    test("updates username field", () => {
      render(<LoginForm {...defaultProps} />);

      const usernameField = screen.getByRole("textbox", { name: /username/i });
      fireEvent.change(usernameField, { target: { value: "testuser" } });

      expect(usernameField.value).toBe("testuser");
    });

    test("updates password field", () => {
      render(<LoginForm {...defaultProps} />);

      const passwordField = document.querySelector('input[type="password"]');
      fireEvent.change(passwordField, { target: { value: "password123" } });

      expect(passwordField.value).toBe("password123");
    });

    test("toggles password visibility", () => {
      render(<LoginForm {...defaultProps} />);

      const passwordField = document.querySelector('input[type="password"]');
      const toggleButton =
        document.querySelector('[aria-label*="toggle"]') ||
        screen.queryByRole("button", { name: /toggle/i });

      expect(passwordField).toHaveAttribute("type", "password");

      fireEvent.click(toggleButton);
      expect(passwordField).toHaveAttribute("type", "text");

      fireEvent.click(toggleButton);
      expect(passwordField).toHaveAttribute("type", "password");
    });

    test("toggles remember me checkbox", () => {
      render(<LoginForm {...defaultProps} />);

      const checkbox = screen.getByRole("checkbox");

      fireEvent.click(checkbox);
      expect(checkbox).toBeChecked();

      fireEvent.click(checkbox);
      expect(checkbox).not.toBeChecked();
    });
  });

  describe("Form Submission", () => {
    test("submits form with valid data", async () => {
      render(<LoginForm {...defaultProps} />);

      const usernameField = screen.getByRole("textbox", { name: /username/i });
      const passwordField = document.querySelector('input[type="password"]');
      const submitButton = screen.getByRole("button", { name: /sign in/i });

      fireEvent.change(usernameField, { target: { value: "testuser" } });
      fireEvent.change(passwordField, { target: { value: "password123" } });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(mockLogin).toHaveBeenCalledWith("testuser", "password123");
      });
    });

    test("shows validation error for empty fields", async () => {
      render(<LoginForm {...defaultProps} />);

      const submitButton = screen.getByRole("button", { name: /sign in/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(
          screen.getByText("Please enter both username and password")
        ).toBeInTheDocument();
      });

      expect(mockLogin).not.toHaveBeenCalled();
    });

    test("shows validation error for missing username", async () => {
      render(<LoginForm {...defaultProps} />);

      const passwordField = document.querySelector('input[type="password"]');
      const submitButton = screen.getByRole("button", { name: /sign in/i });

      fireEvent.change(passwordField, { target: { value: "password123" } });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(
          screen.getByText("Please enter both username and password")
        ).toBeInTheDocument();
      });
    });

    test("shows validation error for missing password", async () => {
      render(<LoginForm {...defaultProps} />);

      const usernameField = screen.getByRole("textbox", { name: /username/i });
      const submitButton = screen.getByRole("button", { name: /sign in/i });

      fireEvent.change(usernameField, { target: { value: "testuser" } });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(
          screen.getByText("Please enter both username and password")
        ).toBeInTheDocument();
      });
    });

    test("stores remember me preference in localStorage", async () => {
      render(<LoginForm {...defaultProps} />);

      const usernameField = screen.getByRole("textbox", { name: /username/i });
      const passwordField = document.querySelector('input[type="password"]');
      const checkbox = screen.getByRole("checkbox");
      const submitButton = screen.getByRole("button", { name: /sign in/i });

      fireEvent.change(usernameField, { target: { value: "testuser" } });
      fireEvent.change(passwordField, { target: { value: "password123" } });
      fireEvent.click(checkbox);
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
          "rememberMe",
          "true"
        );
      });
    });

    test("handles login failure with error message", async () => {
      mockLogin.mockResolvedValue({
        success: false,
        error: "Invalid credentials",
      });

      render(<LoginForm {...defaultProps} />);

      const usernameField = screen.getByRole("textbox", { name: /username/i });
      const passwordField = document.querySelector('input[type="password"]');
      const submitButton = screen.getByRole("button", { name: /sign in/i });

      fireEvent.change(usernameField, { target: { value: "testuser" } });
      fireEvent.change(passwordField, { target: { value: "wrongpass" } });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Invalid credentials")).toBeInTheDocument();
      });
    });
  });

  describe("Error Handling", () => {
    test("displays auth context error", async () => {
      // Override the AuthContext mock for this test
      const { useAuth } = await import("../../../../contexts/AuthContext");
      useAuth.mockReturnValueOnce({
        login: mockLogin,
        isLoading: false,
        error: "Authentication failed",
        clearError: mockClearError,
      });

      render(<LoginForm {...defaultProps} />);

      expect(screen.getByText("Authentication failed")).toBeInTheDocument();
    });

    test("clears auth context error when typing", async () => {
      // Override the AuthContext mock for this test
      const { useAuth } = await import("../../../../contexts/AuthContext");
      useAuth.mockReturnValueOnce({
        login: mockLogin,
        isLoading: false,
        error: "Authentication failed",
        clearError: mockClearError,
      });

      render(<LoginForm {...defaultProps} />);

      const usernameField = screen.getByRole("textbox", { name: /username/i });
      fireEvent.change(usernameField, { target: { value: "test" } });

      expect(mockClearError).toHaveBeenCalled();
    });

    test("clears local error when typing", async () => {
      render(<LoginForm {...defaultProps} />);

      // Trigger local error
      const submitButton = screen.getByRole("button", { name: /sign in/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(
          screen.getByText("Please enter both username and password")
        ).toBeInTheDocument();
      });

      // Type in field to clear error
      const usernameField = screen.getByRole("textbox", { name: /username/i });
      fireEvent.change(usernameField, { target: { value: "test" } });

      await waitFor(() => {
        expect(
          screen.queryByText("Please enter both username and password")
        ).not.toBeInTheDocument();
      });
    });
  });

  describe("Loading State", () => {
    test("disables form elements when loading", async () => {
      // Override the AuthContext mock for this test
      const { useAuth } = await import("../../../../contexts/AuthContext");
      useAuth.mockReturnValueOnce({
        login: mockLogin,
        isLoading: true,
        error: "",
        clearError: mockClearError,
      });

      render(<LoginForm {...defaultProps} />);

      expect(screen.getByRole("textbox", { name: /username/i })).toBeDisabled();
      expect(document.querySelector('input[type="password"]')).toBeDisabled();
      expect(screen.getByRole("checkbox")).toBeDisabled();
      expect(
        screen.getByRole("button", { name: /signing in.../i })
      ).toBeDisabled();
      expect(screen.getByText("Forgot password?")).toHaveAttribute("disabled");
      expect(screen.getByText("Sign up here")).toHaveAttribute("disabled");
    });

    test("shows loading text and spinner when loading", async () => {
      // Override the AuthContext mock for this test
      const { useAuth } = await import("../../../../contexts/AuthContext");
      useAuth.mockReturnValueOnce({
        login: mockLogin,
        isLoading: true,
        error: "",
        clearError: mockClearError,
      });

      render(<LoginForm {...defaultProps} />);

      expect(screen.getByText("Signing In...")).toBeInTheDocument();
      expect(screen.getByRole("progressbar")).toBeInTheDocument();
    });
  });

  describe("Navigation", () => {
    test("switches to register form", () => {
      const onSwitchToRegister = vi.fn();
      render(
        <LoginForm {...defaultProps} onSwitchToRegister={onSwitchToRegister} />
      );

      const signUpLink = screen.getByText("Sign up here");
      fireEvent.click(signUpLink);

      expect(onSwitchToRegister).toHaveBeenCalledTimes(1);
    });

    test("switches to forgot password form", () => {
      const onSwitchToForgotPassword = vi.fn();
      render(
        <LoginForm
          {...defaultProps}
          onSwitchToForgotPassword={onSwitchToForgotPassword}
        />
      );

      const forgotLink = screen.getByText("Forgot password?");
      fireEvent.click(forgotLink);

      expect(onSwitchToForgotPassword).toHaveBeenCalledTimes(1);
    });

    test("does not navigate when loading", async () => {
      // Override the AuthContext mock for this test
      const { useAuth } = await import("../../../../contexts/AuthContext");
      useAuth.mockReturnValueOnce({
        login: mockLogin,
        isLoading: true,
        error: "",
        clearError: mockClearError,
      });

      const onSwitchToRegister = vi.fn();
      const onSwitchToForgotPassword = vi.fn();

      render(
        <LoginForm
          {...defaultProps}
          onSwitchToRegister={onSwitchToRegister}
          onSwitchToForgotPassword={onSwitchToForgotPassword}
        />
      );

      const signUpLink = screen.getByText("Sign up here");
      const forgotLink = screen.getByText("Forgot password?");

      fireEvent.click(signUpLink);
      fireEvent.click(forgotLink);

      expect(onSwitchToRegister).not.toHaveBeenCalled();
      expect(onSwitchToForgotPassword).not.toHaveBeenCalled();
    });
  });

  describe("Accessibility", () => {
    test("has proper form labeling", () => {
      render(<LoginForm {...defaultProps} />);

      const form = screen.getByRole("form");
      expect(form).toBeInTheDocument();

      const usernameField = screen.getByRole("textbox", { name: /username/i });
      const passwordField = document.querySelector('input[type="password"]');

      expect(usernameField).toHaveAttribute("required");
      expect(passwordField).toHaveAttribute("required");
      expect(usernameField).toHaveAttribute("autoComplete", "username");
      expect(passwordField).toHaveAttribute("autoComplete", "current-password");
    });

    test("has proper button types", () => {
      render(<LoginForm {...defaultProps} />);

      const submitButton = screen.getByRole("button", { name: /sign in/i });
      expect(submitButton).toHaveAttribute("type", "submit");
    });

    test("has focus management", () => {
      render(<LoginForm {...defaultProps} />);

      const usernameField = screen.getByRole("textbox", { name: /username/i });
      // MUI TextField may not always pass autoFocus to the underlying input
      // Check if the field is focused or has the autoFocus attribute
      expect(
        usernameField === document.activeElement ||
          usernameField.hasAttribute("autoFocus")
      ).toBeTruthy();
    });
  });
});
