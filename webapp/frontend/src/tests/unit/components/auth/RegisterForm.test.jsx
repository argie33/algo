import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import RegisterForm from '../../../../components/auth/RegisterForm';

// Mock auth context
const mockAuthContext = {
  register: vi.fn(),
  loading: false,
  error: null,
};

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthContext,
}));

describe('RegisterForm Component', () => {
  const defaultProps = {
    onSuccess: vi.fn(),
    onCancel: vi.fn(),
    redirectTo: '/dashboard',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthContext.loading = false;
    mockAuthContext.error = null;
  });

  describe('Form Rendering', () => {
    it('renders all required form fields', () => {
      render(<RegisterForm {...defaultProps} />);
      
      expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/first name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/last name/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument();
    });

    it('displays form title and description', () => {
      render(<RegisterForm {...defaultProps} />);
      
      expect(screen.getByText(/create account/i)).toBeInTheDocument();
      expect(screen.getByText(/join our financial platform/i)).toBeInTheDocument();
    });

    it('includes terms and conditions checkbox', () => {
      render(<RegisterForm {...defaultProps} />);
      
      expect(screen.getByRole('checkbox')).toBeInTheDocument();
      expect(screen.getByText(/terms and conditions/i)).toBeInTheDocument();
      expect(screen.getByText(/privacy policy/i)).toBeInTheDocument();
    });

    it('shows sign in link', () => {
      render(<RegisterForm {...defaultProps} />);
      
      expect(screen.getByText(/already have an account/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
    });
  });

  describe('Form Validation', () => {
    it('validates required fields', async () => {
      const user = userEvent.setup();
      render(<RegisterForm {...defaultProps} />);
      
      const submitButton = screen.getByRole('button', { name: /create account/i });
      await user.click(submitButton);
      
      expect(screen.getByText(/email is required/i)).toBeInTheDocument();
      expect(screen.getByText(/password is required/i)).toBeInTheDocument();
      expect(screen.getByText(/first name is required/i)).toBeInTheDocument();
      expect(screen.getByText(/last name is required/i)).toBeInTheDocument();
    });

    it('validates email format', async () => {
      const user = userEvent.setup();
      render(<RegisterForm {...defaultProps} />);
      
      const emailInput = screen.getByLabelText(/email/i);
      await user.type(emailInput, 'invalid-email');
      await user.tab(); // Trigger blur event
      
      expect(screen.getByText(/please enter a valid email/i)).toBeInTheDocument();
    });

    it('validates password strength', async () => {
      const user = userEvent.setup();
      render(<RegisterForm {...defaultProps} />);
      
      const passwordInput = screen.getByLabelText(/^password/i);
      
      // Test weak password
      await user.type(passwordInput, '123');
      await user.tab();
      
      expect(screen.getByText(/password must be at least 8 characters/i)).toBeInTheDocument();
      
      // Test password without special characters
      await user.clear(passwordInput);
      await user.type(passwordInput, 'password123');
      await user.tab();
      
      expect(screen.getByText(/password must contain at least one special character/i)).toBeInTheDocument();
    });

    it('validates password confirmation', async () => {
      const user = userEvent.setup();
      render(<RegisterForm {...defaultProps} />);
      
      const passwordInput = screen.getByLabelText(/^password/i);
      const confirmPasswordInput = screen.getByLabelText(/confirm password/i);
      
      await user.type(passwordInput, 'Password123!');
      await user.type(confirmPasswordInput, 'Password456!');
      await user.tab();
      
      expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
    });

    it('validates terms and conditions acceptance', async () => {
      const user = userEvent.setup();
      render(<RegisterForm {...defaultProps} />);
      
      // Fill all required fields
      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByLabelText(/first name/i), 'John');
      await user.type(screen.getByLabelText(/last name/i), 'Doe');
      await user.type(screen.getByLabelText(/^password/i), 'Password123!');
      await user.type(screen.getByLabelText(/confirm password/i), 'Password123!');
      
      // Try to submit without accepting terms
      const submitButton = screen.getByRole('button', { name: /create account/i });
      await user.click(submitButton);
      
      expect(screen.getByText(/you must accept the terms and conditions/i)).toBeInTheDocument();
    });

    it('shows password strength indicator', async () => {
      const user = userEvent.setup();
      render(<RegisterForm {...defaultProps} />);
      
      const passwordInput = screen.getByLabelText(/^password/i);
      
      // Test weak password
      await user.type(passwordInput, '123');
      expect(screen.getByText(/weak/i)).toBeInTheDocument();
      
      // Test medium password
      await user.clear(passwordInput);
      await user.type(passwordInput, 'Password123');
      expect(screen.getByText(/medium/i)).toBeInTheDocument();
      
      // Test strong password
      await user.clear(passwordInput);
      await user.type(passwordInput, 'Password123!@#');
      expect(screen.getByText(/strong/i)).toBeInTheDocument();
    });
  });

  describe('Form Submission', () => {
    it('submits form with valid data', async () => {
      const user = userEvent.setup();
      mockAuthContext.register.mockResolvedValue({ success: true });
      
      render(<RegisterForm {...defaultProps} />);
      
      // Fill form with valid data
      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByLabelText(/first name/i), 'John');
      await user.type(screen.getByLabelText(/last name/i), 'Doe');
      await user.type(screen.getByLabelText(/^password/i), 'Password123!');
      await user.type(screen.getByLabelText(/confirm password/i), 'Password123!');
      await user.click(screen.getByRole('checkbox'));
      
      const submitButton = screen.getByRole('button', { name: /create account/i });
      await user.click(submitButton);
      
      expect(mockAuthContext.register).toHaveBeenCalledWith({
        email: 'test@example.com',
        firstName: 'John',
        lastName: 'Doe',
        password: 'Password123!',
      });
    });

    it('shows loading state during submission', async () => {
      const _user = userEvent.setup();
      mockAuthContext.loading = true;
      
      render(<RegisterForm {...defaultProps} />);
      
      expect(screen.getByRole('button', { name: /creating account/i })).toBeDisabled();
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    it('calls onSuccess callback after successful registration', async () => {
      const user = userEvent.setup();
      mockAuthContext.register.mockResolvedValue({ success: true });
      
      render(<RegisterForm {...defaultProps} />);
      
      // Fill and submit form
      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByLabelText(/first name/i), 'John');
      await user.type(screen.getByLabelText(/last name/i), 'Doe');
      await user.type(screen.getByLabelText(/^password/i), 'Password123!');
      await user.type(screen.getByLabelText(/confirm password/i), 'Password123!');
      await user.click(screen.getByRole('checkbox'));
      await user.click(screen.getByRole('button', { name: /create account/i }));
      
      await waitFor(() => {
        expect(defaultProps.onSuccess).toHaveBeenCalled();
      });
    });

    it('handles registration errors', async () => {
      const user = userEvent.setup();
      const errorMessage = 'Email already exists';
      mockAuthContext.register.mockRejectedValue(new Error(errorMessage));
      
      render(<RegisterForm {...defaultProps} />);
      
      // Fill and submit form
      await user.type(screen.getByLabelText(/email/i), 'existing@example.com');
      await user.type(screen.getByLabelText(/first name/i), 'John');
      await user.type(screen.getByLabelText(/last name/i), 'Doe');
      await user.type(screen.getByLabelText(/^password/i), 'Password123!');
      await user.type(screen.getByLabelText(/confirm password/i), 'Password123!');
      await user.click(screen.getByRole('checkbox'));
      await user.click(screen.getByRole('button', { name: /create account/i }));
      
      await waitFor(() => {
        expect(screen.getByText(errorMessage)).toBeInTheDocument();
      });
    });
  });

  describe('Social Registration', () => {
    it('displays social registration options', () => {
      render(<RegisterForm {...defaultProps} enableSocial={true} />);
      
      expect(screen.getByRole('button', { name: /continue with google/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /continue with github/i })).toBeInTheDocument();
    });

    it('handles Google registration', async () => {
      const user = userEvent.setup();
      const mockGoogleRegister = vi.fn();
      
      render(<RegisterForm {...defaultProps} enableSocial={true} onGoogleRegister={mockGoogleRegister} />);
      
      const googleButton = screen.getByRole('button', { name: /continue with google/i });
      await user.click(googleButton);
      
      expect(mockGoogleRegister).toHaveBeenCalled();
    });

    it('handles GitHub registration', async () => {
      const user = userEvent.setup();
      const mockGitHubRegister = vi.fn();
      
      render(<RegisterForm {...defaultProps} enableSocial={true} onGitHubRegister={mockGitHubRegister} />);
      
      const githubButton = screen.getByRole('button', { name: /continue with github/i });
      await user.click(githubButton);
      
      expect(mockGitHubRegister).toHaveBeenCalled();
    });
  });

  describe('Navigation', () => {
    it('navigates to sign in form', async () => {
      const user = userEvent.setup();
      render(<RegisterForm {...defaultProps} />);
      
      const signInButton = screen.getByRole('button', { name: /sign in/i });
      await user.click(signInButton);
      
      expect(defaultProps.onCancel).toHaveBeenCalled();
    });

    it('handles form cancellation', async () => {
      const user = userEvent.setup();
      render(<RegisterForm {...defaultProps} />);
      
      const cancelButton = screen.getByRole('button', { name: /cancel/i });
      await user.click(cancelButton);
      
      expect(defaultProps.onCancel).toHaveBeenCalled();
    });
  });

  describe('Accessibility', () => {
    it('associates labels with form controls', () => {
      render(<RegisterForm {...defaultProps} />);
      
      const emailInput = screen.getByLabelText(/email/i);
      const passwordInput = screen.getByLabelText(/^password/i);
      const confirmPasswordInput = screen.getByLabelText(/confirm password/i);
      const firstNameInput = screen.getByLabelText(/first name/i);
      const lastNameInput = screen.getByLabelText(/last name/i);
      
      expect(emailInput).toHaveAttribute('id');
      expect(passwordInput).toHaveAttribute('id');
      expect(confirmPasswordInput).toHaveAttribute('id');
      expect(firstNameInput).toHaveAttribute('id');
      expect(lastNameInput).toHaveAttribute('id');
    });

    it('provides proper ARIA attributes', () => {
      render(<RegisterForm {...defaultProps} />);
      
      const form = screen.getByRole('form');
      expect(form).toHaveAttribute('aria-label', 'Account registration form');
      
      const submitButton = screen.getByRole('button', { name: /create account/i });
      expect(submitButton).toHaveAttribute('type', 'submit');
    });

    it('announces form errors to screen readers', async () => {
      const user = userEvent.setup();
      render(<RegisterForm {...defaultProps} />);
      
      const submitButton = screen.getByRole('button', { name: /create account/i });
      await user.click(submitButton);
      
      const errorRegion = screen.getByRole('alert');
      expect(errorRegion).toBeInTheDocument();
      expect(errorRegion).toHaveAttribute('aria-live', 'polite');
    });

    it('supports keyboard navigation', async () => {
      const user = userEvent.setup();
      render(<RegisterForm {...defaultProps} />);
      
      // Tab through form fields
      await user.tab();
      expect(screen.getByLabelText(/email/i)).toHaveFocus();
      
      await user.tab();
      expect(screen.getByLabelText(/first name/i)).toHaveFocus();
      
      await user.tab();
      expect(screen.getByLabelText(/last name/i)).toHaveFocus();
    });
  });

  describe('Security Features', () => {
    it('includes password visibility toggle', async () => {
      const user = userEvent.setup();
      render(<RegisterForm {...defaultProps} />);
      
      const passwordInput = screen.getByLabelText(/^password/i);
      const toggleButton = screen.getByRole('button', { name: /show password/i });
      
      expect(passwordInput).toHaveAttribute('type', 'password');
      
      await user.click(toggleButton);
      expect(passwordInput).toHaveAttribute('type', 'text');
      
      await user.click(toggleButton);
      expect(passwordInput).toHaveAttribute('type', 'password');
    });

    it('prevents common password vulnerabilities', async () => {
      const user = userEvent.setup();
      render(<RegisterForm {...defaultProps} />);
      
      const passwordInput = screen.getByLabelText(/^password/i);
      
      // Test against common passwords
      await user.type(passwordInput, 'password');
      await user.tab();
      
      expect(screen.getByText(/password is too common/i)).toBeInTheDocument();
      
      // Test against sequential characters
      await user.clear(passwordInput);
      await user.type(passwordInput, '12345678');
      await user.tab();
      
      expect(screen.getByText(/password cannot contain sequential characters/i)).toBeInTheDocument();
    });

    it('implements rate limiting protection', async () => {
      const user = userEvent.setup();
      mockAuthContext.register.mockRejectedValue(new Error('Rate limit exceeded'));
      
      render(<RegisterForm {...defaultProps} />);
      
      // Fill form
      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByLabelText(/first name/i), 'John');
      await user.type(screen.getByLabelText(/last name/i), 'Doe');
      await user.type(screen.getByLabelText(/^password/i), 'Password123!');
      await user.type(screen.getByLabelText(/confirm password/i), 'Password123!');
      await user.click(screen.getByRole('checkbox'));
      
      // Multiple rapid submissions
      const submitButton = screen.getByRole('button', { name: /create account/i });
      await user.click(submitButton);
      await user.click(submitButton);
      await user.click(submitButton);
      
      await waitFor(() => {
        expect(screen.getByText(/rate limit exceeded/i)).toBeInTheDocument();
      });
    });
  });

  describe('Email Verification', () => {
    it('shows email verification message after registration', async () => {
      const user = userEvent.setup();
      mockAuthContext.register.mockResolvedValue({ 
        success: true, 
        requiresVerification: true 
      });
      
      render(<RegisterForm {...defaultProps} />);
      
      // Complete registration
      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByLabelText(/first name/i), 'John');
      await user.type(screen.getByLabelText(/last name/i), 'Doe');
      await user.type(screen.getByLabelText(/^password/i), 'Password123!');
      await user.type(screen.getByLabelText(/confirm password/i), 'Password123!');
      await user.click(screen.getByRole('checkbox'));
      await user.click(screen.getByRole('button', { name: /create account/i }));
      
      await waitFor(() => {
        expect(screen.getByText(/verification email sent/i)).toBeInTheDocument();
        expect(screen.getByText(/check your email/i)).toBeInTheDocument();
      });
    });

    it('allows resending verification email', async () => {
      const user = userEvent.setup();
      const mockResendVerification = vi.fn();
      
      render(<RegisterForm {...defaultProps} onResendVerification={mockResendVerification} />);
      
      // Simulate post-registration state
      const resendButton = screen.getByRole('button', { name: /resend verification/i });
      await user.click(resendButton);
      
      expect(mockResendVerification).toHaveBeenCalled();
    });
  });

  describe('Form Persistence', () => {
    it('saves form data to localStorage on input change', async () => {
      const user = userEvent.setup();
      const mockSetItem = vi.spyOn(Storage.prototype, 'setItem');
      
      render(<RegisterForm {...defaultProps} enablePersistence={true} />);
      
      await user.type(screen.getByLabelText(/email/i), 'test@example.com');
      await user.type(screen.getByLabelText(/first name/i), 'John');
      
      expect(mockSetItem).toHaveBeenCalledWith(
        'register_form_data',
        expect.stringContaining('test@example.com')
      );
      
      mockSetItem.mockRestore();
    });

    it('restores form data from localStorage on mount', () => {
      const mockGetItem = vi.spyOn(Storage.prototype, 'getItem');
      mockGetItem.mockReturnValue(JSON.stringify({
        email: 'saved@example.com',
        firstName: 'Saved',
        lastName: 'User',
      }));
      
      render(<RegisterForm {...defaultProps} enablePersistence={true} />);
      
      expect(screen.getByDisplayValue('saved@example.com')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Saved')).toBeInTheDocument();
      expect(screen.getByDisplayValue('User')).toBeInTheDocument();
      
      mockGetItem.mockRestore();
    });
  });
});