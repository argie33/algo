import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeProvider } from '@mui/material/styles';
import { createTheme } from '@mui/material/styles';
import ConfirmationForm from '../../../../components/auth/ConfirmationForm';

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

describe('ConfirmationForm', () => {
  const mockOnConfirmationSuccess = vi.fn();
  const mockOnSwitchToLogin = vi.fn();
  const mockConfirmRegistration = vi.fn();
  const mockClearError = vi.fn();
  
  const defaultProps = {
    username: 'testuser@example.com',
    onConfirmationSuccess: mockOnConfirmationSuccess,
    onSwitchToLogin: mockOnSwitchToLogin
  };

  const defaultAuthState = {
    confirmRegistration: mockConfirmRegistration,
    isLoading: false,
    error: null,
    clearError: mockClearError
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue(defaultAuthState);
  });

  describe('Rendering', () => {
    it('should render the confirmation form with all elements', () => {
      renderWithTheme(<ConfirmationForm {...defaultProps} />);

      expect(screen.getByRole('heading', { name: 'Verify Account' })).toBeInTheDocument();
      expect(screen.getByText('Enter the verification code sent to your email address')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('Enter 6-digit code')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /verify account/i })).toBeInTheDocument();
      expect(screen.getByText('Back to Sign In')).toBeInTheDocument();
      expect(screen.getByText('Resend')).toBeInTheDocument();
    });

    it('should render with confirmation icon', () => {
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      // The component has CheckCircle icons in both the header and button
      const icons = screen.getAllByTestId('CheckCircleIcon');
      expect(icons.length).toBeGreaterThan(0);
      expect(screen.getByRole('button', { name: /verify account/i })).toBeInTheDocument();
    });

    it('should have input field with proper attributes', () => {
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      const input = screen.getByPlaceholderText('Enter 6-digit code');
      expect(input).toHaveAttribute('type', 'text');
      expect(input).toHaveAttribute('maxLength', '6');
      expect(input).toHaveAttribute('placeholder', 'Enter 6-digit code');
      expect(input).toBeRequired();
      expect(input).toHaveFocus();
    });
  });

  describe('User Interactions', () => {
    it('should update input value when user types', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      const input = screen.getByPlaceholderText('Enter 6-digit code');
      await user.type(input, '123456');
      
      expect(input).toHaveValue('123456');
    });

    it('should clear errors when user starts typing', async () => {
      const user = userEvent.setup();
      mockUseAuth.mockReturnValue({
        ...defaultAuthState,
        error: 'Previous error'
      });
      
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      const input = screen.getByPlaceholderText('Enter 6-digit code');
      await user.type(input, '1');
      
      expect(mockClearError).toHaveBeenCalled();
    });

    it('should call onSwitchToLogin when "Back to Sign In" is clicked', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      const backButton = screen.getByText('Back to Sign In');
      await user.click(backButton);
      
      expect(mockOnSwitchToLogin).toHaveBeenCalled();
    });

    it('should handle resend button click', async () => {
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
      const user = userEvent.setup();
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      const resendButton = screen.getByText('Resend');
      await user.click(resendButton);
      
      expect(consoleSpy).toHaveBeenCalledWith('Resend code for:', 'testuser@example.com');
      consoleSpy.mockRestore();
    });
  });

  describe('Form Submission', () => {
    it('should show validation error for empty code', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      const submitButton = screen.getByRole('button', { name: /verify account/i });
      await user.click(submitButton);
      
      expect(screen.getByText('Please enter the confirmation code')).toBeInTheDocument();
      expect(mockConfirmRegistration).not.toHaveBeenCalled();
    });

    it('should submit form with valid code', async () => {
      const user = userEvent.setup();
      mockConfirmRegistration.mockResolvedValue({ success: true });
      
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      const input = screen.getByPlaceholderText('Enter 6-digit code');
      const submitButton = screen.getByRole('button', { name: /verify account/i });
      
      await user.type(input, '123456');
      await user.click(submitButton);
      
      expect(mockConfirmRegistration).toHaveBeenCalledWith('testuser@example.com', '123456');
    });

    it('should call onConfirmationSuccess when confirmation succeeds', async () => {
      const user = userEvent.setup();
      mockConfirmRegistration.mockResolvedValue({ success: true });
      
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      const input = screen.getByPlaceholderText('Enter 6-digit code');
      await user.type(input, '123456');
      await user.click(screen.getByRole('button', { name: /verify account/i }));
      
      await waitFor(() => {
        expect(mockOnConfirmationSuccess).toHaveBeenCalled();
      });
    });

    it('should display local error when confirmation fails', async () => {
      const user = userEvent.setup();
      mockConfirmRegistration.mockResolvedValue({ 
        success: false, 
        error: 'Invalid confirmation code' 
      });
      
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      const input = screen.getByPlaceholderText('Enter 6-digit code');
      await user.type(input, '123456');
      await user.click(screen.getByRole('button', { name: /verify account/i }));
      
      await waitFor(() => {
        expect(screen.getByText('Invalid confirmation code')).toBeInTheDocument();
      });
    });

    it('should prevent form submission while loading', async () => {
      mockUseAuth.mockReturnValue({
        ...defaultAuthState,
        isLoading: true
      });
      
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      const input = screen.getByPlaceholderText('Enter 6-digit code');
      const submitButton = screen.getByRole('button', { name: /verifying.../i });
      
      expect(input).toBeDisabled();
      expect(submitButton).toBeDisabled();
      
      // Don't actually try to click the disabled button with pointer-events: none
      // Just verify that the confirmation function is not called during loading
      expect(mockConfirmRegistration).not.toHaveBeenCalled();
    });
  });

  describe('Error Display', () => {
    it('should display error from AuthContext', () => {
      mockUseAuth.mockReturnValue({
        ...defaultAuthState,
        error: 'Network error'
      });
      
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });

    it('should display local validation error', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      // Submit without entering code
      await user.click(screen.getByRole('button', { name: /verify account/i }));
      
      expect(screen.getByText('Please enter the confirmation code')).toBeInTheDocument();
    });

    it('should prioritize context error over local error', async () => {
      const user = userEvent.setup();
      mockUseAuth.mockReturnValue({
        ...defaultAuthState,
        error: 'Context error'
      });
      
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      // Context error should be displayed immediately
      expect(screen.getByText('Context error')).toBeInTheDocument();
      
      // Even if we try to create a local error, context error takes priority
      await user.click(screen.getByRole('button', { name: /verify account/i }));
      
      expect(screen.getByText('Context error')).toBeInTheDocument();
      expect(screen.queryByText('Please enter the confirmation code')).not.toBeInTheDocument();
    });

    it('should clear local error when user starts typing', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      // Create a local error first
      await user.click(screen.getByRole('button', { name: /verify account/i }));
      expect(screen.getByText('Please enter the confirmation code')).toBeInTheDocument();
      
      // Start typing to clear the error
      const input = screen.getByPlaceholderText('Enter 6-digit code');
      await user.type(input, '1');
      
      expect(screen.queryByText('Please enter the confirmation code')).not.toBeInTheDocument();
    });
  });

  describe('Loading States', () => {
    it('should show loading button text when loading', () => {
      mockUseAuth.mockReturnValue({
        ...defaultAuthState,
        isLoading: true
      });
      
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      expect(screen.getByRole('button', { name: /verifying.../i })).toBeInTheDocument();
    });

    it('should disable all interactive elements when loading', () => {
      mockUseAuth.mockReturnValue({
        ...defaultAuthState,
        isLoading: true
      });
      
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      expect(screen.getByPlaceholderText('Enter 6-digit code')).toBeDisabled();
      expect(screen.getByRole('button', { name: /verifying.../i })).toBeDisabled();
      expect(screen.getByText('Back to Sign In').closest('button')).toBeDisabled();
      expect(screen.getByText('Resend').closest('button')).toBeDisabled();
    });
  });

  describe('Accessibility', () => {
    it('should have proper form labels and structure', () => {
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      const form = screen.getByRole('button', { name: /verify account/i }).closest('form');
      expect(form).toBeInTheDocument();
      
      const input = screen.getByPlaceholderText('Enter 6-digit code');
      expect(input).toBeInTheDocument();
      expect(input).toBeRequired();
    });

    it('should have proper heading hierarchy', () => {
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      const heading = screen.getByRole('heading', { level: 1 });
      expect(heading).toHaveTextContent('Verify Account');
    });

    it('should prevent form submission with Enter key when loading', async () => {
      const user = userEvent.setup();
      mockUseAuth.mockReturnValue({
        ...defaultAuthState,
        isLoading: true
      });
      
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      const input = screen.getByPlaceholderText('Enter 6-digit code');
      await user.type(input, '123456{enter}');
      
      expect(mockConfirmRegistration).not.toHaveBeenCalled();
    });
  });

  describe('Edge Cases', () => {
    it('should handle missing callback props gracefully', async () => {
      const user = userEvent.setup();
      mockConfirmRegistration.mockResolvedValue({ success: true });
      
      renderWithTheme(
        <ConfirmationForm 
          username="test@example.com"
          onConfirmationSuccess={undefined}
          onSwitchToLogin={undefined}
        />
      );
      
      const input = screen.getByPlaceholderText('Enter 6-digit code');
      await user.type(input, '123456');
      await user.click(screen.getByRole('button', { name: /verify account/i }));
      
      // Should not throw error
      await waitFor(() => {
        expect(mockConfirmRegistration).toHaveBeenCalled();
      });
    });

    it('should handle confirmation response without error field', async () => {
      const user = userEvent.setup();
      mockConfirmRegistration.mockResolvedValue({ success: false });
      
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      const input = screen.getByPlaceholderText('Enter 6-digit code');
      await user.type(input, '123456');
      await user.click(screen.getByRole('button', { name: /verify account/i }));
      
      await waitFor(() => {
        expect(mockConfirmRegistration).toHaveBeenCalled();
      });
      
      // Should not display any error message if none provided
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });

    it('should respect maxLength attribute on input', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ConfirmationForm {...defaultProps} />);
      
      const input = screen.getByPlaceholderText('Enter 6-digit code');
      await user.type(input, '1234567890');
      
      // Should only accept 6 characters due to maxLength
      expect(input.value.length).toBeLessThanOrEqual(6);
    });
  });
});