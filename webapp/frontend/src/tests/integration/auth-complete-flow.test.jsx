import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { BrowserRouter } from 'react-router-dom';
import App from '../../App';
import { AuthContext } from '../../contexts/AuthContext';

// Mock AWS Amplify
vi.mock('@aws-amplify/auth', () => ({
  signIn: vi.fn(),
  signUp: vi.fn(),
  confirmSignUp: vi.fn(),
  signOut: vi.fn(),
  getCurrentUser: vi.fn(),
  fetchAuthSession: vi.fn(),
  resendSignUpCode: vi.fn(),
  forgotPassword: vi.fn(),
  forgotPasswordSubmit: vi.fn(),
}));

vi.mock('../../services/api', () => ({
  default: {
    setAuthTokens: vi.fn(),
    clearAuthTokens: vi.fn(),
    testConnection: vi.fn(() => Promise.resolve({ success: true })),
  }
}));

const renderApp = () => {
  return render(
    <BrowserRouter>
      <App />
    </BrowserRouter>
  );
};

describe('Complete Authentication Flow Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  describe('User Registration Flow', () => {
    test('should complete full registration process', async () => {
      const user = userEvent.setup();
      const { signUp, confirmSignUp } = await import('@aws-amplify/auth');
      
      signUp.mockResolvedValue({
        nextStep: {
          signUpStep: 'CONFIRM_SIGN_UP',
          codeDeliveryDetails: {
            deliveryMedium: 'EMAIL',
            destination: 'test@example.com'
          }
        }
      });

      confirmSignUp.mockResolvedValue({
        nextStep: { signUpStep: 'DONE' }
      });

      renderApp();

      // Navigate to registration
      const registerLink = screen.getByText('Sign Up');
      await user.click(registerLink);

      // Fill registration form
      await user.type(screen.getByLabelText('Email'), 'test@example.com');
      await user.type(screen.getByLabelText('Password'), 'TestPassword123!');
      await user.type(screen.getByLabelText('Confirm Password'), 'TestPassword123!');
      await user.type(screen.getByLabelText('First Name'), 'John');
      await user.type(screen.getByLabelText('Last Name'), 'Doe');

      // Submit registration
      const submitButton = screen.getByRole('button', { name: 'Create Account' });
      await user.click(submitButton);

      // Wait for confirmation step
      await waitFor(() => {
        expect(screen.getByText('Confirm Your Email')).toBeInTheDocument();
      });

      // Enter confirmation code
      await user.type(screen.getByLabelText('Confirmation Code'), '123456');
      const confirmButton = screen.getByRole('button', { name: 'Confirm' });
      await user.click(confirmButton);

      // Should redirect to login
      await waitFor(() => {
        expect(screen.getByText('Account confirmed! Please sign in.')).toBeInTheDocument();
      });

      expect(signUp).toHaveBeenCalledWith({
        username: 'test@example.com',
        password: 'TestPassword123!',
        options: {
          userAttributes: {
            email: 'test@example.com',
            given_name: 'John',
            family_name: 'Doe'
          }
        }
      });

      expect(confirmSignUp).toHaveBeenCalledWith({
        username: 'test@example.com',
        confirmationCode: '123456'
      });
    });

    test('should handle registration errors', async () => {
      const user = userEvent.setup();
      const { signUp } = await import('@aws-amplify/auth');
      
      signUp.mockRejectedValue({
        name: 'UsernameExistsException',
        message: 'An account with the given email already exists.'
      });

      renderApp();

      const registerLink = screen.getByText('Sign Up');
      await user.click(registerLink);

      await user.type(screen.getByLabelText('Email'), 'existing@example.com');
      await user.type(screen.getByLabelText('Password'), 'TestPassword123!');
      await user.type(screen.getByLabelText('Confirm Password'), 'TestPassword123!');

      const submitButton = screen.getByRole('button', { name: 'Create Account' });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText('An account with the given email already exists.')).toBeInTheDocument();
      });
    });
  });

  describe('User Login Flow', () => {
    test('should complete successful login', async () => {
      const user = userEvent.setup();
      const { signIn, getCurrentUser, fetchAuthSession } = await import('@aws-amplify/auth');
      const api = await import('../../services/api');
      
      signIn.mockResolvedValue({
        nextStep: { signInStep: 'DONE' }
      });

      getCurrentUser.mockResolvedValue({
        userId: 'test-user-id',
        username: 'test@example.com'
      });

      fetchAuthSession.mockResolvedValue({
        tokens: {
          idToken: { toString: () => 'mock-id-token' },
          accessToken: { toString: () => 'mock-access-token' }
        }
      });

      renderApp();

      // Fill login form
      await user.type(screen.getByLabelText('Email'), 'test@example.com');
      await user.type(screen.getByLabelText('Password'), 'TestPassword123!');

      const signInButton = screen.getByRole('button', { name: 'Sign In' });
      await user.click(signInButton);

      // Should redirect to dashboard
      await waitFor(() => {
        expect(screen.getByText('Dashboard')).toBeInTheDocument();
      });

      expect(signIn).toHaveBeenCalledWith({
        username: 'test@example.com',
        password: 'TestPassword123!'
      });

      expect(api.default.setAuthTokens).toHaveBeenCalledWith({
        idToken: 'mock-id-token',
        accessToken: 'mock-access-token'
      });
    });

    test('should handle MFA challenge', async () => {
      const user = userEvent.setup();
      const { signIn, confirmSignIn } = await import('@aws-amplify/auth');
      
      signIn.mockResolvedValue({
        nextStep: {
          signInStep: 'CONFIRM_SIGN_IN_WITH_TOTP_CODE',
          codeDeliveryDetails: {
            deliveryMedium: 'SMS',
            destination: '+1****1234'
          }
        }
      });

      confirmSignIn.mockResolvedValue({
        nextStep: { signInStep: 'DONE' }
      });

      renderApp();

      await user.type(screen.getByLabelText('Email'), 'test@example.com');
      await user.type(screen.getByLabelText('Password'), 'TestPassword123!');

      const signInButton = screen.getByRole('button', { name: 'Sign In' });
      await user.click(signInButton);

      // Should show MFA challenge
      await waitFor(() => {
        expect(screen.getByText('Multi-Factor Authentication')).toBeInTheDocument();
        expect(screen.getByText('Enter the 6-digit code from your authenticator app')).toBeInTheDocument();
      });

      await user.type(screen.getByLabelText('Authentication Code'), '123456');
      const confirmButton = screen.getByRole('button', { name: 'Verify' });
      await user.click(confirmButton);

      await waitFor(() => {
        expect(screen.getByText('Dashboard')).toBeInTheDocument();
      });

      expect(confirmSignIn).toHaveBeenCalledWith({ challengeResponse: '123456' });
    });

    test('should handle login errors', async () => {
      const user = userEvent.setup();
      const { signIn } = await import('@aws-amplify/auth');
      
      signIn.mockRejectedValue({
        name: 'NotAuthorizedException',
        message: 'Incorrect username or password.'
      });

      renderApp();

      await user.type(screen.getByLabelText('Email'), 'test@example.com');
      await user.type(screen.getByLabelText('Password'), 'WrongPassword');

      const signInButton = screen.getByRole('button', { name: 'Sign In' });
      await user.click(signInButton);

      await waitFor(() => {
        expect(screen.getByText('Incorrect username or password.')).toBeInTheDocument();
      });
    });
  });

  describe('Password Reset Flow', () => {
    test('should complete password reset process', async () => {
      const user = userEvent.setup();
      const { forgotPassword, forgotPasswordSubmit } = await import('@aws-amplify/auth');
      
      forgotPassword.mockResolvedValue({
        nextStep: {
          resetPasswordStep: 'CONFIRM_RESET_PASSWORD_WITH_CODE',
          codeDeliveryDetails: {
            deliveryMedium: 'EMAIL',
            destination: 'test@example.com'
          }
        }
      });

      forgotPasswordSubmit.mockResolvedValue({
        nextStep: { resetPasswordStep: 'DONE' }
      });

      renderApp();

      // Navigate to forgot password
      const forgotPasswordLink = screen.getByText('Forgot Password?');
      await user.click(forgotPasswordLink);

      // Enter email
      await user.type(screen.getByLabelText('Email'), 'test@example.com');
      const sendCodeButton = screen.getByRole('button', { name: 'Send Reset Code' });
      await user.click(sendCodeButton);

      // Wait for confirmation step
      await waitFor(() => {
        expect(screen.getByText('Reset Your Password')).toBeInTheDocument();
      });

      // Enter confirmation code and new password
      await user.type(screen.getByLabelText('Confirmation Code'), '123456');
      await user.type(screen.getByLabelText('New Password'), 'NewPassword123!');
      await user.type(screen.getByLabelText('Confirm New Password'), 'NewPassword123!');

      const resetButton = screen.getByRole('button', { name: 'Reset Password' });
      await user.click(resetButton);

      // Should redirect to login with success message
      await waitFor(() => {
        expect(screen.getByText('Password reset successful! Please sign in with your new password.')).toBeInTheDocument();
      });

      expect(forgotPassword).toHaveBeenCalledWith({ username: 'test@example.com' });
      expect(forgotPasswordSubmit).toHaveBeenCalledWith({
        username: 'test@example.com',
        confirmationCode: '123456',
        newPassword: 'NewPassword123!'
      });
    });
  });

  describe('Session Management', () => {
    test('should handle session expiration', async () => {
      const _user = userEvent.setup();
      const { getCurrentUser, fetchAuthSession } = await import('@aws-amplify/auth');
      
      // Mock initial authentication
      getCurrentUser.mockResolvedValue({
        userId: 'test-user-id',
        username: 'test@example.com'
      });

      fetchAuthSession.mockResolvedValue({
        tokens: {
          idToken: { toString: () => 'expired-token' },
          accessToken: { toString: () => 'expired-token' }
        }
      });

      renderApp();

      // Simulate session expiration
      setTimeout(() => {
        fetchAuthSession.mockRejectedValue({
          name: 'NotAuthorizedException',
          message: 'Access Token has expired'
        });
      }, 100);

      await waitFor(() => {
        expect(screen.getByText('Your session has expired. Please sign in again.')).toBeInTheDocument();
      });
    });

    test('should auto-refresh tokens', async () => {
      const { getCurrentUser, fetchAuthSession } = await import('@aws-amplify/auth');
      
      getCurrentUser.mockResolvedValue({
        userId: 'test-user-id',
        username: 'test@example.com'
      });

      let callCount = 0;
      fetchAuthSession.mockImplementation(() => {
        callCount++;
        return Promise.resolve({
          tokens: {
            idToken: { toString: () => `id-token-${callCount}` },
            accessToken: { toString: () => `access-token-${callCount}` }
          }
        });
      });

      renderApp();

      // Fast forward to trigger token refresh
      vi.advanceTimersByTime(15 * 60 * 1000); // 15 minutes

      await waitFor(() => {
        expect(fetchAuthSession).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe('Logout Flow', () => {
    test('should complete logout process', async () => {
      const user = userEvent.setup();
      const { signOut } = await import('@aws-amplify/auth');
      const api = await import('../../services/api');
      
      signOut.mockResolvedValue({});

      // Start with authenticated state
      const mockAuthContext = {
        user: { id: 'test-user', email: 'test@example.com' },
        isAuthenticated: true,
        logout: vi.fn()
      };

      render(
        <BrowserRouter>
          <AuthContext.Provider value={mockAuthContext}>
            <App />
          </AuthContext.Provider>
        </BrowserRouter>
      );

      // Click logout
      const logoutButton = screen.getByLabelText('Sign out');
      await user.click(logoutButton);

      await waitFor(() => {
        expect(signOut).toHaveBeenCalled();
        expect(api.default.clearAuthTokens).toHaveBeenCalled();
        expect(screen.getByText('Sign In')).toBeInTheDocument();
      });
    });

    test('should clear local storage on logout', async () => {
      const user = userEvent.setup();
      const { signOut } = await import('@aws-amplify/auth');
      
      // Set some data in local storage
      localStorage.setItem('portfolioData', JSON.stringify({}));
      localStorage.setItem('userPreferences', JSON.stringify({}));

      signOut.mockResolvedValue({});

      const mockAuthContext = {
        user: { id: 'test-user', email: 'test@example.com' },
        isAuthenticated: true,
        logout: vi.fn()
      };

      render(
        <BrowserRouter>
          <AuthContext.Provider value={mockAuthContext}>
            <App />
          </AuthContext.Provider>
        </BrowserRouter>
      );

      const logoutButton = screen.getByLabelText('Sign out');
      await user.click(logoutButton);

      await waitFor(() => {
        expect(localStorage.getItem('portfolioData')).toBeNull();
        expect(localStorage.getItem('userPreferences')).toBeNull();
      });
    });
  });

  describe('Protected Routes', () => {
    test('should redirect unauthenticated users to login', () => {
      window.history.pushState({}, 'Portfolio', '/portfolio');
      
      renderApp();

      expect(screen.getByText('Sign In')).toBeInTheDocument();
      expect(screen.queryByText('Portfolio')).not.toBeInTheDocument();
    });

    test('should preserve redirect URL after login', async () => {
      const user = userEvent.setup();
      const { signIn, getCurrentUser, fetchAuthSession } = await import('@aws-amplify/auth');
      
      // Start at protected route
      window.history.pushState({}, 'Portfolio', '/portfolio');
      
      signIn.mockResolvedValue({ nextStep: { signInStep: 'DONE' } });
      getCurrentUser.mockResolvedValue({ userId: 'test-user-id' });
      fetchAuthSession.mockResolvedValue({
        tokens: {
          idToken: { toString: () => 'token' },
          accessToken: { toString: () => 'token' }
        }
      });

      renderApp();

      // Should show login form
      expect(screen.getByText('Sign In')).toBeInTheDocument();

      // Complete login
      await user.type(screen.getByLabelText('Email'), 'test@example.com');
      await user.type(screen.getByLabelText('Password'), 'password');
      await user.click(screen.getByRole('button', { name: 'Sign In' }));

      // Should redirect to original destination
      await waitFor(() => {
        expect(window.location.pathname).toBe('/portfolio');
      });
    });
  });

  describe('Error Boundaries', () => {
    test('should catch authentication errors and show fallback UI', async () => {
      const { getCurrentUser } = await import('@aws-amplify/auth');
      
      getCurrentUser.mockRejectedValue(new Error('Authentication service unavailable'));

      renderApp();

      await waitFor(() => {
        expect(screen.getByText(/authentication error/i)).toBeInTheDocument();
        expect(screen.getByText('Try Again')).toBeInTheDocument();
      });
    });

    test('should allow recovery from authentication errors', async () => {
      const user = userEvent.setup();
      const { getCurrentUser } = await import('@aws-amplify/auth');
      
      getCurrentUser
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValue({ userId: 'test-user-id' });

      renderApp();

      await waitFor(() => {
        const tryAgainButton = screen.getByText('Try Again');
        expect(tryAgainButton).toBeInTheDocument();
      });

      const tryAgainButton = screen.getByText('Try Again');
      await user.click(tryAgainButton);

      await waitFor(() => {
        expect(screen.getByText('Dashboard')).toBeInTheDocument();
      });
    });
  });
});