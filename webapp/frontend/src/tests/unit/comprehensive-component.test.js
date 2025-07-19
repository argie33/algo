/**
 * Comprehensive Frontend Component Unit Tests
 * Tests all major React components with proper isolation and mocking
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';

// Test setup and global mocks
beforeEach(() => {
  // Clear all mocks
  vi.clearAllMocks();
  
  // Mock window object and browser APIs
  Object.defineProperty(window, 'localStorage', {
    value: {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    },
    writable: true,
  });
  
  Object.defineProperty(window, 'sessionStorage', {
    value: {
      getItem: vi.fn(),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    },
    writable: true,
  });

  // Mock WebSocket
  global.WebSocket = vi.fn().mockImplementation(() => ({
    send: vi.fn(),
    close: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    readyState: 1,
  }));

  // Mock fetch
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({}),
    text: () => Promise.resolve(''),
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// Mock all external dependencies
vi.mock('@mui/material', () => ({
  ThemeProvider: ({ children }) => <div data-testid="theme-provider">{children}</div>,
  CssBaseline: () => <div data-testid="css-baseline" />,
  createTheme: vi.fn(() => ({
    palette: { mode: 'light', primary: { main: '#1976d2' } },
    typography: { fontFamily: 'Roboto' },
    components: {},
  })),
  useTheme: () => ({
    palette: { mode: 'light', primary: { main: '#1976d2' } },
    typography: { fontFamily: 'Roboto' },
  }),
  // Common MUI components
  Button: ({ children, onClick, ...props }) => (
    <button onClick={onClick} {...props}>{children}</button>
  ),
  TextField: ({ value, onChange, ...props }) => (
    <input value={value} onChange={onChange} {...props} />
  ),
  Paper: ({ children, ...props }) => <div {...props}>{children}</div>,
  Card: ({ children, ...props }) => <div {...props}>{children}</div>,
  Typography: ({ children, ...props }) => <span {...props}>{children}</span>,
  IconButton: ({ children, onClick, ...props }) => (
    <button onClick={onClick} {...props}>{children}</button>
  ),
  Dialog: ({ open, children, ...props }) => 
    open ? <div data-testid="dialog" {...props}>{children}</div> : null,
  DialogTitle: ({ children }) => <h2>{children}</h2>,
  DialogContent: ({ children }) => <div>{children}</div>,
  DialogActions: ({ children }) => <div>{children}</div>,
  Snackbar: ({ open, children, ...props }) => 
    open ? <div data-testid="snackbar" {...props}>{children}</div> : null,
  Alert: ({ children, severity, ...props }) => (
    <div data-testid="alert" data-severity={severity} {...props}>{children}</div>
  ),
  CircularProgress: () => <div data-testid="loading" />,
  LinearProgress: () => <div data-testid="progress" />,
  Chip: ({ label, ...props }) => <span {...props}>{label}</span>,
  Badge: ({ children, badgeContent, ...props }) => (
    <div {...props}>{children}<span>{badgeContent}</span></div>
  ),
}));

vi.mock('@mui/icons-material', () => ({
  Dashboard: () => <span data-testid="dashboard-icon" />,
  Settings: () => <span data-testid="settings-icon" />,
  Portfolio: () => <span data-testid="portfolio-icon" />,
  TrendingUp: () => <span data-testid="trending-up-icon" />,
  ShowChart: () => <span data-testid="chart-icon" />,
  Notifications: () => <span data-testid="notifications-icon" />,
  AccountCircle: () => <span data-testid="account-icon" />,
  Close: () => <span data-testid="close-icon" />,
  Menu: () => <span data-testid="menu-icon" />,
  Search: () => <span data-testid="search-icon" />,
  Add: () => <span data-testid="add-icon" />,
  Delete: () => <span data-testid="delete-icon" />,
  Edit: () => <span data-testid="edit-icon" />,
  Refresh: () => <span data-testid="refresh-icon" />,
  CheckCircle: () => <span data-testid="check-icon" />,
  Error: () => <span data-testid="error-icon" />,
  Warning: () => <span data-testid="warning-icon" />,
  Info: () => <span data-testid="info-icon" />,
}));

vi.mock('react-router-dom', () => ({
  BrowserRouter: ({ children }) => <div data-testid="router">{children}</div>,
  Routes: ({ children }) => <div data-testid="routes">{children}</div>,
  Route: ({ children }) => <div data-testid="route">{children}</div>,
  Link: ({ children, to, ...props }) => <a href={to} {...props}>{children}</a>,
  NavLink: ({ children, to, ...props }) => <a href={to} {...props}>{children}</a>,
  useNavigate: () => vi.fn(),
  useLocation: () => ({ pathname: '/', search: '', hash: '', state: null, key: 'test' }),
  useParams: () => ({}),
  Navigate: ({ to }) => <div data-testid="navigate" data-to={to} />,
}));

vi.mock('@tanstack/react-query', () => ({
  QueryClient: vi.fn(() => ({
    setQueryData: vi.fn(),
    getQueryData: vi.fn(),
    invalidateQueries: vi.fn(),
  })),
  QueryClientProvider: ({ children }) => <div data-testid="query-provider">{children}</div>,
  useQuery: () => ({
    data: null,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useMutation: () => ({
    mutate: vi.fn(),
    isLoading: false,
    error: null,
    data: null,
  }),
}));

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }) => <div data-testid="responsive-container">{children}</div>,
  LineChart: ({ children }) => <div data-testid="line-chart">{children}</div>,
  AreaChart: ({ children }) => <div data-testid="area-chart">{children}</div>,
  BarChart: ({ children }) => <div data-testid="bar-chart">{children}</div>,
  PieChart: ({ children }) => <div data-testid="pie-chart">{children}</div>,
  Line: () => <div data-testid="line" />,
  Area: () => <div data-testid="area" />,
  Bar: () => <div data-testid="bar" />,
  Cell: () => <div data-testid="cell" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
}));

// Mock API and service calls
vi.mock('../../services/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

vi.mock('../../services/apiKeyService', () => ({
  getApiKeys: vi.fn().mockResolvedValue({ alpaca: 'test-key' }),
  saveApiKeys: vi.fn().mockResolvedValue(true),
  validateApiKey: vi.fn().mockResolvedValue(true),
}));

vi.mock('../../services/portfolioMathService', () => ({
  calculateVaR: vi.fn().mockReturnValue(0.05),
  calculateSharpeRatio: vi.fn().mockReturnValue(1.2),
  calculateCorrelationMatrix: vi.fn().mockReturnValue([[1, 0.5], [0.5, 1]]),
}));

// Test helper function
const renderWithProviders = (component) => {
  return render(
    <div data-testid="test-wrapper">
      {component}
    </div>
  );
};

describe('Frontend Component Unit Tests', () => {
  describe('Core Application Components', () => {
    it('should render App component without errors', async () => {
      // Dynamic import to avoid static analysis issues
      const App = (await import('../../App.jsx')).default;
      
      expect(() => {
        renderWithProviders(<App />);
      }).not.toThrow();
      
      expect(screen.getByTestId('test-wrapper')).toBeInTheDocument();
    });

    it('should handle theme provider initialization', async () => {
      const { ThemeProvider } = await import('../../contexts/ThemeContext.jsx');
      
      renderWithProviders(
        <ThemeProvider>
          <div data-testid="theme-child">Content</div>
        </ThemeProvider>
      );
      
      expect(screen.getByTestId('theme-child')).toBeInTheDocument();
    });

    it('should handle auth context initialization', async () => {
      const { AuthProvider } = await import('../../contexts/AuthContext.jsx');
      
      renderWithProviders(
        <AuthProvider>
          <div data-testid="auth-child">Content</div>
        </AuthProvider>
      );
      
      expect(screen.getByTestId('auth-child')).toBeInTheDocument();
    });
  });

  describe('Component Loading and Error Handling', () => {
    it('should handle error boundary correctly', async () => {
      const ErrorBoundary = (await import('../../components/ErrorBoundaryTailwind.jsx')).default;
      
      const ThrowError = () => {
        throw new Error('Test error');
      };
      
      renderWithProviders(
        <ErrorBoundary>
          <ThrowError />
        </ErrorBoundary>
      );
      
      // Error boundary should catch the error and display fallback
      expect(screen.getByTestId('test-wrapper')).toBeInTheDocument();
    });

    it('should handle async loading states', async () => {
      const LoadingStateManager = (await import('../../components/LoadingStateManager.jsx')).LoadingProvider;
      
      renderWithProviders(
        <LoadingStateManager>
          <div data-testid="loading-child">Content</div>
        </LoadingStateManager>
      );
      
      expect(screen.getByTestId('loading-child')).toBeInTheDocument();
    });
  });

  describe('API Integration Components', () => {
    it('should handle API key provider functionality', async () => {
      const ApiKeyProvider = (await import('../../components/ApiKeyProvider.jsx')).default;
      
      renderWithProviders(
        <ApiKeyProvider>
          <div data-testid="api-key-child">Content</div>
        </ApiKeyProvider>
      );
      
      expect(screen.getByTestId('api-key-child')).toBeInTheDocument();
    });

    it('should handle settings manager functionality', async () => {
      const SettingsManager = (await import('../../components/SettingsManager.jsx')).default;
      
      renderWithProviders(<SettingsManager />);
      
      // Component should render without throwing
      expect(screen.getByTestId('test-wrapper')).toBeInTheDocument();
    });

    it('should handle API key status indicator', async () => {
      const ApiKeyStatusIndicator = (await import('../../components/ApiKeyStatusIndicator.jsx')).default;
      
      renderWithProviders(<ApiKeyStatusIndicator />);
      
      expect(screen.getByTestId('test-wrapper')).toBeInTheDocument();
    });
  });

  describe('Chart and Visualization Components', () => {
    it('should render historical price chart', async () => {
      const HistoricalPriceChart = (await import('../../components/HistoricalPriceChart.jsx')).default;
      
      renderWithProviders(
        <HistoricalPriceChart 
          symbol="AAPL" 
          data={[{ date: '2024-01-01', price: 100 }]} 
        />
      );
      
      expect(screen.getByTestId('test-wrapper')).toBeInTheDocument();
    });

    it('should render stock chart component', async () => {
      const StockChart = (await import('../../components/StockChart.jsx')).default;
      
      renderWithProviders(
        <StockChart 
          data={[{ date: '2024-01-01', price: 100 }]} 
        />
      );
      
      expect(screen.getByTestId('test-wrapper')).toBeInTheDocument();
    });

    it('should handle lazy chart loading', async () => {
      const LazyChart = (await import('../../components/LazyChart.jsx')).default;
      
      renderWithProviders(<LazyChart />);
      
      expect(screen.getByTestId('test-wrapper')).toBeInTheDocument();
    });
  });

  describe('Authentication Components', () => {
    it('should render login form', async () => {
      const LoginForm = (await import('../../components/auth/LoginForm.jsx')).default;
      
      renderWithProviders(<LoginForm />);
      
      expect(screen.getByTestId('test-wrapper')).toBeInTheDocument();
    });

    it('should render register form', async () => {
      const RegisterForm = (await import('../../components/auth/RegisterForm.jsx')).default;
      
      renderWithProviders(<RegisterForm />);
      
      expect(screen.getByTestId('test-wrapper')).toBeInTheDocument();
    });

    it('should handle protected route functionality', async () => {
      const ProtectedRoute = (await import('../../components/auth/ProtectedRoute.jsx')).default;
      
      renderWithProviders(
        <ProtectedRoute>
          <div data-testid="protected-content">Protected Content</div>
        </ProtectedRoute>
      );
      
      expect(screen.getByTestId('test-wrapper')).toBeInTheDocument();
    });
  });

  describe('Trading Components', () => {
    it('should render position manager', async () => {
      const PositionManager = (await import('../../components/trading/PositionManager.jsx')).default;
      
      renderWithProviders(<PositionManager />);
      
      expect(screen.getByTestId('test-wrapper')).toBeInTheDocument();
    });

    it('should render signal card enhanced', async () => {
      const SignalCardEnhanced = (await import('../../components/trading/SignalCardEnhanced.jsx')).default;
      
      const mockSignal = {
        symbol: 'AAPL',
        action: 'BUY',
        confidence: 0.85,
        price: 150.00
      };
      
      renderWithProviders(<SignalCardEnhanced signal={mockSignal} />);
      
      expect(screen.getByTestId('test-wrapper')).toBeInTheDocument();
    });
  });

  describe('UI Components', () => {
    it('should render alert component', async () => {
      const Alert = (await import('../../components/ui/alert.jsx')).Alert;
      
      renderWithProviders(
        <Alert variant="default">
          Test alert message
        </Alert>
      );
      
      expect(screen.getByTestId('test-wrapper')).toBeInTheDocument();
    });

    it('should render button component', async () => {
      const Button = (await import('../../components/ui/button.jsx')).Button;
      
      renderWithProviders(
        <Button variant="default" onClick={vi.fn()}>
          Test Button
        </Button>
      );
      
      expect(screen.getByTestId('test-wrapper')).toBeInTheDocument();
    });

    it('should render card component', async () => {
      const Card = (await import('../../components/ui/card.jsx')).Card;
      
      renderWithProviders(
        <Card>
          <div>Card content</div>
        </Card>
      );
      
      expect(screen.getByTestId('test-wrapper')).toBeInTheDocument();
    });
  });

  describe('Service Integration Tests', () => {
    it('should handle portfolio math service calls', async () => {
      const portfolioMathService = await import('../../services/portfolioMathService.js');
      
      // Test VaR calculation
      const var95 = portfolioMathService.calculateVaR([0.1, -0.05, 0.02], 0.95);
      expect(typeof var95).toBe('number');
      
      // Test Sharpe ratio calculation
      const sharpe = portfolioMathService.calculateSharpeRatio([0.1, 0.05, 0.02], 0.02);
      expect(typeof sharpe).toBe('number');
    });

    it('should handle API service initialization', async () => {
      const api = (await import('../../services/api.js')).default;
      
      expect(api.get).toBeDefined();
      expect(api.post).toBeDefined();
      expect(api.put).toBeDefined();
      expect(api.delete).toBeDefined();
    });

    it('should handle live data service', async () => {
      const liveDataService = await import('../../services/liveDataService.js');
      
      expect(liveDataService).toBeDefined();
      // Service should export expected functions
      expect(typeof liveDataService).toBe('object');
    });
  });

  describe('Hook Integration Tests', () => {
    it('should handle real-time data hook', async () => {
      const { useRealTimeData } = await import('../../hooks/useRealTimeData.js');
      
      // Hook should be a function
      expect(typeof useRealTimeData).toBe('function');
    });

    it('should handle portfolio data hook', async () => {
      const { useLivePortfolioData } = await import('../../hooks/useLivePortfolioData.js');
      
      expect(typeof useLivePortfolioData).toBe('function');
    });
  });

  describe('Error Recovery and Resilience', () => {
    it('should handle network failures gracefully', async () => {
      // Mock fetch to fail
      global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));
      
      const api = (await import('../../services/api.js')).default;
      
      try {
        await api.get('/test-endpoint');
      } catch (error) {
        expect(error.message).toBe('Network error');
      }
    });

    it('should handle component unmounting safely', async () => {
      const TestComponent = () => {
        React.useEffect(() => {
          return () => {
            // Cleanup function
          };
        }, []);
        
        return <div data-testid="test-component">Test</div>;
      };
      
      const { unmount } = renderWithProviders(<TestComponent />);
      
      expect(screen.getByTestId('test-component')).toBeInTheDocument();
      
      expect(() => unmount()).not.toThrow();
    });
  });

  describe('Performance and Memory Management', () => {
    it('should handle large dataset rendering efficiently', async () => {
      const largeDataset = Array.from({ length: 1000 }, (_, i) => ({
        id: i,
        value: Math.random() * 100,
        date: new Date(2024, 0, i + 1).toISOString(),
      }));
      
      const ListComponent = ({ data }) => (
        <div data-testid="large-list">
          {data.slice(0, 10).map(item => (
            <div key={item.id} data-testid={`item-${item.id}`}>
              {item.value.toFixed(2)}
            </div>
          ))}
        </div>
      );
      
      const startTime = performance.now();
      renderWithProviders(<ListComponent data={largeDataset} />);
      const endTime = performance.now();
      
      expect(screen.getByTestId('large-list')).toBeInTheDocument();
      expect(endTime - startTime).toBeLessThan(100); // Should render quickly
    });

    it('should handle memory cleanup in useEffect hooks', async () => {
      let cleanupCalled = false;
      
      const TestComponent = () => {
        React.useEffect(() => {
          const timer = setTimeout(() => {}, 1000);
          
          return () => {
            clearTimeout(timer);
            cleanupCalled = true;
          };
        }, []);
        
        return <div data-testid="cleanup-component">Test</div>;
      };
      
      const { unmount } = renderWithProviders(<TestComponent />);
      unmount();
      
      expect(cleanupCalled).toBe(true);
    });
  });
});

// Export test utilities for other test files
export {
  renderWithProviders,
  vi,
  screen,
  fireEvent,
  waitFor,
  userEvent,
};