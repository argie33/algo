import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import MFAChallenge from '../../../../components/auth/MFAChallenge';

// Mock auth context
const mockAuthContext = {
  verifyMFA: vi.fn(),
  resendMFACode: vi.fn(),
  loading: false,
  error: null,
};

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthContext,
}));

describe('MFAChallenge Component', () => {
  const defaultProps = {
    challengeType: 'totp', // or 'sms', 'email'
    onSuccess: vi.fn(),
    onCancel: vi.fn(),
    maskedContact: '***-***-1234',
    sessionId: 'mfa-session-123',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthContext.loading = false;
    mockAuthContext.error = null;
  });

  describe('TOTP Challenge', () => {
    it('renders TOTP challenge interface', () => {
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      expect(screen.getByText(/enter verification code/i)).toBeInTheDocument();
      expect(screen.getByText(/authenticator app/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/verification code/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /verify code/i })).toBeInTheDocument();
    });

    it('displays 6-digit code input format', () => {
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      const codeInputs = screen.getAllByRole('textbox');
      expect(codeInputs).toHaveLength(6);
      
      codeInputs.forEach(input => {
        expect(input).toHaveAttribute('maxLength', '1');
        expect(input).toHaveAttribute('pattern', '[0-9]');
      });
    });

    it('handles code input with auto-focus progression', async () => {
      const user = userEvent.setup();
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      const codeInputs = screen.getAllByRole('textbox');
      
      // Type first digit
      await user.type(codeInputs[0], '1');
      expect(codeInputs[1]).toHaveFocus();
      
      // Type remaining digits
      await user.type(codeInputs[1], '2');
      await user.type(codeInputs[2], '3');
      await user.type(codeInputs[3], '4');
      await user.type(codeInputs[4], '5');
      await user.type(codeInputs[5], '6');
      
      // Verify button should be enabled
      expect(screen.getByRole('button', { name: /verify code/i })).not.toBeDisabled();
    });

    it('handles backspace navigation', async () => {
      const user = userEvent.setup();
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      const codeInputs = screen.getAllByRole('textbox');
      
      // Fill first two digits
      await user.type(codeInputs[0], '1');
      await user.type(codeInputs[1], '2');
      
      // Backspace should focus previous input
      await user.keyboard('[Backspace]');
      expect(codeInputs[0]).toHaveFocus();
    });

    it('submits TOTP code when complete', async () => {
      const user = userEvent.setup();
      mockAuthContext.verifyMFA.mockResolvedValue({ success: true });
      
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      const codeInputs = screen.getAllByRole('textbox');
      
      // Enter complete code
      await user.type(codeInputs[0], '1');
      await user.type(codeInputs[1], '2');
      await user.type(codeInputs[2], '3');
      await user.type(codeInputs[3], '4');
      await user.type(codeInputs[4], '5');
      await user.type(codeInputs[5], '6');
      
      const verifyButton = screen.getByRole('button', { name: /verify code/i });
      await user.click(verifyButton);
      
      expect(mockAuthContext.verifyMFA).toHaveBeenCalledWith({
        sessionId: 'mfa-session-123',
        code: '123456',
        challengeType: 'totp',
      });
    });
  });

  describe('SMS Challenge', () => {
    it('renders SMS challenge interface', () => {
      render(<MFAChallenge {...defaultProps} challengeType="sms" maskedContact="***-***-1234" />);
      
      expect(screen.getByText(/verification code sent/i)).toBeInTheDocument();
      expect(screen.getByText(/\*\*\*-\*\*\*-1234/)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /resend code/i })).toBeInTheDocument();
    });

    it('allows resending SMS code', async () => {
      const user = userEvent.setup();
      mockAuthContext.resendMFACode.mockResolvedValue({ success: true });
      
      render(<MFAChallenge {...defaultProps} challengeType="sms" />);
      
      const resendButton = screen.getByRole('button', { name: /resend code/i });
      await user.click(resendButton);
      
      expect(mockAuthContext.resendMFACode).toHaveBeenCalledWith({
        sessionId: 'mfa-session-123',
        challengeType: 'sms',
      });
    });

    it('implements resend cooldown timer', async () => {
      const user = userEvent.setup();
      mockAuthContext.resendMFACode.mockResolvedValue({ success: true });
      
      render(<MFAChallenge {...defaultProps} challengeType="sms" />);
      
      const resendButton = screen.getByRole('button', { name: /resend code/i });
      await user.click(resendButton);
      
      // Button should show countdown
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /resend in 30s/i })).toBeDisabled();
      });
    });
  });

  describe('Email Challenge', () => {
    it('renders email challenge interface', () => {
      render(<MFAChallenge {...defaultProps} challengeType="email" maskedContact="t***@example.com" />);
      
      expect(screen.getByText(/verification code sent/i)).toBeInTheDocument();
      expect(screen.getByText(/t\*\*\*@example\.com/)).toBeInTheDocument();
      expect(screen.getByText(/check your email/i)).toBeInTheDocument();
    });

    it('provides email troubleshooting help', () => {
      render(<MFAChallenge {...defaultProps} challengeType="email" />);
      
      expect(screen.getByText(/didn't receive the email/i)).toBeInTheDocument();
      expect(screen.getByText(/check spam folder/i)).toBeInTheDocument();
    });
  });

  describe('Code Validation', () => {
    it('validates code format for different challenge types', async () => {
      const user = userEvent.setup();
      
      // Test TOTP (6 digits)
      const { rerender } = render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      const codeInputs = screen.getAllByRole('textbox');
      await user.type(codeInputs[0], 'a'); // Non-numeric
      
      expect(screen.getByText(/code must contain only numbers/i)).toBeInTheDocument();
      
      // Test SMS (6 digits)
      rerender(<MFAChallenge {...defaultProps} challengeType="sms" />);
      
      const smsInput = screen.getByLabelText(/verification code/i);
      await user.type(smsInput, '12345'); // Too short
      await user.tab();
      
      expect(screen.getByText(/code must be 6 digits/i)).toBeInTheDocument();
    });

    it('handles expired codes', async () => {
      const user = userEvent.setup();
      mockAuthContext.verifyMFA.mockRejectedValue(new Error('Code expired'));
      
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      // Enter code
      const codeInputs = screen.getAllByRole('textbox');
      for (let i = 0; i < 6; i++) {
        await user.type(codeInputs[i], String(i + 1));
      }
      
      const verifyButton = screen.getByRole('button', { name: /verify code/i });
      await user.click(verifyButton);
      
      await waitFor(() => {
        expect(screen.getByText(/code expired/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
      });
    });

    it('handles invalid codes', async () => {
      const user = userEvent.setup();
      mockAuthContext.verifyMFA.mockRejectedValue(new Error('Invalid code'));
      
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      // Enter code
      const codeInputs = screen.getAllByRole('textbox');
      for (let i = 0; i < 6; i++) {
        await user.type(codeInputs[i], '0');
      }
      
      const verifyButton = screen.getByRole('button', { name: /verify code/i });
      await user.click(verifyButton);
      
      await waitFor(() => {
        expect(screen.getByText(/invalid code/i)).toBeInTheDocument();
        // Should clear the inputs for retry
        codeInputs.forEach(input => expect(input).toHaveValue(''));
      });
    });
  });

  describe('Loading States', () => {
    it('shows loading during verification', async () => {
      const _user = userEvent.setup();
      mockAuthContext.loading = true;
      
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      expect(screen.getByRole('button', { name: /verifying/i })).toBeDisabled();
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    it('shows loading during code resend', async () => {
      const _user = userEvent.setup();
      mockAuthContext.loading = true;
      
      render(<MFAChallenge {...defaultProps} challengeType="sms" />);
      
      expect(screen.getByRole('button', { name: /sending/i })).toBeDisabled();
    });
  });

  describe('Success Handling', () => {
    it('calls onSuccess callback after verification', async () => {
      const user = userEvent.setup();
      mockAuthContext.verifyMFA.mockResolvedValue({ 
        success: true, 
        accessToken: 'token123' 
      });
      
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      // Enter complete code
      const codeInputs = screen.getAllByRole('textbox');
      for (let i = 0; i < 6; i++) {
        await user.type(codeInputs[i], String(i + 1));
      }
      
      const verifyButton = screen.getByRole('button', { name: /verify code/i });
      await user.click(verifyButton);
      
      await waitFor(() => {
        expect(defaultProps.onSuccess).toHaveBeenCalledWith({ 
          success: true, 
          accessToken: 'token123' 
        });
      });
    });

    it('shows success message before redirect', async () => {
      const user = userEvent.setup();
      mockAuthContext.verifyMFA.mockResolvedValue({ success: true });
      
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      // Complete verification
      const codeInputs = screen.getAllByRole('textbox');
      for (let i = 0; i < 6; i++) {
        await user.type(codeInputs[i], String(i + 1));
      }
      await user.click(screen.getByRole('button', { name: /verify code/i }));
      
      await waitFor(() => {
        expect(screen.getByText(/verification successful/i)).toBeInTheDocument();
      });
    });
  });

  describe('Alternative Methods', () => {
    it('allows switching between MFA methods', async () => {
      const user = userEvent.setup();
      const mockOnMethodChange = vi.fn();
      
      render(
        <MFAChallenge 
          {...defaultProps} 
          challengeType="sms"
          alternativeMethods={['totp', 'email']}
          onMethodChange={mockOnMethodChange}
        />
      );
      
      expect(screen.getByText(/try another way/i)).toBeInTheDocument();
      
      const totpOption = screen.getByRole('button', { name: /authenticator app/i });
      await user.click(totpOption);
      
      expect(mockOnMethodChange).toHaveBeenCalledWith('totp');
    });

    it('displays backup codes option', async () => {
      const user = userEvent.setup();
      const mockOnBackupCode = vi.fn();
      
      render(
        <MFAChallenge 
          {...defaultProps} 
          challengeType="totp"
          enableBackupCodes={true}
          onBackupCode={mockOnBackupCode}
        />
      );
      
      const backupCodeLink = screen.getByRole('button', { name: /use backup code/i });
      await user.click(backupCodeLink);
      
      expect(mockOnBackupCode).toHaveBeenCalled();
    });
  });

  describe('Accessibility', () => {
    it('provides proper ARIA labels', () => {
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      const form = screen.getByRole('form');
      expect(form).toHaveAttribute('aria-label', 'Multi-factor authentication');
      
      const codeInputs = screen.getAllByRole('textbox');
      codeInputs.forEach((input, index) => {
        expect(input).toHaveAttribute('aria-label', `Digit ${index + 1}`);
      });
    });

    it('announces errors to screen readers', async () => {
      const user = userEvent.setup();
      mockAuthContext.verifyMFA.mockRejectedValue(new Error('Invalid code'));
      
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      // Submit invalid code
      const codeInputs = screen.getAllByRole('textbox');
      for (let i = 0; i < 6; i++) {
        await user.type(codeInputs[i], '0');
      }
      await user.click(screen.getByRole('button', { name: /verify code/i }));
      
      await waitFor(() => {
        const errorRegion = screen.getByRole('alert');
        expect(errorRegion).toBeInTheDocument();
        expect(errorRegion).toHaveAttribute('aria-live', 'assertive');
      });
    });

    it('supports keyboard navigation', async () => {
      const user = userEvent.setup();
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      // Should start focused on first input
      expect(screen.getAllByRole('textbox')[0]).toHaveFocus();
      
      // Arrow keys should navigate between inputs
      await user.keyboard('[ArrowRight]');
      expect(screen.getAllByRole('textbox')[1]).toHaveFocus();
      
      await user.keyboard('[ArrowLeft]');
      expect(screen.getAllByRole('textbox')[0]).toHaveFocus();
    });

    it('provides clear instructions for screen readers', () => {
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      expect(screen.getByText(/enter the 6-digit code/i)).toBeInTheDocument();
      expect(screen.getByText(/from your authenticator app/i)).toBeInTheDocument();
    });
  });

  describe('Security Features', () => {
    it('implements attempt limiting', async () => {
      const user = userEvent.setup();
      const mockOnTooManyAttempts = vi.fn();
      
      render(
        <MFAChallenge 
          {...defaultProps} 
          challengeType="totp"
          maxAttempts={3}
          onTooManyAttempts={mockOnTooManyAttempts}
        />
      );
      
      // Mock multiple failed attempts
      mockAuthContext.verifyMFA.mockRejectedValue(new Error('Invalid code'));
      
      const codeInputs = screen.getAllByRole('textbox');
      const verifyButton = screen.getByRole('button', { name: /verify code/i });
      
      // Attempt 1
      for (let i = 0; i < 6; i++) {
        await user.type(codeInputs[i], '0');
      }
      await user.click(verifyButton);
      
      // Clear and attempt 2
      await waitFor(() => {
        codeInputs.forEach(input => expect(input).toHaveValue(''));
      });
      
      for (let i = 0; i < 6; i++) {
        await user.type(codeInputs[i], '1');
      }
      await user.click(verifyButton);
      
      // Clear and attempt 3
      await waitFor(() => {
        codeInputs.forEach(input => expect(input).toHaveValue(''));
      });
      
      for (let i = 0; i < 6; i++) {
        await user.type(codeInputs[i], '2');
      }
      await user.click(verifyButton);
      
      await waitFor(() => {
        expect(mockOnTooManyAttempts).toHaveBeenCalled();
        expect(screen.getByText(/too many attempts/i)).toBeInTheDocument();
      });
    });

    it('clears sensitive data after successful verification', async () => {
      const user = userEvent.setup();
      mockAuthContext.verifyMFA.mockResolvedValue({ success: true });
      
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      const codeInputs = screen.getAllByRole('textbox');
      for (let i = 0; i < 6; i++) {
        await user.type(codeInputs[i], String(i + 1));
      }
      
      await user.click(screen.getByRole('button', { name: /verify code/i }));
      
      await waitFor(() => {
        codeInputs.forEach(input => expect(input).toHaveValue(''));
      });
    });

    it('prevents clipboard pasting of potentially malicious content', async () => {
      const _user = userEvent.setup();
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      const firstInput = screen.getAllByRole('textbox')[0];
      firstInput.focus();
      
      // Simulate paste with malicious content
      const clipboardData = new DataTransfer();
      clipboardData.setData('text/plain', '<script>alert("xss")</script>123456');
      
      const pasteEvent = new ClipboardEvent('paste', {
        clipboardData,
        bubbles: true,
        cancelable: true,
      });
      
      fireEvent(firstInput, pasteEvent);
      
      // Should only accept numeric characters
      const codeInputs = screen.getAllByRole('textbox');
      expect(codeInputs[0]).toHaveValue('1');
      expect(codeInputs[1]).toHaveValue('2');
      expect(codeInputs[2]).toHaveValue('3');
      expect(codeInputs[3]).toHaveValue('4');
      expect(codeInputs[4]).toHaveValue('5');
      expect(codeInputs[5]).toHaveValue('6');
    });
  });

  describe('Error Recovery', () => {
    it('provides clear recovery options for common errors', async () => {
      const user = userEvent.setup();
      mockAuthContext.verifyMFA.mockRejectedValue(new Error('Network error'));
      
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      // Submit code to trigger error
      const codeInputs = screen.getAllByRole('textbox');
      for (let i = 0; i < 6; i++) {
        await user.type(codeInputs[i], String(i + 1));
      }
      await user.click(screen.getByRole('button', { name: /verify code/i }));
      
      await waitFor(() => {
        expect(screen.getByText(/network error/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
      });
    });

    it('handles session timeout gracefully', async () => {
      const user = userEvent.setup();
      mockAuthContext.verifyMFA.mockRejectedValue(new Error('Session expired'));
      
      render(<MFAChallenge {...defaultProps} challengeType="totp" />);
      
      // Submit code
      const codeInputs = screen.getAllByRole('textbox');
      for (let i = 0; i < 6; i++) {
        await user.type(codeInputs[i], String(i + 1));
      }
      await user.click(screen.getByRole('button', { name: /verify code/i }));
      
      await waitFor(() => {
        expect(screen.getByText(/session expired/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /start over/i })).toBeInTheDocument();
      });
    });
  });
});