import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect } from 'vitest';
import ProtectedRoute from '../../../components/auth/ProtectedRoute';
import { AuthContext } from '../../../contexts/AuthContext';

// Mock child component
const MockComponent = () => <div data-testid="protected-content">Protected Content</div>;

const renderWithAuth = (isAuthenticated = false, user = null) => {
  const mockAuthContext = {
    isAuthenticated,
    user,
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
    register: vi.fn(),
  };

  return render(
    <AuthContext.Provider value={mockAuthContext}>
      <MemoryRouter>
        <ProtectedRoute>
          <MockComponent />
        </ProtectedRoute>
      </MemoryRouter>
    </AuthContext.Provider>
  );
};

describe('ProtectedRoute', () => {
  it('renders children when user is authenticated', () => {
    renderWithAuth(true, { id: '1', username: 'testuser' });
    
    expect(screen.getByTestId('protected-content')).toBeInTheDocument();
  });

  it('shows login prompt when user is not authenticated', () => {
    renderWithAuth(false);
    
    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
    expect(screen.getByText(/sign in required/i)).toBeInTheDocument();
  });

  it('displays loading state while authentication is being checked', () => {
    const mockAuthContext = {
      isAuthenticated: false,
      user: null,
      loading: true,
      login: vi.fn(),
      logout: vi.fn(),
      register: vi.fn(),
    };

    render(
      <AuthContext.Provider value={mockAuthContext}>
        <MemoryRouter>
          <ProtectedRoute>
            <MockComponent />
          </ProtectedRoute>
        </MemoryRouter>
      </AuthContext.Provider>
    );
    
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('shows sign in button when not authenticated', () => {
    renderWithAuth(false);
    
    const signInButton = screen.getByRole('button', { name: /sign in/i });
    expect(signInButton).toBeInTheDocument();
  });

  it('handles authentication error states gracefully', () => {
    const mockAuthContext = {
      isAuthenticated: false,
      user: null,
      loading: false,
      error: 'Authentication failed',
      login: vi.fn(),
      logout: vi.fn(),
      register: vi.fn(),
    };

    render(
      <AuthContext.Provider value={mockAuthContext}>
        <MemoryRouter>
          <ProtectedRoute>
            <MockComponent />
          </ProtectedRoute>
        </MemoryRouter>
      </AuthContext.Provider>
    );
    
    expect(screen.getByText(/authentication failed/i)).toBeInTheDocument();
  });

  it('supports custom redirect behavior', () => {
    const customRedirect = vi.fn();
    
    const mockAuthContext = {
      isAuthenticated: false,
      user: null,
      loading: false,
      login: vi.fn(),
      logout: vi.fn(),
      register: vi.fn(),
    };

    render(
      <AuthContext.Provider value={mockAuthContext}>
        <MemoryRouter>
          <ProtectedRoute onUnauthenticated={customRedirect}>
            <MockComponent />
          </ProtectedRoute>
        </MemoryRouter>
      </AuthContext.Provider>
    );
    
    expect(customRedirect).toHaveBeenCalled();
  });

  it('validates user permissions when specified', () => {
    const mockUser = { 
      id: '1', 
      username: 'testuser',
      permissions: ['read', 'write']
    };
    
    const mockAuthContext = {
      isAuthenticated: true,
      user: mockUser,
      loading: false,
      login: vi.fn(),
      logout: vi.fn(),
      register: vi.fn(),
    };

    render(
      <AuthContext.Provider value={mockAuthContext}>
        <MemoryRouter>
          <ProtectedRoute requiredPermissions={['read']}>
            <MockComponent />
          </ProtectedRoute>
        </MemoryRouter>
      </AuthContext.Provider>
    );
    
    expect(screen.getByTestId('protected-content')).toBeInTheDocument();
  });

  it('blocks access when user lacks required permissions', () => {
    const mockUser = { 
      id: '1', 
      username: 'testuser',
      permissions: ['read']
    };
    
    const mockAuthContext = {
      isAuthenticated: true,
      user: mockUser,
      loading: false,
      login: vi.fn(),
      logout: vi.fn(),
      register: vi.fn(),
    };

    render(
      <AuthContext.Provider value={mockAuthContext}>
        <MemoryRouter>
          <ProtectedRoute requiredPermissions={['admin']}>
            <MockComponent />
          </ProtectedRoute>
        </MemoryRouter>
      </AuthContext.Provider>
    );
    
    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument();
    expect(screen.getByText(/insufficient permissions/i)).toBeInTheDocument();
  });
});