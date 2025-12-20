import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, test, expect, beforeEach, vi } from "vitest";
import ResetPasswordForm from "../../../../components/auth/ResetPasswordForm";

// Mock API service with standardized pattern
vi.mock("../../../../services/api.js", () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    login: vi.fn().mockResolvedValue({ success: true, data: { token: "mock-token" } }),
    register: vi.fn().mockResolvedValue({ success: true, data: {} }),
    logout: vi.fn().mockResolvedValue({ success: true }),
    resetPassword: vi.fn().mockResolvedValue({ success: true }),
    verifyMFA: vi.fn().mockResolvedValue({ success: true }),
    getTradingSignalsDaily: vi.fn().mockResolvedValue({ success: true, data: [] }),
    getPortfolioAnalytics: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getStockMetrics: vi.fn().mockResolvedValue({ success: true, data: {} }),
  },
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
}));

// Mock AuthContext
const mockConfirmForgotPassword = vi.fn();
const mockClearError = vi.fn();

vi.mock("../../../../contexts/AuthContext", () => ({
  useAuth: () => ({
    confirmForgotPassword: mockConfirmForgotPassword,
    isLoading: false,
    error: "",
    clearError: mockClearError,
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
    mockConfirmForgotPassword.mockResolvedValue({ success: true });
  });

  test("renders reset password form", () => {
    render(<ResetPasswordForm {...defaultProps} />);

    expect(screen.getByText("Set New Password")).toBeInTheDocument();
    expect(screen.getByLabelText(/reset code/i)).toBeInTheDocument();
    expect(document.getElementById("newPassword")).toBeInTheDocument();
    expect(document.getElementById("confirmPassword")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /reset password/i })
    ).toBeInTheDocument();
  });

  test("submits password reset", async () => {
    render(<ResetPasswordForm {...defaultProps} />);

    fireEvent.change(screen.getByLabelText(/reset code/i), {
      target: { value: "123456" },
    });
    fireEvent.change(document.getElementById("newPassword"), {
      target: { value: "NewPassword123!" },
    });
    fireEvent.change(document.getElementById("confirmPassword"), {
      target: { value: "NewPassword123!" },
    });

    const submitButton = screen.getByRole("button", {
      name: /reset password/i,
    });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockConfirmForgotPassword).toHaveBeenCalledWith(
        "testuser",
        "123456",
        "NewPassword123!"
      );
    });
  });

  test("shows validation error for password mismatch", async () => {
    render(<ResetPasswordForm {...defaultProps} />);

    fireEvent.change(screen.getByLabelText(/reset code/i), {
      target: { value: "123456" },
    });
    fireEvent.change(document.getElementById("newPassword"), {
      target: { value: "NewPassword123!" },
    });
    fireEvent.change(document.getElementById("confirmPassword"), {
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

    fireEvent.change(screen.getByLabelText(/reset code/i), {
      target: { value: "123456" },
    });
    fireEvent.change(document.getElementById("newPassword"), {
      target: { value: "NewPassword123!" },
    });
    fireEvent.change(document.getElementById("confirmPassword"), {
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
