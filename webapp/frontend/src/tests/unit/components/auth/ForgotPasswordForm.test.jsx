import { render, screen, fireEvent, waitFor } from "@testing-library/react";
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
    render(<ForgotPasswordForm {...defaultProps} />);

    expect(screen.getByText("Reset Password")).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /send reset email/i })
    ).toBeInTheDocument();
  });

  test("submits email for password reset", async () => {
    render(<ForgotPasswordForm {...defaultProps} />);

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
    render(<ForgotPasswordForm {...defaultProps} />);

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
    render(<ForgotPasswordForm {...defaultProps} />);

    const submitButton = screen.getByRole("button", {
      name: /send reset email/i,
    });

    expect(submitButton).toBeDisabled();
  });

  test("switches back to login", () => {
    const onBack = vi.fn();
    render(<ForgotPasswordForm {...defaultProps} onBack={onBack} />);

    const backButton = screen.getByText("Back to Sign In");
    fireEvent.click(backButton);

    expect(onBack).toHaveBeenCalled();
  });
});