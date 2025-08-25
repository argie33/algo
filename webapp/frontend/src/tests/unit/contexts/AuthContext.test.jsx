import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuthProvider, useAuth } from '../../../contexts/AuthContext';

// Mock AWS Amplify Auth
vi.mock('@aws-amplify/auth', () => ({
  fetchAuthSession: vi.fn(),
  signIn: vi.fn(),
  signUp: vi.fn(),
  confirmSignUp: vi.fn(),
  signOut: vi.fn(),
  resetPassword: vi.fn(),
  confirmResetPassword: vi.fn(),
  getCurrentUser: vi.fn(),
}));

// Mock config
vi.mock('../../../config/amplify', () => ({
  isCognitoConfigured: vi.fn(() => true),
}));

// Mock services
vi.mock('../../../services/devAuth', () => ({
  default: {
    login: vi.fn(),
    logout: vi.fn(),
    getUser: vi.fn(),
    isEnabled: false,
  },
}));

vi.mock('../../../services/sessionManager', () => ({
  default: {
    startSession: vi.fn(),
    endSession: vi.fn(),
    extendSession: vi.fn(),
    checkSession: vi.fn(),
    isSessionExpired: vi.fn(() => false),
    getTimeUntilExpiry: vi.fn(() => 3600000),
    on: vi.fn(),
    off: vi.fn(),
  },
}));

// Mock SessionWarningDialog
vi.mock('../../../components/auth/SessionWarningDialog', () => ({
  default: ({ open, onExtend, onLogout }) =>
    open ? (
      <div data-testid="session-warning">
        <button onClick={onExtend}>Extend</button>
        <button onClick={onLogout}>Logout</button>
      </div>
    ) : null,
}));

// Import mocked modules
import {
  fetchAuthSession,
  signIn,
  signUp,
  signOut,
  getCurrentUser,
} from '@aws-amplify/auth';
import { isCognitoConfigured } from '../../../config/amplify';
import devAuth from '../../../services/devAuth';
import sessionManager from '../../../services/sessionManager';

// Test component to access auth context
const TestComponent = () => {
  const auth = useAuth();
  
  return (
    <div>
      <div data-testid="loading">{auth.isLoading.toString()}</div>
      <div data-testid="authenticated">{auth.isAuthenticated.toString()}</div>
      <div data-testid="user">{auth.user?.username || 'null'}</div>
      <div data-testid="error">{auth.error || 'null'}</div>
      <button onClick={() => auth.login('test@example.com', 'password')}>
        Login
      </button>
      <button onClick={auth.logout}>Logout</button>
      <button onClick={() => auth.register('test@example.com', 'password')}>
        Register
      </button>
    </div>
  );
};

describe('AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset to default behavior
    isCognitoConfigured.mockReturnValue(true);
    devAuth.isEnabled = false;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  const renderAuthProvider = (children = <TestComponent />) => {
    return render(<AuthProvider>{children}</AuthProvider>);
  };

  describe('Provider Initialization', () => {
    it('should provide auth context to children', () => {
      getCurrentUser.mockResolvedValue({ username: 'testuser' });
      fetchAuthSession.mockResolvedValue({
        tokens: { accessToken: { toString: () => 'token' } },
      });
      
      renderAuthProvider();
      
      expect(screen.getByTestId('loading')).toBeInTheDocument();
      expect(screen.getByTestId('authenticated')).toBeInTheDocument();
      expect(screen.getByTestId('user')).toBeInTheDocument();
    });

    it('should initialize with loading state', () => {
      getCurrentUser.mockImplementation(() => new Promise(() => {})); // Never resolves
      
      renderAuthProvider();
      
      expect(screen.getByTestId('loading')).toHaveTextContent('true');
      expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
    });
  });

  describe('Authentication State Management', () => {
    it('should set authenticated state when user is logged in', async () => {
      const mockUser = { username: 'testuser' };
      const mockSession = {
        tokens: { accessToken: { toString: () => 'access-token' } },
      };

      getCurrentUser.mockResolvedValue(mockUser);
      fetchAuthSession.mockResolvedValue(mockSession);

      renderAuthProvider();

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('false');
        expect(screen.getByTestId('authenticated')).toHaveTextContent('true');
        expect(screen.getByTestId('user')).toHaveTextContent('testuser');
      });
    });

    it('should handle unauthenticated state', async () => {
      getCurrentUser.mockRejectedValue(new Error('Not authenticated'));

      renderAuthProvider();

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('false');
        expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
        expect(screen.getByTestId('user')).toHaveTextContent('null');
      });
    });
  });

  describe('Login Functionality', () => {
    it('should handle successful login', async () => {
      const user = userEvent.setup();
      const mockUser = { username: 'testuser' };
      const mockSession = {
        tokens: { accessToken: { toString: () => 'access-token' } },
      };

      // Initial state - not authenticated
      getCurrentUser.mockRejectedValueOnce(new Error('Not authenticated'));
      
      // After login - authenticated
      signIn.mockResolvedValue({ nextStep: { signInStep: 'DONE' } });
      getCurrentUser.mockResolvedValue(mockUser);
      fetchAuthSession.mockResolvedValue(mockSession);

      renderAuthProvider();

      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('false');
      });

      // Click login
      await user.click(screen.getByText('Login'));

      await waitFor(() => {
        expect(signIn).toHaveBeenCalledWith({
          username: 'test@example.com',
          password: 'password',
        });
        expect(screen.getByTestId('authenticated')).toHaveTextContent('true');
        expect(screen.getByTestId('user')).toHaveTextContent('testuser');
      });
    });

    it('should handle login errors', async () => {
      const user = userEvent.setup();
      getCurrentUser.mockRejectedValue(new Error('Not authenticated'));
      signIn.mockRejectedValue(new Error('Invalid credentials'));

      renderAuthProvider();

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('false');
      });

      await user.click(screen.getByText('Login'));

      await waitFor(() => {
        expect(screen.getByTestId('error')).toHaveTextContent('Invalid credentials');
        expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
      });
    });

    it('should handle MFA challenge', async () => {
      const user = userEvent.setup();
      getCurrentUser.mockRejectedValue(new Error('Not authenticated'));
      signIn.mockResolvedValue({
        nextStep: { signInStep: 'CONFIRM_SIGN_IN_WITH_SMS_CODE' },
      });

      renderAuthProvider();

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('false');
      });

      await user.click(screen.getByText('Login'));

      await waitFor(() => {
        expect(signIn).toHaveBeenCalled();
        // In a real implementation, this would trigger MFA flow
        expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
      });
    });
  });

  describe('Logout Functionality', () => {
    it('should handle successful logout', async () => {
      const user = userEvent.setup();
      const mockUser = { username: 'testuser' };

      // Start authenticated
      getCurrentUser.mockResolvedValue(mockUser);
      fetchAuthSession.mockResolvedValue({
        tokens: { accessToken: { toString: () => 'token' } },
      });
      signOut.mockResolvedValue();

      renderAuthProvider();

      // Wait for authentication
      await waitFor(() => {
        expect(screen.getByTestId('authenticated')).toHaveTextContent('true');
      });

      // Logout
      await user.click(screen.getByText('Logout'));

      await waitFor(() => {
        expect(signOut).toHaveBeenCalled();
        expect(screen.getByTestId('authenticated')).toHaveTextContent('false');
        expect(screen.getByTestId('user')).toHaveTextContent('null');
      });
    });
  });

  describe('Registration Functionality', () => {
    it('should handle successful registration', async () => {
      const user = userEvent.setup();
      getCurrentUser.mockRejectedValue(new Error('Not authenticated'));
      signUp.mockResolvedValue({
        nextStep: { signUpStep: 'CONFIRM_SIGN_UP' },
        userId: 'test-user-id',
      });

      renderAuthProvider();

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('false');
      });

      await user.click(screen.getByText('Register'));

      await waitFor(() => {
        expect(signUp).toHaveBeenCalledWith({
          username: 'test@example.com',
          password: 'password',
        });
      });
    });

    it('should handle registration errors', async () => {
      const user = userEvent.setup();
      getCurrentUser.mockRejectedValue(new Error('Not authenticated'));
      signUp.mockRejectedValue(new Error('Username already exists'));

      renderAuthProvider();

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('false');
      });

      await user.click(screen.getByText('Register'));

      await waitFor(() => {
        expect(screen.getByTestId('error')).toHaveTextContent('Username already exists');
      });
    });
  });

  describe('Development Auth Mode', () => {
    beforeEach(() => {
      devAuth.isEnabled = true;
      isCognitoConfigured.mockReturnValue(false);
    });

    it('should use development auth when enabled', async () => {
      const user = userEvent.setup();
      devAuth.getUser.mockResolvedValue({ username: 'devuser' });
      devAuth.login.mockResolvedValue({ username: 'devuser' });

      renderAuthProvider();

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('false');
      });

      await user.click(screen.getByText('Login'));

      await waitFor(() => {
        expect(devAuth.login).toHaveBeenCalled();
      });
    });
  });

  describe('Session Management Integration', () => {
    it('should integrate with session manager', async () => {
      const mockUser = { username: 'testuser' };
      getCurrentUser.mockResolvedValue(mockUser);
      fetchAuthSession.mockResolvedValue({
        tokens: { accessToken: { toString: () => 'token' } },
      });

      renderAuthProvider();

      await waitFor(() => {
        expect(sessionManager.startSession).toHaveBeenCalled();
      });
    });

    it('should show session warning dialog when session is expiring', async () => {
      const mockUser = { username: 'testuser' };
      getCurrentUser.mockResolvedValue(mockUser);
      fetchAuthSession.mockResolvedValue({
        tokens: { accessToken: { toString: () => 'token' } },
      });

      // Mock session manager to trigger warning
      let warningCallback;
      sessionManager.on.mockImplementation((event, callback) => {
        if (event === 'sessionExpiring') {
          warningCallback = callback;
        }
      });

      renderAuthProvider();

      // Wait for initial setup
      await waitFor(() => {
        expect(sessionManager.on).toHaveBeenCalledWith(
          'sessionExpiring',
          expect.any(Function)
        );
      });

      // Trigger session expiring warning
      act(() => {
        warningCallback();
      });

      await waitFor(() => {
        expect(screen.getByTestId('session-warning')).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('should clear errors on new actions', async () => {
      const user = userEvent.setup();
      getCurrentUser.mockRejectedValue(new Error('Not authenticated'));
      signIn.mockRejectedValueOnce(new Error('Network error'))
           .mockResolvedValueOnce({ nextStep: { signInStep: 'DONE' } });

      renderAuthProvider();

      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('false');
      });

      // First login attempt - error
      await user.click(screen.getByText('Login'));

      await waitFor(() => {
        expect(screen.getByTestId('error')).toHaveTextContent('Network error');
      });

      // Second login attempt - success
      await user.click(screen.getByText('Login'));

      await waitFor(() => {
        expect(screen.getByTestId('error')).toHaveTextContent('null');
      });
    });
  });

  describe('Context Hook Usage', () => {
    it('should throw error when used outside provider', () => {
      // Mock console.error to avoid test output noise
      const originalError = console.error;
      console.error = vi.fn();

      expect(() => {
        render(<TestComponent />);
      }).toThrow('useAuth must be used within an AuthProvider');

      console.error = originalError;
    });
  });

  describe('Token Management', () => {
    it('should update tokens when session changes', async () => {
      const mockUser = { username: 'testuser' };
      const mockSession = {
        tokens: { 
          accessToken: { toString: () => 'new-access-token' },
          idToken: { toString: () => 'new-id-token' }
        },
      };

      getCurrentUser.mockResolvedValue(mockUser);
      fetchAuthSession.mockResolvedValue(mockSession);

      renderAuthProvider();

      await waitFor(() => {
        expect(screen.getByTestId('authenticated')).toHaveTextContent('true');
      });

      // In a real implementation, you might test token updates
      // This would require exposing token state in the test component
    });
  });

  describe('Cleanup', () => {
    it('should cleanup session manager listeners on unmount', () => {
      const mockUser = { username: 'testuser' };
      getCurrentUser.mockResolvedValue(mockUser);
      fetchAuthSession.mockResolvedValue({
        tokens: { accessToken: { toString: () => 'token' } },
      });

      const { unmount } = renderAuthProvider();

      unmount();

      expect(sessionManager.off).toHaveBeenCalled();
    });
  });
});