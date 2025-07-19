/**
 * Real AuthContext Unit Tests
 * Testing the actual AuthContext.jsx with AWS Amplify integration
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import React from 'react';

// Mock AWS Amplify auth functions
vi.mock('@aws-amplify/auth', () => ({
  fetchAuthSession: vi.fn(),
  signIn: vi.fn(),
  signUp: vi.fn(),
  confirmSignUp: vi.fn(),
  signOut: vi.fn(),
  resetPassword: vi.fn(),
  confirmResetPassword: vi.fn(),
  getCurrentUser: vi.fn()
}));

// Mock SessionManager
vi.mock('../../../components/auth/SessionManager', () => ({
  default: vi.fn(() => null)
}));

// Import the REAL AuthContext
import { AuthProvider, useAuth } from '../../../contexts/AuthContext';
import { 
  fetchAuthSession, 
  signIn, 
  signUp, 
  confirmSignUp, 
  signOut, 
  resetPassword, 
  confirmResetPassword, 
  getCurrentUser 
} from '@aws-amplify/auth';

describe('🔐 Real AuthContext', () => {
  let mockSessionManager;

  beforeEach(() => {
    vi.clearAllMocks();
    
    // Setup default mock implementations
    fetchAuthSession.mockResolvedValue({
      tokens: {
        accessToken: { toString: () => 'mock_access_token' },
        idToken: { toString: () => 'mock_id_token' }
      }
    });

    getCurrentUser.mockResolvedValue({
      userId: 'user_123',
      username: 'testuser',
      attributes: {
        email: 'test@example.com',
        given_name: 'John',
        family_name: 'Doe'
      }
    });
  });

  describe('AuthProvider Initialization', () => {
    it('should initialize with correct default state', () => {
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      
      const { result } = renderHook(() => useAuth(), { wrapper });

      expect(result.current.user).toBeNull();
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.isLoading).toBe(true);
      expect(result.current.error).toBeNull();
      expect(result.current.tokens).toBeNull();
    });

    it('should provide all required auth methods', () => {
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      
      const { result } = renderHook(() => useAuth(), { wrapper });

      expect(typeof result.current.login).toBe('function');
      expect(typeof result.current.register).toBe('function');
      expect(typeof result.current.logout).toBe('function');
      expect(typeof result.current.confirmRegistration).toBe('function');
      expect(typeof result.current.forgotPassword).toBe('function');
      expect(typeof result.current.confirmPasswordReset).toBe('function');
      expect(typeof result.current.clearError).toBe('function');
    });

    it('should attempt to restore session on mount', async () => {
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      
      renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(fetchAuthSession).toHaveBeenCalled();
      });
    });
  });

  describe('Authentication Actions', () => {
    describe('Login', () => {
      it('should handle successful login', async () => {
        const mockSignInResult = {
          isSignedIn: true,
          nextStep: { signInStep: 'DONE' }
        };
        
        signIn.mockResolvedValue(mockSignInResult);
        
        const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
        const { result } = renderHook(() => useAuth(), { wrapper });

        await act(async () => {
          await result.current.login('test@example.com', 'password123');
        });

        expect(signIn).toHaveBeenCalledWith({
          username: 'test@example.com',
          password: 'password123'
        });

        await waitFor(() => {
          expect(result.current.isAuthenticated).toBe(true);
          expect(result.current.error).toBeNull();
        });
      });

      it('should handle login failure', async () => {
        const loginError = new Error('Invalid credentials');
        signIn.mockRejectedValue(loginError);
        
        const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
        const { result } = renderHook(() => useAuth(), { wrapper });

        await act(async () => {
          try {
            await result.current.login('test@example.com', 'wrongpassword');
          } catch (error) {
            // Error handled by context
          }
        });

        expect(result.current.isAuthenticated).toBe(false);
        expect(result.current.error).toBe('Invalid credentials');
      });

      it('should handle MFA challenge during login', async () => {
        const mockSignInResult = {
          isSignedIn: false,
          nextStep: { 
            signInStep: 'CONFIRM_SIGN_IN_WITH_TOTP_CODE'
          }
        };
        
        signIn.mockResolvedValue(mockSignInResult);
        
        const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
        const { result } = renderHook(() => useAuth(), { wrapper });

        await act(async () => {
          await result.current.login('test@example.com', 'password123');
        });

        expect(result.current.isAuthenticated).toBe(false);
        // Should indicate MFA challenge is needed
        expect(result.current.error).toBeNull();
      });
    });

    describe('Registration', () => {
      it('should handle successful registration', async () => {
        const mockSignUpResult = {
          isSignUpComplete: false,
          nextStep: {
            signUpStep: 'CONFIRM_SIGN_UP'
          },
          userId: 'user_456'
        };
        
        signUp.mockResolvedValue(mockSignUpResult);
        
        const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
        const { result } = renderHook(() => useAuth(), { wrapper });

        await act(async () => {
          await result.current.register(
            'newuser@example.com',
            'password123',
            'John',
            'Doe'
          );
        });

        expect(signUp).toHaveBeenCalledWith({
          username: 'newuser@example.com',
          password: 'password123',
          options: {
            userAttributes: {
              given_name: 'John',
              family_name: 'Doe',
              email: 'newuser@example.com'
            }
          }
        });

        expect(result.current.error).toBeNull();
      });

      it('should handle registration with existing user', async () => {
        const registrationError = new Error('User already exists');
        signUp.mockRejectedValue(registrationError);
        
        const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
        const { result } = renderHook(() => useAuth(), { wrapper });

        await act(async () => {
          try {
            await result.current.register(
              'existing@example.com',
              'password123',
              'John',
              'Doe'
            );
          } catch (error) {
            // Error handled by context
          }
        });

        expect(result.current.error).toBe('User already exists');
      });
    });

    describe('Registration Confirmation', () => {
      it('should handle successful confirmation', async () => {
        const mockConfirmResult = {
          isSignUpComplete: true,
          nextStep: {
            signUpStep: 'DONE'
          }
        };
        
        confirmSignUp.mockResolvedValue(mockConfirmResult);
        
        const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
        const { result } = renderHook(() => useAuth(), { wrapper });

        await act(async () => {
          await result.current.confirmRegistration('test@example.com', '123456');
        });

        expect(confirmSignUp).toHaveBeenCalledWith({
          username: 'test@example.com',
          confirmationCode: '123456'
        });

        expect(result.current.error).toBeNull();
      });

      it('should handle invalid confirmation code', async () => {
        const confirmError = new Error('Invalid verification code');
        confirmSignUp.mockRejectedValue(confirmError);
        
        const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
        const { result } = renderHook(() => useAuth(), { wrapper });

        await act(async () => {
          try {
            await result.current.confirmRegistration('test@example.com', 'wrongcode');
          } catch (error) {
            // Error handled by context
          }
        });

        expect(result.current.error).toBe('Invalid verification code');
      });
    });

    describe('Logout', () => {
      it('should handle successful logout', async () => {
        signOut.mockResolvedValue();
        
        const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
        const { result } = renderHook(() => useAuth(), { wrapper });

        // First set authenticated state
        await act(async () => {
          result.current.dispatch({
            type: 'LOGIN_SUCCESS',
            payload: {
              user: { id: 'user_123', email: 'test@example.com' },
              tokens: { accessToken: 'token_123' }
            }
          });
        });

        // Then logout
        await act(async () => {
          await result.current.logout();
        });

        expect(signOut).toHaveBeenCalled();
        expect(result.current.isAuthenticated).toBe(false);
        expect(result.current.user).toBeNull();
        expect(result.current.tokens).toBeNull();
      });

      it('should handle logout error gracefully', async () => {
        const logoutError = new Error('Logout failed');
        signOut.mockRejectedValue(logoutError);
        
        const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
        const { result } = renderHook(() => useAuth(), { wrapper });

        await act(async () => {
          try {
            await result.current.logout();
          } catch (error) {
            // Error handled by context
          }
        });

        // Should still clear local state even if logout call fails
        expect(result.current.isAuthenticated).toBe(false);
        expect(result.current.user).toBeNull();
      });
    });

    describe('Password Reset', () => {
      it('should handle forgot password request', async () => {
        const mockResetResult = {
          nextStep: {
            resetPasswordStep: 'CONFIRM_RESET_PASSWORD_WITH_CODE'
          }
        };
        
        resetPassword.mockResolvedValue(mockResetResult);
        
        const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
        const { result } = renderHook(() => useAuth(), { wrapper });

        await act(async () => {
          await result.current.forgotPassword('test@example.com');
        });

        expect(resetPassword).toHaveBeenCalledWith({
          username: 'test@example.com'
        });

        expect(result.current.error).toBeNull();
      });

      it('should handle password reset confirmation', async () => {
        confirmResetPassword.mockResolvedValue();
        
        const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
        const { result } = renderHook(() => useAuth(), { wrapper });

        await act(async () => {
          await result.current.confirmPasswordReset(
            'test@example.com',
            '123456',
            'newpassword123'
          );
        });

        expect(confirmResetPassword).toHaveBeenCalledWith({
          username: 'test@example.com',
          confirmationCode: '123456',
          newPassword: 'newpassword123'
        });

        expect(result.current.error).toBeNull();
      });
    });
  });

  describe('State Management', () => {
    it('should update loading state correctly', async () => {
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });

      expect(result.current.isLoading).toBe(true);

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });
    });

    it('should clear errors when clearError is called', async () => {
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });

      // Set an error state
      await act(async () => {
        result.current.dispatch({
          type: 'SET_ERROR',
          payload: 'Test error'
        });
      });

      expect(result.current.error).toBe('Test error');

      // Clear the error
      await act(async () => {
        result.current.clearError();
      });

      expect(result.current.error).toBeNull();
    });

    it('should handle token updates', async () => {
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });

      const newTokens = {
        accessToken: 'new_access_token',
        idToken: 'new_id_token'
      };

      await act(async () => {
        result.current.dispatch({
          type: 'UPDATE_TOKENS',
          payload: newTokens
        });
      });

      expect(result.current.tokens).toEqual(newTokens);
    });
  });

  describe('Session Restoration', () => {
    it('should restore valid session on mount', async () => {
      const mockSession = {
        tokens: {
          accessToken: { toString: () => 'valid_token' },
          idToken: { toString: () => 'valid_id_token' }
        }
      };

      const mockUser = {
        userId: 'user_123',
        username: 'testuser',
        attributes: {
          email: 'test@example.com'
        }
      };

      fetchAuthSession.mockResolvedValue(mockSession);
      getCurrentUser.mockResolvedValue(mockUser);

      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true);
        expect(result.current.user).toEqual(expect.objectContaining({
          email: 'test@example.com'
        }));
      });
    });

    it('should handle expired session gracefully', async () => {
      const sessionError = new Error('Session expired');
      fetchAuthSession.mockRejectedValue(sessionError);

      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(false);
        expect(result.current.isLoading).toBe(false);
      });
    });

    it('should handle invalid tokens during restoration', async () => {
      const mockSession = {
        tokens: null // Invalid session
      };

      fetchAuthSession.mockResolvedValue(mockSession);

      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(false);
        expect(result.current.isLoading).toBe(false);
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors gracefully', async () => {
      const networkError = new Error('Network request failed');
      signIn.mockRejectedValue(networkError);

      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });

      await act(async () => {
        try {
          await result.current.login('test@example.com', 'password123');
        } catch (error) {
          // Error handled by context
        }
      });

      expect(result.current.error).toBe('Network request failed');
      expect(result.current.isAuthenticated).toBe(false);
    });

    it('should handle AWS Amplify specific errors', async () => {
      const amplifyError = {
        name: 'UserNotConfirmedException',
        message: 'User is not confirmed'
      };
      signIn.mockRejectedValue(amplifyError);

      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });

      await act(async () => {
        try {
          await result.current.login('test@example.com', 'password123');
        } catch (error) {
          // Error handled by context
        }
      });

      expect(result.current.error).toBe('User is not confirmed');
    });

    it('should handle unknown errors with fallback message', async () => {
      const unknownError = { someProperty: 'unknown error structure' };
      signIn.mockRejectedValue(unknownError);

      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });

      await act(async () => {
        try {
          await result.current.login('test@example.com', 'password123');
        } catch (error) {
          // Error handled by context
        }
      });

      expect(typeof result.current.error).toBe('string');
      expect(result.current.error.length).toBeGreaterThan(0);
    });
  });

  describe('Integration with SessionManager', () => {
    it('should render SessionManager component', () => {
      const mockSessionManager = require('../../../components/auth/SessionManager').default;
      
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      renderHook(() => useAuth(), { wrapper });

      expect(mockSessionManager).toHaveBeenCalled();
    });
  });

  describe('Performance', () => {
    it('should not cause unnecessary re-renders', async () => {
      let renderCount = 0;
      const TestComponent = () => {
        renderCount++;
        const auth = useAuth();
        return null;
      };

      const wrapper = ({ children }) => (
        <AuthProvider>
          <TestComponent />
          {children}
        </AuthProvider>
      );

      renderHook(() => useAuth(), { wrapper });

      const initialRenderCount = renderCount;

      // Multiple calls to the same method should not cause extra renders
      const { result } = renderHook(() => useAuth(), { wrapper });
      result.current.clearError();
      result.current.clearError();
      result.current.clearError();

      // Allow for some reasonable number of renders during initialization
      expect(renderCount - initialRenderCount).toBeLessThan(5);
    });

    it('should handle rapid authentication state changes efficiently', async () => {
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result } = renderHook(() => useAuth(), { wrapper });

      const startTime = performance.now();

      // Simulate rapid state changes
      await act(async () => {
        for (let i = 0; i < 10; i++) {
          result.current.dispatch({
            type: 'LOADING',
            payload: i % 2 === 0
          });
        }
      });

      const executionTime = performance.now() - startTime;
      expect(executionTime).toBeLessThan(100); // Should be fast
    });
  });

  describe('useAuth Hook', () => {
    it('should throw error when used outside AuthProvider', () => {
      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
      
      expect(() => {
        renderHook(() => useAuth());
      }).toThrow('useAuth must be used within an AuthProvider');

      consoleError.mockRestore();
    });

    it('should provide stable references for functions', () => {
      const wrapper = ({ children }) => <AuthProvider>{children}</AuthProvider>;
      const { result, rerender } = renderHook(() => useAuth(), { wrapper });

      const initialLogin = result.current.login;
      const initialLogout = result.current.logout;

      rerender();

      expect(result.current.login).toBe(initialLogin);
      expect(result.current.logout).toBe(initialLogout);
    });
  });
});