/**
 * Real AuthContext Unit Tests
 * Tests the actual AuthContext functionality with real AWS Cognito integration patterns
 * Tests reducer logic, auth state management, and real authentication flows
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import React from 'react';
import { AuthProvider, useAuth } from '../../../contexts/AuthContext';

// Mock AWS Amplify Auth for controlled testing
vi.mock('@aws-amplify/auth', () => ({
  fetchAuthSession: vi.fn(),
  signIn: vi.fn(),
  signUp: vi.fn(),  
  confirmSignUp: vi.fn(),
  confirmSignIn: vi.fn(),
  signOut: vi.fn(),
  resetPassword: vi.fn(),
  confirmResetPassword: vi.fn(),
  getCurrentUser: vi.fn()
}));

// Mock SessionManager component
vi.mock('../../../components/auth/SessionManager', () => ({
  default: ({ children }) => children
}));

// Mock secureSessionStorage
vi.mock('../../../utils/secureSessionStorage', () => ({
  default: {
    storeTokens: vi.fn(),
    clearSession: vi.fn(),
    getTokens: vi.fn(() => null)
  }
}));

// Mock config modules
vi.mock('../../../config/environment', () => ({
  FEATURES: {
    authentication: {
      enabled: true,
      methods: {
        cognito: true
      }
    }
  },
  AWS_CONFIG: {
    cognito: {
      userPoolId: 'test-pool',
      clientId: 'test-client'
    }
  }
}));

vi.mock('../../../config/amplify', () => ({
  isCognitoConfigured: vi.fn(() => true)
}));

vi.mock('../../../services/runtimeConfig', () => ({
  initializeRuntimeConfig: vi.fn(() => Promise.resolve())
}));

describe('🔐 AuthContext - Real Functionality Tests', () => {
  let mockAuth;
  
  beforeEach(async () => {
    // Reset all mocks
    vi.clearAllMocks();
    
    // Setup AWS Amplify Auth mocks
    mockAuth = await import('@aws-amplify/auth');
    
    // Default mock implementations
    mockAuth.getCurrentUser.mockRejectedValue(new Error('No current user'));
    mockAuth.fetchAuthSession.mockRejectedValue(new Error('No session'));
    mockAuth.signOut.mockResolvedValue({});
    
    // Clear localStorage and sessionStorage
    localStorage.clear();
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderAuthHook = () => {
    return renderHook(() => useAuth(), {
      wrapper: ({ children }) => (
        <AuthProvider>{children}</AuthProvider>
      )
    });
  };

  describe('Authentication State Management', () => {
    it('should initialize with correct default state', async () => {
      const { result } = renderAuthHook();

      // Initial state should be loading
      expect(result.current.isLoading).toBe(true);
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBe(null);
      expect(result.current.tokens).toBe(null);
      expect(result.current.error).toBe(null);

      // Wait for initial auth check to complete
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should be unauthenticated after check
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBe(null);
    });

    it('should handle successful authentication state', async () => {
      const mockUser = {
        userId: 'test-user-123',
        username: 'testuser',
        userAttributes: {
          email: 'test@example.com',
          given_name: 'Test',
          family_name: 'User'
        },
        signInDetails: {
          loginId: 'test@example.com'
        }
      };

      const mockTokens = {
        accessToken: { toString: () => 'access-token-123' },
        idToken: { toString: () => 'id-token-123' },
        refreshToken: { toString: () => 'refresh-token-123' }
      };

      mockAuth.getCurrentUser.mockResolvedValue(mockUser);
      mockAuth.fetchAuthSession.mockResolvedValue({ tokens: mockTokens });

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should be authenticated
      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.user).toEqual({
        username: 'testuser',
        userId: 'test-user-123',
        email: 'test@example.com',
        firstName: 'Test',
        lastName: 'User',
        signInDetails: mockUser.signInDetails,
        mfaEnabled: false
      });
      expect(result.current.tokens).toEqual({
        accessToken: 'access-token-123',
        idToken: 'id-token-123',
        refreshToken: 'refresh-token-123'
      });
      expect(result.current.error).toBe(null);
    });

    it('should detect MFA enabled users correctly', async () => {
      const mockUserWithMfa = {
        userId: 'test-user-mfa',
        username: 'mfauser',
        userAttributes: {
          email: 'mfa@example.com',
          'custom:mfa_enabled': 'true'
        },
        signInDetails: {
          loginId: 'mfa@example.com'
        }
      };

      const mockTokens = {
        accessToken: { toString: () => 'access-token-mfa' },
        idToken: { toString: () => 'id-token-mfa' },
        refreshToken: { toString: () => 'refresh-token-mfa' }
      };

      mockAuth.getCurrentUser.mockResolvedValue(mockUserWithMfa);
      mockAuth.fetchAuthSession.mockResolvedValue({ tokens: mockTokens });

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.user.mfaEnabled).toBe(true);
    });
  });

  describe('Login Functionality', () => {
    it('should handle successful login', async () => {
      const mockUser = {
        userId: 'login-user',
        username: 'loginuser',
        userAttributes: { email: 'login@example.com' },
        signInDetails: { loginId: 'login@example.com' }
      };

      const mockTokens = {
        accessToken: { toString: () => 'login-access-token' },
        idToken: { toString: () => 'login-id-token' },
        refreshToken: { toString: () => 'login-refresh-token' }
      };

      mockAuth.signIn.mockResolvedValue({ isSignedIn: true });
      mockAuth.getCurrentUser.mockResolvedValue(mockUser);
      mockAuth.fetchAuthSession.mockResolvedValue({ tokens: mockTokens });

      const { result } = renderAuthHook();

      // Wait for initial state
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Perform login
      let loginResult;
      await act(async () => {
        loginResult = await result.current.login('loginuser', 'password123');
      });

      expect(loginResult.success).toBe(true);
      expect(mockAuth.signIn).toHaveBeenCalledWith({
        username: 'loginuser',
        password: 'password123'
      });

      // Should update auth state
      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true);
      });

      expect(result.current.user.username).toBe('loginuser');
      expect(result.current.tokens.accessToken).toBe('login-access-token');
    });

    it('should handle MFA challenge during login', async () => {
      mockAuth.signIn.mockResolvedValue({
        isSignedIn: false,
        nextStep: {
          signInStep: 'CONFIRM_SIGN_IN_WITH_SMS_MFA_CODE',
          additionalInfo: {
            destination: '+1***-***-1234'
          }
        }
      });

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      let loginResult;
      await act(async () => {
        loginResult = await result.current.login('mfauser', 'password123');
      });

      expect(loginResult.success).toBe(false);
      expect(loginResult.nextStep).toBe('MFA_CHALLENGE');
      expect(loginResult.challengeType).toBe('SMS_MFA');
      expect(loginResult.message).toContain('+1***-***-1234');

      // Should set MFA challenge state
      expect(result.current.mfaChallenge).toBe('SMS_MFA');
      expect(result.current.mfaChallengeSession).toBeTruthy();
    });

    it('should handle TOTP MFA challenge', async () => {
      mockAuth.signIn.mockResolvedValue({
        isSignedIn: false,
        nextStep: {
          signInStep: 'CONFIRM_SIGN_IN_WITH_TOTP_MFA_CODE'
        }
      });

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      let loginResult;
      await act(async () => {
        loginResult = await result.current.login('totpuser', 'password123');
      });

      expect(loginResult.success).toBe(false);
      expect(loginResult.nextStep).toBe('MFA_CHALLENGE');
      expect(loginResult.challengeType).toBe('TOTP_MFA');
      expect(loginResult.message).toContain('authenticator app');

      expect(result.current.mfaChallenge).toBe('TOTP_MFA');
    });

    it('should handle login errors gracefully', async () => {
      const loginError = new Error('Invalid username or password');
      mockAuth.signIn.mockRejectedValue(loginError);

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      let loginResult;
      await act(async () => {
        loginResult = await result.current.login('baduser', 'wrongpassword');
      });

      expect(loginResult.success).toBe(false);
      expect(loginResult.message).toBe('Invalid username or password');
      expect(result.current.error).toBe('Invalid username or password');
      expect(result.current.isAuthenticated).toBe(false);
    });
  });

  describe('MFA Confirmation', () => {
    it('should handle successful MFA confirmation', async () => {
      const mockUser = {
        userId: 'mfa-user',
        username: 'mfauser',
        userAttributes: { email: 'mfa@example.com' },
        signInDetails: { loginId: 'mfa@example.com' }
      };

      const mockTokens = {
        accessToken: { toString: () => 'mfa-access-token' },
        idToken: { toString: () => 'mfa-id-token' },
        refreshToken: { toString: () => 'mfa-refresh-token' }
      };

      mockAuth.confirmSignIn.mockResolvedValue({ isSignedIn: true });
      mockAuth.getCurrentUser.mockResolvedValue(mockUser);
      mockAuth.fetchAuthSession.mockResolvedValue({ tokens: mockTokens });

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Set up MFA challenge state first
      await act(async () => {
        result.current.login('mfauser', 'password'); // This would set MFA state
      });

      let mfaResult;
      await act(async () => {
        mfaResult = await result.current.confirmMFA('123456');
      });

      expect(mfaResult.success).toBe(true);
      expect(mockAuth.confirmSignIn).toHaveBeenCalledWith({
        challengeResponse: '123456'
      });

      // Should clear MFA state and authenticate
      await waitFor(() => {
        expect(result.current.mfaChallenge).toBe(null);
        expect(result.current.isAuthenticated).toBe(true);
      });
    });

    it('should handle MFA confirmation errors', async () => {
      const mfaError = new Error('Invalid verification code');
      mockAuth.confirmSignIn.mockRejectedValue(mfaError);

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      let mfaResult;
      await act(async () => {
        mfaResult = await result.current.confirmMFA('000000');
      });

      expect(mfaResult.success).toBe(false);
      expect(mfaResult.message).toBe('Invalid verification code');
      expect(result.current.error).toBe('Invalid verification code');
    });
  });

  describe('Registration Functionality', () => {
    it('should handle successful registration', async () => {
      mockAuth.signUp.mockResolvedValue({
        isSignUpComplete: false,
        userId: 'new-user-123',
        nextStep: { signUpStep: 'CONFIRM_SIGN_UP' }
      });

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      let registerResult;
      await act(async () => {
        registerResult = await result.current.register(
          'newuser',
          'password123',
          'new@example.com',
          'New',
          'User'
        );
      });

      expect(registerResult.success).toBe(false);
      expect(registerResult.nextStep).toBe('CONFIRM_SIGN_UP');
      expect(registerResult.message).toContain('verification code');

      expect(mockAuth.signUp).toHaveBeenCalledWith({
        username: 'newuser',
        password: 'password123',
        options: {
          userAttributes: {
            email: 'new@example.com',
            given_name: 'New',
            family_name: 'User'
          }
        }
      });
    });

    it('should handle registration confirmation', async () => {
      mockAuth.confirmSignUp.mockResolvedValue({
        isSignUpComplete: true
      });

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      let confirmResult;
      await act(async () => {
        confirmResult = await result.current.confirmRegistration('newuser', '123456');
      });

      expect(confirmResult.success).toBe(true);
      expect(confirmResult.message).toContain('confirmed successfully');

      expect(mockAuth.confirmSignUp).toHaveBeenCalledWith({
        username: 'newuser',
        confirmationCode: '123456'
      });
    });
  });

  describe('Logout Functionality', () => {
    it('should handle successful logout', async () => {
      const secureSessionStorage = (await import('../../../utils/secureSessionStorage')).default;

      mockAuth.signOut.mockResolvedValue({});

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      let logoutResult;
      await act(async () => {
        logoutResult = await result.current.logout();
      });

      expect(logoutResult.success).toBe(true);
      expect(mockAuth.signOut).toHaveBeenCalled();
      expect(secureSessionStorage.clearSession).toHaveBeenCalled();

      // Should clear auth state
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBe(null);
      expect(result.current.tokens).toBe(null);
    });

    it('should handle logout even when Cognito signOut fails', async () => {
      const secureSessionStorage = (await import('../../../utils/secureSessionStorage')).default;
      
      mockAuth.signOut.mockRejectedValue(new Error('Network error'));

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      let logoutResult;
      await act(async () => {
        logoutResult = await result.current.logout();
      });

      expect(logoutResult.success).toBe(false);
      expect(logoutResult.message).toBe('Network error');

      // Should still clear local state
      expect(secureSessionStorage.clearSession).toHaveBeenCalled();
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBe(null);
    });
  });

  describe('Password Reset Functionality', () => {
    it('should handle password reset request', async () => {
      mockAuth.resetPassword.mockResolvedValue({
        nextStep: { resetPasswordStep: 'CONFIRM_RESET_PASSWORD_WITH_CODE' }
      });

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      let resetResult;
      await act(async () => {
        resetResult = await result.current.resetPasswordRequest('testuser');
      });

      expect(resetResult.success).toBe(true);
      expect(resetResult.message).toContain('reset code sent');
      expect(mockAuth.resetPassword).toHaveBeenCalledWith({ username: 'testuser' });
    });

    it('should handle password reset confirmation', async () => {
      mockAuth.confirmResetPassword.mockResolvedValue({});

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      let confirmResult;
      await act(async () => {
        confirmResult = await result.current.confirmPasswordReset(
          'testuser',
          '123456',
          'newpassword123'
        );
      });

      expect(confirmResult.success).toBe(true);
      expect(confirmResult.message).toContain('reset successfully');
      
      expect(mockAuth.confirmResetPassword).toHaveBeenCalledWith({
        username: 'testuser',
        confirmationCode: '123456',
        newPassword: 'newpassword123'
      });
    });
  });

  describe('Token Management', () => {
    it('should refresh tokens successfully', async () => {
      const secureSessionStorage = (await import('../../../utils/secureSessionStorage')).default;
      
      const mockRefreshedTokens = {
        accessToken: { toString: () => 'refreshed-access-token' },
        idToken: { toString: () => 'refreshed-id-token' },
        refreshToken: { toString: () => 'refreshed-refresh-token' }
      };

      mockAuth.fetchAuthSession.mockResolvedValue({ tokens: mockRefreshedTokens });

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      let refreshedTokens;
      await act(async () => {
        refreshedTokens = await result.current.refreshTokens();
      });

      expect(refreshedTokens).toEqual({
        accessToken: 'refreshed-access-token',
        idToken: 'refreshed-id-token',
        refreshToken: 'refreshed-refresh-token'
      });

      expect(secureSessionStorage.storeTokens).toHaveBeenCalled();
      expect(result.current.tokens).toEqual(refreshedTokens);
    });

    it('should handle token refresh failure by logging out', async () => {
      mockAuth.fetchAuthSession.mockRejectedValue(new Error('Token refresh failed'));

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      await act(async () => {
        try {
          await result.current.refreshTokens();
        } catch (error) {
          expect(error.message).toBe('Token refresh failed');
        }
      });

      // Should have logged out
      expect(result.current.isAuthenticated).toBe(false);
    });
  });

  describe('Circuit Breaker and Retry Logic', () => {
    it('should implement retry circuit breaker correctly', async () => {
      // Mock consecutive failures to trigger circuit breaker
      mockAuth.getCurrentUser.mockRejectedValue(new Error('Network error'));
      mockAuth.fetchAuthSession.mockRejectedValue(new Error('Network error'));

      const { result } = renderAuthHook();

      // Should initially fail but not exceed max retries immediately
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.retryCount).toBeGreaterThan(0);
      expect(result.current.retryCount).toBeLessThanOrEqual(result.current.maxRetries);

      // Subsequent auth checks should be limited by circuit breaker
      const initialRetryCount = result.current.retryCount;
      
      await act(async () => {
        result.current.checkAuthState(); // Should be limited by backoff
      });

      // Retry count should not immediately increment due to backoff
      expect(result.current.retryCount).toBe(initialRetryCount);
    });

    it('should reset retry count on successful authentication', async () => {
      const mockUser = {
        userId: 'reset-user',
        username: 'resetuser',
        userAttributes: { email: 'reset@example.com' },
        signInDetails: { loginId: 'reset@example.com' }
      };

      const mockTokens = {
        accessToken: { toString: () => 'reset-access-token' },
        idToken: { toString: () => 'reset-id-token' },
        refreshToken: { toString: () => 'reset-refresh-token' }
      };

      // First fail, then succeed
      mockAuth.getCurrentUser
        .mockRejectedValueOnce(new Error('First failure'))
        .mockResolvedValue(mockUser);
      
      mockAuth.fetchAuthSession.mockResolvedValue({ tokens: mockTokens });

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should have incremented retry count initially
      expect(result.current.retryCount).toBeGreaterThan(0);

      // Force a successful auth check
      await act(async () => {
        result.current.checkAuthState(true); // Force retry
      });

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true);
      });

      // Retry count should be reset on success
      expect(result.current.retryCount).toBe(0);
    });
  });

  describe('Error Handling and Security', () => {
    it('should clear demo/fallback authentication sessions', async () => {
      // Set up fake demo sessions
      localStorage.setItem('demo-user', 'fake-user');
      localStorage.setItem('demo-session', 'fake-session');
      localStorage.setItem('fallback-auth', 'true');
      sessionStorage.setItem('demo-user', 'fake-user');
      sessionStorage.setItem('demo-session', 'fake-session');

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should have cleared all demo sessions
      expect(localStorage.getItem('demo-user')).toBe(null);
      expect(localStorage.getItem('demo-session')).toBe(null);
      expect(localStorage.getItem('fallback-auth')).toBe(null);
      expect(sessionStorage.getItem('demo-user')).toBe(null);
      expect(sessionStorage.getItem('demo-session')).toBe(null);
    });

    it('should handle disabled authentication gracefully', async () => {
      // Mock authentication disabled
      vi.doMock('../../../config/environment', () => ({
        FEATURES: {
          authentication: {
            enabled: false
          }
        }
      }));

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should remain unauthenticated
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBe(null);
    });

    it('should handle unconfigured Cognito gracefully', async () => {
      const { isCognitoConfigured } = await import('../../../config/amplify');
      isCognitoConfigured.mockReturnValue(false);

      const { result } = renderAuthHook();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should remain unauthenticated
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBe(null);
    });
  });

  describe('Hook Usage Requirements', () => {
    it('should throw error when used outside AuthProvider', () => {
      // Capture console.error to prevent test noise
      const originalError = console.error;
      console.error = vi.fn();

      expect(() => {
        renderHook(() => useAuth());
      }).toThrow('useAuth must be used within an AuthProvider');

      console.error = originalError;
    });
  });
});