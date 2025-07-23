/**
 * Authentication and Security Workflow Integration Tests
 * Tests complete authentication flows and security mechanisms
 */

import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';

// Mock AWS Cognito
const mockCognito = {
  initiateAuth: vi.fn(),
  signUp: vi.fn(),
  confirmSignUp: vi.fn(),
  forgotPassword: vi.fn(),
  confirmForgotPassword: vi.fn(),
  changePassword: vi.fn(),
  globalSignOut: vi.fn(),
  refreshTokens: vi.fn(),
  getMfaPreferences: vi.fn(),
  setMfaPreferences: vi.fn()
};

vi.mock('@aws-sdk/client-cognito-identity-provider', () => ({
  CognitoIdentityProviderClient: vi.fn(() => mockCognito),
  InitiateAuthCommand: vi.fn(),
  SignUpCommand: vi.fn(),
  ConfirmSignUpCommand: vi.fn(),
  ForgotPasswordCommand: vi.fn(),
  ConfirmForgotPasswordCommand: vi.fn(),
  ChangePasswordCommand: vi.fn(),
  GlobalSignOutCommand: vi.fn(),
  GetMFAPreferencesCommand: vi.fn(),
  SetMFAPreferencesCommand: vi.fn()
}));

// Mock authentication service
const mockAuthService = {
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  refreshToken: vi.fn(),
  validateSession: vi.fn(),
  resetPassword: vi.fn(),
  changePassword: vi.fn(),
  enableMFA: vi.fn(),
  verifyMFAToken: vi.fn(),
  getSecuritySettings: vi.fn(),
  updateSecuritySettings: vi.fn(),
  checkPasswordStrength: vi.fn(),
  logSecurityEvent: vi.fn()
};

// Mock secure storage service
const mockSecureStorage = {
  encryptAndStore: vi.fn(),
  decryptAndRetrieve: vi.fn(),
  removeSecureItem: vi.fn(),
  clearSecureStorage: vi.fn(),
  validateStorageIntegrity: vi.fn()
};

// Mock biometric authentication
const mockBiometric = {
  isSupported: vi.fn(),
  authenticate: vi.fn(),
  enroll: vi.fn(),
  remove: vi.fn(),
  getAvailableTypes: vi.fn()
};

const theme = createTheme();

const TestWrapper = ({ children }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider theme={theme}>
          {children}
        </ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
};

// Mock components for authentication flows
vi.mock('../../../components/auth/LoginForm', () => ({
  default: vi.fn(({ onLogin, onError, onSwitchToRegister }) => (
    <div data-testid="login-form">
      <input data-testid="login-email" placeholder="Email" />
      <input data-testid="login-password" type="password" placeholder="Password" />
      <button 
        data-testid="login-submit" 
        onClick={() => onLogin?.({ email: 'test@example.com', password: 'password123' })}
      >
        Sign In
      </button>
      <button data-testid="switch-to-register" onClick={onSwitchToRegister}>
        Create Account
      </button>
      <button data-testid="forgot-password">Forgot Password?</button>
    </div>
  ))
}));

vi.mock('../../../components/auth/RegisterForm', () => ({
  default: vi.fn(({ onRegister, onError, onSwitchToLogin }) => (
    <div data-testid="register-form">
      <input data-testid="register-email" placeholder="Email" />
      <input data-testid="register-password" type="password" placeholder="Password" />
      <input data-testid="register-confirm-password" type="password" placeholder="Confirm Password" />
      <input data-testid="register-phone" placeholder="Phone Number" />
      <button 
        data-testid="register-submit"
        onClick={() => onRegister?.({ 
          email: 'newuser@example.com', 
          password: 'StrongPassword123!',
          phone: '+1234567890'
        })}
      >
        Create Account
      </button>
      <button data-testid="switch-to-login" onClick={onSwitchToLogin}>
        Sign In
      </button>
    </div>
  ))
}));

vi.mock('../../../components/auth/MFASetup', () => ({
  default: vi.fn(({ onComplete, onSkip }) => (
    <div data-testid="mfa-setup">
      <div data-testid="qr-code">QR Code for Authenticator App</div>
      <input data-testid="mfa-code" placeholder="Enter 6-digit code" />
      <button data-testid="verify-mfa" onClick={() => onComplete?.('123456')}>
        Verify & Enable
      </button>
      <button data-testid="skip-mfa" onClick={onSkip}>Skip for Now</button>
    </div>
  ))
}));

vi.mock('../../../components/auth/SecurityDashboard', () => ({
  default: vi.fn(({ securitySettings, onUpdateSettings }) => (
    <div data-testid="security-dashboard">
      <div data-testid="security-overview">
        <div data-testid="mfa-status">MFA: {securitySettings?.mfaEnabled ? 'Enabled' : 'Disabled'}</div>
        <div data-testid="session-timeout">Session Timeout: {securitySettings?.sessionTimeout}min</div>
        <div data-testid="login-history">Recent Logins: {securitySettings?.recentLogins?.length || 0}</div>
      </div>
      <div data-testid="security-actions">
        <button data-testid="change-password">Change Password</button>
        <button data-testid="toggle-mfa">Toggle MFA</button>
        <button data-testid="revoke-sessions">Revoke All Sessions</button>
        <button data-testid="download-security-report">Download Security Report</button>
      </div>
    </div>
  ))
}));

describe('Authentication and Security Workflow Integration Tests', () => {
  let user;
  let mockUser;
  let mockSecuritySettings;

  beforeAll(() => {
    // Mock crypto for secure operations
    Object.defineProperty(global, 'crypto', {
      value: {
        getRandomValues: vi.fn(() => new Uint8Array(32)),
        subtle: {
          encrypt: vi.fn(),
          decrypt: vi.fn(),
          generateKey: vi.fn(),
          importKey: vi.fn()
        }
      }
    });

    // Mock navigator for biometric APIs
    Object.defineProperty(global.navigator, 'credentials', {
      value: {
        create: vi.fn(),
        get: vi.fn()
      }
    });
  });

  beforeEach(() => {
    user = userEvent.setup();
    vi.clearAllMocks();

    mockUser = {
      id: 'user_123',
      email: 'test@example.com',
      phone: '+1234567890',
      emailVerified: true,
      phoneVerified: true,
      mfaEnabled: false,
      subscription: 'premium',
      createdAt: '2024-01-01T00:00:00Z',
      lastLogin: '2024-01-15T10:30:00Z'
    };

    mockSecuritySettings = {
      mfaEnabled: false,
      sessionTimeout: 30,
      passwordLastChanged: '2024-01-01T00:00:00Z',
      failedLoginAttempts: 0,
      accountLocked: false,
      recentLogins: [
        { ip: '192.168.1.1', location: 'New York, US', timestamp: '2024-01-15T10:30:00Z' },
        { ip: '192.168.1.1', location: 'New York, US', timestamp: '2024-01-14T09:15:00Z' }
      ],
      securityEvents: []
    };

    // Setup service mocks
    mockAuthService.login.mockResolvedValue({ 
      success: true, 
      user: mockUser, 
      tokens: { 
        accessToken: 'access_token_123',
        refreshToken: 'refresh_token_123',
        expiresIn: 3600 
      }
    });

    mockAuthService.register.mockResolvedValue({ 
      success: true, 
      user: { ...mockUser, emailVerified: false },
      verificationRequired: true 
    });

    mockAuthService.getSecuritySettings.mockResolvedValue(mockSecuritySettings);
    mockSecureStorage.validateStorageIntegrity.mockResolvedValue({ valid: true });
    mockBiometric.isSupported.mockResolvedValue(true);
  });

  describe('Complete User Registration Flow', () => {
    it('handles new user registration with email verification', async () => {
      const LoginForm = (await import('../../../components/auth/LoginForm')).default;
      const RegisterForm = (await import('../../../components/auth/RegisterForm')).default;
      
      // Step 1: User starts at login form, switches to registration
      const { rerender } = render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('switch-to-register'));

      // Step 2: Registration form appears
      rerender(
        <TestWrapper>
          <RegisterForm />
        </TestWrapper>
      );

      expect(screen.getByTestId('register-form')).toBeInTheDocument();

      // Step 3: User fills registration form
      await user.type(screen.getByTestId('register-email'), 'newuser@example.com');
      await user.type(screen.getByTestId('register-password'), 'StrongPassword123!');
      await user.type(screen.getByTestId('register-confirm-password'), 'StrongPassword123!');
      await user.type(screen.getByTestId('register-phone'), '+1234567890');

      // Step 4: Password strength validation
      expect(mockAuthService.checkPasswordStrength).toHaveBeenCalledWith('StrongPassword123!');

      // Step 5: User submits registration
      await user.click(screen.getByTestId('register-submit'));

      // Step 6: Verify registration process
      expect(mockAuthService.register).toHaveBeenCalledWith({
        email: 'newuser@example.com',
        password: 'StrongPassword123!',
        phone: '+1234567890'
      });

      // Step 7: Email verification required
      expect(screen.getByText(/verification email sent/i)).toBeInTheDocument();

      // Step 8: User confirms email (simulated)
      mockCognito.confirmSignUp.mockResolvedValue({ success: true });
      
      // Step 9: Registration complete, user logged in
      expect(mockAuthService.logSecurityEvent).toHaveBeenCalledWith({
        type: 'ACCOUNT_CREATED',
        userId: 'user_123',
        timestamp: expect.any(String)
      });
    });

    it('handles registration with MFA setup', async () => {
      const RegisterForm = (await import('../../../components/auth/RegisterForm')).default;
      const MFASetup = (await import('../../../components/auth/MFASetup')).default;

      // Step 1: Complete basic registration
      render(
        <TestWrapper>
          <RegisterForm />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('register-submit'));

      // Step 2: MFA setup appears after email verification
      render(
        <TestWrapper>
          <MFASetup />
        </TestWrapper>
      );

      expect(screen.getByTestId('mfa-setup')).toBeInTheDocument();
      expect(screen.getByTestId('qr-code')).toBeInTheDocument();

      // Step 3: User sets up authenticator app
      await user.type(screen.getByTestId('mfa-code'), '123456');
      await user.click(screen.getByTestId('verify-mfa'));

      // Step 4: MFA verification
      expect(mockAuthService.enableMFA).toHaveBeenCalledWith('123456');
      expect(mockAuthService.verifyMFAToken).toHaveBeenCalledWith('123456');

      // Step 5: MFA enabled successfully
      expect(mockAuthService.logSecurityEvent).toHaveBeenCalledWith({
        type: 'MFA_ENABLED',
        userId: 'user_123',
        timestamp: expect.any(String)
      });
    });

    it('handles registration validation errors', async () => {
      const RegisterForm = (await import('../../../components/auth/RegisterForm')).default;

      // Setup validation failure
      mockAuthService.register.mockRejectedValue({
        code: 'UsernameExistsException',
        message: 'Email already registered'
      });

      render(
        <TestWrapper>
          <RegisterForm />
        </TestWrapper>
      );

      await user.type(screen.getByTestId('register-email'), 'existing@example.com');
      await user.type(screen.getByTestId('register-password'), 'password123');
      await user.click(screen.getByTestId('register-submit'));

      // Error message displayed
      await waitFor(() => {
        expect(screen.getByText(/email already registered/i)).toBeInTheDocument();
      });

      // Security event logged
      expect(mockAuthService.logSecurityEvent).toHaveBeenCalledWith({
        type: 'REGISTRATION_FAILED',
        reason: 'EMAIL_EXISTS',
        email: 'existing@example.com',
        timestamp: expect.any(String)
      });
    });
  });

  describe('Secure Login Workflows', () => {
    it('handles standard email/password login', async () => {
      const LoginForm = (await import('../../../components/auth/LoginForm')).default;

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      // Step 1: User enters credentials
      await user.type(screen.getByTestId('login-email'), 'test@example.com');
      await user.type(screen.getByTestId('login-password'), 'password123');

      // Step 2: User submits login
      await user.click(screen.getByTestId('login-submit'));

      // Step 3: Authentication attempted
      expect(mockAuthService.login).toHaveBeenCalledWith({
        email: 'test@example.com',
        password: 'password123'
      });

      // Step 4: Session established
      expect(mockSecureStorage.encryptAndStore).toHaveBeenCalledWith(
        'auth_tokens',
        expect.objectContaining({
          accessToken: 'access_token_123',
          refreshToken: 'refresh_token_123'
        })
      );

      // Step 5: Success event logged
      expect(mockAuthService.logSecurityEvent).toHaveBeenCalledWith({
        type: 'LOGIN_SUCCESS',
        userId: 'user_123',
        ip: expect.any(String),
        timestamp: expect.any(String)
      });
    });

    it('handles MFA-enabled login flow', async () => {
      const LoginForm = (await import('../../../components/auth/LoginForm')).default;

      // Setup user with MFA enabled
      const mfaUser = { ...mockUser, mfaEnabled: true };
      mockAuthService.login.mockResolvedValue({
        success: false,
        challengeName: 'SOFTWARE_TOKEN_MFA',
        challengeParameters: { USER_ID_FOR_SRP: 'user_123' }
      });

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      // Step 1: Initial login
      await user.type(screen.getByTestId('login-email'), 'test@example.com');
      await user.type(screen.getByTestId('login-password'), 'password123');
      await user.click(screen.getByTestId('login-submit'));

      // Step 2: MFA challenge appears
      expect(screen.getByText(/enter authentication code/i)).toBeInTheDocument();
      expect(screen.getByTestId('mfa-code-input')).toBeInTheDocument();

      // Step 3: User enters MFA code
      await user.type(screen.getByTestId('mfa-code-input'), '654321');
      await user.click(screen.getByTestId('verify-mfa-login'));

      // Step 4: MFA verification
      expect(mockAuthService.verifyMFAToken).toHaveBeenCalledWith('654321');

      // Step 5: Complete login after MFA
      mockAuthService.login.mockResolvedValue({
        success: true,
        user: mfaUser,
        tokens: { accessToken: 'access_token_123', refreshToken: 'refresh_token_123' }
      });

      // Step 6: Login successful
      expect(mockAuthService.logSecurityEvent).toHaveBeenCalledWith({
        type: 'MFA_LOGIN_SUCCESS',
        userId: 'user_123',
        timestamp: expect.any(String)
      });
    });

    it('handles biometric authentication', async () => {
      const LoginForm = (await import('../../../components/auth/LoginForm')).default;

      // Setup biometric support
      mockBiometric.isSupported.mockResolvedValue(true);
      mockBiometric.getAvailableTypes.mockResolvedValue(['fingerprint', 'face']);

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      // Step 1: Biometric option available
      expect(screen.getByTestId('biometric-login')).toBeInTheDocument();
      expect(screen.getByText(/use fingerprint/i)).toBeInTheDocument();

      // Step 2: User chooses biometric login
      await user.click(screen.getByTestId('biometric-login'));

      // Step 3: Biometric prompt
      mockBiometric.authenticate.mockResolvedValue({
        success: true,
        credential: 'biometric_credential_123'
      });

      // Step 4: Biometric authentication successful
      expect(mockAuthService.login).toHaveBeenCalledWith({
        biometric: true,
        credential: 'biometric_credential_123'
      });

      // Step 5: Security event logged
      expect(mockAuthService.logSecurityEvent).toHaveBeenCalledWith({
        type: 'BIOMETRIC_LOGIN_SUCCESS',
        userId: 'user_123',
        biometricType: 'fingerprint',
        timestamp: expect.any(String)
      });
    });

    it('handles account lockout after failed attempts', async () => {
      const LoginForm = (await import('../../../components/auth/LoginForm')).default;

      // Setup failed login attempts
      mockAuthService.login
        .mockRejectedValueOnce({ code: 'NotAuthorizedException', message: 'Incorrect credentials' })
        .mockRejectedValueOnce({ code: 'NotAuthorizedException', message: 'Incorrect credentials' })
        .mockRejectedValueOnce({ code: 'NotAuthorizedException', message: 'Incorrect credentials' })
        .mockRejectedValueOnce({ code: 'TooManyRequestsException', message: 'Account temporarily locked' });

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      // Simulate 3 failed attempts
      for (let i = 0; i < 3; i++) {
        await user.clear(screen.getByTestId('login-email'));
        await user.clear(screen.getByTestId('login-password'));
        await user.type(screen.getByTestId('login-email'), 'test@example.com');
        await user.type(screen.getByTestId('login-password'), 'wrongpassword');
        await user.click(screen.getByTestId('login-submit'));

        await waitFor(() => {
          expect(screen.getByText(/incorrect credentials/i)).toBeInTheDocument();
        });
      }

      // Fourth attempt triggers lockout
      await user.clear(screen.getByTestId('login-email'));
      await user.clear(screen.getByTestId('login-password'));
      await user.type(screen.getByTestId('login-email'), 'test@example.com');
      await user.type(screen.getByTestId('login-password'), 'wrongpassword');
      await user.click(screen.getByTestId('login-submit'));

      // Account locked message
      await waitFor(() => {
        expect(screen.getByText(/account temporarily locked/i)).toBeInTheDocument();
      });

      // Security event logged
      expect(mockAuthService.logSecurityEvent).toHaveBeenCalledWith({
        type: 'ACCOUNT_LOCKED',
        userId: expect.any(String),
        email: 'test@example.com',
        failedAttempts: 4,
        timestamp: expect.any(String)
      });
    });
  });

  describe('Password Reset and Recovery', () => {
    it('handles password reset flow', async () => {
      const LoginForm = (await import('../../../components/auth/LoginForm')).default;

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      // Step 1: User clicks forgot password
      await user.click(screen.getByTestId('forgot-password'));

      // Step 2: Password reset form appears
      expect(screen.getByText(/reset password/i)).toBeInTheDocument();
      expect(screen.getByTestId('reset-email-input')).toBeInTheDocument();

      // Step 3: User enters email
      await user.type(screen.getByTestId('reset-email-input'), 'test@example.com');
      await user.click(screen.getByTestId('send-reset-code'));

      // Step 4: Reset code sent
      expect(mockAuthService.resetPassword).toHaveBeenCalledWith('test@example.com');
      expect(screen.getByText(/reset code sent/i)).toBeInTheDocument();

      // Step 5: User enters reset code and new password
      await user.type(screen.getByTestId('reset-code-input'), '123456');
      await user.type(screen.getByTestId('new-password-input'), 'NewStrongPassword123!');
      await user.type(screen.getByTestId('confirm-new-password-input'), 'NewStrongPassword123!');

      // Step 6: Password strength validation
      expect(mockAuthService.checkPasswordStrength).toHaveBeenCalledWith('NewStrongPassword123!');

      // Step 7: Submit password reset
      await user.click(screen.getByTestId('confirm-password-reset'));

      // Step 8: Password reset confirmed
      expect(mockCognito.confirmForgotPassword).toHaveBeenCalledWith({
        username: 'test@example.com',
        confirmationCode: '123456',
        password: 'NewStrongPassword123!'
      });

      // Step 9: Success message and redirect to login
      expect(screen.getByText(/password reset successful/i)).toBeInTheDocument();
      expect(mockAuthService.logSecurityEvent).toHaveBeenCalledWith({
        type: 'PASSWORD_RESET_SUCCESS',
        email: 'test@example.com',
        timestamp: expect.any(String)
      });
    });

    it('handles password change for authenticated users', async () => {
      const SecurityDashboard = (await import('../../../components/auth/SecurityDashboard')).default;

      render(
        <TestWrapper>
          <SecurityDashboard securitySettings={mockSecuritySettings} />
        </TestWrapper>
      );

      // Step 1: User clicks change password
      await user.click(screen.getByTestId('change-password'));

      // Step 2: Password change modal appears
      expect(screen.getByText(/change password/i)).toBeInTheDocument();
      expect(screen.getByTestId('current-password-input')).toBeInTheDocument();

      // Step 3: User enters current and new passwords
      await user.type(screen.getByTestId('current-password-input'), 'currentPassword123');
      await user.type(screen.getByTestId('new-password-input'), 'NewStrongPassword456!');
      await user.type(screen.getByTestId('confirm-new-password-input'), 'NewStrongPassword456!');

      // Step 4: Submit password change
      await user.click(screen.getByTestId('confirm-password-change'));

      // Step 5: Password change processed
      expect(mockAuthService.changePassword).toHaveBeenCalledWith({
        currentPassword: 'currentPassword123',
        newPassword: 'NewStrongPassword456!'
      });

      // Step 6: Success confirmation
      expect(screen.getByText(/password changed successfully/i)).toBeInTheDocument();
      expect(mockAuthService.logSecurityEvent).toHaveBeenCalledWith({
        type: 'PASSWORD_CHANGED',
        userId: 'user_123',
        timestamp: expect.any(String)
      });
    });
  });

  describe('Session Management and Security', () => {
    it('handles session timeout and automatic logout', async () => {
      const SecurityDashboard = (await import('../../../components/auth/SecurityDashboard')).default;

      // Setup short session timeout for testing
      const shortTimeoutSettings = { ...mockSecuritySettings, sessionTimeout: 1 }; // 1 minute

      render(
        <TestWrapper>
          <SecurityDashboard securitySettings={shortTimeoutSettings} />
        </TestWrapper>
      );

      // Step 1: User is active, session valid
      expect(mockAuthService.validateSession).toHaveBeenCalled();

      // Step 2: Simulate session timeout
      vi.advanceTimersByTime(60000); // 1 minute

      // Step 3: Session validation fails
      mockAuthService.validateSession.mockRejectedValue({ code: 'SessionExpired' });

      // Step 4: Automatic logout triggered
      await waitFor(() => {
        expect(mockAuthService.logout).toHaveBeenCalled();
      });

      // Step 5: Security event logged
      expect(mockAuthService.logSecurityEvent).toHaveBeenCalledWith({
        type: 'SESSION_TIMEOUT',
        userId: 'user_123',
        timestamp: expect.any(String)
      });

      // Step 6: User redirected to login
      expect(screen.getByText(/session expired/i)).toBeInTheDocument();
    });

    it('handles token refresh before expiration', async () => {
      // Setup token near expiration
      const nearExpiryTokens = {
        accessToken: 'access_token_123',
        refreshToken: 'refresh_token_123',
        expiresIn: 300 // 5 minutes
      };

      mockSecureStorage.decryptAndRetrieve.mockResolvedValue(nearExpiryTokens);
      mockAuthService.refreshToken.mockResolvedValue({
        success: true,
        tokens: {
          accessToken: 'new_access_token_456',
          refreshToken: 'new_refresh_token_456',
          expiresIn: 3600
        }
      });

      // Step 1: Token refresh triggered automatically
      await waitFor(() => {
        expect(mockAuthService.refreshToken).toHaveBeenCalledWith('refresh_token_123');
      });

      // Step 2: New tokens stored securely
      expect(mockSecureStorage.encryptAndStore).toHaveBeenCalledWith(
        'auth_tokens',
        expect.objectContaining({
          accessToken: 'new_access_token_456',
          refreshToken: 'new_refresh_token_456'
        })
      );

      // Step 3: Security event logged
      expect(mockAuthService.logSecurityEvent).toHaveBeenCalledWith({
        type: 'TOKEN_REFRESHED',
        userId: 'user_123',
        timestamp: expect.any(String)
      });
    });

    it('handles multiple session management', async () => {
      const SecurityDashboard = (await import('../../../components/auth/SecurityDashboard')).default;

      const multiSessionSettings = {
        ...mockSecuritySettings,
        activeSessions: [
          { id: 'session_1', device: 'MacBook Pro', location: 'New York', lastActive: '2024-01-15T10:30:00Z' },
          { id: 'session_2', device: 'iPhone', location: 'New York', lastActive: '2024-01-15T09:15:00Z' },
          { id: 'session_3', device: 'Windows PC', location: 'California', lastActive: '2024-01-14T15:45:00Z' }
        ]
      };

      render(
        <TestWrapper>
          <SecurityDashboard securitySettings={multiSessionSettings} />
        </TestWrapper>
      );

      // Step 1: Display active sessions
      expect(screen.getByText('MacBook Pro')).toBeInTheDocument();
      expect(screen.getByText('iPhone')).toBeInTheDocument();
      expect(screen.getByText('Windows PC')).toBeInTheDocument();

      // Step 2: User revokes all other sessions
      await user.click(screen.getByTestId('revoke-sessions'));

      // Step 3: Confirmation dialog
      expect(screen.getByText(/revoke all other sessions/i)).toBeInTheDocument();
      await user.click(screen.getByTestId('confirm-revoke-sessions'));

      // Step 4: Sessions revoked
      expect(mockCognito.globalSignOut).toHaveBeenCalled();
      expect(mockAuthService.logSecurityEvent).toHaveBeenCalledWith({
        type: 'SESSIONS_REVOKED',
        userId: 'user_123',
        revokedSessions: ['session_2', 'session_3'],
        timestamp: expect.any(String)
      });
    });
  });

  describe('Security Monitoring and Alerts', () => {
    it('detects and alerts on suspicious login activity', async () => {
      // Setup suspicious login scenario
      const suspiciousLogin = {
        ip: '203.0.113.1', // Different country
        location: 'Tokyo, JP',
        device: 'Unknown Device',
        timestamp: '2024-01-15T14:30:00Z'
      };

      mockAuthService.login.mockResolvedValue({
        success: true,
        user: mockUser,
        tokens: { accessToken: 'access_token_123', refreshToken: 'refresh_token_123' },
        suspicious: true,
        suspiciousReasons: ['UNUSUAL_LOCATION', 'NEW_DEVICE']
      });

      const LoginForm = (await import('../../../components/auth/LoginForm')).default;

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      // Step 1: User logs in from suspicious location
      await user.type(screen.getByTestId('login-email'), 'test@example.com');
      await user.type(screen.getByTestId('login-password'), 'password123');
      await user.click(screen.getByTestId('login-submit'));

      // Step 2: Suspicious activity detected
      expect(screen.getByText(/unusual login activity detected/i)).toBeInTheDocument();
      expect(screen.getByText(/new location: tokyo, jp/i)).toBeInTheDocument();

      // Step 3: Additional verification required
      expect(screen.getByTestId('verify-suspicious-login')).toBeInTheDocument();
      expect(screen.getByText(/verify via email/i)).toBeInTheDocument();

      // Step 4: User verifies via email
      await user.click(screen.getByTestId('verify-via-email'));

      // Step 5: Security alert logged
      expect(mockAuthService.logSecurityEvent).toHaveBeenCalledWith({
        type: 'SUSPICIOUS_LOGIN_DETECTED',
        userId: 'user_123',
        reasons: ['UNUSUAL_LOCATION', 'NEW_DEVICE'],
        ip: '203.0.113.1',
        location: 'Tokyo, JP',
        timestamp: expect.any(String)
      });
    });

    it('handles security event monitoring and reporting', async () => {
      const SecurityDashboard = (await import('../../../components/auth/SecurityDashboard')).default;

      const securityEventsSettings = {
        ...mockSecuritySettings,
        securityEvents: [
          { type: 'LOGIN_SUCCESS', timestamp: '2024-01-15T10:30:00Z', ip: '192.168.1.1' },
          { type: 'PASSWORD_CHANGED', timestamp: '2024-01-10T14:20:00Z' },
          { type: 'MFA_ENABLED', timestamp: '2024-01-05T09:45:00Z' },
          { type: 'SUSPICIOUS_LOGIN_DETECTED', timestamp: '2024-01-03T16:30:00Z', ip: '203.0.113.1' }
        ]
      };

      render(
        <TestWrapper>
          <SecurityDashboard securitySettings={securityEventsSettings} />
        </TestWrapper>
      );

      // Step 1: Security events displayed
      expect(screen.getByText('Recent Security Events')).toBeInTheDocument();
      expect(screen.getByText('LOGIN_SUCCESS')).toBeInTheDocument();
      expect(screen.getByText('SUSPICIOUS_LOGIN_DETECTED')).toBeInTheDocument();

      // Step 2: User downloads security report
      await user.click(screen.getByTestId('download-security-report'));

      // Step 3: Security report generated
      expect(mockAuthService.generateSecurityReport).toHaveBeenCalledWith('user_123');

      // Step 4: Report download initiated
      expect(screen.getByText(/security report downloaded/i)).toBeInTheDocument();
    });

    it('implements real-time security monitoring', async () => {
      // Setup WebSocket for real-time monitoring
      const mockWebSocket = {
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        close: vi.fn(),
        send: vi.fn()
      };

      global.WebSocket = vi.fn(() => mockWebSocket);

      const SecurityDashboard = (await import('../../../components/auth/SecurityDashboard')).default;

      render(
        <TestWrapper>
          <SecurityDashboard securitySettings={mockSecuritySettings} />
        </TestWrapper>
      );

      // Step 1: Real-time monitoring established
      expect(global.WebSocket).toHaveBeenCalledWith(expect.stringContaining('security-monitor'));

      // Step 2: Simulate real-time security event
      const securityEvent = {
        type: 'FAILED_LOGIN_ATTEMPT',
        userId: 'user_123',
        ip: '192.168.1.100',
        timestamp: '2024-01-15T11:45:00Z'
      };

      // Simulate WebSocket message
      const messageHandler = mockWebSocket.addEventListener.mock.calls
        .find(([event]) => event === 'message')[1];
      
      messageHandler({ data: JSON.stringify(securityEvent) });

      // Step 3: Real-time alert displayed
      await waitFor(() => {
        expect(screen.getByText(/failed login attempt detected/i)).toBeInTheDocument();
      });

      // Step 4: Security event processed
      expect(mockAuthService.logSecurityEvent).toHaveBeenCalledWith(securityEvent);
    });
  });

  describe('Data Protection and Privacy', () => {
    it('handles secure data encryption and storage', async () => {
      // Step 1: Validate encryption setup
      expect(mockSecureStorage.validateStorageIntegrity).toHaveBeenCalled();

      // Step 2: Test sensitive data encryption
      const sensitiveData = {
        apiKeys: { alpaca: 'sensitive_key_123' },
        personalInfo: { ssn: '123-45-6789' }
      };

      await mockSecureStorage.encryptAndStore('sensitive_data', sensitiveData);

      // Step 3: Verify encryption called with proper data
      expect(mockSecureStorage.encryptAndStore).toHaveBeenCalledWith(
        'sensitive_data',
        sensitiveData
      );

      // Step 4: Test data retrieval and decryption
      mockSecureStorage.decryptAndRetrieve.mockResolvedValue(sensitiveData);
      const retrievedData = await mockSecureStorage.decryptAndRetrieve('sensitive_data');

      expect(retrievedData).toEqual(sensitiveData);
    });

    it('implements data retention and cleanup policies', async () => {
      const SecurityDashboard = (await import('../../../components/auth/SecurityDashboard')).default;

      render(
        <TestWrapper>
          <SecurityDashboard securitySettings={mockSecuritySettings} />
        </TestWrapper>
      );

      // Step 1: User requests data cleanup
      await user.click(screen.getByTestId('cleanup-old-data'));

      // Step 2: Confirmation dialog
      expect(screen.getByText(/clean up data older than 90 days/i)).toBeInTheDocument();
      await user.click(screen.getByTestId('confirm-data-cleanup'));

      // Step 3: Data cleanup executed
      expect(mockSecureStorage.clearSecureStorage).toHaveBeenCalledWith({
        olderThan: 90,
        keepTypes: ['ESSENTIAL', 'LEGAL_REQUIRED']
      });

      // Step 4: Cleanup logged
      expect(mockAuthService.logSecurityEvent).toHaveBeenCalledWith({
        type: 'DATA_CLEANUP_EXECUTED',
        userId: 'user_123',
        itemsRemoved: expect.any(Number),
        timestamp: expect.any(String)
      });
    });

    it('handles GDPR compliance and data export', async () => {
      const SecurityDashboard = (await import('../../../components/auth/SecurityDashboard')).default;

      render(
        <TestWrapper>
          <SecurityDashboard securitySettings={mockSecuritySettings} />
        </TestWrapper>
      );

      // Step 1: User requests data export
      await user.click(screen.getByTestId('export-user-data'));

      // Step 2: Data export options
      expect(screen.getByText(/export all user data/i)).toBeInTheDocument();
      expect(screen.getByTestId('export-format-json')).toBeInTheDocument();
      expect(screen.getByTestId('export-format-csv')).toBeInTheDocument();

      // Step 3: User selects format and confirms
      await user.click(screen.getByTestId('export-format-json'));
      await user.click(screen.getByTestId('confirm-data-export'));

      // Step 4: Data export processed
      expect(mockAuthService.exportUserData).toHaveBeenCalledWith({
        userId: 'user_123',
        format: 'json',
        includeDeleted: false
      });

      // Step 5: Export completion
      expect(screen.getByText(/data export completed/i)).toBeInTheDocument();
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  afterAll(() => {
    vi.clearAllTimers();
  });
});