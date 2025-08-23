import { vi, describe, test, beforeEach, expect, afterEach } from 'vitest';
import authService from '../../../services/authService';

// Mock Amplify Auth
vi.mock('@aws-amplify/auth', () => ({
  Auth: {
    signUp: vi.fn(),
    confirmSignUp: vi.fn(),
    signIn: vi.fn(),
    signOut: vi.fn(),
    getCurrentUser: vi.fn(),
    getIdToken: vi.fn(),
    forgotPassword: vi.fn(),
    forgotPasswordSubmit: vi.fn(),
    changePassword: vi.fn(),
    updateUserAttributes: vi.fn(),
    resendSignUp: vi.fn(),
  }
}));

// Mock localStorage
const mockLocalStorage = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
};
Object.defineProperty(window, 'localStorage', {
  value: mockLocalStorage
});

describe('AuthService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLocalStorage.getItem.mockReturnValue(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('User Registration', () => {
    test('should register new user successfully', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      Auth.signUp.mockResolvedValue({
        user: { username: 'testuser' },
        userConfirmed: false,
        codeDeliveryDetails: {
          destination: 'test@example.com',
          deliveryMedium: 'EMAIL',
          attributeName: 'email'
        }
      });

      const userData = {
        username: 'testuser',
        password: 'TestPassword123!',
        email: 'test@example.com',
        name: 'Test User'
      };

      const result = await authService.signUp(userData);

      expect(Auth.signUp).toHaveBeenCalledWith({
        username: 'testuser',
        password: 'TestPassword123!',
        attributes: {
          email: 'test@example.com',
          name: 'Test User'
        }
      });

      expect(result.success).toBe(true);
      expect(result.user.username).toBe('testuser');
      expect(result.userConfirmed).toBe(false);
    });

    test('should handle registration errors', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      Auth.signUp.mockRejectedValue({
        code: 'UsernameExistsException',
        message: 'An account with the given email already exists.'
      });

      const userData = {
        username: 'existinguser',
        password: 'TestPassword123!',
        email: 'existing@example.com'
      };

      const result = await authService.signUp(userData);

      expect(result.success).toBe(false);
      expect(result.error.code).toBe('UsernameExistsException');
      expect(result.error.message).toContain('email already exists');
    });

    test('should validate password strength', () => {
      const weakPasswords = [
        'short',
        '12345678',
        'password',
        'PASSWORD',
        'Password',
        'Pass123',
        'passwordwithoutuppercase123',
        'PASSWORDWITHOUTLOWERCASE123'
      ];

      weakPasswords.forEach(password => {
        const validation = authService.validatePassword(password);
        expect(validation.isValid).toBe(false);
        expect(validation.errors.length).toBeGreaterThan(0);
      });
    });

    test('should accept strong passwords', () => {
      const strongPasswords = [
        'TestPassword123!',
        'MySecure@Pass2024',
        'Complex#Password99',
        'Str0ng&Password$'
      ];

      strongPasswords.forEach(password => {
        const validation = authService.validatePassword(password);
        expect(validation.isValid).toBe(true);
        expect(validation.errors.length).toBe(0);
      });
    });
  });

  describe('User Authentication', () => {
    test('should sign in user successfully', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      const mockUser = {
        username: 'testuser',
        attributes: {
          email: 'test@example.com',
          name: 'Test User'
        },
        signInUserSession: {
          idToken: {
            jwtToken: 'mock-jwt-token',
            payload: {
              sub: 'user-123',
              email: 'test@example.com',
              'custom:role': 'user'
            }
          }
        }
      };

      Auth.signIn.mockResolvedValue(mockUser);

      const result = await authService.signIn('testuser', 'TestPassword123!');

      expect(Auth.signIn).toHaveBeenCalledWith('testuser', 'TestPassword123!');
      expect(result.success).toBe(true);
      expect(result.user.username).toBe('testuser');
      expect(result.user.email).toBe('test@example.com');
      expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
        'financial_auth_token',
        'mock-jwt-token'
      );
    });

    test('should handle sign in errors', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      Auth.signIn.mockRejectedValue({
        code: 'NotAuthorizedException',
        message: 'Incorrect username or password.'
      });

      const result = await authService.signIn('wronguser', 'wrongpass');

      expect(result.success).toBe(false);
      expect(result.error.code).toBe('NotAuthorizedException');
      expect(result.error.message).toContain('Incorrect username or password');
    });

    test('should handle MFA challenge', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      Auth.signIn.mockResolvedValue({
        challengeName: 'SMS_MFA',
        challengeParam: {
          CODE_DELIVERY_DELIVERY_MEDIUM: 'SMS',
          CODE_DELIVERY_DESTINATION: '+1***123'
        }
      });

      const result = await authService.signIn('testuser', 'TestPassword123!');

      expect(result.success).toBe(true);
      expect(result.challengeName).toBe('SMS_MFA');
      expect(result.requiresMFA).toBe(true);
    });

    test('should confirm MFA code successfully', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      const mockUser = {
        username: 'testuser',
        attributes: { email: 'test@example.com' },
        signInUserSession: {
          idToken: { jwtToken: 'mock-jwt-token' }
        }
      };

      const cognitoUser = { username: 'testuser' };
      Auth.confirmSignIn = vi.fn().mockResolvedValue(mockUser);

      const result = await authService.confirmMFA(cognitoUser, '123456');

      expect(Auth.confirmSignIn).toHaveBeenCalledWith(cognitoUser, '123456', 'SMS_MFA');
      expect(result.success).toBe(true);
      expect(result.user.username).toBe('testuser');
    });
  });

  describe('Session Management', () => {
    test('should get current authenticated user', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      const mockUser = {
        username: 'testuser',
        attributes: {
          sub: 'user-123',
          email: 'test@example.com',
          name: 'Test User'
        }
      };

      Auth.getCurrentUser.mockResolvedValue(mockUser);
      mockLocalStorage.getItem.mockReturnValue('mock-jwt-token');

      const result = await authService.getCurrentUser();

      expect(result.success).toBe(true);
      expect(result.user.username).toBe('testuser');
      expect(result.user.email).toBe('test@example.com');
      expect(result.isAuthenticated).toBe(true);
    });

    test('should handle no current user', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      Auth.getCurrentUser.mockRejectedValue(new Error('No current user'));

      const result = await authService.getCurrentUser();

      expect(result.success).toBe(true);
      expect(result.user).toBeNull();
      expect(result.isAuthenticated).toBe(false);
    });

    test('should get valid JWT token', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      const mockSession = {
        getIdToken: () => ({
          getJwtToken: () => 'valid-jwt-token',
          payload: {
            sub: 'user-123',
            exp: Math.floor(Date.now() / 1000) + 3600 // 1 hour from now
          }
        })
      };

      Auth.currentSession = vi.fn().mockResolvedValue(mockSession);

      const token = await authService.getAuthToken();

      expect(token).toBe('valid-jwt-token');
      expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
        'financial_auth_token',
        'valid-jwt-token'
      );
    });

    test('should handle expired token', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      const mockSession = {
        getIdToken: () => ({
          getJwtToken: () => 'expired-jwt-token',
          payload: {
            sub: 'user-123',
            exp: Math.floor(Date.now() / 1000) - 3600 // 1 hour ago
          }
        })
      };

      Auth.currentSession = vi.fn().mockResolvedValue(mockSession);
      Auth.currentSession.mockRejectedValueOnce(new Error('Token expired'));

      const token = await authService.getAuthToken();

      expect(token).toBeNull();
      expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('financial_auth_token');
    });
  });

  describe('User Sign Out', () => {
    test('should sign out user successfully', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      Auth.signOut.mockResolvedValue();

      const result = await authService.signOut();

      expect(Auth.signOut).toHaveBeenCalled();
      expect(result.success).toBe(true);
      expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('financial_auth_token');
      expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('financial_user_data');
    });

    test('should handle sign out errors gracefully', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      Auth.signOut.mockRejectedValue(new Error('Sign out failed'));

      const result = await authService.signOut();

      // Should still clear local storage even if Cognito sign out fails
      expect(result.success).toBe(true);
      expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('financial_auth_token');
    });
  });

  describe('Password Management', () => {
    test('should initiate password reset', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      Auth.forgotPassword.mockResolvedValue({
        CodeDeliveryDetails: {
          Destination: 'test@example.com',
          DeliveryMedium: 'EMAIL',
          AttributeName: 'email'
        }
      });

      const result = await authService.forgotPassword('testuser');

      expect(Auth.forgotPassword).toHaveBeenCalledWith('testuser');
      expect(result.success).toBe(true);
      expect(result.codeDeliveryDetails.Destination).toBe('test@example.com');
    });

    test('should confirm password reset', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      Auth.forgotPasswordSubmit.mockResolvedValue();

      const result = await authService.confirmForgotPassword(
        'testuser',
        '123456',
        'NewPassword123!'
      );

      expect(Auth.forgotPasswordSubmit).toHaveBeenCalledWith(
        'testuser',
        '123456',
        'NewPassword123!'
      );
      expect(result.success).toBe(true);
    });

    test('should change password for authenticated user', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      const mockUser = { username: 'testuser' };
      Auth.getCurrentUser.mockResolvedValue(mockUser);
      Auth.changePassword.mockResolvedValue('SUCCESS');

      const result = await authService.changePassword(
        'OldPassword123!',
        'NewPassword123!'
      );

      expect(Auth.changePassword).toHaveBeenCalledWith(
        mockUser,
        'OldPassword123!',
        'NewPassword123!'
      );
      expect(result.success).toBe(true);
    });
  });

  describe('Token Validation', () => {
    test('should validate JWT token format', () => {
      const validTokens = [
        'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyLTEyMyJ9.signature',
        'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature'
      ];

      validTokens.forEach(token => {
        expect(authService.isValidTokenFormat(token)).toBe(true);
      });
    });

    test('should reject invalid JWT token formats', () => {
      const invalidTokens = [
        'invalid-token',
        'not.jwt.format',
        'too.many.parts.here.invalid',
        '',
        null,
        undefined
      ];

      invalidTokens.forEach(token => {
        expect(authService.isValidTokenFormat(token)).toBe(false);
      });
    });

    test('should check token expiration', () => {
      const futureTimestamp = Math.floor(Date.now() / 1000) + 3600; // 1 hour from now
      const pastTimestamp = Math.floor(Date.now() / 1000) - 3600;   // 1 hour ago

      expect(authService.isTokenExpired(futureTimestamp)).toBe(false);
      expect(authService.isTokenExpired(pastTimestamp)).toBe(true);
    });
  });

  describe('User Attributes Management', () => {
    test('should update user attributes', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      const mockUser = { username: 'testuser' };
      Auth.getCurrentUser.mockResolvedValue(mockUser);
      Auth.updateUserAttributes.mockResolvedValue('SUCCESS');

      const attributes = {
        name: 'Updated Name',
        email: 'updated@example.com'
      };

      const result = await authService.updateUserAttributes(attributes);

      expect(Auth.updateUserAttributes).toHaveBeenCalledWith(mockUser, attributes);
      expect(result.success).toBe(true);
    });

    test('should handle attribute update errors', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      Auth.getCurrentUser.mockRejectedValue(new Error('No authenticated user'));

      const result = await authService.updateUserAttributes({ name: 'Test' });

      expect(result.success).toBe(false);
      expect(result.error.message).toContain('No authenticated user');
    });
  });

  describe('Error Handling and Edge Cases', () => {
    test('should handle network errors gracefully', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      Auth.signIn.mockRejectedValue(new Error('NetworkError: Failed to fetch'));

      const result = await authService.signIn('testuser', 'password');

      expect(result.success).toBe(false);
      expect(result.error.message).toContain('network error');
      expect(result.error.retryable).toBe(true);
    });

    test('should sanitize error messages', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      Auth.signIn.mockRejectedValue({
        code: 'InternalErrorException',
        message: 'Internal server error at line 123 in /path/to/sensitive/file.js'
      });

      const result = await authService.signIn('testuser', 'password');

      expect(result.success).toBe(false);
      expect(result.error.message).not.toContain('/path/to/sensitive/file.js');
      expect(result.error.message).toContain('internal error');
    });

    test('should handle concurrent authentication requests', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      Auth.signIn.mockImplementation(() => 
        new Promise(resolve => setTimeout(resolve, 100))
      );

      const concurrentRequests = Array.from({ length: 3 }, () =>
        authService.signIn('testuser', 'password')
      );

      const results = await Promise.all(concurrentRequests);
      
      // Only one should succeed, others should be rejected or queued
      const successful = results.filter(r => r.success);
      expect(successful.length).toBeLessThanOrEqual(1);
    });

    test('should clear sensitive data on errors', async () => {
      const { Auth } = await import('@aws-amplify/auth');
      Auth.signIn.mockRejectedValue(new Error('Authentication failed'));

      await authService.signIn('testuser', 'password');

      expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('financial_auth_token');
    });
  });
});