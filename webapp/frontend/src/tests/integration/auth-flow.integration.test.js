/**
 * Authentication Flow Integration Test
 * Critical: Validates complete auth flow for secure financial data access
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '../../contexts/AuthContext';
import LoginForm from '../../components/auth/LoginForm';
import Dashboard from '../../pages/Dashboard';
import { api } from '../../services/api';

// Mock AWS Amplify
vi.mock('aws-amplify', () => ({
  Amplify: {
    configure: vi.fn(),
  },
}));

vi.mock('@aws-amplify/auth', () => ({
  signIn: vi.fn(),
  signOut: vi.fn(),
  getCurrentUser: vi.fn(),
  fetchAuthSession: vi.fn(),
  confirmSignIn: vi.fn(),
}));

// Mock API service
vi.mock('../../services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    defaults: { headers: { common: {} } },
  },
  getApiConfig: vi.fn(() => ({
    baseURL: 'https://test-api.example.com',
    isConfigured: true,
  })),
}));

describe('Authentication Flow Integration', () => {
  let queryClient;
  let mockAuthService;

  const TestWrapper = ({ children }) => (
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          {children}
        </AuthProvider>
      </QueryClientProvider>
    </BrowserRouter>
  );

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    // Reset mocks
    vi.clearAllMocks();
    
    // Setup default mock implementations
    const { signIn, getCurrentUser, fetchAuthSession } = require('@aws-amplify/auth');
    
    mockAuthService = {
      signIn,
      getCurrentUser,
      fetchAuthSession,
    };

    // Mock localStorage
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: vi.fn(),
        setItem: vi.fn(),
        removeItem: vi.fn(),
        clear: vi.fn(),
      },
      writable: true,
    });
  });

  afterEach(() => {
    queryClient.clear();
    vi.restoreAllMocks();
  });

  describe('User Registration Flow', () => {
    it('should handle successful user registration', async () => {
      const { signUp } = require('@aws-amplify/auth');
      signUp.mockResolvedValueOnce({
        isSignUpComplete: false,
        nextStep: {
          signUpStep: 'CONFIRM_SIGN_UP',
        },
        userId: 'test-user-123',
      });

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      // Switch to register mode
      const registerButton = screen.getByText(/sign up/i);
      fireEvent.click(registerButton);

      // Fill registration form
      const emailInput = screen.getByLabelText(/email/i);
      const passwordInput = screen.getByLabelText(/password/i);
      const submitButton = screen.getByRole('button', { name: /create account/i });

      fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
      fireEvent.change(passwordInput, { target: { value: 'Test123!@#' } });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(signUp).toHaveBeenCalledWith({
          username: 'test@example.com',
          password: 'Test123!@#',
          attributes: {
            email: 'test@example.com',
          },
        });
      });

      // Should show confirmation step
      expect(screen.getByText(/verification code/i)).toBeInTheDocument();
    });

    it('should handle registration validation errors', async () => {
      const { signUp } = require('@aws-amplify/auth');
      signUp.mockRejectedValueOnce({
        name: 'InvalidPasswordException',
        message: 'Password must be at least 8 characters',
      });

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      // Switch to register mode and fill form
      const registerButton = screen.getByText(/sign up/i);
      fireEvent.click(registerButton);

      const emailInput = screen.getByLabelText(/email/i);
      const passwordInput = screen.getByLabelText(/password/i);
      const submitButton = screen.getByRole('button', { name: /create account/i });

      fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
      fireEvent.change(passwordInput, { target: { value: 'weak' } });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/password must be at least 8 characters/i)).toBeInTheDocument();
      });
    });
  });

  describe('User Login Flow', () => {
    it('should handle successful login with MFA', async () => {
      // Mock successful login requiring MFA
      mockAuthService.signIn.mockResolvedValueOnce({
        isSignedIn: false,
        nextStep: {
          signInStep: 'CONFIRM_SIGN_IN_WITH_TOTP_CODE',
        },
      });

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      const emailInput = screen.getByLabelText(/email/i);
      const passwordInput = screen.getByLabelText(/password/i);
      const loginButton = screen.getByRole('button', { name: /sign in/i });

      fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
      fireEvent.change(passwordInput, { target: { value: 'Test123!@#' } });
      fireEvent.click(loginButton);

      await waitFor(() => {
        expect(mockAuthService.signIn).toHaveBeenCalledWith({
          username: 'test@example.com',
          password: 'Test123!@#',
        });
      });

      // Should show MFA challenge
      expect(screen.getByText(/enter.*code/i)).toBeInTheDocument();
    });

    it('should complete login flow and redirect to dashboard', async () => {
      // Mock successful complete login
      mockAuthService.signIn.mockResolvedValueOnce({
        isSignedIn: true,
        nextStep: {
          signInStep: 'DONE',
        },
      });

      mockAuthService.getCurrentUser.mockResolvedValueOnce({
        username: 'test@example.com',
        userId: 'test-user-123',
        attributes: {
          email: 'test@example.com',
        },
      });

      mockAuthService.fetchAuthSession.mockResolvedValueOnce({
        tokens: {
          accessToken: {
            toString: () => 'mock-access-token',
          },
          idToken: {
            toString: () => 'mock-id-token',
            payload: {
              'cognito:username': 'test@example.com',
              sub: 'test-user-123',
            },
          },
        },
      });

      // Mock API health check
      api.get.mockResolvedValueOnce({
        data: { status: 'healthy', healthy: true },
      });

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      const emailInput = screen.getByLabelText(/email/i);
      const passwordInput = screen.getByLabelText(/password/i);
      const loginButton = screen.getByRole('button', { name: /sign in/i });

      fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
      fireEvent.change(passwordInput, { target: { value: 'Test123!@#' } });
      fireEvent.click(loginButton);

      await waitFor(() => {
        expect(mockAuthService.signIn).toHaveBeenCalled();
        expect(mockAuthService.getCurrentUser).toHaveBeenCalled();
        expect(mockAuthService.fetchAuthSession).toHaveBeenCalled();
      });
    });

    it('should handle login failure gracefully', async () => {
      mockAuthService.signIn.mockRejectedValueOnce({
        name: 'NotAuthorizedException',
        message: 'Incorrect username or password.',
      });

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      const emailInput = screen.getByLabelText(/email/i);
      const passwordInput = screen.getByLabelText(/password/i);
      const loginButton = screen.getByRole('button', { name: /sign in/i });

      fireEvent.change(emailInput, { target: { value: 'wrong@example.com' } });
      fireEvent.change(passwordInput, { target: { value: 'wrongpassword' } });
      fireEvent.click(loginButton);

      await waitFor(() => {
        expect(screen.getByText(/incorrect username or password/i)).toBeInTheDocument();
      });
    });
  });

  describe('Session Management', () => {
    it('should persist authentication state across page refreshes', async () => {
      // Mock existing session
      mockAuthService.getCurrentUser.mockResolvedValueOnce({
        username: 'test@example.com',
        userId: 'test-user-123',
      });

      mockAuthService.fetchAuthSession.mockResolvedValueOnce({
        tokens: {
          accessToken: {
            toString: () => 'mock-access-token',
          },
          idToken: {
            toString: () => 'mock-id-token',
            payload: {
              'cognito:username': 'test@example.com',
              sub: 'test-user-123',
            },
          },
        },
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockAuthService.getCurrentUser).toHaveBeenCalled();
        expect(mockAuthService.fetchAuthSession).toHaveBeenCalled();
      });
    });

    it('should handle token refresh automatically', async () => {
      // Mock token refresh scenario
      mockAuthService.fetchAuthSession
        .mockResolvedValueOnce({
          tokens: {
            accessToken: {
              toString: () => 'expired-token',
            },
          },
        })
        .mockResolvedValueOnce({
          tokens: {
            accessToken: {
              toString: () => 'new-fresh-token',
            },
          },
        });

      api.get.mockRejectedValueOnce({ status: 401 })
           .mockResolvedValueOnce({ data: { status: 'healthy' } });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockAuthService.fetchAuthSession).toHaveBeenCalledTimes(2);
      });
    });

    it('should handle session expiration and redirect to login', async () => {
      mockAuthService.getCurrentUser.mockRejectedValueOnce({
        name: 'UserUnAuthenticatedException',
      });

      mockAuthService.fetchAuthSession.mockRejectedValueOnce({
        name: 'UserUnAuthenticatedException',
      });

      const { location } = window;
      delete window.location;
      window.location = { href: '', replace: vi.fn() };

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockAuthService.getCurrentUser).toHaveBeenCalled();
        // Should redirect to login or show login form
      });

      window.location = location;
    });
  });

  describe('API Integration with Authentication', () => {
    it('should set authorization headers after successful login', async () => {
      mockAuthService.fetchAuthSession.mockResolvedValueOnce({
        tokens: {
          accessToken: {
            toString: () => 'mock-access-token-12345',
          },
        },
      });

      // Mock API call that requires authentication
      api.get.mockResolvedValueOnce({
        data: { portfolioValue: 50000 },
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(api.defaults.headers.common.Authorization).toBe('Bearer mock-access-token-12345');
      });
    });

    it('should handle API authentication failures', async () => {
      api.get.mockRejectedValueOnce({
        response: { status: 401, data: { error: 'Unauthorized' } },
      });

      mockAuthService.signOut = vi.fn();

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should handle 401 by refreshing token or signing out
        expect(api.get).toHaveBeenCalled();
      });
    });
  });

  describe('Logout Flow', () => {
    it('should clear authentication state on logout', async () => {
      const { signOut } = require('@aws-amplify/auth');
      signOut.mockResolvedValueOnce();

      // Mock authenticated state first
      mockAuthService.getCurrentUser.mockResolvedValueOnce({
        username: 'test@example.com',
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Find and click logout button
      const logoutButton = screen.getByRole('button', { name: /logout|sign out/i });
      fireEvent.click(logoutButton);

      await waitFor(() => {
        expect(signOut).toHaveBeenCalled();
        expect(window.localStorage.clear).toHaveBeenCalled();
      });
    });

    it('should remove API authorization headers on logout', async () => {
      const { signOut } = require('@aws-amplify/auth');
      signOut.mockResolvedValueOnce();

      // Set initial auth header
      api.defaults.headers.common.Authorization = 'Bearer test-token';

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      const logoutButton = screen.getByRole('button', { name: /logout|sign out/i });
      fireEvent.click(logoutButton);

      await waitFor(() => {
        expect(api.defaults.headers.common.Authorization).toBeUndefined();
      });
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('should handle network errors during authentication', async () => {
      mockAuthService.signIn.mockRejectedValueOnce({
        name: 'NetworkError',
        message: 'Network request failed',
      });

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      const emailInput = screen.getByLabelText(/email/i);
      const passwordInput = screen.getByLabelText(/password/i);
      const loginButton = screen.getByRole('button', { name: /sign in/i });

      fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
      fireEvent.change(passwordInput, { target: { value: 'Test123!@#' } });
      fireEvent.click(loginButton);

      await waitFor(() => {
        expect(screen.getByText(/network.*error|connection.*failed/i)).toBeInTheDocument();
      });
    });

    it('should handle concurrent authentication requests', async () => {
      let resolveFirst, resolveSecond;
      const firstPromise = new Promise(resolve => { resolveFirst = resolve; });
      const secondPromise = new Promise(resolve => { resolveSecond = resolve; });

      mockAuthService.signIn
        .mockReturnValueOnce(firstPromise)
        .mockReturnValueOnce(secondPromise);

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      const emailInput = screen.getByLabelText(/email/i);
      const passwordInput = screen.getByLabelText(/password/i);
      const loginButton = screen.getByRole('button', { name: /sign in/i });

      fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
      fireEvent.change(passwordInput, { target: { value: 'Test123!@#' } });
      
      // Trigger two rapid login attempts
      fireEvent.click(loginButton);
      fireEvent.click(loginButton);

      // Resolve first request
      resolveFirst({ isSignedIn: true });
      
      await waitFor(() => {
        expect(mockAuthService.signIn).toHaveBeenCalledTimes(1); // Second call should be prevented
      });
    });
  });
});