import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import AuthModal from '../../../../components/auth/AuthModal';

// Mock all auth form components
vi.mock('../../../../components/auth/LoginForm', () => ({
  default: ({ onSwitchToRegister, onSwitchToForgotPassword }) => (
    <div data-testid="login-form">
      <button onClick={onSwitchToRegister} data-testid="switch-to-register">
        Create Account
      </button>
      <button onClick={onSwitchToForgotPassword} data-testid="switch-to-forgot">
        Forgot Password
      </button>
    </div>
  )
}));

vi.mock('../../../../components/auth/RegisterForm', () => ({
  default: ({ onSwitchToLogin, onRegistrationSuccess }) => (
    <div data-testid="register-form">
      <button onClick={onSwitchToLogin} data-testid="switch-to-login">
        Back to Login
      </button>
      <button 
        onClick={() => onRegistrationSuccess('testuser', 'confirm')} 
        data-testid="register-success"
      >
        Register Success
      </button>
    </div>
  )
}));

vi.mock('../../../../components/auth/ConfirmationForm', () => ({
  default: ({ username, onConfirmationSuccess, onSwitchToLogin }) => (
    <div data-testid="confirmation-form">
      <div data-testid="confirm-username">{username}</div>
      <button onClick={onConfirmationSuccess} data-testid="confirm-success">
        Confirm Success
      </button>
      <button onClick={onSwitchToLogin} data-testid="switch-to-login">
        Back to Login
      </button>
    </div>
  )
}));

vi.mock('../../../../components/auth/ForgotPasswordForm', () => ({
  default: ({ onForgotPasswordSuccess, onSwitchToLogin }) => (
    <div data-testid="forgot-password-form">
      <button 
        onClick={() => onForgotPasswordSuccess('testuser')} 
        data-testid="forgot-success"
      >
        Forgot Success
      </button>
      <button onClick={onSwitchToLogin} data-testid="switch-to-login">
        Back to Login
      </button>
    </div>
  )
}));

vi.mock('../../../../components/auth/ResetPasswordForm', () => ({
  default: ({ username, onPasswordResetSuccess, onSwitchToLogin }) => (
    <div data-testid="reset-password-form">
      <div data-testid="reset-username">{username}</div>
      <button onClick={onPasswordResetSuccess} data-testid="reset-success">
        Reset Success
      </button>
      <button onClick={onSwitchToLogin} data-testid="switch-to-login">
        Back to Login
      </button>
    </div>
  )
}));

vi.mock('../../../../components/auth/MFAChallenge', () => ({
  default: ({ challengeType, message, onSuccess, onCancel }) => (
    <div data-testid="mfa-challenge">
      <div data-testid="mfa-type">{challengeType}</div>
      <div data-testid="mfa-message">{message}</div>
      <button onClick={() => onSuccess({ token: 'test-token' })} data-testid="mfa-success">
        MFA Success
      </button>
      <button onClick={onCancel} data-testid="mfa-cancel">
        MFA Cancel
      </button>
    </div>
  )
}));

describe('AuthModal', () => {
  const defaultProps = {
    open: true,
    onClose: vi.fn(),
    initialMode: 'login'
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Functionality', () => {
    test('renders login form by default', () => {
      render(<AuthModal {...defaultProps} />);
      
      expect(screen.getByText('Sign In')).toBeInTheDocument();
      expect(screen.getByTestId('login-form')).toBeInTheDocument();
    });

    test('renders with custom initial mode', () => {
      render(<AuthModal {...defaultProps} initialMode="register" />);
      
      expect(screen.getByText('Create Account')).toBeInTheDocument();
      expect(screen.getByTestId('register-form')).toBeInTheDocument();
    });

    test('closes modal when close button is clicked', () => {
      const onClose = vi.fn();
      render(<AuthModal {...defaultProps} onClose={onClose} />);
      
      const closeButton = screen.getByLabelText('close');
      fireEvent.click(closeButton);
      
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    test('does not render when open is false', () => {
      render(<AuthModal {...defaultProps} open={false} />);
      
      expect(screen.queryByText('Sign In')).not.toBeInTheDocument();
    });
  });

  describe('Mode Navigation', () => {
    test('switches from login to register', () => {
      render(<AuthModal {...defaultProps} />);
      
      const switchButton = screen.getByTestId('switch-to-register');
      fireEvent.click(switchButton);
      
      expect(screen.getByText('Create Account')).toBeInTheDocument();
      expect(screen.getByTestId('register-form')).toBeInTheDocument();
    });

    test('switches from login to forgot password', () => {
      render(<AuthModal {...defaultProps} />);
      
      const switchButton = screen.getByTestId('switch-to-forgot');
      fireEvent.click(switchButton);
      
      expect(screen.getByText('Reset Password')).toBeInTheDocument();
      expect(screen.getByTestId('forgot-password-form')).toBeInTheDocument();
    });

    test('switches from register back to login', () => {
      render(<AuthModal {...defaultProps} initialMode="register" />);
      
      const switchButton = screen.getByTestId('switch-to-login');
      fireEvent.click(switchButton);
      
      expect(screen.getByText('Sign In')).toBeInTheDocument();
      expect(screen.getByTestId('login-form')).toBeInTheDocument();
    });
  });

  describe('Registration Flow', () => {
    test('handles successful registration and switches to confirmation', () => {
      render(<AuthModal {...defaultProps} initialMode="register" />);
      
      const successButton = screen.getByTestId('register-success');
      fireEvent.click(successButton);
      
      expect(screen.getByText('Verify Account')).toBeInTheDocument();
      expect(screen.getByTestId('confirmation-form')).toBeInTheDocument();
      expect(screen.getByTestId('confirm-username')).toHaveTextContent('testuser');
      expect(screen.getByText('Registration successful! Please check your email for a verification code.')).toBeInTheDocument();
    });

    test('handles successful confirmation and returns to login', () => {
      render(<AuthModal {...defaultProps} initialMode="confirm" />);
      
      const confirmButton = screen.getByTestId('confirm-success');
      fireEvent.click(confirmButton);
      
      expect(screen.getByText('Sign In')).toBeInTheDocument();
      expect(screen.getByTestId('login-form')).toBeInTheDocument();
      expect(screen.getByText('Account confirmed! You can now sign in.')).toBeInTheDocument();
    });
  });

  describe('Password Reset Flow', () => {
    test('handles successful forgot password and switches to reset', () => {
      render(<AuthModal {...defaultProps} initialMode="forgot_password" />);
      
      const forgotButton = screen.getByTestId('forgot-success');
      fireEvent.click(forgotButton);
      
      expect(screen.getByText('Set New Password')).toBeInTheDocument();
      expect(screen.getByTestId('reset-password-form')).toBeInTheDocument();
      expect(screen.getByTestId('reset-username')).toHaveTextContent('testuser');
      expect(screen.getByText('Password reset code sent! Please check your email.')).toBeInTheDocument();
    });

    test('handles successful password reset and returns to login', () => {
      render(<AuthModal {...defaultProps} initialMode="reset_password" />);
      
      const resetButton = screen.getByTestId('reset-success');
      fireEvent.click(resetButton);
      
      expect(screen.getByText('Sign In')).toBeInTheDocument();
      expect(screen.getByTestId('login-form')).toBeInTheDocument();
      expect(screen.getByText('Password reset successful! You can now sign in with your new password.')).toBeInTheDocument();
    });
  });

  describe('MFA Flow', () => {
    test('renders MFA challenge correctly', () => {
      render(<AuthModal {...defaultProps} initialMode="mfa_challenge" />);
      
      expect(screen.getByText('Multi-Factor Authentication')).toBeInTheDocument();
      expect(screen.getByTestId('mfa-challenge')).toBeInTheDocument();
      expect(screen.getByTestId('mfa-type')).toHaveTextContent('SMS_MFA');
      expect(screen.getByTestId('mfa-message')).toHaveTextContent('Please enter the verification code sent to your device.');
    });

    test('handles MFA success', () => {
      const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
      render(<AuthModal {...defaultProps} initialMode="mfa_challenge" />);
      
      const mfaButton = screen.getByTestId('mfa-success');
      fireEvent.click(mfaButton);
      
      expect(screen.getByText('Sign In')).toBeInTheDocument();
      expect(screen.getByText('Multi-factor authentication successful!')).toBeInTheDocument();
      expect(consoleSpy).toHaveBeenCalledWith('MFA Success:', { token: 'test-token' });
      
      consoleSpy.mockRestore();
    });

    test('handles MFA cancel', () => {
      render(<AuthModal {...defaultProps} initialMode="mfa_challenge" />);
      
      const cancelButton = screen.getByTestId('mfa-cancel');
      fireEvent.click(cancelButton);
      
      expect(screen.getByText('Sign In')).toBeInTheDocument();
      expect(screen.getByTestId('login-form')).toBeInTheDocument();
    });
  });

  describe('Success Messages', () => {
    test('clears success message when switching modes', () => {
      render(<AuthModal {...defaultProps} initialMode="register" />);
      
      // Trigger success message
      const successButton = screen.getByTestId('register-success');
      fireEvent.click(successButton);
      expect(screen.getByText('Registration successful! Please check your email for a verification code.')).toBeInTheDocument();
      
      // Switch modes
      const switchButton = screen.getByTestId('switch-to-login');
      fireEvent.click(switchButton);
      
      // Success message should be cleared
      expect(screen.queryByText('Registration successful! Please check your email for a verification code.')).not.toBeInTheDocument();
    });
  });

  describe('Modal State Reset', () => {
    test('resets state when modal is closed', () => {
      const onClose = vi.fn();
      render(<AuthModal {...defaultProps} onClose={onClose} initialMode="register" />);
      
      // Change to different mode
      const switchButton = screen.getByTestId('switch-to-login');
      fireEvent.click(switchButton);
      
      // Close modal
      const closeButton = screen.getByLabelText('close');
      fireEvent.click(closeButton);
      
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  describe('Title Display', () => {
    const titleTests = [
      { mode: 'login', expectedTitle: 'Sign In' },
      { mode: 'register', expectedTitle: 'Create Account' },
      { mode: 'confirm', expectedTitle: 'Verify Account' },
      { mode: 'forgot_password', expectedTitle: 'Reset Password' },
      { mode: 'reset_password', expectedTitle: 'Set New Password' },
      { mode: 'mfa_challenge', expectedTitle: 'Multi-Factor Authentication' },
    ];

    titleTests.forEach(({ mode, expectedTitle }) => {
      test(`displays correct title for ${mode} mode`, () => {
        render(<AuthModal {...defaultProps} initialMode={mode} />);
        expect(screen.getByText(expectedTitle)).toBeInTheDocument();
      });
    });
  });
});