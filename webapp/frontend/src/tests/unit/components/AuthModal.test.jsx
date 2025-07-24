import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { vi } from 'vitest';
import AuthModal from '../../../components/auth/AuthModal';
import { useAuth } from '../../../contexts/AuthContext';

// Mock the auth context
vi.mock('../../../contexts/AuthContext');

// Mock child components
vi.mock('../../../components/auth/LoginForm', () => ({
  default: function MockLoginForm({ onSwitchToRegister, onSwitchToForgotPassword }) {
    return (
      <div data-testid="login-form">
        <button onClick={onSwitchToRegister}>Switch to Register</button>
        <button onClick={onSwitchToForgotPassword}>Forgot Password</button>
      </div>
    );
  }
}));

vi.mock('../../../components/auth/RegisterForm', () => ({
  default: function MockRegisterForm({ onSwitchToLogin }) {
    return (
      <div data-testid="register-form">
        <button onClick={onSwitchToLogin}>Switch to Login</button>
      </div>
    );
  }
}));

const theme = createTheme();

const renderWithTheme = (component) => {
  return render(
    <ThemeProvider theme={theme}>
      {component}
    </ThemeProvider>
  );
};

describe('Enhanced AuthModal Component', () => {
  const mockOnClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    useAuth.mockReturnValue({
      isAuthenticated: false,
      user: null
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders login form by default', () => {
    renderWithTheme(
      <AuthModal open={true} onClose={mockOnClose} />
    );
    
    expect(screen.getByText('Sign In')).toBeInTheDocument();
    expect(screen.getByTestId('login-form')).toBeInTheDocument();
  });

  it('can switch between different auth modes', () => {
    renderWithTheme(
      <AuthModal open={true} onClose={mockOnClose} />
    );
    
    // Switch to register
    fireEvent.click(screen.getByText('Switch to Register'));
    expect(screen.getByText('Create Account')).toBeInTheDocument();
    expect(screen.getByTestId('register-form')).toBeInTheDocument();
    
    // Switch back to login
    fireEvent.click(screen.getByText('Switch to Login'));
    expect(screen.getByText('Sign In')).toBeInTheDocument();
    expect(screen.getByTestId('login-form')).toBeInTheDocument();
  });

  it('displays success animation on authentication', async () => {
    // Start with unauthenticated state
    const { rerender } = renderWithTheme(
      <AuthModal open={true} onClose={mockOnClose} />
    );
    
    // Simulate successful authentication
    useAuth.mockReturnValue({
      isAuthenticated: true,
      user: { username: 'testuser', email: 'test@example.com' }
    });
    
    rerender(
      <AuthModal open={true} onClose={mockOnClose} />
    );
    
    // Should show success animation
    expect(screen.getByText('Login Successful!')).toBeInTheDocument();
    expect(screen.getByText(/Welcome back, testuser/)).toBeInTheDocument();
  });

  it('auto-dismisses modal after successful authentication', async () => {
    // Start with unauthenticated state
    const { rerender } = renderWithTheme(
      <AuthModal open={true} onClose={mockOnClose} />
    );
    
    // Simulate successful authentication
    act(() => {
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { username: 'testuser', email: 'test@example.com' }
      });
      
      rerender(
        <AuthModal open={true} onClose={mockOnClose} />
      );
    });
    
    // Fast-forward past the auto-close timer (2000ms)
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    
    await waitFor(() => {
      expect(mockOnClose).toHaveBeenCalled();
    });
  });

  it('prevents manual close during success animation', () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      user: { username: 'testuser' }
    });
    
    renderWithTheme(
      <AuthModal open={true} onClose={mockOnClose} />
    );
    
    // Success overlay should not have close button functionality
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog).toBeInTheDocument();
    
    // Try to press escape (should not close during success)
    fireEvent.keyDown(dialog, { key: 'Escape', code: 'Escape' });
    expect(mockOnClose).not.toHaveBeenCalled();
  });

  it('shows enhanced styling with blur effects', () => {
    renderWithTheme(
      <AuthModal open={true} onClose={mockOnClose} />
    );
    
    const paper = document.querySelector('.MuiPaper-root');
    expect(paper).toHaveStyle({
      'border-radius': '24px' // 3 * 8px (theme spacing)
    });
  });

  it('displays success message with proper user greeting', () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      user: { 
        username: 'johnsmith',
        email: 'john@example.com'
      }
    });
    
    renderWithTheme(
      <AuthModal open={true} onClose={mockOnClose} />
    );
    
    expect(screen.getByText('Welcome back, johnsmith!')).toBeInTheDocument();
  });

  it('handles user without username gracefully', () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      user: { 
        email: 'user@example.com'
      }
    });
    
    renderWithTheme(
      <AuthModal open={true} onClose={mockOnClose} />
    );
    
    expect(screen.getByText('Welcome back, user@example.com!')).toBeInTheDocument();
  });

  it('closes modal when close button is clicked (non-success state)', () => {
    renderWithTheme(
      <AuthModal open={true} onClose={mockOnClose} />
    );
    
    const closeButton = screen.getByLabelText('close');
    fireEvent.click(closeButton);
    
    expect(mockOnClose).toHaveBeenCalled();
  });

  it('resets state when modal is closed', () => {
    const { rerender } = renderWithTheme(
      <AuthModal open={true} onClose={mockOnClose} initialMode="register" />
    );
    
    // Should show register form
    expect(screen.getByText('Create Account')).toBeInTheDocument();
    
    // Close and reopen
    rerender(
      <AuthModal open={false} onClose={mockOnClose} initialMode="register" />
    );
    
    rerender(
      <AuthModal open={true} onClose={mockOnClose} initialMode="register" />
    );
    
    // Should reset to initial mode
    expect(screen.getByText('Create Account')).toBeInTheDocument();
  });

  it('shows slide animation when opening', () => {
    renderWithTheme(
      <AuthModal open={true} onClose={mockOnClose} />
    );
    
    // Check for slide transition component
    const slideElement = document.querySelector('.MuiSlide-root');
    expect(slideElement).toBeInTheDocument();
  });

  it('displays loading spinner during success transition', () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      user: { username: 'testuser' }
    });
    
    const { rerender } = renderWithTheme(
      <AuthModal open={true} onClose={mockOnClose} />
    );
    
    // Fast-forward to show closing animation
    act(() => {
      vi.advanceTimersByTime(1500); // After success display, before close
    });
    
    rerender(
      <AuthModal open={true} onClose={mockOnClose} />
    );
    
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });
});

// Integration Tests
describe('AuthModal Integration', () => {
  const mockOnClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({
      isAuthenticated: false,
      user: null
    });
  });

  it('integrates properly with authentication flow', async () => {
    const { rerender } = renderWithTheme(
      <AuthModal open={true} onClose={mockOnClose} />
    );
    
    // Initially shows login form
    expect(screen.getByTestId('login-form')).toBeInTheDocument();
    
    // Simulate login success
    useAuth.mockReturnValue({
      isAuthenticated: true,
      user: { username: 'newuser', email: 'new@example.com' }
    });
    
    rerender(
      <AuthModal open={true} onClose={mockOnClose} />
    );
    
    // Should show success state
    expect(screen.getByText('Login Successful!')).toBeInTheDocument();
    expect(screen.queryByTestId('login-form')).not.toBeInTheDocument();
  });
});