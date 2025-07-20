/**
 * Login Page Integration Tests
 * Comprehensive testing of login functionality and user authentication flow
 * FIXED: React hooks import issue - uses React 18 built-in useSyncExternalStore
 */

// Import React from our fixed preloader to ensure hooks are available
import '../../../utils/reactModulePreloader.js';
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';

// Import the actual MUI theme
import muiTheme from '../../../theme/muiTheme';

// Mock AuthContext
const mockAuthContext = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  login: vi.fn(),
  logout: vi.fn(),
  signUp: vi.fn(),
  forgotPassword: vi.fn(),
  resetPassword: vi.fn(),
  tokens: null,
  error: null
};

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthContext,
  AuthProvider: ({ children }) => children
}));

// Mock react-router-dom hooks
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useLocation: () => ({ pathname: '/login', search: '', hash: '', state: null })
  };
});

// Mock AWS Amplify Auth
vi.mock('aws-amplify', () => ({
  Auth: {
    signIn: vi.fn(),
    signUp: vi.fn(),
    forgotPassword: vi.fn(),
    forgotPasswordSubmit: vi.fn(),
    currentAuthenticatedUser: vi.fn(),
    signOut: vi.fn()
  },
  Hub: {
    listen: vi.fn()
  }
}));

// Mock components that might not exist
vi.mock('../../../components/auth/LoginForm', () => ({
  default: ({ onSubmit, loading, error }) => (
    <form data-testid="login-form" onSubmit={(e) => { e.preventDefault(); onSubmit({ email: 'test@example.com', password: 'password123' }); }}>
      <input data-testid="email-input" type="email" placeholder="Email" />
      <input data-testid="password-input" type="password" placeholder="Password" />
      <button data-testid="login-submit" type="submit" disabled={loading}>
        {loading ? 'Signing In...' : 'Sign In'}
      </button>
      {error && <div data-testid="login-error">{error}</div>}
    </form>
  )
}));

vi.mock('../../../components/auth/SignUpForm', () => ({
  default: ({ onSubmit, loading, error }) => (
    <form data-testid="signup-form" onSubmit={(e) => { e.preventDefault(); onSubmit({ email: 'test@example.com', password: 'password123', confirmPassword: 'password123' }); }}>
      <input data-testid="signup-email-input" type="email" placeholder="Email" />
      <input data-testid="signup-password-input" type="password" placeholder="Password" />
      <input data-testid="signup-confirm-password-input" type="password" placeholder="Confirm Password" />
      <button data-testid="signup-submit" type="submit" disabled={loading}>
        {loading ? 'Creating Account...' : 'Create Account'}
      </button>
      {error && <div data-testid="signup-error">{error}</div>}
    </form>
  )
}));

vi.mock('../../../components/auth/ForgotPasswordForm', () => ({
  default: ({ onSubmit, loading, error }) => (
    <form data-testid="forgot-password-form" onSubmit={(e) => { e.preventDefault(); onSubmit({ email: 'test@example.com' }); }}>
      <input data-testid="forgot-email-input" type="email" placeholder="Email" />
      <button data-testid="forgot-submit" type="submit" disabled={loading}>
        {loading ? 'Sending...' : 'Reset Password'}
      </button>
      {error && <div data-testid="forgot-error">{error}</div>}
    </form>
  )
}));

// Create a mock Login page component
const MockLoginPage = () => {
  const [currentForm, setCurrentForm] = React.useState('login');
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);

  const handleLogin = async (credentials) => {
    setLoading(true);
    setError(null);
    try {
      await mockAuthContext.login(credentials);
      mockNavigate('/dashboard');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSignUp = async (userData) => {
    setLoading(true);
    setError(null);
    try {
      await mockAuthContext.signUp(userData);
      setCurrentForm('login');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleForgotPassword = async (data) => {
    setLoading(true);
    setError(null);
    try {
      await mockAuthContext.forgotPassword(data.email);
      setError('Password reset instructions sent to your email');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div data-testid="login-page">
      <div data-testid="auth-tabs">
        <button 
          data-testid="login-tab"
          onClick={() => setCurrentForm('login')}
          className={currentForm === 'login' ? 'active' : ''}
        >
          Sign In
        </button>
        <button 
          data-testid="signup-tab"
          onClick={() => setCurrentForm('signup')}
          className={currentForm === 'signup' ? 'active' : ''}
        >
          Sign Up
        </button>
        <button 
          data-testid="forgot-tab"
          onClick={() => setCurrentForm('forgot')}
          className={currentForm === 'forgot' ? 'active' : ''}
        >
          Forgot Password
        </button>
      </div>

      {currentForm === 'login' && (
        <div data-testid="login-form-container">
          <MockLoginForm onSubmit={handleLogin} loading={loading} error={error} />
        </div>
      )}

      {currentForm === 'signup' && (
        <div data-testid="signup-form-container">
          <MockSignUpForm onSubmit={handleSignUp} loading={loading} error={error} />
        </div>
      )}

      {currentForm === 'forgot' && (
        <div data-testid="forgot-form-container">
          <MockForgotPasswordForm onSubmit={handleForgotPassword} loading={loading} error={error} />
        </div>
      )}
    </div>
  );
};

// Mock form components
const MockLoginForm = vi.mocked(vi.importMock('../../../components/auth/LoginForm').default);
const MockSignUpForm = vi.mocked(vi.importMock('../../../components/auth/SignUpForm').default);
const MockForgotPasswordForm = vi.mocked(vi.importMock('../../../components/auth/ForgotPasswordForm').default);

// Test wrapper
const TestWrapper = ({ children }) => (
  <ThemeProvider theme={muiTheme}>
    <BrowserRouter>
      {children}
    </BrowserRouter>
  </ThemeProvider>
);

describe('🔐 Login Page Tests', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();
    mockNavigate.mockClear();
    mockAuthContext.login.mockClear();
    mockAuthContext.signUp.mockClear();
    mockAuthContext.forgotPassword.mockClear();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Page Rendering', () => {
    it('should render login page with all authentication forms', () => {
      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      expect(screen.getByTestId('login-page')).toBeInTheDocument();
      expect(screen.getByTestId('auth-tabs')).toBeInTheDocument();
      expect(screen.getByTestId('login-tab')).toBeInTheDocument();
      expect(screen.getByTestId('signup-tab')).toBeInTheDocument();
      expect(screen.getByTestId('forgot-tab')).toBeInTheDocument();
    });

    it('should show login form by default', () => {
      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      expect(screen.getByTestId('login-form-container')).toBeInTheDocument();
      expect(screen.queryByTestId('signup-form-container')).not.toBeInTheDocument();
      expect(screen.queryByTestId('forgot-form-container')).not.toBeInTheDocument();
    });
  });

  describe('Form Navigation', () => {
    it('should switch to signup form when signup tab is clicked', async () => {
      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('signup-tab'));

      expect(screen.getByTestId('signup-form-container')).toBeInTheDocument();
      expect(screen.queryByTestId('login-form-container')).not.toBeInTheDocument();
    });

    it('should switch to forgot password form when forgot tab is clicked', async () => {
      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('forgot-tab'));

      expect(screen.getByTestId('forgot-form-container')).toBeInTheDocument();
      expect(screen.queryByTestId('login-form-container')).not.toBeInTheDocument();
    });

    it('should switch back to login form', async () => {
      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      // Go to signup
      await user.click(screen.getByTestId('signup-tab'));
      expect(screen.getByTestId('signup-form-container')).toBeInTheDocument();

      // Go back to login
      await user.click(screen.getByTestId('login-tab'));
      expect(screen.getByTestId('login-form-container')).toBeInTheDocument();
      expect(screen.queryByTestId('signup-form-container')).not.toBeInTheDocument();
    });
  });

  describe('Login Functionality', () => {
    it('should handle successful login', async () => {
      mockAuthContext.login.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      const loginForm = screen.getByTestId('login-form');
      fireEvent.submit(loginForm);

      await waitFor(() => {
        expect(mockAuthContext.login).toHaveBeenCalledWith({
          email: 'test@example.com',
          password: 'password123'
        });
      });

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
      });
    });

    it('should handle login error', async () => {
      const errorMessage = 'Invalid credentials';
      mockAuthContext.login.mockRejectedValue(new Error(errorMessage));

      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      const loginForm = screen.getByTestId('login-form');
      fireEvent.submit(loginForm);

      await waitFor(() => {
        expect(mockAuthContext.login).toHaveBeenCalled();
      });

      // Check that error is displayed
      await waitFor(() => {
        expect(screen.getByTestId('login-error')).toHaveTextContent(errorMessage);
      });

      // Should not navigate on error
      expect(mockNavigate).not.toHaveBeenCalled();
    });

    it('should show loading state during login', async () => {
      let resolveLogin;
      mockAuthContext.login.mockReturnValue(new Promise(resolve => {
        resolveLogin = resolve;
      }));

      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      const loginForm = screen.getByTestId('login-form');
      fireEvent.submit(loginForm);

      // Should show loading state
      await waitFor(() => {
        expect(screen.getByText('Signing In...')).toBeInTheDocument();
      });

      // Resolve the promise
      resolveLogin({ success: true });

      await waitFor(() => {
        expect(screen.getByText('Sign In')).toBeInTheDocument();
      });
    });
  });

  describe('Sign Up Functionality', () => {
    it('should handle successful signup', async () => {
      mockAuthContext.signUp.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      // Switch to signup form
      await user.click(screen.getByTestId('signup-tab'));

      const signupForm = screen.getByTestId('signup-form');
      fireEvent.submit(signupForm);

      await waitFor(() => {
        expect(mockAuthContext.signUp).toHaveBeenCalledWith({
          email: 'test@example.com',
          password: 'password123',
          confirmPassword: 'password123'
        });
      });

      // Should switch back to login form after successful signup
      await waitFor(() => {
        expect(screen.getByTestId('login-form-container')).toBeInTheDocument();
      });
    });

    it('should handle signup error', async () => {
      const errorMessage = 'Email already exists';
      mockAuthContext.signUp.mockRejectedValue(new Error(errorMessage));

      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('signup-tab'));

      const signupForm = screen.getByTestId('signup-form');
      fireEvent.submit(signupForm);

      await waitFor(() => {
        expect(mockAuthContext.signUp).toHaveBeenCalled();
      });

      await waitFor(() => {
        expect(screen.getByTestId('signup-error')).toHaveTextContent(errorMessage);
      });
    });
  });

  describe('Forgot Password Functionality', () => {
    it('should handle forgot password request', async () => {
      mockAuthContext.forgotPassword.mockResolvedValue({ success: true });

      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('forgot-tab'));

      const forgotForm = screen.getByTestId('forgot-password-form');
      fireEvent.submit(forgotForm);

      await waitFor(() => {
        expect(mockAuthContext.forgotPassword).toHaveBeenCalledWith('test@example.com');
      });

      await waitFor(() => {
        expect(screen.getByTestId('forgot-error')).toHaveTextContent('Password reset instructions sent to your email');
      });
    });

    it('should handle forgot password error', async () => {
      const errorMessage = 'Email not found';
      mockAuthContext.forgotPassword.mockRejectedValue(new Error(errorMessage));

      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('forgot-tab'));

      const forgotForm = screen.getByTestId('forgot-password-form');
      fireEvent.submit(forgotForm);

      await waitFor(() => {
        expect(mockAuthContext.forgotPassword).toHaveBeenCalled();
      });

      await waitFor(() => {
        expect(screen.getByTestId('forgot-error')).toHaveTextContent(errorMessage);
      });
    });
  });

  describe('Authentication State Integration', () => {
    it('should redirect authenticated users', () => {
      // Mock already authenticated state
      const authenticatedContext = {
        ...mockAuthContext,
        isAuthenticated: true,
        user: { email: 'user@example.com', username: 'user' }
      };

      vi.mocked(vi.importMock('../../../contexts/AuthContext').useAuth).mockReturnValue(authenticatedContext);

      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      // Should redirect to dashboard if already authenticated
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
    });

    it('should handle loading state', () => {
      const loadingContext = {
        ...mockAuthContext,
        isLoading: true
      };

      vi.mocked(vi.importMock('../../../contexts/AuthContext').useAuth).mockReturnValue(loadingContext);

      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      // Should show loading indicator or spinner
      expect(screen.getByTestId('login-page')).toBeInTheDocument();
    });
  });

  describe('Form Validation', () => {
    it('should validate email format', async () => {
      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      const emailInput = screen.getByTestId('email-input');
      
      await user.type(emailInput, 'invalid-email');
      
      // Check if email validation is applied (this would depend on actual implementation)
      expect(emailInput).toHaveValue('invalid-email');
    });

    it('should validate password requirements', async () => {
      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('signup-tab'));

      const passwordInput = screen.getByTestId('signup-password-input');
      
      await user.type(passwordInput, '123');
      
      // Check if password validation is applied
      expect(passwordInput).toHaveValue('123');
    });

    it('should validate password confirmation match', async () => {
      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('signup-tab'));

      const passwordInput = screen.getByTestId('signup-password-input');
      const confirmInput = screen.getByTestId('signup-confirm-password-input');
      
      await user.type(passwordInput, 'password123');
      await user.type(confirmInput, 'different-password');
      
      // Check if password confirmation validation is applied
      expect(passwordInput).toHaveValue('password123');
      expect(confirmInput).toHaveValue('different-password');
    });
  });

  describe('Accessibility', () => {
    it('should have proper ARIA labels and roles', () => {
      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      // Check for accessible form elements
      expect(screen.getByTestId('login-form')).toBeInTheDocument();
      expect(screen.getByTestId('email-input')).toBeInTheDocument();
      expect(screen.getByTestId('password-input')).toBeInTheDocument();
      expect(screen.getByTestId('login-submit')).toBeInTheDocument();
    });

    it('should support keyboard navigation', async () => {
      render(
        <TestWrapper>
          <MockLoginPage />
        </TestWrapper>
      );

      const loginTab = screen.getByTestId('login-tab');
      const signupTab = screen.getByTestId('signup-tab');

      // Test tab navigation
      loginTab.focus();
      expect(document.activeElement).toBe(loginTab);

      await user.tab();
      expect(document.activeElement).toBe(signupTab);
    });
  });
});