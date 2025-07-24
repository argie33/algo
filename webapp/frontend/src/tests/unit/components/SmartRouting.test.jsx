import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
import SmartRouting from '../../../components/SmartRouting';
import { useAuth } from '../../../contexts/AuthContext';

// Mock the auth context
vi.mock('../../../contexts/AuthContext');

// Mock the navigation hook
const mockNavigate = vi.fn();
vi.mock('react-router-dom', () => ({
  ...vi.importActual('react-router-dom'),
  useNavigate: () => mockNavigate,
  useLocation: () => ({ pathname: '/' })
}));

// Mock child components
vi.mock('../../../pages/WelcomeLanding', () => {
  return function MockWelcomeLanding({ onSignInClick }) {
    return (
      <div data-testid="welcome-landing">
        <button onClick={onSignInClick}>Sign In</button>
      </div>
    );
  };
});

vi.mock('../../../pages/Dashboard', () => {
  return function MockDashboard() {
    return <div data-testid="dashboard">Dashboard Content</div>;
  };
});

vi.mock('../../../components/LoadingTransition', () => {
  return function MockLoadingTransition({ message, submessage, type }) {
    return (
      <div data-testid="loading-transition">
        <div data-testid="loading-message">{message}</div>
        <div data-testid="loading-submessage">{submessage}</div>
        <div data-testid="loading-type">{type}</div>
      </div>
    );
  };
});

const renderWithRouter = (component) => {
  return render(
    <BrowserRouter>
      {component}
    </BrowserRouter>
  );
};

describe('SmartRouting Component', () => {
  const mockOnSignInClick = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  describe('Loading States', () => {
    it('shows loading screen when authentication is loading', () => {
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: true
      });

      renderWithRouter(<SmartRouting onSignInClick={mockOnSignInClick} />);

      expect(screen.getByTestId('loading-transition')).toBeInTheDocument();
      expect(screen.getByTestId('loading-message')).toHaveTextContent('Checking authentication...');
      expect(screen.getByTestId('loading-submessage')).toHaveTextContent('Verifying your session and preparing your dashboard');
      expect(screen.getByTestId('loading-type')).toHaveTextContent('auth');
    });

    it('does not show loading screen when not loading', () => {
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: false
      });

      renderWithRouter(<SmartRouting onSignInClick={mockOnSignInClick} />);

      expect(screen.queryByTestId('loading-transition')).not.toBeInTheDocument();
    });
  });

  describe('Authentication State Routing', () => {
    it('shows Dashboard for authenticated users', () => {
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { username: 'testuser', email: 'test@example.com' },
        isLoading: false
      });

      renderWithRouter(<SmartRouting onSignInClick={mockOnSignInClick} />);

      expect(screen.getByTestId('dashboard')).toBeInTheDocument();
      expect(screen.queryByTestId('welcome-landing')).not.toBeInTheDocument();
    });

    it('shows WelcomeLanding for anonymous users', () => {
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: false
      });

      renderWithRouter(<SmartRouting onSignInClick={mockOnSignInClick} />);

      expect(screen.getByTestId('welcome-landing')).toBeInTheDocument();
      expect(screen.queryByTestId('dashboard')).not.toBeInTheDocument();
    });

    it('passes onSignInClick prop to WelcomeLanding', () => {
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: false
      });

      renderWithRouter(<SmartRouting onSignInClick={mockOnSignInClick} />);

      const signInButton = screen.getByText('Sign In');
      signInButton.click();

      expect(mockOnSignInClick).toHaveBeenCalledTimes(1);
    });
  });

  describe('Post-Login Redirect Logic', () => {
    it('redirects to dashboard for successful authentication', async () => {
      // Start with unauthenticated state
      const { rerender } = renderWithRouter(<SmartRouting onSignInClick={mockOnSignInClick} />);

      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: false
      });

      // Verify welcome landing is shown
      expect(screen.getByTestId('welcome-landing')).toBeInTheDocument();

      // Simulate successful authentication
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { username: 'testuser', email: 'test@example.com' },
        isLoading: false
      });

      rerender(<SmartRouting onSignInClick={mockOnSignInClick} />);

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
      });
    });

    it('handles intended path redirect from sessionStorage', async () => {
      // Set an intended path
      sessionStorage.setItem('intendedPath', '/portfolio');

      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { username: 'testuser' },
        isLoading: false
      });

      renderWithRouter(<SmartRouting onSignInClick={mockOnSignInClick} />);

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/portfolio', { replace: true });
      });

      // Should clear the intended path
      expect(sessionStorage.getItem('intendedPath')).toBeNull();
    });

    it('does not redirect to root path as intended path', async () => {
      // Set root path as intended (should be ignored)
      sessionStorage.setItem('intendedPath', '/');

      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { username: 'testuser' },
        isLoading: false
      });

      renderWithRouter(<SmartRouting onSignInClick={mockOnSignInClick} />);

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
      });
    });

    it('ignores market path as intended path', async () => {
      sessionStorage.setItem('intendedPath', '/market');

      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { username: 'testuser' },
        isLoading: false
      });

      renderWithRouter(<SmartRouting onSignInClick={mockOnSignInClick} />);

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true });
      });
    });
  });

  describe('Intended Path Storage', () => {
    const mockUseLocation = () => ({ pathname: '/settings' });
    
    beforeEach(() => {
      vi.doMock('react-router-dom', () => ({
        ...vi.importActual('react-router-dom'),
        useNavigate: () => mockNavigate,
        useLocation: mockUseLocation
      }));
    });

    it('stores intended path for unauthenticated users on protected routes', () => {
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: false
      });

      // Mock location to return /settings
      vi.doMock('react-router-dom', () => ({
        ...vi.importActual('react-router-dom'),
        useNavigate: () => mockNavigate,
        useLocation: () => ({ pathname: '/settings' })
      }));

      renderWithRouter(<SmartRouting onSignInClick={mockOnSignInClick} />);

      expect(sessionStorage.getItem('intendedPath')).toBe('/settings');
    });
  });

  describe('Edge Cases', () => {
    it('handles null user gracefully', () => {
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: null,
        isLoading: false
      });

      renderWithRouter(<SmartRouting onSignInClick={mockOnSignInClick} />);

      // Should still show dashboard even with null user if authenticated
      expect(screen.getByTestId('dashboard')).toBeInTheDocument();
    });

    it('handles authentication state changes', () => {
      const { rerender } = renderWithRouter(<SmartRouting onSignInClick={mockOnSignInClick} />);

      // Start unauthenticated
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: false
      });

      rerender(<SmartRouting onSignInClick={mockOnSignInClick} />);
      expect(screen.getByTestId('welcome-landing')).toBeInTheDocument();

      // Become authenticated
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { username: 'testuser' },
        isLoading: false
      });

      rerender(<SmartRouting onSignInClick={mockOnSignInClick} />);
      expect(screen.getByTestId('dashboard')).toBeInTheDocument();
    });

    it('handles loading to authenticated transition', async () => {
      const { rerender } = renderWithRouter(<SmartRouting onSignInClick={mockOnSignInClick} />);

      // Start loading
      useAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        isLoading: true
      });

      rerender(<SmartRouting onSignInClick={mockOnSignInClick} />);
      expect(screen.getByTestId('loading-transition')).toBeInTheDocument();

      // Finish loading and become authenticated
      useAuth.mockReturnValue({
        isAuthenticated: true,
        user: { username: 'testuser' },
        isLoading: false
      });

      rerender(<SmartRouting onSignInClick={mockOnSignInClick} />);
      expect(screen.getByTestId('dashboard')).toBeInTheDocument();
    });
  });
});