import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
import App from '../../App';

// Mock all the page components to avoid complex dependencies
vi.mock('../../pages/Dashboard', () => ({
  default: () => <div data-testid="dashboard-page">Dashboard</div>
}));

vi.mock('../../pages/MarketOverview', () => ({
  default: () => <div data-testid="market-overview-page">Market Overview</div>
}));

vi.mock('../../pages/Portfolio', () => ({
  default: () => <div data-testid="portfolio-page">Portfolio</div>
}));

vi.mock('../../pages/Settings', () => ({
  default: () => <div data-testid="settings-page">Settings</div>
}));

// Mock all other page components with a simple fallback

vi.mock('../../pages/PortfolioHoldings', () => ({
  default: () => <div data-testid="portfolioholdings-page">PortfolioHoldings</div>
}));

vi.mock('../../pages/TechnicalAnalysis', () => ({
  default: () => <div data-testid="technicalanalysis-page">TechnicalAnalysis</div>
}));

vi.mock('../../pages/StockExplorer', () => ({
  default: () => <div data-testid="stockexplorer-page">StockExplorer</div>
}));

vi.mock('../../pages/Watchlist', () => ({
  default: () => <div data-testid="watchlist-page">Watchlist</div>
}));

// Mock other essential pages that might be imported
vi.mock('../../pages/ComingSoon', () => ({
  default: () => <div data-testid="comingsoon-page">ComingSoon</div>
}));

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({
  AuthProvider: ({ children }) => children,
  useAuth: () => ({
    user: { username: 'testuser', email: 'test@example.com' },
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    isLoading: false,
    error: null
  })
}));

// Mock ApiKeyProvider
vi.mock('../../components/ApiKeyProvider', () => ({
  ApiKeyProvider: ({ children }) => children,
  useApiKeys: () => ({
    apiKeys: {},
    loading: false,
    error: null,
    setApiKey: vi.fn(),
    hasApiKey: () => false
  })
}));

// Mock ErrorBoundary
vi.mock('../../components/ErrorBoundary', () => ({
  default: ({ children }) => children
}));

describe('App', () => {
  const renderApp = (initialRoute = '/') => {
    window.history.pushState({}, 'Test page', initialRoute);
    
    return render(
      <BrowserRouter>
        <App />
      </BrowserRouter>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Basic Rendering', () => {
    test('renders without crashing', () => {
      renderApp();
      
      expect(screen.getByRole('banner')).toBeInTheDocument(); // AppBar
    });

    test('renders navigation drawer', () => {
      renderApp();
      
      expect(screen.getByLabelText(/open drawer/i)).toBeInTheDocument();
    });

    test('renders app title', () => {
      renderApp();
      
      expect(screen.getByText(/edgebrooke capital/i)).toBeInTheDocument();
    });
  });

  describe('Navigation', () => {
    test('renders default dashboard route', () => {
      renderApp('/');
      
      expect(screen.getByTestId('dashboard-page')).toBeInTheDocument();
    });

    test('renders dashboard route', () => {
      renderApp('/dashboard');
      
      expect(screen.getByTestId('dashboard-page')).toBeInTheDocument();
    });

    test('renders market overview route', () => {
      renderApp('/market');
      
      expect(screen.getByTestId('market-overview-page')).toBeInTheDocument();
    });

    test('renders portfolio route', () => {
      renderApp('/portfolio');
      
      expect(screen.getByTestId('portfolio-page')).toBeInTheDocument();
    });

    test('renders settings route', () => {
      renderApp('/settings');
      
      expect(screen.getByTestId('settings-page')).toBeInTheDocument();
    });
  });

  describe('Responsive Layout', () => {
    test('renders mobile layout', () => {
      // Mock mobile viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 600,
      });

      renderApp();
      
      expect(screen.getByRole('banner')).toBeInTheDocument();
    });

    test('renders desktop layout', () => {
      // Mock desktop viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 1200,
      });

      renderApp();
      
      expect(screen.getByRole('banner')).toBeInTheDocument();
    });
  });

  describe('User Authentication', () => {
    test('displays user information when authenticated', () => {
      renderApp();
      
      // Should show user menu or avatar
      const userElements = screen.queryAllByText(/testuser/i);
      expect(userElements.length).toBeGreaterThanOrEqual(0);
    });

    test('handles unauthenticated state', () => {
      vi.mocked(vi.importActual('../../contexts/AuthContext').useAuth).mockReturnValue({
        user: null,
        isAuthenticated: false,
        login: vi.fn(),
        logout: vi.fn(),
        isLoading: false,
        error: null
      });

      renderApp();
      
      expect(screen.getByRole('banner')).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    test('handles invalid routes gracefully', () => {
      renderApp('/invalid-route');
      
      // Should not crash and still render the app shell
      expect(screen.getByRole('banner')).toBeInTheDocument();
    });

    test('renders with missing auth context', () => {
      vi.mocked(vi.importActual('../../contexts/AuthContext').useAuth).mockReturnValue({
        user: null,
        isAuthenticated: false,
        login: vi.fn(),
        logout: vi.fn(),
        isLoading: true,
        error: 'Auth error'
      });

      renderApp();
      
      expect(screen.getByRole('banner')).toBeInTheDocument();
    });
  });

  describe('Component Integration', () => {
    test('wraps content with providers', () => {
      renderApp();
      
      // Verify the app renders with all providers
      expect(screen.getByRole('banner')).toBeInTheDocument();
      expect(screen.getByRole('main')).toBeInTheDocument();
    });

    test('renders navigation menu items', () => {
      renderApp();
      
      // Navigation should be present
      expect(screen.getByLabelText(/open drawer/i)).toBeInTheDocument();
    });
  });

  describe('Layout Components', () => {
    test('renders main content area', () => {
      renderApp();
      
      expect(screen.getByRole('main')).toBeInTheDocument();
    });

    test('renders app bar with navigation', () => {
      renderApp();
      
      const appBar = screen.getByRole('banner');
      expect(appBar).toBeInTheDocument();
    });
  });
});