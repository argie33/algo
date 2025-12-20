import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import MFAChallenge from "../../../../components/auth/MFAChallenge";

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

describe("MFAChallenge", () => {
  const defaultProps = {
    challengeType: "SMS_MFA",
    message: "Please enter the verification code sent to your device.",
    onSuccess: vi.fn(),
    onCancel: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("renders MFA challenge form", () => {
    render(<MFAChallenge {...defaultProps} />);

    expect(screen.getByText("SMS Verification")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Please enter the verification code sent to your device."
      )
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/verification code/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /verify/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
  });

  test("submits MFA code", async () => {
    const onSuccess = vi.fn();
    render(<MFAChallenge {...defaultProps} onSuccess={onSuccess} />);

    const codeInput = screen.getByLabelText(/verification code/i);
    fireEvent.change(codeInput, { target: { value: "123456" } });

    const submitButton = screen.getByRole("button", { name: /verify/i });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith({
        username: "testuser",
        code: "123456",
        challengeType: "SMS_MFA",
      });
    });
  });

  test("calls onSuccess after successful verification", async () => {
    const onSuccess = vi.fn();
    render(<MFAChallenge {...defaultProps} onSuccess={onSuccess} />);

    const codeInput = screen.getByLabelText(/verification code/i);
    fireEvent.change(codeInput, { target: { value: "123456" } });

    const submitButton = screen.getByRole("button", { name: /verify/i });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith({
        username: "testuser",
        code: "123456",
        challengeType: "SMS_MFA",
      });
    });
  });

  test("shows validation error for empty code", async () => {
    render(<MFAChallenge {...defaultProps} />);

    const submitButton = screen.getByRole("button", { name: /verify/i });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(
        screen.getByText(/please enter the verification code/i)
      ).toBeInTheDocument();
    });
  });

  test("calls onCancel when cancel button is clicked", () => {
    const onCancel = vi.fn();
    render(<MFAChallenge {...defaultProps} onCancel={onCancel} />);

    const cancelButton = screen.getByRole("button", { name: /cancel/i });
    fireEvent.click(cancelButton);

    expect(onCancel).toHaveBeenCalled();
  });

  test("displays different challenge types", () => {
    render(<MFAChallenge {...defaultProps} challengeType="SOFTWARE_TOKEN_MFA" />);

    expect(screen.getByText("Authenticator App")).toBeInTheDocument();
  });

  test("shows loading state when verifying", async () => {
    render(<MFAChallenge {...defaultProps} />);

    const codeInput = screen.getByLabelText(/verification code/i);
    fireEvent.change(codeInput, { target: { value: "123456" } });

    const submitButton = screen.getByRole("button", { name: /verify/i });

    expect(submitButton).not.toBeDisabled();
    expect(submitButton).toHaveTextContent("Verify");
  });
});
