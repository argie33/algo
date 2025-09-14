import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import ConfirmationForm from "../../../../components/auth/ConfirmationForm";

// Mock AuthContext
const mockConfirmRegistration = vi.fn();
const mockResendConfirmationCode = vi.fn();
const mockClearError = vi.fn();

vi.mock("../../../../contexts/AuthContext", () => ({
  useAuth: () => ({
    confirmRegistration: mockConfirmRegistration,
    resendConfirmationCode: mockResendConfirmationCode,
    clearError: mockClearError,
    isLoading: false,
    error: "",
  }),
}));

describe("ConfirmationForm", () => {
  const defaultProps = {
    username: "testuser",
    onConfirmationSuccess: vi.fn(),
    onSwitchToLogin: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockConfirmRegistration.mockResolvedValue({ success: true });
    mockResendConfirmationCode.mockResolvedValue({
      success: true,
      message: "Code sent",
    });
  });

  test("renders confirmation form", () => {
    render(<ConfirmationForm {...defaultProps} />);

    expect(
      screen.getByRole("heading", { name: "Verify Account" })
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/verification code/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /verify account/i })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/enter the verification code sent to your email/i)
    ).toBeInTheDocument();
  });

  test("submits verification code", async () => {
    render(<ConfirmationForm {...defaultProps} />);

    const codeInput = screen.getByLabelText(/verification code/i);
    fireEvent.change(codeInput, { target: { value: "123456" } });

    const submitButton = screen.getByRole("button", {
      name: /verify account/i,
    });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(mockConfirmRegistration).toHaveBeenCalledWith(
        "testuser",
        "123456"
      );
    });
  });

  test("calls onConfirmationSuccess on success", async () => {
    const onConfirmationSuccess = vi.fn();
    render(
      <ConfirmationForm
        {...defaultProps}
        onConfirmationSuccess={onConfirmationSuccess}
      />
    );

    const codeInput = screen.getByLabelText(/verification code/i);
    fireEvent.change(codeInput, { target: { value: "123456" } });

    const submitButton = screen.getByRole("button", {
      name: /verify account/i,
    });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(onConfirmationSuccess).toHaveBeenCalled();
    });
  });

  test("resends verification code", async () => {
    render(<ConfirmationForm {...defaultProps} />);

    const resendButton = screen.getByText(/resend/i);
    fireEvent.click(resendButton);

    await waitFor(() => {
      expect(mockResendConfirmationCode).toHaveBeenCalledWith("testuser");
    });
  });

  test("switches back to login", () => {
    const onSwitchToLogin = vi.fn();
    render(
      <ConfirmationForm {...defaultProps} onSwitchToLogin={onSwitchToLogin} />
    );

    const backButton = screen.getByText(/back to sign in/i);
    fireEvent.click(backButton);

    expect(onSwitchToLogin).toHaveBeenCalled();
  });
});
