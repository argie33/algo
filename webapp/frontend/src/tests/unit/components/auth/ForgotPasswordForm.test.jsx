import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from '../../setup/test-wrapper';
import { vi } from "vitest";
import ForgotPasswordForm from "../../../../components/auth/ForgotPasswordForm";

// Mock AuthContext
const mockForgotPassword = vi.fn();

vi.mock("../../../../contexts/AuthContext", () => ({
  useAuth: () => ({
    forgotPassword: mockForgotPassword,
  }),
}));

describe("ForgotPasswordForm", () => {
  const defaultProps = {
    onBack: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockForgotPassword.mockResolvedValue({ success: true, message: "Reset code sent. Check your email." });
  });

  test("renders forgot password form", () => {
    renderWithProviders(<ForgotPasswordForm {...defaultProps} />);

    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /send reset code/i })
    ).toBeInTheDocument();
  });

  test("submits email for password reset", async () => {
    renderWithProviders(<ForgotPasswordForm {...defaultProps} />);

    const emailInput = screen.getByLabelText(/email address/i);
    fireEvent.change(emailInput, { target: { value: "test@example.com" } });

    const submitButton = screen.getByRole("button", {
      name: /send reset code/i,
    });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/reset code sent/i)).toBeInTheDocument();
    });
  });

  test("shows success message after submission", async () => {
    renderWithProviders(<ForgotPasswordForm {...defaultProps} />);

    const emailInput = screen.getByLabelText(/email address/i);
    fireEvent.change(emailInput, { target: { value: "test@example.com" } });

    const submitButton = screen.getByRole("button", {
      name: /send reset code/i,
    });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText("Reset code sent. Check your email.")).toBeInTheDocument();
    });
  });

  test("disables submit button when email is empty", () => {
    renderWithProviders(<ForgotPasswordForm {...defaultProps} />);

    const submitButton = screen.getByRole("button", {
      name: /send reset code/i,
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
