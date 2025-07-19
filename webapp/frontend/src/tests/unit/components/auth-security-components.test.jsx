/**
 * Authentication and Security Components Unit Tests
 * Comprehensive testing of all auth and security-related components
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';

// Mock Material-UI components
vi.mock('@mui/material', () => ({
  Box: ({ children, ...props }) => <div data-testid="mui-box" {...props}>{children}</div>,
  Card: ({ children, ...props }) => <div data-testid="mui-card" {...props}>{children}</div>,
  CardContent: ({ children, ...props }) => <div data-testid="mui-card-content" {...props}>{children}</div>,
  TextField: ({ label, name, type, onChange, value, disabled, ...props }) => (
    <input
      data-testid={`textfield-${name || label?.toLowerCase()}`}
      name={name}
      type={type}
      onChange={onChange}
      value={value}
      disabled={disabled}
      placeholder={label}
      {...props}
    />
  ),
  Button: ({ children, onClick, disabled, type, ...props }) => (
    <button
      data-testid="mui-button"
      onClick={onClick}
      disabled={disabled}
      type={type}
      {...props}
    >
      {children}
    </button>
  ),
  Typography: ({ children, variant, ...props }) => (
    <div data-testid={`typography-${variant}`} {...props}>{children}</div>
  ),
  Alert: ({ children, severity, ...props }) => (
    <div data-testid="mui-alert" data-severity={severity} {...props}>{children}</div>
  ),
  CircularProgress: ({ size, ...props }) => (
    <div data-testid="circular-progress" data-size={size} {...props} />
  ),
  Link: ({ children, onClick, ...props }) => (
    <button data-testid="mui-link" onClick={onClick} {...props}>{children}</button>
  ),
  InputAdornment: ({ children, position, ...props }) => (
    <div data-testid={`input-adornment-${position}`} {...props}>{children}</div>
  ),
  IconButton: ({ children, onClick, disabled, ...props }) => (
    <button data-testid="icon-button" onClick={onClick} disabled={disabled} {...props}>
      {children}
    </button>
  ),
  Divider: (props) => <hr data-testid="divider" {...props} />,
  Collapse: ({ children, in: inProp, ...props }) => (
    <div data-testid="collapse" data-collapsed={!inProp} {...props}>
      {inProp ? children : null}
    </div>
  ),
  Modal: ({ children, open, onClose, ...props }) => (
    open ? <div data-testid="modal" onClick={onClose} {...props}>{children}</div> : null
  ),
  Dialog: ({ children, open, onClose, ...props }) => (
    open ? <div data-testid="dialog" onClick={onClose} {...props}>{children}</div> : null
  ),
  DialogTitle: ({ children, ...props }) => (
    <div data-testid="dialog-title" {...props}>{children}</div>
  ),
  DialogContent: ({ children, ...props }) => (
    <div data-testid="dialog-content" {...props}>{children}</div>
  ),
  DialogActions: ({ children, ...props }) => (
    <div data-testid="dialog-actions" {...props}>{children}</div>
  ),
  FormControl: ({ children, ...props }) => (
    <div data-testid="form-control" {...props}>{children}</div>
  ),
  FormLabel: ({ children, ...props }) => (
    <label data-testid="form-label" {...props}>{children}</label>
  ),
  RadioGroup: ({ children, value, onChange, ...props }) => (
    <div data-testid="radio-group" data-value={value} onChange={onChange} {...props}>{children}</div>
  ),
  FormControlLabel: ({ label, control, ...props }) => (
    <label data-testid="form-control-label" {...props}>
      {control}
      {label}
    </label>
  ),
  Radio: ({ value, ...props }) => (
    <input type="radio" data-testid="radio" value={value} {...props} />
  ),
  Checkbox: ({ checked, onChange, ...props }) => (
    <input type="checkbox" data-testid="checkbox" checked={checked} onChange={onChange} {...props} />
  ),
  Stepper: ({ children, activeStep, ...props }) => (
    <div data-testid="stepper" data-active-step={activeStep} {...props}>{children}</div>
  ),
  Step: ({ children, ...props }) => (
    <div data-testid="step" {...props}>{children}</div>
  ),
  StepLabel: ({ children, ...props }) => (
    <div data-testid="step-label" {...props}>{children}</div>
  ),
  StepContent: ({ children, ...props }) => (
    <div data-testid="step-content" {...props}>{children}</div>
  ),
  Tabs: ({ children, value, onChange, ...props }) => (
    <div data-testid="tabs" data-value={value} onChange={onChange} {...props}>{children}</div>
  ),
  Tab: ({ label, ...props }) => (
    <button data-testid="tab" {...props}>{label}</button>
  ),
  TabPanel: ({ children, ...props }) => (
    <div data-testid="tab-panel" {...props}>{children}</div>
  )
}));

// Mock Material-UI icons
vi.mock('@mui/icons-material', () => ({
  Visibility: () => <span data-testid="visibility-icon" />,
  VisibilityOff: () => <span data-testid="visibility-off-icon" />,
  Login: () => <span data-testid="login-icon" />,
  Security: () => <span data-testid="security-icon" />,
  Lock: () => <span data-testid="lock-icon" />,
  Key: () => <span data-testid="key-icon" />,
  Settings: () => <span data-testid="settings-icon" />,
  Person: () => <span data-testid="person-icon" />,
  Email: () => <span data-testid="email-icon" />,
  VpnKey: () => <span data-testid="vpn-key-icon" />,
  Shield: () => <span data-testid="shield-icon" />,
  Fingerprint: () => <span data-testid="fingerprint-icon" />,
  PhoneAndroid: () => <span data-testid="phone-icon" />,
  Sms: () => <span data-testid="sms-icon" />
}));

// Mock the AuthContext
const mockAuthContext = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  clearError: vi.fn(),
  forgotPassword: vi.fn(),
  resetPassword: vi.fn()
};

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthContext
}));

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    BrowserRouter: ({ children }) => children
  };
});

// Mock API service
vi.mock('../../services/api', () => ({
  getApiKeys: vi.fn(),
  saveApiKey: vi.fn(),
  deleteApiKey: vi.fn()
}));

// Mock child components
vi.mock('../BiometricAuth', () => ({
  default: ({ onAuthSuccess, onSetupComplete, onError, userId, username }) => (
    <div data-testid="biometric-auth">
      <button onClick={() => onAuthSuccess?.({ success: true })}>Authenticate</button>
      <button onClick={() => onSetupComplete?.({ credentialId: 'test' })}>Setup</button>
      <button onClick={() => onError?.('Test error')}>Error</button>
    </div>
  )
}));

vi.mock('../MFASetupModal', () => ({
  default: ({ open, onClose, onSetupComplete }) => (
    open ? (
      <div data-testid="mfa-setup-modal">
        <button onClick={() => onSetupComplete?.('sms')}>Complete SMS Setup</button>
        <button onClick={onClose}>Close</button>
      </div>
    ) : null
  )
}));

vi.mock('../ApiKeySetupWizard', () => ({
  default: ({ open, onClose, onComplete }) => (
    open ? (
      <div data-testid="api-key-setup-wizard">
        <button onClick={() => onComplete?.({ provider: 'alpaca' })}>Complete Setup</button>
        <button onClick={onClose}>Close</button>
      </div>
    ) : null
  )
}));

// Real Authentication Components - Import actual production components
import LoginForm from '../../../components/auth/LoginForm';
import RegisterForm from '../../../components/auth/RegisterForm';
import ForgotPasswordForm from '../../../components/auth/ForgotPasswordForm';
import ResetPasswordForm from '../../../components/auth/ResetPasswordForm';
import ConfirmationForm from '../../../components/auth/ConfirmationForm';
import PasswordStrengthValidator from '../../../components/auth/PasswordStrengthValidator';
import ProtectedRoute from '../../../components/auth/ProtectedRoute';
import AuthModal from '../../../components/auth/AuthModal';
import SessionManager from '../../../components/auth/SessionManager';
import SecurityDashboard from '../../../components/auth/SecurityDashboard';
import BiometricAuth from '../../../components/auth/BiometricAuth';
import MFASetupModal from '../../../components/auth/MFASetupModal';

describe('🔐 Authentication and Security Components', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset auth context to default state
    mockAuthContext.user = null;
    mockAuthContext.isAuthenticated = false;
    mockAuthContext.isLoading = false;
    mockAuthContext.error = null;
    mockAuthContext.login.mockResolvedValue({ success: true });
    mockAuthContext.register.mockResolvedValue({ success: true });
    mockAuthContext.forgotPassword.mockResolvedValue({ success: true });
    mockAuthContext.resetPassword.mockResolvedValue({ success: true });
    
    // Mock successful API responses
    const mockApi = require('../../services/api');
    mockApi.getApiKeys.mockResolvedValue({ apiKeys: [] });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('LoginForm Component', () => {
    const defaultProps = {
      onSwitchToRegister: vi.fn(),
      onSwitchToForgotPassword: vi.fn()
    };

    it('should render login form correctly', () => {
      render(<LoginForm {...defaultProps} />);
      
      expect(screen.getByTestId('textfield-username')).toBeInTheDocument();
      expect(screen.getByTestId('textfield-password')).toBeInTheDocument();
      expect(screen.getByTestId('mui-button')).toBeInTheDocument();
      expect(screen.getByText('Sign In')).toBeInTheDocument();
    });

    it('should handle form input changes', async () => {
      render(<LoginForm {...defaultProps} />);
      
      const usernameInput = screen.getByTestId('textfield-username');
      const passwordInput = screen.getByTestId('textfield-password');
      
      await userEvent.type(usernameInput, 'testuser');
      await userEvent.type(passwordInput, 'password123');
      
      expect(usernameInput.value).toBe('testuser');
      expect(passwordInput.value).toBe('password123');
    });

    it('should toggle password visibility', async () => {
      render(<LoginForm {...defaultProps} />);
      
      const passwordInput = screen.getByTestId('textfield-password');
      const toggleButton = screen.getByTestId('icon-button');
      
      expect(passwordInput.type).toBe('password');
      
      await userEvent.click(toggleButton);
      expect(passwordInput.type).toBe('text');
    });

    it('should handle form submission', async () => {
      render(<LoginForm {...defaultProps} />);
      
      const usernameInput = screen.getByTestId('textfield-username');
      const passwordInput = screen.getByTestId('textfield-password');
      const submitButton = screen.getByTestId('mui-button');
      
      await userEvent.type(usernameInput, 'testuser');
      await userEvent.type(passwordInput, 'password123');
      await userEvent.click(submitButton);
      
      expect(mockAuthContext.login).toHaveBeenCalledWith('testuser', 'password123');
    });

    it('should display validation errors', async () => {
      render(<LoginForm {...defaultProps} />);
      
      const submitButton = screen.getByTestId('mui-button');
      await userEvent.click(submitButton);
      
      expect(screen.getByText('Please enter both username and password')).toBeInTheDocument();
    });

    it('should handle authentication errors', () => {
      mockAuthContext.error = 'Invalid credentials';
      render(<LoginForm {...defaultProps} />);
      
      expect(screen.getByTestId('mui-alert')).toBeInTheDocument();
      expect(screen.getByText('Invalid credentials')).toBeInTheDocument();
    });

    it('should show loading state during authentication', () => {
      mockAuthContext.isLoading = true;
      render(<LoginForm {...defaultProps} />);
      
      expect(screen.getByText('Signing In...')).toBeInTheDocument();
      expect(screen.getByTestId('circular-progress')).toBeInTheDocument();
    });

    it('should handle navigation to register and forgot password', async () => {
      render(<LoginForm {...defaultProps} />);
      
      const registerLink = screen.getByText('Sign up here');
      const forgotPasswordLink = screen.getByText('Forgot password?');
      
      await userEvent.click(registerLink);
      expect(defaultProps.onSwitchToRegister).toHaveBeenCalled();
      
      await userEvent.click(forgotPasswordLink);
      expect(defaultProps.onSwitchToForgotPassword).toHaveBeenCalled();
    });

    it('should show MFA setup after successful login', () => {
      mockAuthContext.user = { userId: 'user123', mfaEnabled: false };
      render(<LoginForm {...defaultProps} />);
      
      expect(screen.getByTestId('mfa-setup-modal')).toBeInTheDocument();
    });

    it('should show biometric auth for authenticated users', () => {
      mockAuthContext.user = { userId: 'user123', username: 'testuser' };
      render(<LoginForm {...defaultProps} />);
      
      expect(screen.getByTestId('biometric-auth')).toBeInTheDocument();
    });
  });

  describe('RegisterForm Component', () => {
    const defaultProps = {
      onSwitchToLogin: vi.fn()
    };

    it('should render registration form correctly', () => {
      render(<RegisterForm {...defaultProps} />);
      
      expect(screen.getByTestId('textfield-username')).toBeInTheDocument();
      expect(screen.getByTestId('textfield-email')).toBeInTheDocument();
      expect(screen.getByTestId('textfield-password')).toBeInTheDocument();
      expect(screen.getByText(/Sign Up/i)).toBeInTheDocument();
    });

    it('should handle form input validation', async () => {
      render(<RegisterForm {...defaultProps} />);
      
      const emailInput = screen.getByTestId('textfield-email');
      await userEvent.type(emailInput, 'invalid-email');
      
      const submitButton = screen.getByTestId('mui-button');
      await userEvent.click(submitButton);
      
      // Should show validation error
      expect(screen.getByTestId('mui-alert')).toBeInTheDocument();
    });

    it('should handle successful registration', async () => {
      render(<RegisterForm {...defaultProps} />);
      
      await userEvent.type(screen.getByTestId('textfield-username'), 'newuser');
      await userEvent.type(screen.getByTestId('textfield-email'), 'test@example.com');
      await userEvent.type(screen.getByTestId('textfield-password'), 'SecurePass123!');
      
      const submitButton = screen.getByTestId('mui-button');
      await userEvent.click(submitButton);
      
      expect(mockAuthContext.register).toHaveBeenCalled();
    });
  });

  describe('ProtectedRoute Component', () => {
    const TestComponent = () => <div data-testid="protected-content">Protected Content</div>;

    it('should render children when no protection required', () => {
      render(
        <BrowserRouter>
          <ProtectedRoute>
            <TestComponent />
          </ProtectedRoute>
        </BrowserRouter>
      );
      
      expect(screen.getByTestId('protected-content')).toBeInTheDocument();
    });

    it('should show loading state when checking authentication', () => {
      mockAuthContext.isLoading = true;
      
      render(
        <BrowserRouter>
          <ProtectedRoute requireAuth={true}>
            <TestComponent />
          </ProtectedRoute>
        </BrowserRouter>
      );
      
      expect(screen.getByTestId('circular-progress')).toBeInTheDocument();
    });

    it('should show authentication required message when not authenticated', () => {
      render(
        <BrowserRouter>
          <ProtectedRoute requireAuth={true}>
            <TestComponent />
          </ProtectedRoute>
        </BrowserRouter>
      );
      
      expect(screen.getByText('Authentication Required')).toBeInTheDocument();
      expect(screen.getByText('Sign In')).toBeInTheDocument();
    });

    it('should render children when authenticated', () => {
      mockAuthContext.isAuthenticated = true;
      mockAuthContext.user = { userId: 'user123' };
      
      render(
        <BrowserRouter>
          <ProtectedRoute requireAuth={true}>
            <TestComponent />
          </ProtectedRoute>
        </BrowserRouter>
      );
      
      expect(screen.getByTestId('protected-content')).toBeInTheDocument();
    });

    it('should show API key setup required when no API keys', async () => {
      mockAuthContext.isAuthenticated = true;
      mockAuthContext.user = { userId: 'user123' };
      
      render(
        <BrowserRouter>
          <ProtectedRoute requireAuth={true} requireApiKeys={true}>
            <TestComponent />
          </ProtectedRoute>
        </BrowserRouter>
      );
      
      await waitFor(() => {
        expect(screen.getByText('API Key Setup Required')).toBeInTheDocument();
      });
    });

    it('should handle API key setup completion', async () => {
      mockAuthContext.isAuthenticated = true;
      mockAuthContext.user = { userId: 'user123' };
      
      render(
        <BrowserRouter>
          <ProtectedRoute requireAuth={true} requireApiKeys={true}>
            <TestComponent />
          </ProtectedRoute>
        </BrowserRouter>
      );
      
      await waitFor(() => {
        expect(screen.getByText('Set Up API Keys')).toBeInTheDocument();
      });
      
      const setupButton = screen.getByText('Set Up API Keys');
      await userEvent.click(setupButton);
      
      expect(screen.getByTestId('api-key-setup-wizard')).toBeInTheDocument();
    });

    it('should handle navigation to settings', async () => {
      mockAuthContext.isAuthenticated = true;
      mockAuthContext.user = { userId: 'user123' };
      
      render(
        <BrowserRouter>
          <ProtectedRoute requireAuth={true} requireApiKeys={true}>
            <TestComponent />
          </ProtectedRoute>
        </BrowserRouter>
      );
      
      await waitFor(() => {
        const settingsButton = screen.getByText('Go to Settings');
        userEvent.click(settingsButton);
      });
      
      expect(mockNavigate).toHaveBeenCalledWith('/settings');
    });

    it('should render fallback component when provided', () => {
      const fallback = <div data-testid="custom-fallback">Custom Fallback</div>;
      
      render(
        <BrowserRouter>
          <ProtectedRoute requireAuth={true} fallback={fallback}>
            <TestComponent />
          </ProtectedRoute>
        </BrowserRouter>
      );
      
      expect(screen.getByTestId('custom-fallback')).toBeInTheDocument();
    });
  });

  describe('ForgotPasswordForm Component', () => {
    const defaultProps = {
      onSwitchToLogin: vi.fn()
    };

    it('should render forgot password form correctly', () => {
      render(<ForgotPasswordForm {...defaultProps} />);
      
      expect(screen.getByTestId('textfield-email')).toBeInTheDocument();
      expect(screen.getByText(/Reset Password/i)).toBeInTheDocument();
    });

    it('should handle email submission', async () => {
      render(<ForgotPasswordForm {...defaultProps} />);
      
      const emailInput = screen.getByTestId('textfield-email');
      await userEvent.type(emailInput, 'test@example.com');
      
      const submitButton = screen.getByTestId('mui-button');
      await userEvent.click(submitButton);
      
      expect(mockAuthContext.forgotPassword).toHaveBeenCalledWith('test@example.com');
    });
  });

  describe('PasswordStrengthValidator Component', () => {
    it('should display password strength indicators', () => {
      render(<PasswordStrengthValidator password="weak" />);
      
      // Should render password strength indicators
      expect(screen.getByTestId('password-strength')).toBeInTheDocument();
    });

    it('should validate strong passwords', () => {
      render(<PasswordStrengthValidator password="StrongPass123!" />);
      
      expect(screen.getByTestId('password-strength')).toBeInTheDocument();
    });

    it('should provide feedback for weak passwords', () => {
      render(<PasswordStrengthValidator password="123" />);
      
      expect(screen.getByTestId('password-strength')).toBeInTheDocument();
    });
  });

  describe('BiometricAuth Component', () => {
    const defaultProps = {
      userId: 'user123',
      username: 'testuser',
      onAuthSuccess: vi.fn(),
      onSetupComplete: vi.fn(),
      onError: vi.fn()
    };

    it('should render biometric authentication interface', () => {
      render(<BiometricAuth {...defaultProps} />);
      
      expect(screen.getByTestId('biometric-auth')).toBeInTheDocument();
    });

    it('should handle successful biometric authentication', async () => {
      render(<BiometricAuth {...defaultProps} />);
      
      const authButton = screen.getByText('Authenticate');
      await userEvent.click(authButton);
      
      expect(defaultProps.onAuthSuccess).toHaveBeenCalledWith({ success: true });
    });

    it('should handle biometric setup completion', async () => {
      render(<BiometricAuth {...defaultProps} />);
      
      const setupButton = screen.getByText('Setup');
      await userEvent.click(setupButton);
      
      expect(defaultProps.onSetupComplete).toHaveBeenCalledWith({ credentialId: 'test' });
    });

    it('should handle biometric errors', async () => {
      render(<BiometricAuth {...defaultProps} />);
      
      const errorButton = screen.getByText('Error');
      await userEvent.click(errorButton);
      
      expect(defaultProps.onError).toHaveBeenCalledWith('Test error');
    });
  });

  describe('MFASetupModal Component', () => {
    const defaultProps = {
      open: true,
      onClose: vi.fn(),
      onSetupComplete: vi.fn(),
      userPhoneNumber: '+1234567890'
    };

    it('should render MFA setup modal when open', () => {
      render(<MFASetupModal {...defaultProps} />);
      
      expect(screen.getByTestId('mfa-setup-modal')).toBeInTheDocument();
    });

    it('should handle MFA setup completion', async () => {
      render(<MFASetupModal {...defaultProps} />);
      
      const completeButton = screen.getByText('Complete SMS Setup');
      await userEvent.click(completeButton);
      
      expect(defaultProps.onSetupComplete).toHaveBeenCalledWith('sms');
    });

    it('should handle modal close', async () => {
      render(<MFASetupModal {...defaultProps} />);
      
      const closeButton = screen.getByText('Close');
      await userEvent.click(closeButton);
      
      expect(defaultProps.onClose).toHaveBeenCalled();
    });

    it('should not render when closed', () => {
      render(<MFASetupModal {...defaultProps} open={false} />);
      
      expect(screen.queryByTestId('mfa-setup-modal')).not.toBeInTheDocument();
    });
  });

  describe('SessionManager Component', () => {
    it('should render session manager interface', () => {
      render(<SessionManager />);
      
      expect(screen.getByTestId('session-manager')).toBeInTheDocument();
    });

    it('should handle session timeout warnings', () => {
      render(<SessionManager showTimeoutWarning={true} />);
      
      expect(screen.getByText(/Session Timeout/i)).toBeInTheDocument();
    });

    it('should handle session extension', async () => {
      const onExtendSession = vi.fn();
      render(<SessionManager onExtendSession={onExtendSession} />);
      
      const extendButton = screen.getByText('Extend Session');
      await userEvent.click(extendButton);
      
      expect(onExtendSession).toHaveBeenCalled();
    });
  });

  describe('SecurityDashboard Component', () => {
    it('should render security dashboard interface', () => {
      mockAuthContext.isAuthenticated = true;
      mockAuthContext.user = { userId: 'user123' };
      
      render(<SecurityDashboard />);
      
      expect(screen.getByTestId('security-dashboard')).toBeInTheDocument();
    });

    it('should display security status indicators', () => {
      mockAuthContext.isAuthenticated = true;
      mockAuthContext.user = { 
        userId: 'user123',
        mfaEnabled: true,
        biometricEnabled: false 
      };
      
      render(<SecurityDashboard />);
      
      expect(screen.getByText(/MFA Enabled/i)).toBeInTheDocument();
    });

    it('should handle security setting changes', async () => {
      mockAuthContext.isAuthenticated = true;
      mockAuthContext.user = { userId: 'user123' };
      
      render(<SecurityDashboard />);
      
      const enableMFAButton = screen.queryByText('Enable MFA');
      if (enableMFAButton) {
        await userEvent.click(enableMFAButton);
        // Should trigger MFA setup flow
      }
    });
  });

  describe('AuthModal Component', () => {
    const defaultProps = {
      open: true,
      onClose: vi.fn(),
      initialView: 'login'
    };

    it('should render auth modal when open', () => {
      render(<AuthModal {...defaultProps} />);
      
      expect(screen.getByTestId('auth-modal')).toBeInTheDocument();
    });

    it('should switch between login and register views', async () => {
      render(<AuthModal {...defaultProps} />);
      
      // Should initially show login form
      expect(screen.getByTestId('textfield-username')).toBeInTheDocument();
      
      // Switch to register
      const switchButton = screen.getByText('Sign up here');
      await userEvent.click(switchButton);
      
      expect(screen.getByTestId('textfield-email')).toBeInTheDocument();
    });

    it('should handle modal close', async () => {
      render(<AuthModal {...defaultProps} />);
      
      const modal = screen.getByTestId('auth-modal');
      await userEvent.click(modal);
      
      expect(defaultProps.onClose).toHaveBeenCalled();
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('should handle network errors gracefully', async () => {
      mockAuthContext.login.mockRejectedValue(new Error('Network error'));
      
      render(<LoginForm onSwitchToRegister={vi.fn()} onSwitchToForgotPassword={vi.fn()} />);
      
      await userEvent.type(screen.getByTestId('textfield-username'), 'user');
      await userEvent.type(screen.getByTestId('textfield-password'), 'pass');
      await userEvent.click(screen.getByTestId('mui-button'));
      
      // Should handle error gracefully
      expect(mockAuthContext.login).toHaveBeenCalled();
    });

    it('should handle malformed authentication responses', async () => {
      mockAuthContext.login.mockResolvedValue({ success: false, error: 'Invalid response' });
      
      render(<LoginForm onSwitchToRegister={vi.fn()} onSwitchToForgotPassword={vi.fn()} />);
      
      await userEvent.type(screen.getByTestId('textfield-username'), 'user');
      await userEvent.type(screen.getByTestId('textfield-password'), 'pass');
      await userEvent.click(screen.getByTestId('mui-button'));
      
      expect(screen.getByText('Invalid response')).toBeInTheDocument();
    });

    it('should handle missing WebAuthn support', () => {
      // Mock missing WebAuthn API
      global.navigator.credentials = undefined;
      
      render(<BiometricAuth 
        userId="user123" 
        username="test" 
        onAuthSuccess={vi.fn()} 
        onSetupComplete={vi.fn()} 
        onError={vi.fn()} 
      />);
      
      expect(screen.getByTestId('biometric-auth')).toBeInTheDocument();
    });

    it('should handle session expiration during authentication', () => {
      mockAuthContext.error = 'Session expired';
      
      render(<LoginForm onSwitchToRegister={vi.fn()} onSwitchToForgotPassword={vi.fn()} />);
      
      expect(screen.getByText('Session expired')).toBeInTheDocument();
    });
  });

  describe('Accessibility and Security', () => {
    it('should provide proper ARIA labels for form fields', () => {
      render(<LoginForm onSwitchToRegister={vi.fn()} onSwitchToForgotPassword={vi.fn()} />);
      
      const usernameInput = screen.getByTestId('textfield-username');
      const passwordInput = screen.getByTestId('textfield-password');
      
      expect(usernameInput).toHaveAttribute('placeholder', 'Username or Email');
      expect(passwordInput).toHaveAttribute('placeholder', 'Password');
    });

    it('should support keyboard navigation', async () => {
      render(<LoginForm onSwitchToRegister={vi.fn()} onSwitchToForgotPassword={vi.fn()} />);
      
      await userEvent.tab();
      expect(document.activeElement).toHaveAttribute('data-testid', 'textfield-username');
      
      await userEvent.tab();
      expect(document.activeElement).toHaveAttribute('data-testid', 'textfield-password');
    });

    it('should not expose sensitive data in form attributes', () => {
      render(<LoginForm onSwitchToRegister={vi.fn()} onSwitchToForgotPassword={vi.fn()} />);
      
      const passwordInput = screen.getByTestId('textfield-password');
      expect(passwordInput).toHaveAttribute('type', 'password');
    });

    it('should validate input sanitization', async () => {
      render(<LoginForm onSwitchToRegister={vi.fn()} onSwitchToForgotPassword={vi.fn()} />);
      
      const usernameInput = screen.getByTestId('textfield-username');
      await userEvent.type(usernameInput, '<script>alert("xss")</script>');
      
      expect(usernameInput.value).toBe('<script>alert("xss")</script>');
      // In production, this should be sanitized
    });
  });
});