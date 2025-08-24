import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect } from 'vitest';
import { renderWithTheme } from '../test-helpers/component-test-utils';
import ForgotPasswordForm from '../../../../components/auth/ForgotPasswordForm';

describe('ForgotPasswordForm Component', () => {
  const defaultProps = {
    onBack: vi.fn(),
  };

  describe('Form Rendering', () => {
    it('renders form with email input', () => {
      renderWithTheme(<ForgotPasswordForm {...defaultProps} />);
      
      expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /send reset email/i })).toBeInTheDocument();
    });

    it('displays form title and instructions', () => {
      renderWithTheme(<ForgotPasswordForm {...defaultProps} />);
      
      expect(screen.getByText(/reset password/i)).toBeInTheDocument();
      expect(screen.getByText(/enter your email address and we'll send you a password reset link/i)).toBeInTheDocument();
    });

    it('includes back to sign in button', () => {
      renderWithTheme(<ForgotPasswordForm {...defaultProps} />);
      
      expect(screen.getByRole('button', { name: /back to sign in/i })).toBeInTheDocument();
    });
  });

  describe('Form Interaction', () => {
    it('disables submit button when email is empty', () => {
      renderWithTheme(<ForgotPasswordForm {...defaultProps} />);
      
      const submitButton = screen.getByRole('button', { name: /send reset email/i });
      expect(submitButton).toBeDisabled();
    });

    it('enables submit button when email is entered', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm {...defaultProps} />);
      
      const emailInput = screen.getByLabelText(/email address/i);
      const submitButton = screen.getByRole('button', { name: /send reset email/i });
      
      await user.type(emailInput, 'test@example.com');
      
      expect(submitButton).not.toBeDisabled();
    });

    it('shows loading state during submission', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm {...defaultProps} />);
      
      const emailInput = screen.getByLabelText(/email address/i);
      await user.type(emailInput, 'test@example.com');
      
      const submitButton = screen.getByRole('button', { name: /send reset email/i });
      await user.click(submitButton);
      
      expect(screen.getByText(/sending/i)).toBeInTheDocument();
    });

    it('shows success message after submission', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm {...defaultProps} />);
      
      const emailInput = screen.getByLabelText(/email address/i);
      await user.type(emailInput, 'test@example.com');
      
      const submitButton = screen.getByRole('button', { name: /send reset email/i });
      await user.click(submitButton);
      
      await waitFor(() => {
        expect(screen.getByText(/password reset email sent! check your inbox/i)).toBeInTheDocument();
      });
    });

    it('calls onBack when back button is clicked', async () => {
      const user = userEvent.setup();
      const mockOnBack = vi.fn();
      renderWithTheme(<ForgotPasswordForm onBack={mockOnBack} />);
      
      const backButton = screen.getByRole('button', { name: /back to sign in/i });
      await user.click(backButton);
      
      expect(mockOnBack).toHaveBeenCalled();
    });
  });

  describe('Email Input', () => {
    it('accepts valid email format', async () => {
      const user = userEvent.setup();
      renderWithTheme(<ForgotPasswordForm {...defaultProps} />);
      
      const emailInput = screen.getByLabelText(/email address/i);
      await user.type(emailInput, 'valid@example.com');
      
      expect(emailInput).toHaveValue('valid@example.com');
    });

    it('has correct input attributes', () => {
      renderWithTheme(<ForgotPasswordForm {...defaultProps} />);
      
      const emailInput = screen.getByLabelText(/email address/i);
      expect(emailInput).toHaveAttribute('type', 'email');
      expect(emailInput).toHaveAttribute('required');
      expect(emailInput).toHaveAttribute('autoComplete', 'email');
    });
  });

  describe('Form Elements', () => {
    it('has proper form structure', () => {
      renderWithTheme(<ForgotPasswordForm {...defaultProps} />);
      
      expect(screen.getByRole('textbox', { name: /email address/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /send reset email/i })).toHaveAttribute('type', 'submit');
      expect(screen.getByRole('button', { name: /back to sign in/i })).toHaveAttribute('type', 'button');
    });

    it('renders within a Paper component', () => {
      const { container } = renderWithTheme(<ForgotPasswordForm {...defaultProps} />);
      
      expect(container.querySelector('.MuiPaper-root')).toBeInTheDocument();
    });
  });
});