import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import ResetPasswordForm from "../../../../components/auth/ResetPasswordForm";

// Mock AuthContext
const mockForgotPasswordSubmit = vi.fn();

vi.mock("../../../../contexts/AuthContext", () => ({
  useAuth: () => ({
    forgotPasswordSubmit: mockForgotPasswordSubmit,
    isLoading: false,
    error: "",
  }),
}));

describe("ResetPasswordForm", () => {
  const defaultProps = {
    username: "testuser",
    onPasswordResetSuccess: vi.fn(),
    onSwitchToLogin: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockForgotPasswordSubmit.mockResolvedValue({ success: true });
  });

  test("renders reset password form", () => {
    render(<ResetPasswordForm {...defaultProps} />);

    expect(screen.getByText("Set New Password")).toBeInTheDocument();
    expect(screen.getByLabelText(/verification code/i)).toBeInTheDocument();
    expect(screen.getByLabelText("New Password")).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm new password/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /reset password/i })
    ).toBeInTheDocument();
  });

  test("submits password reset", async () => {
    render(<ResetPasswordForm {...defaultProps} />);

    fireEvent.change(screen.getByLabelText(/verification code/i), {
      target: { value: "123456" },
    });
    fireEvent.change(screen.getByLabelText("New Password"), {
      target: { value: "NewPassword123!" },
    });
    fireEvent.change(screen.getByLabelText(/confirm new password/i), {
      target: { value: "NewPassword123!" },
    });

    const submitButton = screen.getByRole("button", {
      name: /reset password/i,
    });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockForgotPasswordSubmit).toHaveBeenCalledWith(
        "testuser",
        "123456",
        "NewPassword123!"
      );
    });
  });

  test("shows validation error for password mismatch", async () => {
    render(<ResetPasswordForm {...defaultProps} />);

    fireEvent.change(screen.getByLabelText(/verification code/i), {
      target: { value: "123456" },
    });
    fireEvent.change(screen.getByLabelText("New Password"), {
      target: { value: "NewPassword123!" },
    });
    fireEvent.change(screen.getByLabelText(/confirm new password/i), {
      target: { value: "Different123!" },
    });

    const submitButton = screen.getByRole("button", {
      name: /reset password/i,
    });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
    });
  });

  test("calls onPasswordResetSuccess on success", async () => {
    const onPasswordResetSuccess = vi.fn();
    render(
      <ResetPasswordForm
        {...defaultProps}
        onPasswordResetSuccess={onPasswordResetSuccess}
      />
    );

    fireEvent.change(screen.getByLabelText(/verification code/i), {
      target: { value: "123456" },
    });
    fireEvent.change(screen.getByLabelText("New Password"), {
      target: { value: "NewPassword123!" },
    });
    fireEvent.change(screen.getByLabelText(/confirm new password/i), {
      target: { value: "NewPassword123!" },
    });

    const submitButton = screen.getByRole("button", {
      name: /reset password/i,
    });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(onPasswordResetSuccess).toHaveBeenCalled();
    });
  });

  test("switches back to login", () => {
    const onSwitchToLogin = vi.fn();
    render(
      <ResetPasswordForm {...defaultProps} onSwitchToLogin={onSwitchToLogin} />
    );

    const backButton = screen.getByText(/back to sign in/i);
    fireEvent.click(backButton);

    expect(onSwitchToLogin).toHaveBeenCalled();
  });
});
