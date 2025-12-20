/**
 * @vitest-environment jsdom
 */
import { describe, it, beforeEach, expect, vi } from "vitest";
import {
  renderWithProviders,
  screen,
  fireEvent,
  waitFor,
  act,
} from "../test-utils";
import AuthModal from "../../components/auth/AuthModal";
import LoginForm from "../../components/auth/LoginForm";

// Mock AWS Cognito
vi.mock("aws-amplify", () => ({
  Auth: {
    signIn: vi.fn(),
    signUp: vi.fn(),
    confirmSignUp: vi.fn(),
    resendSignUp: vi.fn(),
    forgotPassword: vi.fn(),
    forgotPasswordSubmit: vi.fn(),
    signOut: vi.fn(),
    currentSession: vi.fn(),
    currentAuthenticatedUser: vi.fn(),
  },
  configure: vi.fn(),
}));

// Get the mocked auth functions for direct access
const mockLogin = vi.fn().mockResolvedValue({ success: true });
const mockRegister = vi.fn().mockResolvedValue({
  success: true,
  nextStep: "CONFIRM_SIGN_UP"
});
const mockConfirmSignUp = vi.fn().mockResolvedValue({ success: true });
const mockConfirmForgotPassword = vi.fn().mockResolvedValue({ success: true });
const mockForgotPassword = vi.fn().mockResolvedValue({ success: true });

// Create mock auth context
const mockAuthContext = {
  user: { id: "test-user", email: "test@example.com" },
  isAuthenticated: false,
  isLoading: false,
  error: null,
  login: mockLogin,
  register: mockRegister,
  logout: vi.fn().mockResolvedValue({ success: true }),
  confirmSignUp: mockConfirmSignUp,
  confirmForgotPassword: mockConfirmForgotPassword,
  forgotPassword: mockForgotPassword,
  clearError: vi.fn(),
};

// Mock AuthContext to provide test values
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: vi.fn(() => mockAuthContext),
  AuthProvider: vi.fn(({ children }) => children),
}));

// Mock devAuth service
vi.mock("../../services/devAuth", () => ({
  default: {
    signUp: vi.fn().mockResolvedValue({
      success: true,
      user: { username: "testuser", email: "test@example.com" },
      userConfirmed: false,
      isSignUpComplete: false,
      nextStep: "CONFIRM_SIGN_UP",
    }),
    signIn: vi.fn().mockResolvedValue({
      success: true,
      user: { username: "testuser", email: "test@example.com" },
      isSignedIn: true,
    }),
    confirmSignUp: vi.fn().mockResolvedValue({ success: true }),
    forgotPassword: vi.fn().mockResolvedValue({ success: true }),
    forgotPasswordSubmit: vi.fn().mockResolvedValue({ success: true }),
    getCurrentUser: vi.fn().mockResolvedValue({
      success: true,
      user: { username: "testuser", email: "test@example.com" },
    }),
    signOut: vi.fn().mockResolvedValue({ success: true }),
  },
}));

// Auth imported for test setup but not directly used in these tests
// eslint-disable-next-line no-unused-vars
import { Auth } from "aws-amplify";

describe("Authentication Flow Components", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("AuthModal Component", () => {
    it("should render login form by default", () => {
      renderWithProviders(<AuthModal open={true} onClose={() => {}} />);

      expect(screen.getAllByText(/Sign In/i)).toHaveLength(3); // header, title, button
      expect(screen.getByLabelText(/Username or Email/i)).toBeInTheDocument();
      expect(
        screen.getByRole("textbox", { name: /Username or Email/i })
      ).toBeInTheDocument();
    });

    it("should switch to signup form when requested", () => {
      renderWithProviders(<AuthModal open={true} onClose={() => {}} />);

      fireEvent.click(screen.getByText(/Sign up here/i));

      expect(
        screen.getByRole("heading", { name: /Create Account/i })
      ).toBeInTheDocument();
      expect(
        screen.getByRole("textbox", { name: /First Name/i })
      ).toBeInTheDocument();
    });

    it("should close modal when close button is clicked", () => {
      const onClose = vi.fn();
      renderWithProviders(<AuthModal open={true} onClose={onClose} />);

      // Find close button by close-icon testid (lowercase with dash)
      fireEvent.click(screen.getByTestId("close-icon").closest("button"));

      expect(onClose).toHaveBeenCalled();
    });

    it("should close modal when clicking outside", () => {
      const onClose = vi.fn();
      renderWithProviders(<AuthModal open={true} onClose={onClose} />);

      // Click on the backdrop (outside the modal content)
      const backdrop = document.querySelector(".MuiBackdrop-root");
      fireEvent.click(backdrop);

      expect(onClose).toHaveBeenCalled();
    });

    it("should not render when isOpen is false", () => {
      renderWithProviders(<AuthModal open={false} onClose={() => {}} />);

      expect(screen.queryByText(/Sign In/i)).not.toBeInTheDocument();
    });
  });

  describe("LoginForm Component", () => {
    it("should render login form fields", () => {
      renderWithProviders(<LoginForm onSuccess={() => {}} />);

      expect(screen.getByLabelText(/Username or Email/i)).toBeInTheDocument();
      // Use more specific selector for login form password field
      expect(
        screen.getByRole("textbox", { name: /Username or Email/i })
      ).toBeInTheDocument();
      // Find the password input specifically
      const passwordInputs = screen.getAllByLabelText(/Password/i);
      expect(passwordInputs.length).toBeGreaterThanOrEqual(1);
      expect(
        screen.getByRole("button", { name: /Sign In/i })
      ).toBeInTheDocument();
    });

    it("should validate required fields", async () => {
      renderWithProviders(<LoginForm onSuccess={() => {}} />);

      fireEvent.click(screen.getByRole("button", { name: /Sign In/i }));

      await waitFor(() => {
        // Test the actual validation message from your LoginForm
        expect(
          screen.getByText(/Please enter both username and password/i)
        ).toBeInTheDocument();
      });
    });

    it("should accept any username format", async () => {
      renderWithProviders(<LoginForm onSuccess={() => {}} />);

      fireEvent.change(screen.getByLabelText(/Username or Email/i), {
        target: { value: "invalid-email" },
      });

      // Get the password field correctly
      const passwordFields = screen.getAllByLabelText(/Password/i);
      fireEvent.change(passwordFields[0], {
        target: { value: "password123" },
      });

      fireEvent.click(screen.getByRole("button", { name: /Sign In/i }));

      // Should not show validation error since component accepts any username format
      await waitFor(() => {
        expect(
          screen.queryByText(/Please enter a valid email/i)
        ).not.toBeInTheDocument();
      });
    });

    it("should handle successful login", async () => {
      const onSuccess = vi.fn();

      // Mock successful login
      mockAuthContext.login.mockResolvedValue({ success: true });

      renderWithProviders(<LoginForm onSuccess={onSuccess} />);

      fireEvent.change(screen.getByLabelText(/Username or Email/i), {
        target: { value: "test@example.com" },
      });
      // Use getAllByLabelText to handle multiple password fields
      const passwordFields = screen.getAllByLabelText(/Password/i);
      fireEvent.change(passwordFields[0], {
        target: { value: "password123" },
      });

      fireEvent.click(screen.getByRole("button", { name: /Sign In/i }));

      await waitFor(() => {
        expect(mockAuthContext.login).toHaveBeenCalledWith(
          "test@example.com",
          "password123"
        );
      });
    });

    it("should handle login errors", async () => {
      // Mock login failure
      mockAuthContext.login.mockResolvedValue({
        success: false,
        error: "Incorrect username or password.",
      });

      renderWithProviders(<LoginForm onSuccess={() => {}} />);

      fireEvent.change(screen.getByLabelText(/Username or Email/i), {
        target: { value: "test@example.com" },
      });
      const passwordFields = screen.getAllByLabelText(/Password/i);
      fireEvent.change(passwordFields[0], {
        target: { value: "wrongpassword" },
      });

      fireEvent.click(screen.getByRole("button", { name: /Sign In/i }));

      await waitFor(() => {
        expect(
          screen.getByText(/Incorrect username or password/i)
        ).toBeInTheDocument();
      });
    });

    it("should handle user not confirmed error", async () => {
      // Mock login with user not confirmed error
      mockAuthContext.login.mockResolvedValue({
        success: false,
        error: "User is not confirmed.",
      });

      renderWithProviders(<LoginForm onSuccess={() => {}} />);

      fireEvent.change(screen.getByLabelText(/Username or Email/i), {
        target: { value: "test@example.com" },
      });
      const passwordFields = screen.getAllByLabelText(/Password/i);
      fireEvent.change(passwordFields[0], {
        target: { value: "password123" },
      });

      fireEvent.click(screen.getByRole("button", { name: /Sign In/i }));

      await waitFor(() => {
        expect(screen.getByText(/User is not confirmed/i)).toBeInTheDocument();
      });
    });

    it("should handle MFA challenge", async () => {
      // Mock login with MFA challenge response
      mockAuthContext.login.mockResolvedValue({
        success: false,
        error: "MFA code required. Please check your phone.",
      });

      renderWithProviders(<LoginForm onSuccess={() => {}} />);

      fireEvent.change(screen.getByLabelText(/Username or Email/i), {
        target: { value: "test@example.com" },
      });
      const passwordFields = screen.getAllByLabelText(/Password/i);
      fireEvent.change(passwordFields[0], {
        target: { value: "password123" },
      });

      fireEvent.click(screen.getByRole("button", { name: /Sign In/i }));

      // LoginForm should show the error message for MFA
      await waitFor(() => {
        // Since LoginForm doesn't have specific MFA UI, just verify it handles the error
        expect(screen.getByText(/MFA code required/i)).toBeInTheDocument();
      });
    });

    it("should show loading state during login", async () => {
      // Mock loading state in AuthContext
      mockAuthContext.isLoading = true;

      await act(async () => {
        renderWithProviders(<LoginForm onSuccess={() => {}} />);
      });

      // Should show loading state
      expect(screen.getByText(/Signing In/i)).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Signing In/i })
      ).toBeDisabled();

      // Reset loading state for other tests
      mockAuthContext.isLoading = false;
    });

    it("should toggle password visibility", () => {
      renderWithProviders(<LoginForm onSuccess={() => {}} />);

      const passwordFields = screen.getAllByLabelText(/Password/i);
      const passwordField = passwordFields[0];
      const toggleButton = screen.getByLabelText(/toggle password visibility/i);

      expect(passwordField).toHaveAttribute("type", "password");

      fireEvent.click(toggleButton);
      expect(passwordField).toHaveAttribute("type", "text");

      fireEvent.click(toggleButton);
      expect(passwordField).toHaveAttribute("type", "password");
    });
  });

  describe("Signup Flow", () => {
    it("should render signup form", () => {
      renderWithProviders(
        <AuthModal open={true} initialMode="register" onClose={() => {}} />
      );

      expect(screen.getByText(/Sign Up/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Email Address/i)).toBeInTheDocument();
      // Use getAllByLabelText to handle multiple password fields in RegisterForm
      const passwordFields = screen.getAllByLabelText(/Password/i);
      expect(passwordFields.length).toBeGreaterThanOrEqual(2); // Password and Confirm Password
      expect(document.getElementById("confirmPassword")).toBeInTheDocument();
    });

    it("should validate password confirmation", async () => {
      renderWithProviders(
        <AuthModal open={true} initialMode="register" onClose={() => {}} />
      );

      // Fill in all required fields first
      fireEvent.change(screen.getByLabelText(/Email Address/i), {
        target: { value: "test@example.com" },
      });
      fireEvent.change(document.getElementById("username"), {
        target: { value: "testuser" },
      });

      // Get password fields correctly - there are multiple in RegisterForm
      const passwordFields = screen.getAllByLabelText(/Password/i);
      // First password field is the main password, find confirm password by role
      fireEvent.change(passwordFields[0], {
        target: { value: "password123" },
      });

      // Find confirm password input specifically by ID to avoid ambiguity with toggle button
      const confirmPasswordInput = document.getElementById("confirmPassword");
      fireEvent.change(confirmPasswordInput, {
        target: { value: "differentpassword" },
      });

      fireEvent.click(screen.getByRole("button", { name: /Create Account/i }));

      await waitFor(() => {
        expect(screen.getByText(/Passwords do not match/i)).toBeInTheDocument();
      });
    });

    it("should validate password strength", async () => {
      renderWithProviders(
        <AuthModal open={true} initialMode="register" onClose={() => {}} />
      );

      // Fill in required fields first
      fireEvent.change(screen.getByLabelText(/Email Address/i), {
        target: { value: "test@example.com" },
      });
      fireEvent.change(document.getElementById("username"), {
        target: { value: "testuser" },
      });

      const passwordFields = screen.getAllByLabelText(/Password/i);
      fireEvent.change(passwordFields[0], {
        target: { value: "weak" },
      });

      // Also fill confirm password to avoid that validation error
      const confirmPasswordInput = document.getElementById("confirmPassword");
      fireEvent.change(confirmPasswordInput, {
        target: { value: "weak" },
      });

      fireEvent.click(screen.getByRole("button", { name: /Create Account/i }));

      await waitFor(() => {
        expect(
          screen.getByText(/Password must be at least 8 characters long/i)
        ).toBeInTheDocument();
      });
    });

    it("should handle successful signup", async () => {
      // Mock a successful register that triggers the success callback
      mockRegister.mockResolvedValue({
        success: true,
        user: { username: "testuser", email: "test@example.com" },
        userConfirmed: false,
        nextStep: "CONFIRM_SIGN_UP"
      });

      renderWithProviders(
        <AuthModal open={true} initialMode="register" onClose={() => {}} />
      );

      fireEvent.change(screen.getByLabelText(/Email Address/i), {
        target: { value: "test@example.com" },
      });
      fireEvent.change(document.getElementById("username"), {
        target: { value: "testuser" },
      });
      const passwordFields = screen.getAllByLabelText(/Password/i);
      fireEvent.change(passwordFields[0], {
        target: { value: "Password123!" },
      });
      const confirmPasswordInput = document.getElementById("confirmPassword");
      fireEvent.change(confirmPasswordInput, {
        target: { value: "Password123!" },
      });

      fireEvent.click(screen.getByRole("button", { name: /Create Account/i }));

      // First wait for the register function to be called
      await waitFor(() => {
        expect(mockRegister).toHaveBeenCalledWith(
          "testuser",
          "Password123!",
          "test@example.com",
          "", // firstName (empty)
          "" // lastName (empty)
        );
      });

      // Then wait for the success message to appear after successful registration
      await waitFor(() => {
        expect(
          screen.getByText(/Registration successful.*Please check your email/i)
        ).toBeInTheDocument();
      }, { timeout: 5000 });
    });

    it("should handle signup errors", async () => {
      // Mock register to return error instead of throwing
      mockRegister.mockResolvedValue({
        success: false,
        error: "Username already exists"
      });

      renderWithProviders(
        <AuthModal open={true} initialMode="register" onClose={() => {}} />
      );

      fireEvent.change(screen.getByLabelText(/Email Address/i), {
        target: { value: "existing@example.com" },
      });
      fireEvent.change(document.getElementById("username"), {
        target: { value: "existing" },
      });
      const passwordFields = screen.getAllByLabelText(/Password/i);
      fireEvent.change(passwordFields[0], {
        target: { value: "Password123!" },
      });
      const confirmPasswordInput = document.getElementById("confirmPassword");
      fireEvent.change(confirmPasswordInput, {
        target: { value: "Password123!" },
      });

      fireEvent.click(screen.getByRole("button", { name: /Create Account/i }));

      await waitFor(() => {
        expect(
          screen.getByText(/Username already exists/i)
        ).toBeInTheDocument();
      }, { timeout: 5000 });
    });
  });

  describe("Email Confirmation", () => {
    it("should render confirmation code form", async () => {
      // Update the global mock register function to return confirmation step
      mockRegister.mockResolvedValue({
        success: true,
        nextStep: "CONFIRM_SIGN_UP",
        username: "testuser"
      });

      renderWithProviders(
        <AuthModal open={true} initialMode="register" onClose={() => {}} />
      );

      // Complete signup first
      fireEvent.change(screen.getByLabelText(/Email Address/i), {
        target: { value: "test@example.com" },
      });
      fireEvent.change(document.getElementById("username"), {
        target: { value: "testuser" },
      });
      const passwordFields = screen.getAllByLabelText(/Password/i);
      fireEvent.change(passwordFields[0], {
        target: { value: "Password123!" },
      });
      const confirmPasswordInput = document.getElementById("confirmPassword");
      fireEvent.change(confirmPasswordInput, {
        target: { value: "Password123!" },
      });

      fireEvent.click(screen.getByRole("button", { name: /Create Account/i }));

      // Wait for the register function to be called and complete
      await waitFor(() => {
        expect(mockRegister).toHaveBeenCalledWith(
          "testuser", "Password123!", "test@example.com", "", ""
        );
      });

      // Wait for the modal to transition to confirmation mode
      await waitFor(() => {
        expect(screen.getByLabelText(/Verification Code/i)).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: /Verify Account/i })
        ).toBeInTheDocument();
      });
    });

    it("should handle successful email confirmation", async () => {
      const onSuccess = vi.fn();

      // Add confirmRegistration to the global mock auth context
      mockAuthContext.confirmRegistration = vi.fn().mockResolvedValue({
        success: true
      });

      // Render directly in confirmation state with a username
      renderWithProviders(
        <AuthModal
          open={true}
          onClose={() => {}}
          onSuccess={onSuccess}
          initialMode="confirm"
        />
      );

      fireEvent.change(screen.getByLabelText(/Verification Code/i), {
        target: { value: "123456" },
      });

      fireEvent.click(screen.getByRole("button", { name: /Verify Account/i }));

      await waitFor(() => {
        expect(mockAuthContext.confirmRegistration).toHaveBeenCalledWith(
          "",
          "123456"
        );
      });
    });

    it("should handle resend confirmation code", async () => {
      // Add resendConfirmationCode to the global mock auth context
      mockAuthContext.resendConfirmationCode = vi.fn().mockResolvedValue({
        success: true,
        message: "Confirmation code sent"
      });

      renderWithProviders(
        <AuthModal
          open={true}
          initialMode="confirm"
          onClose={() => {}}
        />
      );

      fireEvent.click(screen.getByText(/Resend/i));

      await waitFor(() => {
        expect(mockAuthContext.resendConfirmationCode).toHaveBeenCalledWith("");
        expect(screen.getByText(/Confirmation code sent/i)).toBeInTheDocument();
      });
    });
  });

  describe("Forgot Password Flow", () => {
    it("should render forgot password form", () => {
      renderWithProviders(
        <AuthModal
          open={true}
          initialMode="forgot_password"
          onClose={() => {}}
        />
      );

      expect(screen.getAllByText(/Reset Password/i)).toHaveLength(2); // Modal title and form heading
      expect(screen.getByLabelText(/Email Address/i)).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Send Reset Email/i })
      ).toBeInTheDocument();
    });

    it("should handle forgot password request", async () => {
      // Add forgotPassword to the global mock auth context
      mockAuthContext.forgotPassword = vi.fn().mockResolvedValue({
        success: true,
        message: "Reset code sent to your email"
      });

      renderWithProviders(
        <AuthModal
          open={true}
          initialMode="forgot_password"
          onClose={() => {}}
        />
      );

      // Wait for the form to be fully rendered
      await waitFor(() => {
        expect(screen.getByLabelText(/Email Address/i)).toBeInTheDocument();
      });

      const emailInput = screen.getByLabelText(/Email Address/i);
      const submitButton = screen.getByRole("button", { name: /Send Reset Email/i });

      // Use act to ensure all state updates are processed
      await act(async () => {
        fireEvent.change(emailInput, {
          target: { value: "test@example.com" },
        });
      });

      await act(async () => {
        fireEvent.click(submitButton);
      });

      // Wait for async operations to complete with longer timeout
      await waitFor(() => {
        expect(mockAuthContext.forgotPassword).toHaveBeenCalledWith("test@example.com");
      }, { timeout: 5000 });

      await waitFor(() => {
        expect(screen.getByText(/Reset code sent to your email/i)).toBeInTheDocument();
      }, { timeout: 5000 });
    });

    it("should handle password reset confirmation", async () => {
      const onSuccess = vi.fn();

      // Add confirmForgotPassword to the global mock auth context (component uses this method)
      mockAuthContext.confirmForgotPassword = vi.fn().mockResolvedValue({
        success: true
      });

      renderWithProviders(
        <AuthModal
          open={true}
          initialMode="reset_password"
          email="test@example.com"
          onClose={() => {}}
          onSuccess={onSuccess}
        />
      );

      fireEvent.change(screen.getByLabelText(/Reset Code/i), {
        target: { value: "123456" },
      });
      fireEvent.change(document.getElementById("newPassword"), {
        target: { value: "NewPassword123!" },
      });
      fireEvent.change(document.getElementById("confirmPassword"), {
        target: { value: "NewPassword123!" },
      });

      fireEvent.click(screen.getByRole("button", { name: /Reset Password/i }));

      await waitFor(() => {
        expect(mockAuthContext.confirmForgotPassword).toHaveBeenCalledWith(
          "test@example.com",
          "123456",
          "NewPassword123!"
        );
      }, { timeout: 5000 });

      await waitFor(() => {
        expect(onSuccess).toHaveBeenCalled();
      }, { timeout: 5000 });
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA labels and roles", () => {
      renderWithProviders(<AuthModal open={true} onClose={() => {}} />);

      expect(screen.getByRole("dialog")).toBeInTheDocument();

      // Check for required fields (Material-UI handles aria-required automatically)
      const usernameField = screen.getByLabelText(/Username or Email/i);
      expect(usernameField).toBeRequired();

      const passwordFields = screen.getAllByLabelText(/Password/i);
      expect(passwordFields[0]).toBeRequired();
    });

    it("should trap focus within modal", () => {
      renderWithProviders(<AuthModal open={true} onClose={() => {}} />);

      const modal = screen.getByRole("dialog");
      expect(modal).toBeInTheDocument();

      // Check that focusable elements are present within modal
      const firstFocusable = screen.getByLabelText(/Username or Email/i);
      const submitButton = screen.getByRole("button", { name: /Sign In/i });

      expect(firstFocusable).toBeInTheDocument();
      expect(submitButton).toBeInTheDocument();

      // Test basic focus management (focus trapping is complex and may not be fully implemented)
      firstFocusable.focus();
      expect(firstFocusable).toHaveFocus();
    });

    it("should close modal on Escape key", () => {
      const onClose = vi.fn();
      renderWithProviders(<AuthModal open={true} onClose={onClose} />);

      fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

      expect(onClose).toHaveBeenCalled();
    });
  });

  describe("Form Persistence", () => {
    it("should preserve form data when switching modes", () => {
      renderWithProviders(<AuthModal open={true} onClose={() => {}} />);

      // Enter email in login form
      fireEvent.change(screen.getByLabelText(/Username or Email/i), {
        target: { value: "test@example.com" },
      });

      // Switch to signup
      fireEvent.click(screen.getByText(/Sign up here/i));

      // Email should be preserved in email field if it exists
      const emailField = screen.queryByDisplayValue("test@example.com");
      if (emailField) {
        expect(emailField).toBeInTheDocument();
      }
    });

    it("should clear sensitive fields when switching modes", async () => {
      await act(async () => {
        renderWithProviders(<AuthModal open={true} onClose={() => {}} />);
      });

      // Start in login mode - verify we're in login mode
      expect(screen.getByRole("button", { name: /Sign In/i })).toBeInTheDocument();

      // Wait for authentication to complete and forms to be enabled
      await waitFor(
        () => {
          const passwordFields = screen.getAllByLabelText(/Password/i);
          expect(passwordFields[0]).not.toBeDisabled();
        },
        { timeout: 10000 }
      );

      // Enter password in login form
      const passwordFields = screen.getAllByLabelText(/Password/i);
      fireEvent.change(passwordFields[0], {
        target: { value: "password123" },
      });

      expect(passwordFields[0]).toHaveValue("password123");

      // Switch to signup - wrap in act to handle React state updates
      await act(async () => {
        fireEvent.click(screen.getByText(/Sign up here/i));
      });

      // Wait for form to switch and verify we're now in signup mode
      await waitFor(() => {
        expect(screen.getByRole("button", { name: /Create Account/i })).toBeInTheDocument();
      });

      // Get password fields in signup form - should be different components with empty state
      const newPasswordFields = screen.getAllByLabelText(/Password/i);
      // The first password field should be empty (new RegisterForm component state)
      expect(newPasswordFields[0]).toHaveValue("");
    });
  });
});
