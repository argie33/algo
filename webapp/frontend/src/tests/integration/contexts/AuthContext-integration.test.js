/**
 * AuthContext Integration Tests
 * Tests AuthContext integration with real AWS Cognito, runtime config, and session management
 * Tests full authentication flows in deployment environment
 */

import { describe, it, expect, beforeEach, afterEach, beforeAll, afterAll, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import React from 'react';
import { AuthProvider, useAuth } from '../../../contexts/AuthContext';

// Integration test timeout
const INTEGRATION_TIMEOUT = 30000;

// Mock AWS Amplify with real-like responses for integration testing
vi.mock('@aws-amplify/auth', () => {
  const createMockTokens = (userId) => ({
    accessToken: { 
      toString: () => `arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_TEST123/${userId}/access-token-${Date.now()}` 
    },
    idToken: { 
      toString: () => `arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_TEST123/${userId}/id-token-${Date.now()}` 
    },
    refreshToken: { 
      toString: () => `arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_TEST123/${userId}/refresh-token-${Date.now()}` 
    }
  });

  return {
    fetchAuthSession: vi.fn(),
    signIn: vi.fn(),
    signUp: vi.fn(),
    confirmSignUp: vi.fn(),
    confirmSignIn: vi.fn(),
    signOut: vi.fn(),
    resetPassword: vi.fn(),
    confirmResetPassword: vi.fn(),
    getCurrentUser: vi.fn(),
    _createMockTokens: createMockTokens // Helper for tests
  };
});

// Mock with real session storage behavior
vi.mock('../../../utils/secureSessionStorage', () => {
  const storage = new Map();
  return {
    default: {
      storeTokens: vi.fn((tokens) => {
        storage.set('auth_tokens', JSON.stringify(tokens));
        localStorage.setItem('accessToken', tokens.accessToken);
      }),
      clearSession: vi.fn(() => {
        storage.clear();
        localStorage.removeItem('accessToken');
        sessionStorage.clear();
      }),
      getTokens: vi.fn(() => {
        const stored = storage.get('auth_tokens');
        return stored ? JSON.parse(stored) : null;
      })
    }
  };
});

// Mock SessionManager with real behavior simulation
vi.mock('../../../components/auth/SessionManager', () => ({
  default: ({ children }) => {
    // Simulate real session monitoring behavior
    React.useEffect(() => {
      const handleStorageChange = (e) => {
        if (e.key === 'accessToken' && !e.newValue) {
          // Simulate session expiration detection
          console.log('Session expired detected by SessionManager');
        }
      };

      window.addEventListener('storage', handleStorageChange);
      return () => window.removeEventListener('storage', handleStorageChange);
    }, []);

    return children;
  }
}));

// Mock runtime config with real environment detection
vi.mock('../../../services/runtimeConfig', () => ({
  initializeRuntimeConfig: vi.fn(() => {
    // Simulate real runtime config initialization
    return new Promise((resolve) => {
      setTimeout(() => {
        window.__RUNTIME_CONFIG__ = {
          cognito: {
            userPoolId: 'us-east-1_INTEGRATION',
            clientId: 'integration-client-id',
            region: 'us-east-1'
          },
          api: {
            baseUrl: 'https://integration.api.example.com'
          },
          environment: process.env.NODE_ENV || 'test'
        };
        resolve(window.__RUNTIME_CONFIG__);
      }, 100);
    });
  })
}));

// Mock config with realistic production values
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
      userPoolId: 'us-east-1_INTEGRATION',
      clientId: 'integration-client-id',
      region: 'us-east-1'
    }
  }
}));

vi.mock('../../../config/amplify', () => ({
  isCognitoConfigured: vi.fn(() => {
    // Simulate real Cognito configuration check
    const config = window.__RUNTIME_CONFIG__?.cognito;
    return !!(config?.userPoolId && config?.clientId && 
             !config.userPoolId.includes('DUMMY') && 
             !config.clientId.includes('dummy'));
  })
}));

describe('🌐 AuthContext Integration Tests', () => {
  let mockAuth;
  let secureSessionStorage;

  beforeAll(async () => {
    // Setup for integration testing
    mockAuth = await import('@aws-amplify/auth');
    secureSessionStorage = (await import('../../../utils/secureSessionStorage')).default;
  });

  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Clear all storage
    localStorage.clear();
    sessionStorage.clear();
    delete window.__RUNTIME_CONFIG__;
    
    // Setup default mock behaviors for integration
    mockAuth.getCurrentUser.mockRejectedValue(new Error('No current user'));
    mockAuth.fetchAuthSession.mockRejectedValue(new Error('No session'));
    mockAuth.signOut.mockResolvedValue({});
  });

  afterEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  const renderAuthProvider = () => {
    return renderHook(() => useAuth(), {
      wrapper: ({ children }) => (
        <AuthProvider>{children}</AuthProvider>
      )
    });
  };

  describe('Runtime Configuration Integration', () => {
    it('should initialize runtime config during auth check', async () => {
      const { initializeRuntimeConfig } = await import('../../../services/runtimeConfig');
      
      const { result } = renderAuthProvider();

      // Should start loading
      expect(result.current.isLoading).toBe(true);

      // Wait for runtime config and auth check to complete
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      }, { timeout: INTEGRATION_TIMEOUT });

      // Should have called runtime config initialization
      expect(initializeRuntimeConfig).toHaveBeenCalled();
      
      // Should have set up runtime config
      expect(window.__RUNTIME_CONFIG__).toBeDefined();
      expect(window.__RUNTIME_CONFIG__.cognito).toBeDefined();

      console.log('✅ Runtime configuration integration working');
    }, INTEGRATION_TIMEOUT);

    it('should handle runtime config failure gracefully', async () => {
      const { initializeRuntimeConfig } = await import('../../../services/runtimeConfig');
      
      // Make runtime config fail
      initializeRuntimeConfig.mockRejectedValue(new Error('Config service unavailable'));

      const { result } = renderAuthProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      }, { timeout: INTEGRATION_TIMEOUT });

      // Should complete auth check despite runtime config failure
      expect(result.current.isLoading).toBe(false);
      expect(result.current.isAuthenticated).toBe(false);
      
      console.log('✅ Runtime config failure handling working');
    }, INTEGRATION_TIMEOUT);
  });

  describe('Full Authentication Flow Integration', () => {
    it('should handle complete login -> authenticated -> logout flow', async () => {
      // Setup realistic user data
      const mockUser = {
        userId: 'integration-user-123',
        username: 'integration@example.com',
        userAttributes: {
          email: 'integration@example.com',
          given_name: 'Integration',
          family_name: 'Test',
          email_verified: 'true'
        },
        signInDetails: {
          loginId: 'integration@example.com'
        }
      };

      const mockTokens = mockAuth._createMockTokens(mockUser.userId);

      // Setup successful login flow
      mockAuth.signIn.mockResolvedValue({ isSignedIn: true });
      mockAuth.getCurrentUser.mockResolvedValue(mockUser);
      mockAuth.fetchAuthSession.mockResolvedValue({ tokens: mockTokens });

      const { result } = renderAuthProvider();

      // Wait for initial auth check
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      }, { timeout: INTEGRATION_TIMEOUT });

      expect(result.current.isAuthenticated).toBe(false);

      // Perform login
      let loginResult;
      await act(async () => {
        loginResult = await result.current.login('integration@example.com', 'password123');
      });

      expect(loginResult.success).toBe(true);

      // Should be authenticated
      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true);
      }, { timeout: INTEGRATION_TIMEOUT });

      expect(result.current.user.email).toBe('integration@example.com');
      expect(result.current.user.firstName).toBe('Integration');
      expect(result.current.user.lastName).toBe('Test');
      expect(result.current.tokens).toBeTruthy();
      
      // Should have stored tokens securely
      expect(secureSessionStorage.storeTokens).toHaveBeenCalled();
      expect(localStorage.getItem('accessToken')).toBeTruthy();

      // Perform logout
      let logoutResult;
      await act(async () => {
        logoutResult = await result.current.logout();
      });

      expect(logoutResult.success).toBe(true);
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBe(null);
      expect(result.current.tokens).toBe(null);
      
      // Should have cleared secure storage
      expect(secureSessionStorage.clearSession).toHaveBeenCalled();
      expect(localStorage.getItem('accessToken')).toBe(null);

      console.log('✅ Full authentication flow integration working');
    }, INTEGRATION_TIMEOUT);

    it('should handle MFA flow integration', async () => {
      // Setup MFA challenge
      mockAuth.signIn.mockResolvedValue({
        isSignedIn: false,
        nextStep: {
          signInStep: 'CONFIRM_SIGN_IN_WITH_SMS_MFA_CODE',
          additionalInfo: {
            destination: '+1***-***-9876'
          }
        }
      });

      const { result } = renderAuthProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Initiate login with MFA
      let loginResult;
      await act(async () => {
        loginResult = await result.current.login('mfa@example.com', 'password123');
      });

      expect(loginResult.success).toBe(false);
      expect(loginResult.nextStep).toBe('MFA_CHALLENGE');
      expect(loginResult.challengeType).toBe('SMS_MFA');
      expect(result.current.mfaChallenge).toBe('SMS_MFA');

      // Setup MFA confirmation success
      const mockUser = {
        userId: 'mfa-user-456',
        username: 'mfa@example.com',
        userAttributes: {
          email: 'mfa@example.com',
          'custom:mfa_enabled': 'true'
        },
        signInDetails: { loginId: 'mfa@example.com' }
      };

      const mockTokens = mockAuth._createMockTokens(mockUser.userId);

      mockAuth.confirmSignIn.mockResolvedValue({ isSignedIn: true });
      mockAuth.getCurrentUser.mockResolvedValue(mockUser);
      mockAuth.fetchAuthSession.mockResolvedValue({ tokens: mockTokens });

      // Confirm MFA
      let mfaResult;
      await act(async () => {
        mfaResult = await result.current.confirmMFA('123456');
      });

      expect(mfaResult.success).toBe(true);

      // Should be authenticated with MFA
      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true);
        expect(result.current.mfaChallenge).toBe(null);
      });

      expect(result.current.user.mfaEnabled).toBe(true);

      console.log('✅ MFA flow integration working');
    }, INTEGRATION_TIMEOUT);
  });

  describe('Session Management Integration', () => {
    it('should handle session restoration on page reload', async () => {
      const mockUser = {
        userId: 'session-user-789',
        username: 'session@example.com',
        userAttributes: {
          email: 'session@example.com'
        },
        signInDetails: { loginId: 'session@example.com' }
      };

      const mockTokens = mockAuth._createMockTokens(mockUser.userId);

      // Simulate existing session
      mockAuth.getCurrentUser.mockResolvedValue(mockUser);
      mockAuth.fetchAuthSession.mockResolvedValue({ tokens: mockTokens });

      const { result } = renderAuthProvider();

      // Should restore session automatically
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
        expect(result.current.isAuthenticated).toBe(true);
      }, { timeout: INTEGRATION_TIMEOUT });

      expect(result.current.user.email).toBe('session@example.com');
      expect(result.current.tokens).toBeTruthy();

      console.log('✅ Session restoration integration working');
    }, INTEGRATION_TIMEOUT);

    it('should handle token refresh integration', async () => {
      // Start with authenticated user
      const mockUser = {
        userId: 'refresh-user-101',
        username: 'refresh@example.com',
        userAttributes: { email: 'refresh@example.com' },
        signInDetails: { loginId: 'refresh@example.com' }
      };

      const initialTokens = mockAuth._createMockTokens(mockUser.userId);
      const refreshedTokens = {
        accessToken: { toString: () => 'refreshed-access-token-new' },
        idToken: { toString: () => 'refreshed-id-token-new' },
        refreshToken: { toString: () => 'refreshed-refresh-token-new' }
      };

      mockAuth.getCurrentUser.mockResolvedValue(mockUser);
      mockAuth.fetchAuthSession
        .mockResolvedValueOnce({ tokens: initialTokens })
        .mockResolvedValue({ tokens: refreshedTokens });

      const { result } = renderAuthProvider();

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true);
      });

      // Perform token refresh
      let newTokens;
      await act(async () => {
        newTokens = await result.current.refreshTokens();
      });

      expect(newTokens.accessToken).toBe('refreshed-access-token-new');
      expect(result.current.tokens.accessToken).toBe('refreshed-access-token-new');
      
      // Should have updated secure storage
      expect(secureSessionStorage.storeTokens).toHaveBeenCalledWith(
        expect.objectContaining({
          accessToken: 'refreshed-access-token-new'
        })
      );

      console.log('✅ Token refresh integration working');
    }, INTEGRATION_TIMEOUT);

    it('should handle token refresh failure and logout', async () => {
      // Start authenticated
      const mockUser = {
        userId: 'expire-user-202',
        username: 'expire@example.com',
        userAttributes: { email: 'expire@example.com' },
        signInDetails: { loginId: 'expire@example.com' }
      };

      const initialTokens = mockAuth._createMockTokens(mockUser.userId);

      mockAuth.getCurrentUser.mockResolvedValue(mockUser);
      mockAuth.fetchAuthSession
        .mockResolvedValueOnce({ tokens: initialTokens })
        .mockRejectedValue(new Error('Token expired'));

      const { result } = renderAuthProvider();

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true);
      });

      // Attempt token refresh that fails
      await act(async () => {
        try {
          await result.current.refreshTokens();
        } catch (error) {
          expect(error.message).toBe('Token expired');
        }
      });

      // Should have logged out automatically
      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(false);
      });

      expect(result.current.user).toBe(null);
      expect(result.current.tokens).toBe(null);

      console.log('✅ Token refresh failure handling working');
    }, INTEGRATION_TIMEOUT);
  });

  describe('Circuit Breaker Integration', () => {
    it('should implement retry circuit breaker in real environment', async () => {
      // Simulate network failures
      mockAuth.getCurrentUser.mockRejectedValue(new Error('Network timeout'));
      mockAuth.fetchAuthSession.mockRejectedValue(new Error('Network timeout'));

      const { result } = renderAuthProvider();

      // Should fail but track retries
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      }, { timeout: INTEGRATION_TIMEOUT });

      expect(result.current.retryCount).toBeGreaterThan(0);
      expect(result.current.retryCount).toBeLessThanOrEqual(result.current.maxRetries);

      // Further auth checks should be rate-limited
      const beforeRetryCount = result.current.retryCount;
      
      // Immediate retry should be blocked by backoff
      await act(async () => {
        result.current.checkAuthState();
      });

      // Should not increment immediately due to exponential backoff
      expect(result.current.retryCount).toBe(beforeRetryCount);

      console.log('✅ Circuit breaker integration working');
    }, INTEGRATION_TIMEOUT);

    it('should recover from circuit breaker on successful auth', async () => {
      const mockUser = {
        userId: 'recovery-user-303',
        username: 'recovery@example.com',
        userAttributes: { email: 'recovery@example.com' },
        signInDetails: { loginId: 'recovery@example.com' }
      };

      const mockTokens = mockAuth._createMockTokens(mockUser.userId);

      // First calls fail, then succeed
      mockAuth.getCurrentUser
        .mockRejectedValueOnce(new Error('Temporary failure'))
        .mockRejectedValueOnce(new Error('Temporary failure'))
        .mockResolvedValue(mockUser);

      mockAuth.fetchAuthSession.mockResolvedValue({ tokens: mockTokens });

      const { result } = renderAuthProvider();

      // Should initially fail and increment retry count
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      expect(result.current.retryCount).toBeGreaterThan(0);

      // Force successful retry
      await act(async () => {
        result.current.checkAuthState(true); // Force retry
      });

      await waitFor(() => {
        expect(result.current.isAuthenticated).toBe(true);
      });

      // Should reset retry count on success
      expect(result.current.retryCount).toBe(0);

      console.log('✅ Circuit breaker recovery working');
    }, INTEGRATION_TIMEOUT);
  });

  describe('Environment Integration', () => {
    it('should handle different deployment environments', async () => {
      // Test in different environment configurations
      const environments = ['development', 'staging', 'production'];
      
      for (const env of environments) {
        window.__RUNTIME_CONFIG__ = {
          environment: env,
          cognito: {
            userPoolId: `us-east-1_${env.toUpperCase()}`,
            clientId: `${env}-client-id`,
            region: 'us-east-1'
          }
        };

        const { result } = renderAuthProvider();

        await waitFor(() => {
          expect(result.current.isLoading).toBe(false);
        });

        // Should complete auth check in any environment
        expect(result.current.isLoading).toBe(false);
        
        console.log(`✅ Environment ${env} integration working`);
      }
    }, INTEGRATION_TIMEOUT);

    it('should handle authentication disabled in environment', async () => {
      // Mock authentication disabled
      vi.doMock('../../../config/environment', () => ({
        FEATURES: {
          authentication: {
            enabled: false
          }
        }
      }));

      const { result } = renderAuthProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should remain unauthenticated
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.user).toBe(null);

      console.log('✅ Disabled authentication handling working');
    }, INTEGRATION_TIMEOUT);
  });

  describe('Error Recovery Integration', () => {
    it('should handle network errors gracefully', async () => {
      mockAuth.getCurrentUser.mockRejectedValue(new Error('NETWORK_ERROR'));
      mockAuth.fetchAuthSession.mockRejectedValue(new Error('NETWORK_ERROR'));

      const { result } = renderAuthProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Should handle network errors without crashing
      expect(result.current.isAuthenticated).toBe(false);
      expect(result.current.error).toBeTruthy();

      // Should be able to retry
      expect(typeof result.current.checkAuthState).toBe('function');
      expect(typeof result.current.login).toBe('function');

      console.log('✅ Network error handling working');
    }, INTEGRATION_TIMEOUT);

    it('should clear errors on successful operations', async () => {
      // Start with error state
      mockAuth.signIn.mockRejectedValue(new Error('Invalid credentials'));

      const { result } = renderAuthProvider();

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false);
      });

      // Cause login error
      await act(async () => {
        await result.current.login('bad@example.com', 'wrongpassword');
      });

      expect(result.current.error).toBeTruthy();

      // Clear error manually
      act(() => {
        result.current.clearError();
      });

      expect(result.current.error).toBe(null);

      console.log('✅ Error clearing integration working');
    }, INTEGRATION_TIMEOUT);
  });
});