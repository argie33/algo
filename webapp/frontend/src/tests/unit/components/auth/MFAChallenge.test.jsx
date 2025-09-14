import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import MFAChallenge from "../../../../components/auth/MFAChallenge";

// Mock AuthContext
const mockConfirmMFA = vi.fn();

vi.mock("../../../../contexts/AuthContext", () => ({
  useAuth: () => ({
    confirmMFA: mockConfirmMFA,
    isLoading: false,
    error: "",
  }),
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
    mockConfirmMFA.mockResolvedValue({ success: true });
  });

  test("renders MFA challenge form", () => {
    render(<MFAChallenge {...defaultProps} />);

    expect(screen.getByText("Multi-Factor Authentication")).toBeInTheDocument();
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
    render(<MFAChallenge {...defaultProps} />);

    const codeInput = screen.getByLabelText(/verification code/i);
    fireEvent.change(codeInput, { target: { value: "123456" } });

    const submitButton = screen.getByRole("button", { name: /verify/i });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockConfirmMFA).toHaveBeenCalledWith(expect.any(Object), "123456");
    });
  });

  test("calls onSuccess after successful verification", async () => {
    const onSuccess = vi.fn();
    mockConfirmMFA.mockResolvedValue({
      success: true,
      user: { username: "testuser" },
      tokens: { accessToken: "token123" },
    });

    render(<MFAChallenge {...defaultProps} onSuccess={onSuccess} />);

    const codeInput = screen.getByLabelText(/verification code/i);
    fireEvent.change(codeInput, { target: { value: "123456" } });

    const submitButton = screen.getByRole("button", { name: /verify/i });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledWith(
        expect.objectContaining({
          user: { username: "testuser" },
          tokens: { accessToken: "token123" },
        })
      );
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
    render(<MFAChallenge {...defaultProps} challengeType="TOTP_MFA" />);

    expect(screen.getByText("Multi-Factor Authentication")).toBeInTheDocument();
  });

  test("handles MFA failure", async () => {
    mockConfirmMFA.mockResolvedValue({
      success: false,
      error: "Invalid verification code",
    });

    render(<MFAChallenge {...defaultProps} />);

    const codeInput = screen.getByLabelText(/verification code/i);
    fireEvent.change(codeInput, { target: { value: "123456" } });

    const submitButton = screen.getByRole("button", { name: /verify/i });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText("Invalid verification code")).toBeInTheDocument();
    });
  });
});
