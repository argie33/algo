/**
 * Authentication Components Unit Tests
 * Comprehensive testing of all real authentication components
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Real Auth Components - Import actual production components  
import { LoginForm } from '../../../components/auth/LoginForm';
import { SignupForm } from '../../../components/auth/SignupForm';
import { TwoFactorAuth } from '../../../components/auth/TwoFactorAuth';

describe('🔐 Authentication Components', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('LoginForm Component', () => {
    it('should render login form correctly', () => {
      render(<LoginForm />);

      expect(screen.getByText('Sign In')).toBeInTheDocument();
      expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    });

    it('should handle form submission', async () => {
      const user = userEvent.setup();
      const onSubmit = vi.fn();

      render(<LoginForm onSubmit={onSubmit} />);

      const emailInput = screen.getByLabelText(/email/i);
      const passwordInput = screen.getByLabelText(/password/i);
      const submitButton = screen.getByRole('button', { name: /sign in/i });

      await user.type(emailInput, 'test@example.com');
      await user.type(passwordInput, 'password123');
      await user.click(submitButton);

      expect(onSubmit).toHaveBeenCalledWith({
        email: 'test@example.com',
        password: 'password123'
      });
    });

    it('should validate email format', async () => {
      const user = userEvent.setup();

      render(<LoginForm />);

      const emailInput = screen.getByLabelText(/email/i);
      const submitButton = screen.getByRole('button', { name: /sign in/i });

      await user.type(emailInput, 'invalid-email');
      await user.click(submitButton);

      expect(screen.getByText(/invalid email format/i)).toBeInTheDocument();
    });
  });

  describe('SignupForm Component', () => {
    it('should render signup form correctly', () => {
      render(<SignupForm />);

      expect(screen.getByText('Create Account')).toBeInTheDocument();
      expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/^password/i)).toBeInTheDocument();
    });

    it('should validate password confirmation', async () => {
      const user = userEvent.setup();

      render(<SignupForm />);

      const passwordInput = screen.getByLabelText(/^password/i);
      const confirmPasswordInput = screen.getByLabelText(/confirm password/i);
      const submitButton = screen.getByRole('button', { name: /create account/i });

      await user.type(passwordInput, 'password123');
      await user.type(confirmPasswordInput, 'differentpassword');
      await user.click(submitButton);

      expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
    });
  });

  describe('TwoFactorAuth Component', () => {
    it('should render 2FA verification form correctly', () => {
      render(<TwoFactorAuth method="authenticator" />);

      expect(screen.getByText('Two-Factor Authentication')).toBeInTheDocument();
      expect(screen.getByLabelText(/verification code/i)).toBeInTheDocument();
    });

    it('should handle verification code input', async () => {
      const user = userEvent.setup();
      const onVerify = vi.fn();

      render(<TwoFactorAuth method="authenticator" onVerify={onVerify} />);

      const codeInput = screen.getByLabelText(/verification code/i);
      const verifyButton = screen.getByRole('button', { name: /verify/i });

      await user.type(codeInput, '123456');
      await user.click(verifyButton);

      expect(onVerify).toHaveBeenCalledWith({
        code: '123456',
        method: 'authenticator'
      });
    });
  });
});