import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import ForgotPasswordForm from '../../../../components/auth/ForgotPasswordForm';

// Mock AuthContext
const mockForgotPassword = vi.fn();

vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    forgotPassword: mockForgotPassword,
    isLoading: false,
    error: ''
  })
}));

describe('ForgotPasswordForm', () => {
  const defaultProps = {
    onForgotPasswordSuccess: vi.fn(),
    onSwitchToLogin: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockForgotPassword.mockResolvedValue({ success: true });
  });

  test('renders forgot password form', () => {
    render(<ForgotPasswordForm {...defaultProps} />);
    
    expect(screen.getByText('Reset Password')).toBeInTheDocument();
    expect(screen.getByLabelText(/username or email/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send reset code/i })).toBeInTheDocument();
  });

  test('submits username for password reset', async () => {
    render(<ForgotPasswordForm {...defaultProps} />);
    
    const usernameInput = screen.getByLabelText(/username or email/i);
    fireEvent.change(usernameInput, { target: { value: 'testuser' } });
    
    const submitButton = screen.getByRole('button', { name: /send reset code/i });
    fireEvent.click(submitButton);
    
    await waitFor(() => {
      expect(mockForgotPassword).toHaveBeenCalledWith('testuser');
    });
  });

  test('calls onForgotPasswordSuccess on success', async () => {
    const onForgotPasswordSuccess = vi.fn();
    render(<ForgotPasswordForm {...defaultProps} onForgotPasswordSuccess={onForgotPasswordSuccess} />);
    
    const usernameInput = screen.getByLabelText(/username or email/i);
    fireEvent.change(usernameInput, { target: { value: 'testuser' } });
    
    const submitButton = screen.getByRole('button', { name: /send reset code/i });
    fireEvent.click(submitButton);
    
    await waitFor(() => {
      expect(onForgotPasswordSuccess).toHaveBeenCalledWith('testuser');
    });
  });

  test('shows validation error for empty username', async () => {
    render(<ForgotPasswordForm {...defaultProps} />);
    
    const submitButton = screen.getByRole('button', { name: /send reset code/i });
    fireEvent.click(submitButton);
    
    await waitFor(() => {
      expect(screen.getByText(/please enter your username/i)).toBeInTheDocument();
    });
  });

  test('switches back to login', () => {
    const onSwitchToLogin = vi.fn();
    render(<ForgotPasswordForm {...defaultProps} onSwitchToLogin={onSwitchToLogin} />);
    
    const backButton = screen.getByText(/back to sign in/i);
    fireEvent.click(backButton);
    
    expect(onSwitchToLogin).toHaveBeenCalled();
  });
});