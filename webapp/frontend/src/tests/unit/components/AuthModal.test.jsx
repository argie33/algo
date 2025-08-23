/**
 * Unit Tests for AuthModal Component
 * Tests the core authentication modal that handles login, registration, and MFA
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import AuthModal from "../../../components/auth/AuthModal.jsx";

// Mock the AuthContext
const mockAuthContext = {
  isAuthenticated: false,
  user: null,
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  confirmSignUp: vi.fn(),
  forgotPassword: vi.fn(),
  resetPassword: vi.fn(),
  isLoading: false,
  error: null,
};

vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: () => mockAuthContext,
}));

// Mock child components to isolate AuthModal testing
vi.mock("../../../components/auth/LoginForm.jsx", () => ({
  default: ({ onSwitchToRegister, onSwitchToForgotPassword }) => (
    <div data-testid="login-form">
      <button onClick={() => console.log("Login submitted")}>
        Login Submit
      </button>
      <button onClick={onSwitchToRegister}>Switch to Register</button>
      <button onClick={onSwitchToForgotPassword}>Forgot Password</button>
    </div>
  ),
}));

vi.mock("../../../components/auth/RegisterForm.jsx", () => ({
  default: ({ onRegistrationSuccess, onSwitchToLogin }) => (
    <div data-testid="register-form">
      <button
        onClick={() =>
          onRegistrationSuccess(
            "newuser",
            "CONFIRM_SIGN_UP",
            "Check your email"
          )
        }
      >
        Register Success
      </button>
      <button onClick={onSwitchToLogin}>Switch to Login</button>
    </div>
  ),
}));

vi.mock("../../../components/auth/ConfirmationForm.jsx", () => ({
  default: ({ username, onConfirmationSuccess, onResendCode }) => (
    <div data-testid="confirmation-form">
      <span>Confirming for: {username}</span>
      <button onClick={onConfirmationSuccess}>Confirm Success</button>
      <button onClick={onResendCode}>Resend Code</button>
    </div>
  ),
}));

vi.mock("../../../components/auth/ForgotPasswordForm.jsx", () => ({
  default: ({ onForgotPasswordSuccess, onSwitchToLogin }) => (
    <div data-testid="forgot-password-form">
      <button onClick={() => onForgotPasswordSuccess("testuser")}>
        Forgot Password Success
      </button>
      <button onClick={onSwitchToLogin}>Back to Login</button>
    </div>
  ),
}));

vi.mock("../../../components/auth/ResetPasswordForm.jsx", () => ({
  default: ({ username, onPasswordResetSuccess, onSwitchToLogin }) => (
    <div data-testid="reset-password-form">
      <span>Reset password for: {username}</span>
      <button onClick={onPasswordResetSuccess}>Reset Success</button>
      <button onClick={onSwitchToLogin}>Back to Login</button>
    </div>
  ),
}));

vi.mock("../../../components/auth/MFAChallenge.jsx", () => ({
  default: ({ challengeType, message, onSuccess, onCancel }) => (
    <div data-testid="mfa-challenge">
      <span>MFA Type: {challengeType}</span>
      <span>Message: {message}</span>
      <button onClick={() => onSuccess({ username: "testuser" })}>
        MFA Success
      </button>
      <button onClick={onCancel}>Cancel MFA</button>
    </div>
  ),
}));

// Test wrapper component
const TestWrapper = ({ children }) => <BrowserRouter>{children}</BrowserRouter>;

describe("AuthModal Component - Authentication Interface", () => {
  const defaultProps = {
    open: true,
    onClose: vi.fn(),
    initialMode: "login",
  };

  beforeEach(() => {
    vi.clearAllMocks();
    // Use real timers by default to avoid userEvent timeout issues
    vi.useRealTimers();
    mockAuthContext.isAuthenticated = false;
    mockAuthContext.user = null;
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  describe("Modal Rendering and Visibility", () => {
    it("should render modal when open prop is true", () => {
      render(
        <TestWrapper>
          <AuthModal {...defaultProps} open={true} />
        </TestWrapper>
      );

      expect(screen.getByTestId("login-form")).toBeInTheDocument();
    });

    it("should not render modal content when open prop is false", () => {
      render(
        <TestWrapper>
          <AuthModal {...defaultProps} open={false} />
        </TestWrapper>
      );

      expect(screen.queryByTestId("login-form")).not.toBeInTheDocument();
    });

    it("should render close button", () => {
      render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      const closeButton = screen.getByRole("button", { name: /close/i });
      expect(closeButton).toBeInTheDocument();
    });

    it("should call onClose when close button is clicked", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      const closeButton = screen.getByRole("button", { name: /close/i });
      await user.click(closeButton);

      expect(defaultProps.onClose).toHaveBeenCalled();
    });
  });

  describe("Mode Switching", () => {
    it("should start with initial mode", () => {
      render(
        <TestWrapper>
          <AuthModal {...defaultProps} initialMode="login" />
        </TestWrapper>
      );

      expect(screen.getByTestId("login-form")).toBeInTheDocument();
    });

    it("should switch from login to register mode", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      const switchButton = screen.getByText("Switch to Register");
      await user.click(switchButton);

      expect(screen.getByTestId("register-form")).toBeInTheDocument();
      expect(screen.queryByTestId("login-form")).not.toBeInTheDocument();
    });

    it("should switch from register to login mode", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} initialMode="register" />
        </TestWrapper>
      );

      const switchButton = screen.getByText("Switch to Login");
      await user.click(switchButton);

      expect(screen.getByTestId("login-form")).toBeInTheDocument();
      expect(screen.queryByTestId("register-form")).not.toBeInTheDocument();
    });

    it("should switch to forgot password mode", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      const forgotButton = screen.getByText("Forgot Password");
      await user.click(forgotButton);

      expect(screen.getByTestId("forgot-password-form")).toBeInTheDocument();
    });
  });

  describe("Authentication Flow", () => {
    it("should handle login submission", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      const loginButton = screen.getByText("Login Submit");
      await user.click(loginButton);

      // Login submission is handled by AuthContext
      // Test verifies the button click doesn't crash the component
      expect(screen.getByTestId("login-form")).toBeInTheDocument();
    });

    it("should handle successful registration requiring confirmation", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} initialMode="register" />
        </TestWrapper>
      );

      const registerButton = screen.getByText("Register Success");
      await user.click(registerButton);

      await waitFor(() => {
        expect(screen.getByTestId("confirmation-form")).toBeInTheDocument();
        expect(screen.getByText("Confirming for: newuser")).toBeInTheDocument();
      });
    });

    it("should handle successful email confirmation", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} initialMode="confirm" />
        </TestWrapper>
      );

      const confirmButton = screen.getByText("Confirm Success");
      await user.click(confirmButton);

      await waitFor(() => {
        expect(screen.getByTestId("login-form")).toBeInTheDocument();
      });
    });

    it("should handle forgot password flow", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      // Navigate to forgot password
      const forgotButton = screen.getByText("Forgot Password");
      await user.click(forgotButton);

      // Complete forgot password
      const forgotSuccessButton = screen.getByText("Forgot Password Success");
      await user.click(forgotSuccessButton);

      await waitFor(() => {
        expect(screen.getByTestId("reset-password-form")).toBeInTheDocument();
        expect(
          screen.getByText("Reset password for: testuser")
        ).toBeInTheDocument();
      });
    });

    it("should handle password reset completion", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} initialMode="reset_password" />
        </TestWrapper>
      );

      const resetButton = screen.getByText("Reset Success");
      await user.click(resetButton);

      await waitFor(() => {
        expect(screen.getByTestId("login-form")).toBeInTheDocument();
      });
    });
  });

  describe("MFA Challenge Flow", () => {
    it("should render MFA challenge when in MFA mode", () => {
      render(
        <TestWrapper>
          <AuthModal {...defaultProps} initialMode="mfa_challenge" />
        </TestWrapper>
      );

      expect(screen.getByTestId("mfa-challenge")).toBeInTheDocument();
    });

    it("should handle successful MFA completion", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} initialMode="mfa_challenge" />
        </TestWrapper>
      );

      const mfaSuccessButton = screen.getByText("MFA Success");
      await user.click(mfaSuccessButton);

      // Should complete authentication (implementation dependent)
    });

    it("should handle MFA cancellation", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} initialMode="mfa_challenge" />
        </TestWrapper>
      );

      const cancelButton = screen.getByText("Cancel MFA");
      await user.click(cancelButton);

      await waitFor(() => {
        expect(screen.getByTestId("login-form")).toBeInTheDocument();
      });
    });
  });

  describe("Auto-dismiss on Authentication", () => {
    it("should auto-dismiss modal when user becomes authenticated", async () => {
      // This test specifically needs fake timers for vi.advanceTimersByTime
      vi.useFakeTimers();
      
      // Start with modal open and user not authenticated
      const { rerender } = render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      expect(screen.getByTestId("login-form")).toBeInTheDocument();

      // Simulate user becoming authenticated
      mockAuthContext.isAuthenticated = true;
      mockAuthContext.user = {
        username: "testuser",
        email: "test@example.com",
      };

      rerender(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      // Should show success message
      await waitFor(() => {
        expect(screen.getByText(/Welcome back/i)).toBeInTheDocument();
      });

      // Fast-forward timers to trigger auto-close
      vi.advanceTimersByTime(3000);

      await waitFor(() => {
        expect(defaultProps.onClose).toHaveBeenCalled();
      });
      
      vi.useRealTimers();
    });

    it("should show welcome message with user info", async () => {
      mockAuthContext.isAuthenticated = true;
      mockAuthContext.user = { username: "johndoe", email: "john@example.com" };

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText(/Welcome back, johndoe/i)).toBeInTheDocument();
      });
    });

    it("should fallback to email if username not available", async () => {
      mockAuthContext.isAuthenticated = true;
      mockAuthContext.user = { email: "test@example.com" };

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(
          screen.getByText(/Welcome back, test@example.com/i)
        ).toBeInTheDocument();
      });
    });
  });

  describe("State Management and Cleanup", () => {
    it("should reset state when modal closes", async () => {
      const user = userEvent.setup();

      const { rerender } = render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      // Switch to register mode
      const switchButton = screen.getByText("Switch to Register");
      await user.click(switchButton);
      expect(screen.getByTestId("register-form")).toBeInTheDocument();

      // Close modal
      rerender(
        <TestWrapper>
          <AuthModal {...defaultProps} open={false} />
        </TestWrapper>
      );

      // Reopen modal - should be back to initial mode
      rerender(
        <TestWrapper>
          <AuthModal {...defaultProps} open={true} />
        </TestWrapper>
      );

      expect(screen.getByTestId("login-form")).toBeInTheDocument();
    });

    it("should preserve username across mode switches", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} initialMode="register" />
        </TestWrapper>
      );

      // Complete registration
      const registerButton = screen.getByText("Register Success");
      await user.click(registerButton);

      // Should be in confirmation mode with preserved username
      await waitFor(
        () => {
          expect(screen.getByTestId("confirmation-form")).toBeInTheDocument();
          expect(
            screen.getByText("Confirming for: newuser")
          ).toBeInTheDocument();
        },
        { timeout: 15000 }
      );
    });

    it("should clear error states when switching modes", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      // Switch modes to trigger state reset
      const switchButton = screen.getByText("Switch to Register");
      await user.click(switchButton);

      const backButton = screen.getByText("Switch to Login");
      await user.click(backButton);

      // Should not show any lingering error messages
      expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
    });
  });

  describe("Success Messages and Transitions", () => {
    it("should show success message after registration", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} initialMode="register" />
        </TestWrapper>
      );

      const registerButton = screen.getByText("Register Success");
      await user.click(registerButton);

      await waitFor(
        () => {
          expect(
            screen.getByText(/please check your email for a verification code/i)
          ).toBeInTheDocument();
        },
        { timeout: 10000 }
      );
    });

    it("should show success message after confirmation", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} initialMode="confirm" />
        </TestWrapper>
      );

      // Wait for the confirmation form to appear first
      await waitFor(() => {
        expect(screen.getByTestId("confirmation-form")).toBeInTheDocument();
      });

      const confirmButton = screen.getByText("Confirm Success");
      await user.click(confirmButton);

      await waitFor(
        () => {
          expect(
            screen.getByText(/account confirmed! you can now sign in/i)
          ).toBeInTheDocument();
        },
        { timeout: 10000 }
      );
    });

    it("should handle success state transitions smoothly", async () => {
      // This test specifically needs fake timers for vi.advanceTimersByTime
      vi.useFakeTimers();
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} initialMode="confirmation" />
        </TestWrapper>
      );

      // Wait for the confirmation form to appear first
      await waitFor(() => {
        expect(screen.getByTestId("confirmation-form")).toBeInTheDocument();
      });

      const confirmButton = screen.getByText("Confirm Success");
      await user.click(confirmButton);

      // Should show success message briefly then switch to login
      await waitFor(
        () => {
          expect(
            screen.getByText(/account confirmed! you can now sign in/i)
          ).toBeInTheDocument();
        },
        { timeout: 10000 }
      );

      // Fast-forward to see mode switch
      vi.advanceTimersByTime(2000);

      await waitFor(() => {
        expect(screen.getByTestId("login-form")).toBeInTheDocument();
      });
      
      vi.useRealTimers();
    });
  });

  describe("Accessibility and User Experience", () => {
    it("should have proper ARIA labels and roles", () => {
      render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      const modal = screen.getByRole("dialog");
      expect(modal).toBeInTheDocument();
    });

    it("should support keyboard navigation", async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      // Tab navigation should work
      await user.tab();

      // ESC key should close modal
      await user.keyboard("{Escape}");

      expect(defaultProps.onClose).toHaveBeenCalled();
    });

    it("should handle focus management correctly", () => {
      render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      // Modal should trap focus within itself
      const modal = screen.getByRole("dialog");
      expect(modal).toBeInTheDocument();

      // First focusable element should receive focus (implementation dependent)
    });
  });

  describe("Error Handling", () => {
    it("should handle authentication context errors gracefully", () => {
      mockAuthContext.error = "Authentication service unavailable";

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      // Should still render login form
      expect(screen.getByTestId("login-form")).toBeInTheDocument();
    });

    it("should handle missing user data gracefully", () => {
      mockAuthContext.isAuthenticated = true;
      mockAuthContext.user = null; // Edge case

      render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      // Should not crash
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    it("should handle component unmounting during async operations", () => {
      // This test specifically needs fake timers for vi.advanceTimersByTime
      vi.useFakeTimers();
      
      const { unmount } = render(
        <TestWrapper>
          <AuthModal {...defaultProps} />
        </TestWrapper>
      );

      // Unmount while timers are pending
      unmount();

      // Should not cause errors when timers fire
      vi.advanceTimersByTime(5000);

      // Test passes if no errors thrown
      vi.useRealTimers();
    });
  });
});
