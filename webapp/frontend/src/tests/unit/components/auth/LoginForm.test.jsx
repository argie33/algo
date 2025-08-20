/**
 * Unit Tests for LoginForm Component
 * Tests the authentication form functionality
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import LoginForm from '../../../../components/auth/LoginForm.jsx';

// Mock the auth context
const mockLogin = vi.fn();
const mockClearError = vi.fn();

const mockUseAuth = vi.fn(() => ({
  login: mockLogin,
  isLoading: false,
  error: null,
  clearError: mockClearError,
  user: null
}));

vi.mock('../../../../contexts/AuthContext.jsx', () => ({
  useAuth: mockUseAuth
}));

// Wrapper component for router context
const TestWrapper = ({ children }) => (
  <BrowserRouter>
    {children}
  </BrowserRouter>
);

describe('LoginForm Component', () => {
  
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Form Rendering', () => {
    it('should render login form with required fields', () => {
      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      expect(screen.getByRole('textbox', { name: /username|email/i })).toBeInTheDocument();
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /sign in|login/i })).toBeInTheDocument();
    });

    it('should have password visibility toggle', () => {
      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      const passwordField = screen.getByLabelText(/password/i);
      expect(passwordField).toHaveAttribute('type', 'password');

      const toggleButton = screen.getByRole('button', { name: /toggle password visibility/i });
      expect(toggleButton).toBeInTheDocument();
    });

    it('should render navigation links', () => {
      const mockOnSwitchToRegister = vi.fn();
      const mockOnSwitchToForgotPassword = vi.fn();

      render(
        <TestWrapper>
          <LoginForm 
            onSwitchToRegister={mockOnSwitchToRegister}
            onSwitchToForgotPassword={mockOnSwitchToForgotPassword}
          />
        </TestWrapper>
      );

      expect(screen.getByText(/register|sign up|create account/i)).toBeInTheDocument();
      expect(screen.getByText(/forgot password|reset password/i)).toBeInTheDocument();
    });
  });

  describe('Form Interactions', () => {
    it('should toggle password visibility when clicked', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      const passwordField = screen.getByLabelText(/password/i);
      const toggleButton = screen.getByRole('button', { name: /toggle password visibility/i });

      expect(passwordField).toHaveAttribute('type', 'password');

      await user.click(toggleButton);
      expect(passwordField).toHaveAttribute('type', 'text');

      await user.click(toggleButton);
      expect(passwordField).toHaveAttribute('type', 'password');
    });

    it('should clear errors when user starts typing', async () => {
      const user = userEvent.setup();

      // Mock auth context with error
      mockUseAuth.mockReturnValue({
        login: mockLogin,
        isLoading: false,
        error: 'Invalid credentials',
        clearError: mockClearError,
        user: null
      });

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      const usernameField = screen.getByRole('textbox', { name: /username|email/i });
      await user.type(usernameField, 'test');

      expect(mockClearError).toHaveBeenCalled();
    });

    it('should update form data when inputs change', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      const usernameField = screen.getByRole('textbox', { name: /username|email/i });
      const passwordField = screen.getByLabelText(/password/i);

      await user.type(usernameField, 'testuser@example.com');
      await user.type(passwordField, 'password123');

      expect(usernameField).toHaveValue('testuser@example.com');
      expect(passwordField).toHaveValue('password123');
    });
  });

  describe('Form Validation', () => {
    it('should require username and password', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      const submitButton = screen.getByRole('button', { name: /sign in|login/i });
      await user.click(submitButton);

      expect(screen.getByText(/please enter both username and password/i)).toBeInTheDocument();
      expect(mockLogin).not.toHaveBeenCalled();
    });

    it('should require username when only password provided', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      const passwordField = screen.getByLabelText(/password/i);
      const submitButton = screen.getByRole('button', { name: /sign in|login/i });

      await user.type(passwordField, 'password123');
      await user.click(submitButton);

      expect(screen.getByText(/please enter both username and password/i)).toBeInTheDocument();
      expect(mockLogin).not.toHaveBeenCalled();
    });

    it('should require password when only username provided', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      const usernameField = screen.getByRole('textbox', { name: /username|email/i });
      const submitButton = screen.getByRole('button', { name: /sign in|login/i });

      await user.type(usernameField, 'testuser@example.com');
      await user.click(submitButton);

      expect(screen.getByText(/please enter both username and password/i)).toBeInTheDocument();
      expect(mockLogin).not.toHaveBeenCalled();
    });
  });

  describe('Form Submission', () => {
    it('should call login with correct credentials', async () => {
      const user = userEvent.setup();
      mockLogin.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      const usernameField = screen.getByRole('textbox', { name: /username|email/i });
      const passwordField = screen.getByLabelText(/password/i);
      const submitButton = screen.getByRole('button', { name: /sign in|login/i });

      await user.type(usernameField, 'testuser@example.com');
      await user.type(passwordField, 'password123');
      await user.click(submitButton);

      expect(mockLogin).toHaveBeenCalledWith('testuser@example.com', 'password123');
    });

    it('should handle form submission via Enter key', async () => {
      const user = userEvent.setup();
      mockLogin.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      const usernameField = screen.getByRole('textbox', { name: /username|email/i });
      const passwordField = screen.getByLabelText(/password/i);

      await user.type(usernameField, 'testuser@example.com');
      await user.type(passwordField, 'password123');
      await user.keyboard('{Enter}');

      expect(mockLogin).toHaveBeenCalledWith('testuser@example.com', 'password123');
    });
  });

  describe('Loading States', () => {
    it('should show loading state during authentication', () => {
      // Mock loading state
      mockUseAuth.mockReturnValue({
        login: mockLogin,
        isLoading: true,
        error: null,
        clearError: mockClearError,
        user: null
      });

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      expect(screen.getByRole('progressbar')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /sign in|login/i })).toBeDisabled();
    });

    it('should disable form during loading', () => {
      // Mock loading state
      mockUseAuth.mockReturnValue({
        login: mockLogin,
        isLoading: true,
        error: null,
        clearError: mockClearError,
        user: null
      });

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      expect(screen.getByRole('textbox', { name: /username|email/i })).toBeDisabled();
      expect(screen.getByLabelText(/password/i)).toBeDisabled();
      expect(screen.getByRole('button', { name: /sign in|login/i })).toBeDisabled();
    });
  });

  describe('Error Handling', () => {
    it('should display authentication errors', () => {
      // Mock error state
      mockUseAuth.mockReturnValue({
        login: mockLogin,
        isLoading: false,
        error: 'Invalid username or password',
        clearError: mockClearError,
        user: null
      });

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      expect(screen.getByText('Invalid username or password')).toBeInTheDocument();
    });

    it('should display local validation errors', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      const submitButton = screen.getByRole('button', { name: /sign in|login/i });
      await user.click(submitButton);

      expect(screen.getByText(/please enter both username and password/i)).toBeInTheDocument();
    });
  });

  describe('Navigation Callbacks', () => {
    it('should call onSwitchToRegister when register link clicked', async () => {
      const user = userEvent.setup();
      const mockOnSwitchToRegister = vi.fn();

      render(
        <TestWrapper>
          <LoginForm onSwitchToRegister={mockOnSwitchToRegister} />
        </TestWrapper>
      );

      const registerLink = screen.getByText(/register|sign up|create account/i);
      await user.click(registerLink);

      expect(mockOnSwitchToRegister).toHaveBeenCalled();
    });

    it('should call onSwitchToForgotPassword when forgot password link clicked', async () => {
      const user = userEvent.setup();
      const mockOnSwitchToForgotPassword = vi.fn();

      render(
        <TestWrapper>
          <LoginForm onSwitchToForgotPassword={mockOnSwitchToForgotPassword} />
        </TestWrapper>
      );

      const forgotPasswordLink = screen.getByText(/forgot password|reset password/i);
      await user.click(forgotPasswordLink);

      expect(mockOnSwitchToForgotPassword).toHaveBeenCalled();
    });
  });

  describe('Accessibility', () => {
    it('should have proper ARIA labels and roles', () => {
      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      expect(screen.getByRole('form')).toBeInTheDocument();
      expect(screen.getByLabelText(/username|email/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    });

    it('should be keyboard navigable', async () => {
      const user = userEvent.setup();

      render(
        <TestWrapper>
          <LoginForm />
        </TestWrapper>
      );

      // Tab through form elements
      await user.tab();
      expect(screen.getByRole('textbox', { name: /username|email/i })).toHaveFocus();

      await user.tab();
      expect(screen.getByLabelText(/password/i)).toHaveFocus();

      await user.tab();
      expect(screen.getByRole('button', { name: /toggle password visibility/i })).toHaveFocus();

      await user.tab();
      expect(screen.getByRole('button', { name: /sign in|login/i })).toHaveFocus();
    });
  });
});