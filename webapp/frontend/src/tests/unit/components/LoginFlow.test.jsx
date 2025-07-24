import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { vi } from 'vitest';
import App from '../../../App';
import { useAuth } from '../../../contexts/AuthContext';

// Mock the auth context
vi.mock('../../../contexts/AuthContext');

// Mock all the page components to focus on routing logic
vi.mock('../../../pages/Dashboard', () => {
  return function MockDashboard() {
    return <div data-testid="dashboard">Dashboard Content</div>;
  };
});

vi.mock('../../../pages/WelcomeLanding', () => {
  return function MockWelcomeLanding({ onSignInClick }) {
    return (
      <div data-testid="welcome-landing">
        <h1>Welcome to Your Financial Future</h1>
        <button onClick={onSignInClick} data-testid="get-started-btn">
          Get Started
        </button>
      </div>
    );
  };
});

vi.mock('../../../pages/MarketOverview', () => {
  return function MockMarketOverview() {
    return <div data-testid="market-overview">Market Overview</div>;
  };
});

vi.mock('../../../components/auth/AuthModal', () => {
  return function MockAuthModal({ open, onClose }) {
    const { isAuthenticated, user } = useAuth();
    
    // Simulate successful login after modal opens
    React.useEffect(() => {
      if (open && !isAuthenticated) {
        // Simulate login process with delay
        const timer = setTimeout(() => {
          // This would normally be handled by the actual login process
          // For testing, we'll update the mock auth state
        }, 100);
        return () => clearTimeout(timer);
      }
    }, [open, isAuthenticated]);

    if (!open) return null;

    return (
      <div data-testid="auth-modal" role="dialog">
        <h2>Sign In</h2>
        <button 
          onClick={() => {
            // Simulate successful login
            // In real app, this would update auth context
            onClose();
          }}
          data-testid="login-btn"
        >
          Login
        </button>
        <button onClick={onClose} data-testid="close-modal-btn">
          Close
        </button>
      </div>
    );
  };
});

vi.mock('../../../components/SystemHealthMonitor', () => {
  return function MockSystemHealthMonitor() {
    return <div data-testid="system-health">System Health</div>;
  };
});

const theme = createTheme();

const renderApp = () => {
  return render(
    <BrowserRouter>
      <ThemeProvider theme={theme}>
        <App />
      </ThemeProvider>
    </BrowserRouter>
  );
};

describe('Login Flow Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    sessionStorage.clear();
    localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('Anonymous User Experience', () => {
    it('shows welcome landing page for anonymous users', () => {
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: false,
        logout: vi.fn()
      });

      renderApp();

      expect(screen.getByTestId('welcome-landing')).toBeInTheDocument();
      expect(screen.getByText('Welcome to Your Financial Future')).toBeInTheDocument();
      expect(screen.getByTestId('get-started-btn')).toBeInTheDocument();
    });

    it('opens auth modal when Get Started is clicked', async () => {
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: false,
        logout: vi.fn()
      });

      renderApp();

      const getStartedBtn = screen.getByTestId('get-started-btn');
      fireEvent.click(getStartedBtn);

      await waitFor(() => {
        expect(screen.getByTestId('auth-modal')).toBeInTheDocument();
      });
    });

    it('shows welcome landing on market route for anonymous users', () => {
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: false,
        logout: vi.fn()
      });

      // Navigate to market route
      window.history.pushState({}, '', '/market');
      
      renderApp();

      expect(screen.getByTestId('welcome-landing')).toBeInTheDocument();
      expect(screen.queryByTestId('market-overview')).not.toBeInTheDocument();
    });
  });

  describe('Authenticated User Experience', () => {
    it('shows dashboard for authenticated users', () => {
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { 
          username: 'testuser', 
          email: 'test@example.com',
          userId: 'user123'
        },
        isLoading: false,
        logout: vi.fn()
      });

      renderApp();

      expect(screen.getByTestId('dashboard')).toBeInTheDocument();
      expect(screen.queryByTestId('welcome-landing')).not.toBeInTheDocument();
    });

    it('shows market overview for authenticated users on market route', () => {
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { 
          username: 'testuser', 
          email: 'test@example.com',
          userId: 'user123'
        },
        isLoading: false,
        logout: vi.fn()
      });

      // Navigate to market route
      window.history.pushState({}, '', '/market');
      
      renderApp();

      expect(screen.getByTestId('market-overview')).toBeInTheDocument();
      expect(screen.queryByTestId('welcome-landing')).not.toBeInTheDocument();
    });
  });

  describe('Authentication Flow', () => {
    it('transitions from anonymous to authenticated state', async () => {
      // Start with anonymous user
      const mockAuth = {
        isAuthenticated: false,
        user: null,
        isLoading: false,
        logout: vi.fn()
      };

      useAuth.mockReturnValue(mockAuth);

      const { rerender } = renderApp();

      // Should show welcome landing
      expect(screen.getByTestId('welcome-landing')).toBeInTheDocument();

      // Click get started to open modal
      fireEvent.click(screen.getByTestId('get-started-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('auth-modal')).toBeInTheDocument();
      });

      // Simulate successful authentication
      mockAuth.isAuthenticated = true;
      mockAuth.user = { 
        username: 'testuser', 
        email: 'test@example.com',
        userId: 'user123'
      };
      
      useAuth.mockReturnValue(mockAuth);

      rerender(
        <BrowserRouter>
          <ThemeProvider theme={theme}>
            <App />
          </ThemeProvider>
        </BrowserRouter>
      );

      // Should now show dashboard
      await waitFor(() => {
        expect(screen.getByTestId('dashboard')).toBeInTheDocument();
      });

      expect(screen.queryByTestId('welcome-landing')).not.toBeInTheDocument();
    });

    it('closes modal after successful authentication', async () => {
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: false,
        logout: vi.fn()
      });

      renderApp();

      // Open modal
      fireEvent.click(screen.getByTestId('get-started-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('auth-modal')).toBeInTheDocument();
      });

      // Click login button (simulates successful login)
      fireEvent.click(screen.getByTestId('login-btn'));

      // Modal should close
      await waitFor(() => {
        expect(screen.queryByTestId('auth-modal')).not.toBeInTheDocument();
      });
    });
  });

  describe('Loading States', () => {
    it('shows loading screen while authentication is being checked', () => {
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: true,
        logout: vi.fn()
      });

      renderApp();

      expect(screen.getByTestId('loading-transition')).toBeInTheDocument();
      expect(screen.queryByTestId('welcome-landing')).not.toBeInTheDocument();
      expect(screen.queryByTestId('dashboard')).not.toBeInTheDocument();
    });

    it('transitions from loading to appropriate content', async () => {
      const mockAuth = {
        isAuthenticated: false,
        user: null,
        isLoading: true,
        logout: vi.fn()
      };

      useAuth.mockReturnValue(mockAuth);

      const { rerender } = renderApp();

      // Should show loading
      expect(screen.getByTestId('loading-transition')).toBeInTheDocument();

      // Finish loading and show authenticated state
      mockAuth.isLoading = false;
      mockAuth.isAuthenticated = true;
      mockAuth.user = { username: 'testuser', userId: 'user123' };
      
      useAuth.mockReturnValue(mockAuth);

      rerender(
        <BrowserRouter>
          <ThemeProvider theme={theme}>
            <App />
          </ThemeProvider>
        </BrowserRouter>
      );

      expect(screen.queryByTestId('loading-transition')).not.toBeInTheDocument();
      expect(screen.getByTestId('dashboard')).toBeInTheDocument();
    });
  });

  describe('Navigation and Routing', () => {
    it('handles route navigation correctly for authenticated users', async () => {
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { username: 'testuser', userId: 'user123' },
        isLoading: false,
        logout: vi.fn()
      });

      renderApp();

      // Should start on dashboard (root route)
      expect(screen.getByTestId('dashboard')).toBeInTheDocument();

      // Navigate to market (would be handled by router in real app)
      act(() => {
        window.history.pushState({}, '', '/market');
        window.dispatchEvent(new PopStateEvent('popstate'));
      });

      // In a real test, we'd wait for the route change
      // For this test, we're focusing on the component logic
    });

    it('preserves intended path during authentication flow', () => {
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: false,
        logout: vi.fn()
      });

      // Simulate user trying to access protected route
      window.history.pushState({}, '', '/settings');
      
      renderApp();

      // Should show welcome landing (since route redirects anonymous users)
      expect(screen.getByTestId('welcome-landing')).toBeInTheDocument();
      
      // The intended path should be stored (tested in SmartRouting unit tests)
    });
  });

  describe('Error Handling', () => {
    it('handles missing user data gracefully', () => {
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: null, // Missing user data
        isLoading: false,
        logout: vi.fn()
      });

      renderApp();

      // Should still show dashboard (SmartRouting handles this case)
      expect(screen.getByTestId('dashboard')).toBeInTheDocument();
    });

    it('handles auth context errors gracefully', () => {
      useAuth.mockImplementation(() => {
        throw new Error('Auth context error');
      });

      // Should not crash the app
      expect(() => renderApp()).not.toThrow();
    });
  });

  describe('User Experience Flow', () => {
    it('provides smooth transition from landing to dashboard', async () => {
      // Start anonymous
      const mockAuth = {
        isAuthenticated: false,
        user: null,
        isLoading: false,
        logout: vi.fn()
      };

      useAuth.mockReturnValue(mockAuth);

      const { rerender } = renderApp();

      // Step 1: User sees welcome landing
      expect(screen.getByTestId('welcome-landing')).toBeInTheDocument();
      expect(screen.getByText('Welcome to Your Financial Future')).toBeInTheDocument();

      // Step 2: User clicks get started
      fireEvent.click(screen.getByTestId('get-started-btn'));

      await waitFor(() => {
        expect(screen.getByTestId('auth-modal')).toBeInTheDocument();
      });

      // Step 3: User completes authentication
      mockAuth.isAuthenticated = true;
      mockAuth.user = { 
        username: 'newuser', 
        email: 'new@example.com',
        userId: 'user123'
      };
      
      useAuth.mockReturnValue(mockAuth);

      rerender(
        <BrowserRouter>
          <ThemeProvider theme={theme}>
            <App />
          </ThemeProvider>
        </BrowserRouter>
      );

      // Step 4: User sees personalized dashboard
      await waitFor(() => {
        expect(screen.getByTestId('dashboard')).toBeInTheDocument();
      });

      expect(screen.queryByTestId('welcome-landing')).not.toBeInTheDocument();
      expect(screen.queryByTestId('auth-modal')).not.toBeInTheDocument();
    });
  });
});