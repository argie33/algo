import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from '../../setup/test-wrapper';
import { vi } from "vitest";
import ForgotPasswordForm from "../../../../components/auth/ForgotPasswordForm";

describe("ForgotPasswordForm", () => {
  const defaultProps = {
    onBack: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("renders forgot password form", () => {
    renderWithProviders(<ForgotPasswordForm {...defaultProps} />);

    expect(screen.getByText("Reset Password")).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /send reset email/i })
    ).toBeInTheDocument();
  });

  test("submits email for password reset", async () => {
    renderWithProviders(<ForgotPasswordForm {...defaultProps} />);

    const emailInput = screen.getByLabelText(/email address/i);
    fireEvent.change(emailInput, { target: { value: "test@example.com" } });

    const submitButton = screen.getByRole("button", {
      name: /send reset email/i,
    });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/password reset email sent/i)).toBeInTheDocument();
    });
  });

  test("shows success message after submission", async () => {
    renderWithProviders(<ForgotPasswordForm {...defaultProps} />);

    const emailInput = screen.getByLabelText(/email address/i);
    fireEvent.change(emailInput, { target: { value: "test@example.com" } });

    const submitButton = screen.getByRole("button", {
      name: /send reset email/i,
    });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText("Password reset email sent! Check your inbox.")).toBeInTheDocument();
    });
  });

  test("disables submit button when email is empty", () => {
    renderWithProviders(<ForgotPasswordForm {...defaultProps} />);

    const submitButton = screen.getByRole("button", {
      name: /send reset email/i,
    });

    expect(submitButton).toBeDisabled();
  });

  test("switches back to login", () => {
    const onBack = vi.fn();
    renderWithProviders(<ForgotPasswordForm {...defaultProps} onBack={onBack} />);

    const backButton = screen.getByText("Back to Sign In");
    fireEvent.click(backButton);

    expect(onBack).toHaveBeenCalled();
  });
});
