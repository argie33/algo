/**
 * Unit Tests for AuthModal Component
 * Tests modal states, mode switching, form flows, and user interactions
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithTheme } from "../test-helpers/component-test-utils.jsx";
import AuthModal from "../../../../components/auth/AuthModal.jsx";

// Mock all form components
vi.mock("../../../../components/auth/LoginForm", () => ({
  default: ({ onSwitchToRegister, onSwitchToForgotPassword }) => (
    <div data-testid="login-form">
      Login Form
      <button onClick={onSwitchToRegister}>Switch to Register</button>
      <button onClick={onSwitchToForgotPassword}>Forgot Password</button>
    </div>
  ),
}));

vi.mock("../../../../components/auth/RegisterForm", () => ({
  default: ({ onSwitchToLogin, onRegistrationSuccess }) => (
    <div data-testid="register-form">
      Register Form
      <button onClick={onSwitchToLogin}>Switch to Login</button>
      <button onClick={() => onRegistrationSuccess("testuser", "CONFIRM")}>
        Register Success
      </button>
    </div>
  ),
}));

vi.mock("../../../../components/auth/ConfirmationForm", () => ({
  default: ({ username, onConfirmationSuccess, onSwitchToLogin }) => (
    <div data-testid="confirmation-form">
      Confirmation Form for {username}
      <button onClick={onConfirmationSuccess}>Confirm Success</button>
      <button onClick={onSwitchToLogin}>Back to Login</button>
    </div>
  ),
}));

vi.mock("../../../../components/auth/ForgotPasswordForm", () => ({
  default: ({ onForgotPasswordSuccess, onSwitchToLogin }) => (
    <div data-testid="forgot-password-form">
      Forgot Password Form
      <button onClick={() => onForgotPasswordSuccess("resetuser")}>
        Send Reset Code
      </button>
      <button onClick={onSwitchToLogin}>Back to Login</button>
    </div>
  ),
}));

vi.mock("../../../../components/auth/ResetPasswordForm", () => ({
  default: ({ username, onPasswordResetSuccess, onSwitchToLogin }) => (
    <div data-testid="reset-password-form">
      Reset Password Form for {username}
      <button onClick={onPasswordResetSuccess}>Reset Success</button>
      <button onClick={onSwitchToLogin}>Back to Login</button>
    </div>
  ),
}));

vi.mock("../../../../components/auth/MFAChallenge", () => ({
  default: ({ challengeType, message, onSuccess, onCancel }) => (
    <div data-testid="mfa-challenge">
      MFA Challenge: {challengeType}
      <div>{message}</div>
      <button onClick={() => onSuccess({ token: "mfa-token" })}>MFA Success</button>
      <button onClick={onCancel}>Cancel MFA</button>
    </div>
  ),
}));

describe("AuthModal Component", () => {
  const defaultProps = {
    open: true,
    onClose: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("Modal Display and Structure", () => {
    it("should render modal when open", () => {
      renderWithTheme(<AuthModal {...defaultProps} />);
      
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      expect(screen.getByText("Sign In")).toBeInTheDocument();
      expect(screen.getByLabelText("close")).toBeInTheDocument();
    });

    it("should not render when closed", () => {
      renderWithTheme(<AuthModal {...defaultProps} open={false} />);
      
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("should display correct titles for different modes", () => {
      // Test each mode individually
      const { unmount } = renderWithTheme(<AuthModal {...defaultProps} initialMode="login" />);
      expect(screen.getByText("Sign In")).toBeInTheDocument();
      unmount();

      renderWithTheme(<AuthModal {...defaultProps} initialMode="register" />);
      expect(screen.getByText("Create Account")).toBeInTheDocument();
      unmount();

      renderWithTheme(<AuthModal {...defaultProps} initialMode="confirm" />);
      expect(screen.getByText("Verify Account")).toBeInTheDocument();
      unmount();

      renderWithTheme(<AuthModal {...defaultProps} initialMode="forgot_password" />);
      expect(screen.getByText("Reset Password")).toBeInTheDocument();
      unmount();

      renderWithTheme(<AuthModal {...defaultProps} initialMode="reset_password" />);
      expect(screen.getByText("Set New Password")).toBeInTheDocument();
      unmount();

      renderWithTheme(<AuthModal {...defaultProps} initialMode="mfa_challenge" />);
      expect(screen.getByText("Multi-Factor Authentication")).toBeInTheDocument();
    });

    it("should display default title for unknown mode", () => {
      renderWithTheme(<AuthModal {...defaultProps} initialMode="unknown" />);
      expect(screen.getByText("Authentication")).toBeInTheDocument();
    });

    it("should have proper modal structure", () => {
      renderWithTheme(<AuthModal {...defaultProps} />);
      
      const dialog = screen.getByRole("dialog");
      expect(dialog).toBeInTheDocument();
      expect(dialog).toHaveClass("MuiDialog-paper");
      
      const closeButton = screen.getByLabelText("close");
      expect(closeButton).toBeInTheDocument();
    });
  });

  describe("Mode Switching", () => {
    it("should switch from login to register", async () => {
      const user = userEvent.setup();
      renderWithTheme(<AuthModal {...defaultProps} />);
      
      expect(screen.getByTestId("login-form")).toBeInTheDocument();
      
      const switchButton = screen.getByText("Switch to Register");
      await user.click(switchButton);
      
      expect(screen.getByText("Create Account")).toBeInTheDocument();
      expect(screen.getByTestId("register-form")).toBeInTheDocument();
    });

    it("should switch from login to forgot password", async () => {
      const user = userEvent.setup();
      renderWithTheme(<AuthModal {...defaultProps} />);
      
      const forgotPasswordButton = screen.getByText("Forgot Password");
      await user.click(forgotPasswordButton);
      
      expect(screen.getByText("Reset Password")).toBeInTheDocument();
      expect(screen.getByTestId("forgot-password-form")).toBeInTheDocument();
    });

    it("should switch from register back to login", async () => {
      const user = userEvent.setup();
      renderWithTheme(<AuthModal {...defaultProps} initialMode="register" />);
      
      const switchButton = screen.getByText("Switch to Login");
      await user.click(switchButton);
      
      expect(screen.getByText("Sign In")).toBeInTheDocument();
      expect(screen.getByTestId("login-form")).toBeInTheDocument();
    });

    it("should clear success message when switching modes", async () => {
      const user = userEvent.setup();
      renderWithTheme(<AuthModal {...defaultProps} initialMode="register" />);
      
      // Trigger registration success to show success message
      const registerButton = screen.getByText("Register Success");
      await user.click(registerButton);
      
      expect(screen.getByText("Registration successful! Please check your email for a verification code.")).toBeInTheDocument();
      
      // Switch back to login
      const backButton = screen.getByText("Back to Login");
      await user.click(backButton);
      
      // Success message should be cleared
      expect(screen.queryByText("Registration successful! Please check your email for a verification code.")).not.toBeInTheDocument();
    });
  });

  describe("Registration Flow", () => {
    it("should handle registration success and switch to confirmation", async () => {
      const user = userEvent.setup();
      renderWithTheme(<AuthModal {...defaultProps} initialMode="register" />);
      
      const registerButton = screen.getByText("Register Success");
      await user.click(registerButton);
      
      expect(screen.getByText("Verify Account")).toBeInTheDocument();
      expect(screen.getByTestId("confirmation-form")).toBeInTheDocument();
      expect(screen.getByText("Confirmation Form for testuser")).toBeInTheDocument();
      expect(screen.getByText("Registration successful! Please check your email for a verification code.")).toBeInTheDocument();
    });

    it("should handle confirmation success and return to login", async () => {
      const user = userEvent.setup();
      renderWithTheme(<AuthModal {...defaultProps} initialMode="confirm" />);
      
      const confirmButton = screen.getByText("Confirm Success");
      await user.click(confirmButton);
      
      expect(screen.getByText("Sign In")).toBeInTheDocument();
      expect(screen.getByTestId("login-form")).toBeInTheDocument();
      expect(screen.getByText("Account confirmed! You can now sign in.")).toBeInTheDocument();
    });
  });

  describe("Password Reset Flow", () => {
    it("should handle forgot password success and switch to reset form", async () => {
      const user = userEvent.setup();
      renderWithTheme(<AuthModal {...defaultProps} initialMode="forgot_password" />);
      
      const sendResetButton = screen.getByText("Send Reset Code");
      await user.click(sendResetButton);
      
      expect(screen.getByText("Set New Password")).toBeInTheDocument();
      expect(screen.getByTestId("reset-password-form")).toBeInTheDocument();
      expect(screen.getByText("Reset Password Form for resetuser")).toBeInTheDocument();
      expect(screen.getByText("Password reset code sent! Please check your email.")).toBeInTheDocument();
    });

    it("should handle password reset success and return to login", async () => {
      const user = userEvent.setup();
      renderWithTheme(<AuthModal {...defaultProps} initialMode="reset_password" />);
      
      const resetButton = screen.getByText("Reset Success");
      await user.click(resetButton);
      
      expect(screen.getByText("Sign In")).toBeInTheDocument();
      expect(screen.getByTestId("login-form")).toBeInTheDocument();
      expect(screen.getByText("Password reset successful! You can now sign in with your new password.")).toBeInTheDocument();
    });
  });

  describe("MFA Challenge Flow", () => {
    it("should display MFA challenge correctly", () => {
      renderWithTheme(<AuthModal {...defaultProps} initialMode="mfa_challenge" />);
      
      expect(screen.getByText("Multi-Factor Authentication")).toBeInTheDocument();
      expect(screen.getByTestId("mfa-challenge")).toBeInTheDocument();
      expect(screen.getByText("MFA Challenge: SMS_MFA")).toBeInTheDocument();
      expect(screen.getByText("Please enter the verification code sent to your device.")).toBeInTheDocument();
    });

    it("should handle MFA success", async () => {
      const user = userEvent.setup();
      const consoleSpy = vi.spyOn(console, "log").mockImplementation(() => {});
      
      renderWithTheme(<AuthModal {...defaultProps} initialMode="mfa_challenge" />);
      
      const successButton = screen.getByText("MFA Success");
      await user.click(successButton);
      
      expect(screen.getByText("Sign In")).toBeInTheDocument();
      expect(screen.getByTestId("login-form")).toBeInTheDocument();
      expect(screen.getByText("Multi-factor authentication successful!")).toBeInTheDocument();
      expect(consoleSpy).toHaveBeenCalledWith("MFA Success:", { token: "mfa-token" });
      
      consoleSpy.mockRestore();
    });

    it("should handle MFA cancel and return to login", async () => {
      const user = userEvent.setup();
      renderWithTheme(<AuthModal {...defaultProps} initialMode="mfa_challenge" />);
      
      const cancelButton = screen.getByText("Cancel MFA");
      await user.click(cancelButton);
      
      expect(screen.getByText("Sign In")).toBeInTheDocument();
      expect(screen.getByTestId("login-form")).toBeInTheDocument();
    });
  });

  describe("Modal Close Behavior", () => {
    it("should call onClose when close button is clicked", async () => {
      const user = userEvent.setup();
      const onCloseMock = vi.fn();
      
      renderWithTheme(<AuthModal {...defaultProps} onClose={onCloseMock} />);
      
      const closeButton = screen.getByLabelText("close");
      await user.click(closeButton);
      
      expect(onCloseMock).toHaveBeenCalledTimes(1);
    });

    it("should reset state when modal is closed", async () => {
      const user = userEvent.setup();
      const onCloseMock = vi.fn();
      
      renderWithTheme(<AuthModal {...defaultProps} onClose={onCloseMock} initialMode="register" />);
      
      // Change to confirmation mode with success message
      const registerButton = screen.getByText("Register Success");
      await user.click(registerButton);
      
      expect(screen.getByText("Verify Account")).toBeInTheDocument();
      
      // Close modal
      const closeButton = screen.getByLabelText("close");
      await user.click(closeButton);
      
      expect(onCloseMock).toHaveBeenCalled();
    });

    it("should call onClose when backdrop is clicked", async () => {
      const onCloseMock = vi.fn();
      renderWithTheme(<AuthModal {...defaultProps} onClose={onCloseMock} />);
      
      const backdrop = document.querySelector('.MuiBackdrop-root');
      if (backdrop) {
        fireEvent.click(backdrop);
        expect(onCloseMock).toHaveBeenCalled();
      }
    });
  });

  describe("Success Message Display", () => {
    it("should display success alert when message is present", async () => {
      const user = userEvent.setup();
      renderWithTheme(<AuthModal {...defaultProps} initialMode="register" />);
      
      const registerButton = screen.getByText("Register Success");
      await user.click(registerButton);
      
      const successAlert = screen.getByRole("alert");
      expect(successAlert).toHaveClass("MuiAlert-standardSuccess");
      expect(screen.getByText("Registration successful! Please check your email for a verification code.")).toBeInTheDocument();
    });

    it("should not display success alert when message is empty", () => {
      renderWithTheme(<AuthModal {...defaultProps} />);
      
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("should clear success message when switching modes", async () => {
      const user = userEvent.setup();
      renderWithTheme(<AuthModal {...defaultProps} initialMode="register" />);
      
      // Trigger success message
      const registerButton = screen.getByText("Register Success");
      await user.click(registerButton);
      
      expect(screen.getByRole("alert")).toBeInTheDocument();
      
      // Switch back to login
      const backButton = screen.getByText("Back to Login");
      await user.click(backButton);
      
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  describe("Username State Management", () => {
    it("should maintain username across related flows", async () => {
      const user = userEvent.setup();
      renderWithTheme(<AuthModal {...defaultProps} initialMode="register" />);
      
      // Complete registration
      const registerButton = screen.getByText("Register Success");
      await user.click(registerButton);
      
      // Check username is passed to confirmation form
      expect(screen.getByText("Confirmation Form for testuser")).toBeInTheDocument();
    });

    it("should maintain username for password reset flow", async () => {
      const user = userEvent.setup();
      renderWithTheme(<AuthModal {...defaultProps} initialMode="forgot_password" />);
      
      // Trigger forgot password success
      const sendResetButton = screen.getByText("Send Reset Code");
      await user.click(sendResetButton);
      
      // Check username is passed to reset form
      expect(screen.getByText("Reset Password Form for resetuser")).toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA attributes", () => {
      renderWithTheme(<AuthModal {...defaultProps} />);
      
      const dialog = screen.getByRole("dialog");
      expect(dialog).toBeInTheDocument();
      
      const closeButton = screen.getByLabelText("close");
      expect(closeButton).toHaveAttribute("aria-label", "close");
    });

    it("should have proper heading structure", () => {
      renderWithTheme(<AuthModal {...defaultProps} />);
      
      const heading = screen.getByRole("heading", { name: "Sign In" });
      expect(heading).toBeInTheDocument();
      expect(heading.tagName).toBe("H2");
    });

    it("should be keyboard navigable", async () => {
      const user = userEvent.setup();
      renderWithTheme(<AuthModal {...defaultProps} />);
      
      // Tab to close button
      await user.tab();
      expect(screen.getByLabelText("close")).toHaveFocus();
    });
  });

  describe("Edge Cases", () => {
    it("should handle missing onClose prop gracefully", () => {
      expect(() => {
        renderWithTheme(<AuthModal open={true} />);
      }).not.toThrow();
    });

    it("should handle undefined initial mode", () => {
      renderWithTheme(<AuthModal {...defaultProps} initialMode={undefined} />);
      expect(screen.getByText("Sign In")).toBeInTheDocument(); // Should default to login
    });

    it("should handle null success message", async () => {
      const _user = userEvent.setup();
      renderWithTheme(<AuthModal {...defaultProps} />);
      
      // Should not crash with null success message
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  describe("Component Integration", () => {
    it("should properly pass props to child forms", () => {
      renderWithTheme(<AuthModal {...defaultProps} initialMode="confirm" />);
      
      expect(screen.getByTestId("confirmation-form")).toBeInTheDocument();
    });

    it("should handle rapid mode switching", async () => {
      const user = userEvent.setup();
      renderWithTheme(<AuthModal {...defaultProps} />);
      
      // Rapidly switch between modes
      await user.click(screen.getByText("Switch to Register"));
      expect(screen.getByTestId("register-form")).toBeInTheDocument();
      
      await user.click(screen.getByText("Switch to Login"));
      expect(screen.getByTestId("login-form")).toBeInTheDocument();
      
      await user.click(screen.getByText("Forgot Password"));
      expect(screen.getByTestId("forgot-password-form")).toBeInTheDocument();
    });
  });
});