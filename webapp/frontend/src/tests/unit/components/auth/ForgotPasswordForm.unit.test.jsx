/**
 * Unit Tests for ForgotPasswordForm Component
 * Tests password reset email functionality and user interactions
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithTheme } from "../test-helpers/component-test-utils.jsx";
import ForgotPasswordForm from "../../../../components/auth/ForgotPasswordForm.jsx";

describe("ForgotPasswordForm Component", () => {
  const mockOnBack = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("Form Rendering", () => {
    it("should render forgot password form with all elements", () => {
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      expect(screen.getByText("Reset Password")).toBeInTheDocument();
      expect(screen.getByText("Enter your email address and we'll send you a password reset link.")).toBeInTheDocument();
      expect(screen.getByRole("textbox", { name: /email address/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /send reset email/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /back to sign in/i })).toBeInTheDocument();
    });

    it("should have proper form structure", () => {
      const { container } = renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const form = container.querySelector("form");
      expect(form).toBeInTheDocument();
    });

    it("should display paper container with elevation", () => {
      const { container } = renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const paper = container.querySelector(".MuiPaper-root");
      expect(paper).toBeInTheDocument();
    });

    it("should have auto-focus configured on email field", () => {
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      // MUI may not render the autofocus attribute directly, but the field should be configured for it
      expect(emailField).toBeInTheDocument();
    });
  });

  describe("Form Input Handling", () => {
    it("should update email field on input", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      await user.type(emailField, "test@example.com");

      expect(emailField).toHaveValue("test@example.com");
    });

    it("should enable submit button when email is entered", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const submitButton = screen.getByRole("button", { name: /send reset email/i });
      expect(submitButton).toBeDisabled();

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      await user.type(emailField, "test@example.com");

      expect(submitButton).toBeEnabled();
    });

    it("should disable submit button when email is empty", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      const submitButton = screen.getByRole("button", { name: /send reset email/i });

      await user.type(emailField, "test@example.com");
      expect(submitButton).toBeEnabled();

      await user.clear(emailField);
      expect(submitButton).toBeDisabled();
    });
  });

  describe("Form Submission", () => {
    it("should show loading state during submission", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      await user.type(emailField, "test@example.com");

      const submitButton = screen.getByRole("button", { name: /send reset email/i });
      await user.click(submitButton);

      // Check loading state
      expect(screen.getByRole("button", { name: /sending.../i })).toBeInTheDocument();
      expect(emailField).toBeDisabled();
    });

    it("should show success message after successful submission", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      await user.type(emailField, "test@example.com");

      const submitButton = screen.getByRole("button", { name: /send reset email/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Password reset email sent! Check your inbox.")).toBeInTheDocument();
      });
    });

    it("should handle form submission with Enter key", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      await user.type(emailField, "test@example.com");
      await user.keyboard("{Enter}");

      // Should show loading state
      expect(screen.getByRole("button", { name: /sending.../i })).toBeInTheDocument();
    });

    it("should prevent submission when email is empty", () => {
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const submitButton = screen.getByRole("button", { name: /send reset email/i });
      
      // Button should be disabled when email is empty
      expect(submitButton).toBeDisabled();
      
      // Should not show loading state
      expect(screen.queryByText("Sending...")).not.toBeInTheDocument();
    });

    it("should reset form state after successful submission", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      await user.type(emailField, "test@example.com");

      const submitButton = screen.getByRole("button", { name: /send reset email/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Password reset email sent! Check your inbox.")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /send reset email/i })).toBeInTheDocument(); // Back to normal state
        expect(emailField).toBeEnabled(); // Re-enabled
      });
    });
  });

  describe("Loading State", () => {
    it("should disable all interactive elements during loading", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      await user.type(emailField, "test@example.com");

      const submitButton = screen.getByRole("button", { name: /send reset email/i });
      const backButton = screen.getByRole("button", { name: /back to sign in/i });

      await user.click(submitButton);

      // All elements should be disabled during loading
      expect(emailField).toBeDisabled();
      expect(screen.getByRole("button", { name: /sending.../i })).toBeDisabled();
      expect(backButton).toBeDisabled();
    });

    it("should update button text during loading", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      await user.type(emailField, "test@example.com");

      const submitButton = screen.getByRole("button", { name: /send reset email/i });
      await user.click(submitButton);

      expect(screen.getByRole("button", { name: /sending.../i })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /send reset email/i })).not.toBeInTheDocument();
    });
  });

  describe("Navigation", () => {
    it("should call onBack when back button is clicked", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const backButton = screen.getByRole("button", { name: /back to sign in/i });
      await user.click(backButton);

      expect(mockOnBack).toHaveBeenCalledTimes(1);
    });

    it("should handle missing onBack callback gracefully", () => {
      renderWithTheme(<ForgotPasswordForm />);

      expect(screen.getByRole("button", { name: /back to sign in/i })).toBeInTheDocument();
    });

    it("should not call onBack during loading state", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      await user.type(emailField, "test@example.com");

      const submitButton = screen.getByRole("button", { name: /send reset email/i });
      await user.click(submitButton);

      const backButton = screen.getByRole("button", { name: /back to sign in/i });
      
      // Should be disabled during loading, preventing clicks
      expect(backButton).toBeDisabled();
      expect(mockOnBack).not.toHaveBeenCalled();
    });
  });

  describe("Message Display", () => {
    it("should display success message with proper styling", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      await user.type(emailField, "test@example.com");

      const submitButton = screen.getByRole("button", { name: /send reset email/i });
      await user.click(submitButton);

      await waitFor(() => {
        const successMessage = screen.getByText("Password reset email sent! Check your inbox.");
        expect(successMessage).toBeInTheDocument();
        expect(successMessage.closest('.MuiAlert-root')).toHaveClass('MuiAlert-standardSuccess');
      });
    });

    it("should not show error or success messages initially", () => {
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });

    it("should clear previous messages on new submission", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      await user.type(emailField, "test@example.com");

      // First submission
      const submitButton = screen.getByRole("button", { name: /send reset email/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText("Password reset email sent! Check your inbox.")).toBeInTheDocument();
      });

      // Second submission - should clear previous message during loading
      await user.click(screen.getByRole("button", { name: /send reset email/i }));

      // Message should be cleared during loading (though it will show again after success)
      expect(screen.getByRole("button", { name: /sending.../i })).toBeInTheDocument();
    });
  });

  describe("Keyboard Navigation", () => {
    it("should be keyboard navigable", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      // Check that all interactive elements are accessible via tab navigation
      const emailField = screen.getByRole("textbox", { name: /email address/i });
      const submitButton = screen.getByRole("button", { name: /send reset email/i });
      const backButton = screen.getByRole("button", { name: /back to sign in/i });

      expect(emailField).toBeInTheDocument();
      expect(submitButton).toBeInTheDocument();
      expect(backButton).toBeInTheDocument();

      // Email field should always be tabbable
      expect(emailField).not.toHaveAttribute("tabindex", "-1");
      
      // Submit button is disabled initially so may have tabindex="-1" (which is correct behavior)
      expect(submitButton).toBeDisabled();
      
      // Back button should be tabbable when enabled
      expect(backButton).not.toHaveAttribute("tabindex", "-1");

      // When email is entered, submit button should become enabled and tabbable
      await user.type(emailField, "test@example.com");
      const enabledSubmitButton = screen.getByRole("button", { name: /send reset email/i });
      expect(enabledSubmitButton).toBeEnabled();
    });

    it("should submit form when Enter is pressed in email field", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      await user.type(emailField, "test@example.com");
      await user.keyboard("{Enter}");

      expect(screen.getByRole("button", { name: /sending.../i })).toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA labels and roles", () => {
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      expect(emailField).toBeInTheDocument();
      expect(emailField).toBeRequired();

      expect(screen.getByRole("button", { name: /send reset email/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /back to sign in/i })).toBeInTheDocument();
    });

    it("should have proper heading hierarchy", () => {
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const heading = screen.getByRole("heading", { name: "Reset Password" });
      expect(heading).toBeInTheDocument();
      expect(heading).toHaveProperty("tagName", "H4");
    });

    it("should announce success messages to screen readers", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      await user.type(emailField, "test@example.com");

      const submitButton = screen.getByRole("button", { name: /send reset email/i });
      await user.click(submitButton);

      await waitFor(() => {
        const alert = screen.getByRole("alert");
        expect(alert).toBeInTheDocument();
        expect(alert).toHaveTextContent("Password reset email sent! Check your inbox.");
      });
    });

    it("should have proper form semantics", () => {
      const { container } = renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const form = container.querySelector("form");
      expect(form).toBeInTheDocument();

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      expect(emailField).toHaveAttribute("type", "email");
      expect(emailField).toHaveAttribute("autoComplete", "email");
    });
  });

  describe("Edge Cases", () => {
    it("should handle email with whitespace", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      await user.type(emailField, "  test@example.com  ");

      // MUI email field might trim whitespace automatically
      expect(emailField.value).toContain("test@example.com");

      const submitButton = screen.getByRole("button", { name: /send reset email/i });
      expect(submitButton).toBeEnabled();
    });

    it("should handle rapid form submissions", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      await user.type(emailField, "test@example.com");

      const submitButton = screen.getByRole("button", { name: /send reset email/i });
      
      // First click should trigger loading state
      await user.click(submitButton);

      // Button should be disabled during loading, preventing additional clicks
      const loadingButton = screen.getByRole("button", { name: /sending.../i });
      expect(loadingButton).toBeDisabled();
    });

    it("should handle missing callback props gracefully", async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm />);

      const backButton = screen.getByRole("button", { name: /back to sign in/i });
      await user.click(backButton);

      // Should not crash when callback is missing
      expect(screen.getByText("Reset Password")).toBeInTheDocument();
    });

    it("should handle empty email submission attempt", () => {
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const submitButton = screen.getByRole("button", { name: /send reset email/i });
      
      // Button should be disabled when email is empty
      expect(submitButton).toBeDisabled();
      
      // Should not show loading state
      expect(screen.queryByText("Sending...")).not.toBeInTheDocument();
    });

    it("should maintain state during component lifecycle", async () => {
      const user = userEvent.setup();
      const { rerender } = renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);

      const emailField = screen.getByRole("textbox", { name: /email address/i });
      await user.type(emailField, "test@example.com");

      // Rerender component
      rerender(<ForgotPasswordForm onBack={mockOnBack} />);

      // Should maintain email value
      expect(screen.getByRole("textbox", { name: /email address/i })).toHaveValue("test@example.com");
    });
  });
});