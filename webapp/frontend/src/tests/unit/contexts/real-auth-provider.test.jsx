/**
 * UNIT TESTS: AuthProvider Context
 * Real implementation testing with zero mocks for business logic
 * Comprehensive coverage of authentication flows, state management, and AWS Cognito integration
 */

import { renderHook, act, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { AuthProvider, useAuth } from '../../../contexts/AuthContext';

// Mock AWS Amplify Auth functions
vi.mock('@aws-amplify/auth');
vi.mock('../../../components/auth/SessionManager', () => ({
  default: ({ children }) => children
}));

describe('AuthProvider Context Unit Tests', () => {
  let mockLocalStorage;
  let mockWindow;
  let amplifyAuth;
  
  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Import amplify auth after mocking
    const { default: amplifyAuthModule } = await import('@aws-amplify/auth');
    amplifyAuth = amplifyAuthModule;
    
    // Mock localStorage
    mockLocalStorage = {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn()
    };
    Object.defineProperty(window, 'localStorage', {
      value: mockLocalStorage,
      writable: true
    });
    
    // Mock window.__CONFIG__
    mockWindow = {
      __CONFIG__: {
        COGNITO: {
          USER_POOL_ID: 'us-east-1_TestPool',
          CLIENT_ID: 'test-client-id-12345'
        }
      }
    };
    Object.defineProperty(window, '__CONFIG__', {
      value: mockWindow.__CONFIG__,
      writable: true
    });
    
    // Mock console methods to reduce noise in tests
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
    
    // Default AWS Amplify mocks
    amplifyAuth.getCurrentUser.mockRejectedValue(new Error('No user'));
    amplifyAuth.fetchAuthSession.mockRejectedValue(new Error('No session'));
    amplifyAuth.signIn.mockResolvedValue({ isSignedIn: false });
    amplifyAuth.signUp.mockResolvedValue({ isSignUpComplete: false });
    amplifyAuth.confirmSignUp.mockResolvedValue({ isSignUpComplete: true });
    amplifyAuth.signOut.mockResolvedValue();
    amplifyAuth.resetPassword.mockResolvedValue({ nextStep: {} });
    amplifyAuth.confirmResetPassword.mockResolvedValue();
  });
  
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderAuthProvider = (initialProps = {}) => {
    const wrapper = ({ children }) => (
      <AuthProvider {...initialProps}>
        {children}
      </AuthProvider>
    );
    
    return renderHook(() => useAuth(), { wrapper });
  };

  describe('Context Initialization', () => {
    it('initializes with correct default state when authenticated', async () => {
      const { result } = renderAuthProvider();

      expect(result.current.user).toBe(null);
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.isLoading).toBe(true);
      expect(result.current.error).toBe(null);
      expect(result.current.tokens).toBe(null);

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });
    });

    it('throws error when useAuth is used outside provider', () => {
      expect(() => {
        renderHook(() => useAuth());
      }).toThrow('useAuth must be used within an AuthProvider');
    });

    it('resets state when user is not authenticated', async () => {
      const { result } = renderAuthProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBe(null);
      expect(result.current.tokens).toBe(null);
    });
  });

  describe('Cognito Authentication Flow', () => {
    it('successfully authenticates user with valid Cognito session', async () => {
      const mockUser = {
        username: 'testuser',
        userId: 'user-123',
        userAttributes: {
          given_name: 'John',
          family_name: 'Doe'
        },
        signInDetails: {
          loginId: 'testuser@example.com'
        }
      };

      const mockSession = {
        tokens: {
          accessToken: {
            toString: () => 'mock-access-token'
          },
          idToken: {
            toString: () => 'mock-id-token'
          },
          refreshToken: {
            toString: () => 'mock-refresh-token'
          }
        }
      };

      amplifyAuth.getCurrentUser.mockResolvedValue(mockUser);
      amplifyAuth.fetchAuthSession.mockResolvedValue(mockSession);

      const { result } = renderAuthProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.user).toMatchObject({
        username: 'testuser',
        userId: 'user-123',
        email: 'testuser@example.com',
        firstName: 'John',
        lastName: 'Doe'
      });
      expect(result.current.tokens).toMatchObject({
        accessToken: 'mock-access-token',
        idToken: 'mock-id-token',
        refreshToken: 'mock-refresh-token'
      });
      expect(mockLocalStorage.setItem).toHaveBeenCalledWith('accessToken', 'mock-access-token');
    });

    it('handles missing Cognito session gracefully', async () => {
      const { result } = renderAuthProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBe(null);
    });

    it('falls back to demo user when Cognito is misconfigured', async () => {
      // Mock misconfigured Cognito
      window.__CONFIG__.COGNITO = {
        USER_POOL_ID: 'MISSING_USER_POOL_ID',
        CLIENT_ID: 'missing-client-id'
      };

      const demoUser = {
        id: 'demo-123',
        name: 'Demo User',
        email: 'demo@example.com',
        signInUserSession: {
          accessToken: { jwtToken: 'demo-access-token' },
          idToken: { jwtToken: 'demo-id-token' }
        }
      };

      mockLocalStorage.getItem.mockReturnValue(JSON.stringify(demoUser));

      const { result } = renderAuthProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.isAuthenticated).toBe(true);
      expect(result.current.user).toMatchObject({
        username: 'Demo User',
        userId: 'demo-123',
        email: 'demo@example.com',
        isDemoUser: true
      });
    });
  });

  describe('Login Functionality', () => {
    it('successfully logs in user', async () => {
      const mockSignInResponse = {
        isSignedIn: true,
        nextStep: { signInStep: 'DONE' }
      };

      const mockUser = {
        username: 'testuser',
        userId: 'user-123',
        userAttributes: { given_name: 'John', family_name: 'Doe' },
        signInDetails: { loginId: 'testuser@example.com' }
      };

      const mockSession = {
        tokens: {
          accessToken: { toString: () => 'access-token' },
          idToken: { toString: () => 'id-token' },
          refreshToken: { toString: () => 'refresh-token' }
        }
      };

      amplifyAuth.signIn.mockResolvedValue(mockSignInResponse);
      amplifyAuth.signOut.mockResolvedValue();
      amplifyAuth.getCurrentUser.mockResolvedValue(mockUser);
      amplifyAuth.fetchAuthSession.mockResolvedValue(mockSession);

      const { result } = renderAuthProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      let loginResult;
      await act(async () => {
        loginResult = await result.current.login('testuser', 'password123');
      });

      expect(loginResult.success).toBe(true);
      expect(amplifyAuth.signIn).toHaveBeenCalledWith({
        username: 'testuser',
        password: 'password123'
      });
      expect(result.current.isAuthenticated).toBe(true);
    });

    it('handles login requiring confirmation', async () => {
      const mockSignInResponse = {
        isSignedIn: false,
        nextStep: { signInStep: 'CONFIRM_SIGN_UP' }
      };

      amplifyAuth.signIn.mockResolvedValue(mockSignInResponse);
      amplifyAuth.signOut.mockResolvedValue();

      const { result } = renderAuthProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      let loginResult;
      await act(async () => {
        loginResult = await result.current.login('testuser', 'password123');
      });

      expect(loginResult.success).toBe(false);
      expect(loginResult.nextStep).toBe('CONFIRM_SIGN_UP');
      expect(loginResult.message).toContain('confirm your account');
    });

    it('handles login error', async () => {
      const mockError = new Error('Invalid credentials');
      amplifyAuth.signIn.mockRejectedValue(mockError);
      amplifyAuth.signOut.mockResolvedValue();

      const { result } = renderAuthProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      let loginResult;
      await act(async () => {
        loginResult = await result.current.login('testuser', 'wrongpassword');
      });

      expect(loginResult.success).toBe(false);
      expect(loginResult.message).toBe('Invalid credentials');
      expect(result.current.error).toBe('Invalid credentials');
    });
  });

  describe('Registration Functionality', () => {
    it('successfully registers user', async () => {
      const mockSignUpResponse = {
        isSignUpComplete: true,
        userId: 'new-user-123',
        nextStep: { signUpStep: 'DONE' }
      };

      amplifyAuth.signUp.mockResolvedValue(mockSignUpResponse);

      const { result } = renderAuthProvider();

      let registerResult;
      await act(async () => {
        registerResult = await result.current.register(
          'newuser',
          'password123',
          'newuser@example.com',
          'Jane',
          'Smith'
        );
      });

      expect(registerResult.success).toBe(true);
      expect(registerResult.message).toBe('Registration successful!');
      expect(amplifyAuth.signUp).toHaveBeenCalledWith({
        username: 'newuser',
        password: 'password123',
        options: {
          userAttributes: {
            email: 'newuser@example.com',
            given_name: 'Jane',
            family_name: 'Smith'
          }
        }
      });
    });

    it('handles registration requiring confirmation', async () => {
      const mockSignUpResponse = {
        isSignUpComplete: false,
        nextStep: { signUpStep: 'CONFIRM_SIGN_UP' }
      };

      amplifyAuth.signUp.mockResolvedValue(mockSignUpResponse);

      const { result } = renderAuthProvider();

      let registerResult;
      await act(async () => {
        registerResult = await result.current.register(
          'newuser',
          'password123',
          'newuser@example.com',
          'Jane',
          'Smith'
        );
      });

      expect(registerResult.success).toBe(false);
      expect(registerResult.nextStep).toBe('CONFIRM_SIGN_UP');
      expect(registerResult.message).toContain('check your email');
    });
  });

  describe('Logout Functionality', () => {
    it('successfully logs out user', async () => {
      // First set up authenticated state
      amplifyAuth.getCurrentUser.mockResolvedValue({
        username: 'testuser'
      });
      amplifyAuth.fetchAuthSession.mockResolvedValue({
        tokens: {
          accessToken: { toString: () => 'token' }
        }
      });

      const { result } = renderAuthProvider();

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true);
      });

      // Mock signOut
      amplifyAuth.signOut.mockResolvedValue();

      let logoutResult;
      await act(async () => {
        logoutResult = await result.current.logout();
      });

      expect(logoutResult.success).toBe(true);
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBe(null);
      expect(result.current.tokens).toBe(null);
      expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('accessToken');
    });
  });

  describe('Password Reset Functionality', () => {
    it('successfully requests password reset', async () => {
      const mockResetResponse = {
        nextStep: { resetPasswordStep: 'CONFIRM_RESET_PASSWORD_WITH_CODE' }
      };

      amplifyAuth.resetPassword.mockResolvedValue(mockResetResponse);

      const { result } = renderAuthProvider();

      let resetResult;
      await act(async () => {
        resetResult = await result.current.resetPasswordRequest('testuser');
      });

      expect(resetResult.success).toBe(true);
      expect(resetResult.message).toContain('Password reset code sent');
      expect(amplifyAuth.resetPassword).toHaveBeenCalledWith({ username: 'testuser' });
    });

    it('successfully confirms password reset', async () => {
      amplifyAuth.confirmResetPassword.mockResolvedValue();

      const { result } = renderAuthProvider();

      let confirmResult;
      await act(async () => {
        confirmResult = await result.current.confirmPasswordReset(
          'testuser',
          '123456',
          'newpassword123'
        );
      });

      expect(confirmResult.success).toBe(true);
      expect(confirmResult.message).toBe('Password reset successfully!');
      expect(amplifyAuth.confirmResetPassword).toHaveBeenCalledWith({
        username: 'testuser',
        confirmationCode: '123456',
        newPassword: 'newpassword123'
      });
    });
  });

  describe('Token Management', () => {
    it('successfully refreshes tokens', async () => {
      const mockSession = {
        tokens: {
          accessToken: { toString: () => 'new-access-token' },
          idToken: { toString: () => 'new-id-token' },
          refreshToken: { toString: () => 'new-refresh-token' }
        }
      };

      amplifyAuth.fetchAuthSession.mockResolvedValue(mockSession);

      const { result } = renderAuthProvider();

      let tokens;
      await act(async () => {
        tokens = await result.current.refreshTokens();
      });

      expect(tokens).toMatchObject({
        accessToken: 'new-access-token',
        idToken: 'new-id-token',
        refreshToken: 'new-refresh-token'
      });
      expect(result.current.tokens).toMatchObject(tokens);
      expect(mockLocalStorage.setItem).toHaveBeenCalledWith('accessToken', 'new-access-token');
    });
  });

  describe('Error Management', () => {
    it('clears error when clearError is called', async () => {
      const { result } = renderAuthProvider();

      // Set an error first
      await act(async () => {
        try {
          await result.current.login('invalid', 'invalid');
        } catch (error) {
          // Expected to fail
        }
      });

      act(() => {
        result.current.clearError();
      });

      expect(result.current.error).toBe(null);
    });
  });

  describe('Alias Methods', () => {
    it('forgotPassword is an alias for resetPasswordRequest', () => {
      const { result } = renderAuthProvider();
      
      expect(result.current.forgotPassword).toBe(result.current.resetPasswordRequest);
    });
  });
});