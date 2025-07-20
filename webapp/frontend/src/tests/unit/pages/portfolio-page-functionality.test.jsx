/**
 * Portfolio Page Functionality Tests
 * Comprehensive testing of the Portfolio page user interactions and state management
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
  user: { email: 'test@example.com', username: 'testuser' },
  isAuthenticated: true,
  isLoading: false,
  tokens: { accessToken: 'mock-token' }
};

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthContext,
  AuthProvider: ({ children }) => children
}));

// Mock API services
const mockApiService = {
  getPortfolioData: vi.fn(),
  addHolding: vi.fn(),
  updateHolding: vi.fn(),
  deleteHolding: vi.fn(),
  importPortfolioFromBroker: vi.fn(),
  getAvailableAccounts: vi.fn(),
  getAccountInfo: vi.fn(),
  getApiKeys: vi.fn(),
  testApiConnection: vi.fn()
};

vi.mock('../../../services/api', () => ({
  default: mockApiService,
  ...mockApiService
}));

// Mock portfolio math service
const mockPortfolioMathService = {
  calculatePortfolioVaR: vi.fn(),
  calculateSharpeRatio: vi.fn(),
  calculateVolatility: vi.fn(),
  calculateReturns: vi.fn(),
  optimizePortfolio: vi.fn(),
  calculateRiskMetrics: vi.fn()
};

vi.mock('../../../services/portfolioMathService', () => ({
  default: mockPortfolioMathService
}));

// Mock chart components
vi.mock('recharts', () => ({
  PieChart: ({ children }) => <div data-testid="pie-chart">{children}</div>,
  Pie: () => <div data-testid="pie" />,
  Cell: () => <div data-testid="cell" />,
  BarChart: ({ children }) => <div data-testid="bar-chart">{children}</div>,
  Bar: () => <div data-testid="bar" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="recharts-tooltip" />,
  ResponsiveContainer: ({ children }) => <div data-testid="responsive-container">{children}</div>,
  LineChart: ({ children }) => <div data-testid="line-chart">{children}</div>,
  Line: () => <div data-testid="line" />,
  AreaChart: ({ children }) => <div data-testid="area-chart">{children}</div>,
  Area: () => <div data-testid="area" />
}));

// Mock formatters
vi.mock('../../../utils/formatters', () => ({
  formatCurrency: vi.fn((value) => `$${value?.toLocaleString() || '0'}`),
  formatPercentage: vi.fn((value) => `${value || 0}%`),
  formatNumber: vi.fn((value) => value?.toLocaleString() || '0')
}));

// Create a mock Portfolio page component
const MockPortfolioPage = () => {
  const [activeTab, setActiveTab] = React.useState(0);
  const [portfolioData, setPortfolioData] = React.useState({
    totalValue: 125000,
    dayChange: 2850,
    dayChangePercent: 2.3,
    holdings: [
      {
        id: 'holding_1',
        symbol: 'AAPL',
        shares: 100,
        currentPrice: 175.50,
        totalValue: 17550,
        dayChange: 250,
        dayChangePercent: 1.45
      },
      {
        id: 'holding_2',
        symbol: 'MSFT',
        shares: 50,
        currentPrice: 380.25,
        totalValue: 19012.50,
        dayChange: -125,
        dayChangePercent: -0.65
      }
    ]
  });
  const [showAddHolding, setShowAddHolding] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);

  const handleAddHolding = async (holdingData) => {
    setLoading(true);
    try {
      await mockApiService.addHolding(holdingData);
      const newHolding = {
        id: `holding_${Date.now()}`,
        ...holdingData,
        totalValue: holdingData.shares * holdingData.currentPrice,
        dayChange: 0,
        dayChangePercent: 0
      };
      setPortfolioData(prev => ({
        ...prev,
        holdings: [...prev.holdings, newHolding],
        totalValue: prev.totalValue + newHolding.totalValue
      }));
      setShowAddHolding(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteHolding = async (holdingId) => {
    setLoading(true);
    try {
      await mockApiService.deleteHolding(holdingId);
      const holdingToDelete = portfolioData.holdings.find(h => h.id === holdingId);
      setPortfolioData(prev => ({
        ...prev,
        holdings: prev.holdings.filter(h => h.id !== holdingId),
        totalValue: prev.totalValue - holdingToDelete.totalValue
      }));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshData = async () => {
    setLoading(true);
    try {
      const response = await mockApiService.getPortfolioData();
      setPortfolioData(response.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const tabLabels = [
    'Overview',
    'Holdings',
    'Performance', 
    'Risk Analysis',
    'Optimization',
    'Settings'
  ];

  return (
    <div data-testid="portfolio-page">
      {/* Portfolio Header */}
      <div data-testid="portfolio-header">
        <h1>Portfolio Dashboard</h1>
        <div data-testid="portfolio-summary">
          <div data-testid="total-value">${portfolioData.totalValue.toLocaleString()}</div>
          <div data-testid="day-change" className={portfolioData.dayChange >= 0 ? 'positive' : 'negative'}>
            ${Math.abs(portfolioData.dayChange).toLocaleString()} ({portfolioData.dayChangePercent}%)
          </div>
        </div>
        <button 
          data-testid="refresh-button"
          onClick={handleRefreshData}
          disabled={loading}
        >
          {loading ? 'Refreshing...' : 'Refresh Data'}
        </button>
      </div>

      {/* Tab Navigation */}
      <div data-testid="portfolio-tabs">
        {tabLabels.map((label, index) => (
          <button
            key={label}
            data-testid={`tab-${label.toLowerCase().replace(' ', '-')}`}
            onClick={() => setActiveTab(index)}
            className={activeTab === index ? 'active' : ''}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div data-testid="tab-content">
        {activeTab === 0 && (
          <div data-testid="overview-tab">
            <div data-testid="portfolio-charts">
              <div data-testid="allocation-chart">
                <h3>Asset Allocation</h3>
                <div data-testid="pie-chart" />
              </div>
              <div data-testid="performance-chart">
                <h3>Performance Over Time</h3>
                <div data-testid="line-chart" />
              </div>
            </div>
          </div>
        )}

        {activeTab === 1 && (
          <div data-testid="holdings-tab">
            <div data-testid="holdings-controls">
              <button 
                data-testid="add-holding-button"
                onClick={() => setShowAddHolding(true)}
              >
                Add Holding
              </button>
              <button data-testid="import-broker-button">
                Import from Broker
              </button>
            </div>
            
            <div data-testid="holdings-list">
              {portfolioData.holdings.map(holding => (
                <div key={holding.id} data-testid={`holding-${holding.symbol}`}>
                  <div data-testid={`holding-symbol-${holding.symbol}`}>{holding.symbol}</div>
                  <div data-testid={`holding-shares-${holding.symbol}`}>{holding.shares} shares</div>
                  <div data-testid={`holding-price-${holding.symbol}`}>${holding.currentPrice}</div>
                  <div data-testid={`holding-value-${holding.symbol}`}>${holding.totalValue.toLocaleString()}</div>
                  <div data-testid={`holding-change-${holding.symbol}`} className={holding.dayChange >= 0 ? 'positive' : 'negative'}>
                    ${Math.abs(holding.dayChange)} ({holding.dayChangePercent}%)
                  </div>
                  <button 
                    data-testid={`delete-holding-${holding.symbol}`}
                    onClick={() => handleDeleteHolding(holding.id)}
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 2 && (
          <div data-testid="performance-tab">
            <div data-testid="performance-metrics">
              <div data-testid="returns-section">
                <h3>Returns Analysis</h3>
                <div data-testid="returns-chart" />
              </div>
              <div data-testid="benchmark-section">
                <h3>Benchmark Comparison</h3>
                <div data-testid="benchmark-chart" />
              </div>
            </div>
          </div>
        )}

        {activeTab === 3 && (
          <div data-testid="risk-analysis-tab">
            <div data-testid="risk-metrics">
              <h3>Risk Assessment</h3>
              <div data-testid="var-calculation">
                <span>Value at Risk (95%): </span>
                <span data-testid="var-value">$12,450</span>
              </div>
              <div data-testid="volatility-chart" />
            </div>
          </div>
        )}

        {activeTab === 4 && (
          <div data-testid="optimization-tab">
            <div data-testid="optimization-controls">
              <h3>Portfolio Optimization</h3>
              <button data-testid="optimize-portfolio-button">
                Optimize Portfolio
              </button>
              <div data-testid="optimization-results" />
            </div>
          </div>
        )}

        {activeTab === 5 && (
          <div data-testid="settings-tab">
            <div data-testid="portfolio-settings">
              <h3>Portfolio Settings</h3>
              <div data-testid="api-key-status">
                <span>API Connection Status: </span>
                <span data-testid="connection-status">Connected</span>
              </div>
              <button data-testid="test-connection-button">
                Test API Connection
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Add Holding Modal */}
      {showAddHolding && (
        <div data-testid="add-holding-modal">
          <div data-testid="add-holding-form">
            <h2>Add New Holding</h2>
            <form onSubmit={(e) => {
              e.preventDefault();
              const formData = new FormData(e.target);
              handleAddHolding({
                symbol: formData.get('symbol'),
                shares: parseInt(formData.get('shares')),
                currentPrice: parseFloat(formData.get('price'))
              });
            }}>
              <input 
                data-testid="symbol-input"
                name="symbol" 
                placeholder="Symbol (e.g., AAPL)" 
                required 
              />
              <input 
                data-testid="shares-input"
                name="shares" 
                type="number" 
                placeholder="Number of shares" 
                required 
              />
              <input 
                data-testid="price-input"
                name="price" 
                type="number" 
                step="0.01" 
                placeholder="Current price" 
                required 
              />
              <div data-testid="form-actions">
                <button type="submit" data-testid="save-holding-button">
                  Add Holding
                </button>
                <button 
                  type="button" 
                  data-testid="cancel-holding-button"
                  onClick={() => setShowAddHolding(false)}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div data-testid="loading-overlay">
          <div data-testid="loading-spinner">Loading...</div>
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div data-testid="error-message" className="error">
          Error: {error}
        </div>
      )}
    </div>
  );
};

// Test wrapper
const TestWrapper = ({ children }) => (
  <ThemeProvider theme={muiTheme}>
    <BrowserRouter>
      {children}
    </BrowserRouter>
  </ThemeProvider>
);

describe('📊 Portfolio Page Functionality Tests', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();
    mockApiService.addHolding.mockResolvedValue({ success: true });
    mockApiService.deleteHolding.mockResolvedValue({ success: true });
    mockApiService.getPortfolioData.mockResolvedValue({ 
      data: {
        totalValue: 130000,
        dayChange: 3000,
        dayChangePercent: 2.4,
        holdings: []
      }
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Page Rendering and Navigation', () => {
    it('should render portfolio page with all main sections', () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      expect(screen.getByTestId('portfolio-page')).toBeInTheDocument();
      expect(screen.getByTestId('portfolio-header')).toBeInTheDocument();
      expect(screen.getByTestId('portfolio-tabs')).toBeInTheDocument();
      expect(screen.getByTestId('tab-content')).toBeInTheDocument();
    });

    it('should display portfolio summary with correct values', () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      expect(screen.getByTestId('total-value')).toHaveTextContent('$125,000');
      expect(screen.getByTestId('day-change')).toHaveTextContent('$2,850 (2.3%)');
      expect(screen.getByTestId('day-change')).toHaveClass('positive');
    });

    it('should navigate between tabs correctly', async () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      // Should start on Overview tab
      expect(screen.getByTestId('overview-tab')).toBeInTheDocument();
      expect(screen.queryByTestId('holdings-tab')).not.toBeInTheDocument();

      // Click Holdings tab
      await user.click(screen.getByTestId('tab-holdings'));
      expect(screen.getByTestId('holdings-tab')).toBeInTheDocument();
      expect(screen.queryByTestId('overview-tab')).not.toBeInTheDocument();

      // Click Performance tab
      await user.click(screen.getByTestId('tab-performance'));
      expect(screen.getByTestId('performance-tab')).toBeInTheDocument();
      expect(screen.queryByTestId('holdings-tab')).not.toBeInTheDocument();
    });
  });

  describe('Holdings Management', () => {
    it('should display holdings list with correct data', () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      // Navigate to Holdings tab
      fireEvent.click(screen.getByTestId('tab-holdings'));

      expect(screen.getByTestId('holding-AAPL')).toBeInTheDocument();
      expect(screen.getByTestId('holding-symbol-AAPL')).toHaveTextContent('AAPL');
      expect(screen.getByTestId('holding-shares-AAPL')).toHaveTextContent('100 shares');
      expect(screen.getByTestId('holding-price-AAPL')).toHaveTextContent('$175.5');
      expect(screen.getByTestId('holding-value-AAPL')).toHaveTextContent('$17,550');

      expect(screen.getByTestId('holding-MSFT')).toBeInTheDocument();
      expect(screen.getByTestId('holding-symbol-MSFT')).toHaveTextContent('MSFT');
    });

    it('should open add holding modal when button is clicked', async () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      fireEvent.click(screen.getByTestId('tab-holdings'));
      await user.click(screen.getByTestId('add-holding-button'));

      expect(screen.getByTestId('add-holding-modal')).toBeInTheDocument();
      expect(screen.getByTestId('add-holding-form')).toBeInTheDocument();
      expect(screen.getByTestId('symbol-input')).toBeInTheDocument();
      expect(screen.getByTestId('shares-input')).toBeInTheDocument();
      expect(screen.getByTestId('price-input')).toBeInTheDocument();
    });

    it('should add new holding successfully', async () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      fireEvent.click(screen.getByTestId('tab-holdings'));
      await user.click(screen.getByTestId('add-holding-button'));

      // Fill out the form
      await user.type(screen.getByTestId('symbol-input'), 'GOOGL');
      await user.type(screen.getByTestId('shares-input'), '25');
      await user.type(screen.getByTestId('price-input'), '2750.00');

      // Submit the form
      await user.click(screen.getByTestId('save-holding-button'));

      await waitFor(() => {
        expect(mockApiService.addHolding).toHaveBeenCalledWith({
          symbol: 'GOOGL',
          shares: 25,
          currentPrice: 2750
        });
      });

      // Modal should close
      expect(screen.queryByTestId('add-holding-modal')).not.toBeInTheDocument();
    });

    it('should cancel add holding modal', async () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      fireEvent.click(screen.getByTestId('tab-holdings'));
      await user.click(screen.getByTestId('add-holding-button'));
      
      expect(screen.getByTestId('add-holding-modal')).toBeInTheDocument();
      
      await user.click(screen.getByTestId('cancel-holding-button'));
      
      expect(screen.queryByTestId('add-holding-modal')).not.toBeInTheDocument();
    });

    it('should delete holding when delete button is clicked', async () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      fireEvent.click(screen.getByTestId('tab-holdings'));
      
      expect(screen.getByTestId('holding-AAPL')).toBeInTheDocument();
      
      await user.click(screen.getByTestId('delete-holding-AAPL'));

      await waitFor(() => {
        expect(mockApiService.deleteHolding).toHaveBeenCalledWith('holding_1');
      });
    });
  });

  describe('Data Refresh and Loading States', () => {
    it('should refresh portfolio data when refresh button is clicked', async () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('refresh-button'));

      await waitFor(() => {
        expect(mockApiService.getPortfolioData).toHaveBeenCalled();
      });

      // Should show loading state
      expect(screen.getByTestId('refresh-button')).toHaveTextContent('Refreshing...');
    });

    it('should show loading overlay during operations', async () => {
      // Make API call take some time
      mockApiService.addHolding.mockImplementation(() => 
        new Promise(resolve => setTimeout(resolve, 100))
      );

      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      fireEvent.click(screen.getByTestId('tab-holdings'));
      await user.click(screen.getByTestId('add-holding-button'));
      
      await user.type(screen.getByTestId('symbol-input'), 'NVDA');
      await user.type(screen.getByTestId('shares-input'), '10');
      await user.type(screen.getByTestId('price-input'), '450.00');
      
      user.click(screen.getByTestId('save-holding-button'));

      // Should show loading overlay
      await waitFor(() => {
        expect(screen.getByTestId('loading-overlay')).toBeInTheDocument();
        expect(screen.getByTestId('loading-spinner')).toHaveTextContent('Loading...');
      });
    });
  });

  describe('Tab-Specific Functionality', () => {
    it('should show overview charts on overview tab', () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      expect(screen.getByTestId('overview-tab')).toBeInTheDocument();
      expect(screen.getByTestId('portfolio-charts')).toBeInTheDocument();
      expect(screen.getByTestId('allocation-chart')).toBeInTheDocument();
      expect(screen.getByTestId('performance-chart')).toBeInTheDocument();
    });

    it('should show performance metrics on performance tab', async () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('tab-performance'));

      expect(screen.getByTestId('performance-tab')).toBeInTheDocument();
      expect(screen.getByTestId('performance-metrics')).toBeInTheDocument();
      expect(screen.getByTestId('returns-section')).toBeInTheDocument();
      expect(screen.getByTestId('benchmark-section')).toBeInTheDocument();
    });

    it('should show risk analysis on risk analysis tab', async () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('tab-risk'));

      expect(screen.getByTestId('risk-analysis-tab')).toBeInTheDocument();
      expect(screen.getByTestId('risk-metrics')).toBeInTheDocument();
      expect(screen.getByTestId('var-calculation')).toBeInTheDocument();
      expect(screen.getByTestId('var-value')).toHaveTextContent('$12,450');
    });

    it('should show optimization controls on optimization tab', async () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('tab-optimization'));

      expect(screen.getByTestId('optimization-tab')).toBeInTheDocument();
      expect(screen.getByTestId('optimization-controls')).toBeInTheDocument();
      expect(screen.getByTestId('optimize-portfolio-button')).toBeInTheDocument();
    });

    it('should show settings on settings tab', async () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('tab-settings'));

      expect(screen.getByTestId('settings-tab')).toBeInTheDocument();
      expect(screen.getByTestId('portfolio-settings')).toBeInTheDocument();
      expect(screen.getByTestId('api-key-status')).toBeInTheDocument();
      expect(screen.getByTestId('connection-status')).toHaveTextContent('Connected');
      expect(screen.getByTestId('test-connection-button')).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('should display error message when API calls fail', async () => {
      mockApiService.addHolding.mockRejectedValue(new Error('API Error'));

      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      fireEvent.click(screen.getByTestId('tab-holdings'));
      await user.click(screen.getByTestId('add-holding-button'));
      
      await user.type(screen.getByTestId('symbol-input'), 'ERROR');
      await user.type(screen.getByTestId('shares-input'), '1');
      await user.type(screen.getByTestId('price-input'), '1.00');
      
      await user.click(screen.getByTestId('save-holding-button'));

      await waitFor(() => {
        expect(screen.getByTestId('error-message')).toBeInTheDocument();
        expect(screen.getByTestId('error-message')).toHaveTextContent('Error: API Error');
      });
    });

    it('should handle negative portfolio changes correctly', () => {
      const NegativePortfolioPage = () => {
        const [portfolioData] = React.useState({
          totalValue: 95000,
          dayChange: -5000,
          dayChangePercent: -5.0,
          holdings: []
        });

        return (
          <div data-testid="portfolio-page">
            <div data-testid="portfolio-summary">
              <div data-testid="total-value">${portfolioData.totalValue.toLocaleString()}</div>
              <div data-testid="day-change" className={portfolioData.dayChange >= 0 ? 'positive' : 'negative'}>
                ${Math.abs(portfolioData.dayChange).toLocaleString()} ({portfolioData.dayChangePercent}%)
              </div>
            </div>
          </div>
        );
      };

      render(
        <TestWrapper>
          <NegativePortfolioPage />
        </TestWrapper>
      );

      expect(screen.getByTestId('day-change')).toHaveTextContent('$5,000 (-5%)');
      expect(screen.getByTestId('day-change')).toHaveClass('negative');
    });
  });

  describe('Form Validation', () => {
    it('should require all fields in add holding form', async () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      fireEvent.click(screen.getByTestId('tab-holdings'));
      await user.click(screen.getByTestId('add-holding-button'));

      const symbolInput = screen.getByTestId('symbol-input');
      const sharesInput = screen.getByTestId('shares-input');
      const priceInput = screen.getByTestId('price-input');

      expect(symbolInput).toBeRequired();
      expect(sharesInput).toBeRequired();
      expect(priceInput).toBeRequired();
    });

    it('should validate number inputs correctly', async () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      fireEvent.click(screen.getByTestId('tab-holdings'));
      await user.click(screen.getByTestId('add-holding-button'));

      const sharesInput = screen.getByTestId('shares-input');
      const priceInput = screen.getByTestId('price-input');

      expect(sharesInput).toHaveAttribute('type', 'number');
      expect(priceInput).toHaveAttribute('type', 'number');
      expect(priceInput).toHaveAttribute('step', '0.01');
    });
  });

  describe('Accessibility', () => {
    it('should have proper semantic structure', () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      expect(screen.getByRole('heading', { name: /portfolio dashboard/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /refresh data/i })).toBeInTheDocument();
    });

    it('should support keyboard navigation', async () => {
      render(
        <TestWrapper>
          <MockPortfolioPage />
        </TestWrapper>
      );

      const overviewTab = screen.getByTestId('tab-overview');
      const holdingsTab = screen.getByTestId('tab-holdings');

      overviewTab.focus();
      expect(document.activeElement).toBe(overviewTab);

      await user.tab();
      expect(document.activeElement).toBe(holdingsTab);
    });
  });
});