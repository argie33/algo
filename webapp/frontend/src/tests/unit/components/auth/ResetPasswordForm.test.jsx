import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeProvider } from '@mui/material/styles';
import { createTheme } from '@mui/material/styles';
import ResetPasswordForm from '../../../../components/auth/ResetPasswordForm';

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth()
}));

const theme = createTheme();

const renderWithTheme = (component) => {
  return render(
    <ThemeProvider theme={theme}>
      {component}
    </ThemeProvider>
  );
};

describe('ResetPasswordForm', () => {
  const mockOnPasswordResetSuccess = vi.fn();
  const mockOnSwitchToLogin = vi.fn();
  const mockConfirmForgotPassword = vi.fn();
  const mockClearError = vi.fn();
  
  const defaultProps = {
    username: 'testuser@example.com',
    onPasswordResetSuccess: mockOnPasswordResetSuccess,
    onSwitchToLogin: mockOnSwitchToLogin
  };

  const defaultAuthState = {
    confirmForgotPassword: mockConfirmForgotPassword,
    isLoading: false,
    error: null,
    clearError: mockClearError
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue(defaultAuthState);
  });

  describe('Rendering', () => {
    it('should render the reset password form with all elements', () => {
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);

      expect(screen.getByText('Set New Password')).toBeInTheDocument();
      expect(screen.getByText('Enter the code from your email and choose a new password')).toBeInTheDocument();
      expect(screen.getByRole('textbox', { name: /reset code/i })).toBeInTheDocument();
      expect(document.getElementById('newPassword')).toBeInTheDocument();
      expect(document.getElementById('confirmPassword')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /reset password/i })).toBeInTheDocument();
      expect(screen.getByText('Back to Sign In')).toBeInTheDocument();
    });

    it('should have proper input field attributes', () => {
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      const codeInput = screen.getByRole('textbox', { name: /reset code/i });
      expect(codeInput).toHaveAttribute('type', 'text');
      expect(codeInput).toHaveAttribute('maxLength', '6');
      expect(codeInput).toHaveAttribute('placeholder', 'Enter 6-digit code');
      expect(codeInput).toBeRequired();
      expect(codeInput).toHaveFocus();

      const passwordInput = document.getElementById('newPassword');
      expect(passwordInput).toHaveAttribute('type', 'password');
      expect(passwordInput).toHaveAttribute('autocomplete', 'new-password');
      expect(passwordInput).toBeRequired();

      const confirmInput = document.getElementById('confirmPassword');
      expect(confirmInput).toHaveAttribute('type', 'password');
      expect(confirmInput).toBeRequired();
    });

    it('should show password helper text', () => {
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      expect(screen.getByText('Must be at least 8 characters long')).toBeInTheDocument();
    });
  });

  describe('Password Visibility Toggle', () => {
    it('should toggle new password visibility', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      const passwordInput = document.getElementById('newPassword');
      const visibilityButton = screen.getAllByRole('button').find(button => 
        button.getAttribute('aria-label')?.includes('password')
      );

      expect(passwordInput).toHaveAttribute('type', 'password');
      
      if (visibilityButton) {
        await user.click(visibilityButton);
        expect(passwordInput).toHaveAttribute('type', 'text');
        
        await user.click(visibilityButton);
        expect(passwordInput).toHaveAttribute('type', 'password');
      }
    });

    it('should toggle confirm password visibility independently', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      const confirmInput = document.getElementById('confirmPassword');
      const visibilityButtons = screen.getAllByRole('button').filter(button => 
        button.getAttribute('aria-label')?.includes('password')
      );

      expect(confirmInput).toHaveAttribute('type', 'password');
      
      if (visibilityButtons.length >= 2) {
        await user.click(visibilityButtons[1]);
        expect(confirmInput).toHaveAttribute('type', 'text');
      }
    });
  });

  describe('Form Validation', () => {
    it('should show error for empty fields', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      const submitButton = screen.getByRole('button', { name: /reset password/i });
      await user.click(submitButton);
      
      expect(screen.getByText('Please fill in all fields')).toBeInTheDocument();
      expect(mockConfirmForgotPassword).not.toHaveBeenCalled();
    });

    it('should show error for mismatched passwords', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      await user.type(screen.getByRole('textbox', { name: /reset code/i }), '123456');
      await user.type(document.getElementById('newPassword'), 'password123');
      await user.type(document.getElementById('confirmPassword'), 'password456');
      
      const submitButton = screen.getByRole('button', { name: /reset password/i });
      await user.click(submitButton);
      
      expect(screen.getByText('Passwords do not match')).toBeInTheDocument();
      expect(mockConfirmForgotPassword).not.toHaveBeenCalled();
    });

    it('should show error for password too short', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      await user.type(screen.getByRole('textbox', { name: /reset code/i }), '123456');
      await user.type(document.getElementById('newPassword'), '123');
      await user.type(document.getElementById('confirmPassword'), '123');
      
      const submitButton = screen.getByRole('button', { name: /reset password/i });
      await user.click(submitButton);
      
      expect(screen.getByText('Password must be at least 8 characters long')).toBeInTheDocument();
      expect(mockConfirmForgotPassword).not.toHaveBeenCalled();
    });

    it('should pass validation with valid inputs', async () => {
      const user = userEvent.setup();
      mockConfirmForgotPassword.mockResolvedValue({ success: true });
      
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      await user.type(screen.getByRole('textbox', { name: /reset code/i }), '123456');
      await user.type(document.getElementById('newPassword'), 'validPassword123');
      await user.type(document.getElementById('confirmPassword'), 'validPassword123');
      
      const submitButton = screen.getByRole('button', { name: /reset password/i });
      await user.click(submitButton);
      
      expect(mockConfirmForgotPassword).toHaveBeenCalledWith(
        'testuser@example.com',
        '123456',
        'validPassword123'
      );
    });
  });

  describe('Form Submission', () => {
    it('should call onPasswordResetSuccess when reset succeeds', async () => {
      const user = userEvent.setup();
      mockConfirmForgotPassword.mockResolvedValue({ success: true });
      
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      await user.type(screen.getByRole('textbox', { name: /reset code/i }), '123456');
      await user.type(document.getElementById('newPassword'), 'newPassword123');
      await user.type(document.getElementById('confirmPassword'), 'newPassword123');
      await user.click(screen.getByRole('button', { name: /reset password/i }));
      
      await waitFor(() => {
        expect(mockOnPasswordResetSuccess).toHaveBeenCalled();
      });
    });

    it('should display error when reset fails', async () => {
      const user = userEvent.setup();
      mockConfirmForgotPassword.mockResolvedValue({ 
        success: false, 
        error: 'Invalid reset code' 
      });
      
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      await user.type(screen.getByRole('textbox', { name: /reset code/i }), '123456');
      await user.type(document.getElementById('newPassword'), 'newPassword123');
      await user.type(document.getElementById('confirmPassword'), 'newPassword123');
      await user.click(screen.getByRole('button', { name: /reset password/i }));
      
      await waitFor(() => {
        expect(screen.getByText('Invalid reset code')).toBeInTheDocument();
      });
    });

    it('should prevent submission while loading', async () => {
      const _user = userEvent.setup();
      mockUseAuth.mockReturnValue({
        ...defaultAuthState,
        isLoading: true
      });
      
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      const inputs = [
        screen.getByRole('textbox', { name: /reset code/i }),
        document.getElementById('newPassword'),
        document.getElementById('confirmPassword')
      ];
      const submitButton = screen.getByRole('button', { name: /resetting.../i });
      
      inputs.forEach(input => expect(input).toBeDisabled());
      expect(submitButton).toBeDisabled();
      
      expect(mockConfirmForgotPassword).not.toHaveBeenCalled();
    });
  });

  describe('Error Handling', () => {
    it('should display context error', () => {
      mockUseAuth.mockReturnValue({
        ...defaultAuthState,
        error: 'Network error occurred'
      });
      
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      expect(screen.getByText('Network error occurred')).toBeInTheDocument();
    });

    it('should clear errors when user starts typing', async () => {
      const user = userEvent.setup();
      mockUseAuth.mockReturnValue({
        ...defaultAuthState,
        error: 'Previous error'
      });
      
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      const input = screen.getByRole('textbox', { name: /reset code/i });
      await user.type(input, '1');
      
      expect(mockClearError).toHaveBeenCalled();
    });

    it('should clear local error when user starts typing', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      // Create local error
      await user.click(screen.getByRole('button', { name: /reset password/i }));
      expect(screen.getByText('Please fill in all fields')).toBeInTheDocument();
      
      // Start typing to clear error
      const input = screen.getByRole('textbox', { name: /reset code/i });
      await user.type(input, '1');
      
      expect(screen.queryByText('Please fill in all fields')).not.toBeInTheDocument();
    });
  });

  describe('User Interactions', () => {
    it('should call onSwitchToLogin when back button is clicked', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      const backButton = screen.getByText('Back to Sign In');
      await user.click(backButton);
      
      expect(mockOnSwitchToLogin).toHaveBeenCalled();
    });

    it('should update form data when inputs change', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      const codeInput = screen.getByRole('textbox', { name: /reset code/i });
      const passwordInput = document.getElementById('newPassword');
      const confirmInput = document.getElementById('confirmPassword');
      
      await user.type(codeInput, '123456');
      await user.type(passwordInput, 'password123');
      await user.type(confirmInput, 'password123');
      
      expect(codeInput).toHaveValue('123456');
      expect(passwordInput).toHaveValue('password123');
      expect(confirmInput).toHaveValue('password123');
    });
  });

  describe('Loading States', () => {
    it('should show loading button text when loading', () => {
      mockUseAuth.mockReturnValue({
        ...defaultAuthState,
        isLoading: true
      });
      
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      expect(screen.getByRole('button', { name: /resetting.../i })).toBeInTheDocument();
    });

    it('should disable interactive elements when loading', () => {
      mockUseAuth.mockReturnValue({
        ...defaultAuthState,
        isLoading: true
      });
      
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      expect(screen.getByRole('textbox', { name: /reset code/i })).toBeDisabled();
      expect(document.getElementById('newPassword')).toBeDisabled();
      expect(document.getElementById('confirmPassword')).toBeDisabled();
      expect(screen.getByRole('button', { name: /resetting.../i })).toBeDisabled();
      expect(screen.getByText('Back to Sign In').closest('button')).toBeDisabled();
    });
  });

  describe('Accessibility', () => {
    it('should have proper form structure and labels', () => {
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      const form = screen.getByRole('button', { name: /reset password/i }).closest('form');
      expect(form).toBeInTheDocument();
      
      // Check Reset Code field
      const codeInput = screen.getByRole('textbox', { name: /reset code/i });
      expect(codeInput).toBeInTheDocument();
      expect(codeInput).toBeRequired();
      
      // Check New Password field
      const passwordInput = document.getElementById('newPassword');
      expect(passwordInput).toBeInTheDocument();
      expect(passwordInput).toBeRequired();
      
      // Check Confirm New Password field
      const confirmInput = document.getElementById('confirmPassword');
      expect(confirmInput).toBeInTheDocument();
      expect(confirmInput).toBeRequired();
    });

    it('should have proper heading hierarchy', () => {
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      const heading = screen.getByRole('heading', { level: 1 });
      expect(heading).toHaveTextContent('Set New Password');
    });

    it('should handle keyboard navigation', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      const codeInput = screen.getByRole('textbox', { name: /reset code/i });
      const passwordInput = document.getElementById('newPassword');
      
      expect(codeInput).toHaveFocus();
      
      await user.tab();
      expect(passwordInput).toHaveFocus();
    });
  });

  describe('Edge Cases', () => {
    it('should handle missing callback props gracefully', async () => {
      const user = userEvent.setup();
      mockConfirmForgotPassword.mockResolvedValue({ success: true });
      
      renderWithTheme(
        <ResetPasswordForm 
          username="test@example.com"
          onPasswordResetSuccess={undefined}
          onSwitchToLogin={undefined}
        />
      );
      
      await user.type(screen.getByRole('textbox', { name: /reset code/i }), '123456');
      await user.type(document.getElementById('newPassword'), 'password123');
      await user.type(document.getElementById('confirmPassword'), 'password123');
      await user.click(screen.getByRole('button', { name: /reset password/i }));
      
      await waitFor(() => {
        expect(mockConfirmForgotPassword).toHaveBeenCalled();
      });
    });

    it('should handle response without error field', async () => {
      const user = userEvent.setup();
      mockConfirmForgotPassword.mockResolvedValue({ success: false });
      
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      await user.type(screen.getByRole('textbox', { name: /reset code/i }), '123456');
      await user.type(document.getElementById('newPassword'), 'password123');
      await user.type(document.getElementById('confirmPassword'), 'password123');
      await user.click(screen.getByRole('button', { name: /reset password/i }));
      
      await waitFor(() => {
        expect(mockConfirmForgotPassword).toHaveBeenCalled();
      });
      
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    it('should respect maxLength on reset code input', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ResetPasswordForm {...defaultProps} />);
      
      const codeInput = screen.getByRole('textbox', { name: /reset code/i });
      await user.type(codeInput, '1234567890');
      
      expect(codeInput.value.length).toBeLessThanOrEqual(6);
    });
  });
});