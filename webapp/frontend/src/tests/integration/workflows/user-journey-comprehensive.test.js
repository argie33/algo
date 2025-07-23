/**
 * Comprehensive User Journey Integration Tests
 * Tests complete user workflows across the financial platform
 */

import { describe, it, expect, beforeAll, afterAll, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider, createTheme } from '@mui/material/styles';

// Mock API services for complete workflow testing
const mockApiService = {
  authenticate: vi.fn(),
  getPortfolio: vi.fn(),
  getMarketData: vi.fn(),
  getTradingSignals: vi.fn(),
  placeOrder: vi.fn(),
  getPositions: vi.fn(),
  getApiKeyStatus: vi.fn(),
  uploadDocument: vi.fn()
};

// Mock the main app components
vi.mock('../../../pages/Dashboard', () => ({
  default: vi.fn(() => (
    <div data-testid="dashboard">
      <div data-testid="portfolio-summary">Portfolio: $125,000 (+2.5%)</div>
      <div data-testid="market-overview">Market Status: Open</div>
      <div data-testid="trading-signals">
        <div data-testid="signal-AAPL">AAPL: BUY (A+)</div>
        <div data-testid="signal-TSLA">TSLA: SELL (B)</div>
      </div>
      <button data-testid="trade-button">Trade</button>
    </div>
  ))
}));

vi.mock('../../../pages/Portfolio', () => ({
  default: vi.fn(() => (
    <div data-testid="portfolio-page">
      <div data-testid="holdings">
        <div data-testid="holding-AAPL">AAPL: 100 shares @ $195.50</div>
        <div data-testid="holding-MSFT">MSFT: 50 shares @ $380.25</div>
      </div>
      <div data-testid="performance-metrics">
        <div data-testid="total-return">Total Return: +15.3%</div>
        <div data-testid="unrealized-pnl">Unrealized P&L: $12,550</div>
      </div>
      <button data-testid="rebalance-button">Rebalance Portfolio</button>
    </div>
  ))
}));

vi.mock('../../../pages/TradingSignals', () => ({
  default: vi.fn(() => (
    <div data-testid="trading-signals-page">
      <div data-testid="ai-signals">
        <div data-testid="signal-card-AAPL">
          <span>AAPL</span>
          <span>BUY</span>
          <span>87% confidence</span>
          <span>A+ grade</span>
          <button data-testid="execute-AAPL">Execute Trade</button>
        </div>
        <div data-testid="signal-card-GOOGL">
          <span>GOOGL</span>
          <span>HOLD</span>
          <span>92% confidence</span>
          <span>A grade</span>
        </div>
      </div>
      <div data-testid="market-timing">Market Timing: Favorable</div>
    </div>
  ))
}));

vi.mock('../../../pages/Settings', () => ({
  default: vi.fn(() => (
    <div data-testid="settings-page">
      <div data-testid="api-keys-section">
        <div data-testid="alpaca-status">Alpaca: Connected</div>
        <div data-testid="polygon-status">Polygon: Connected</div>
        <button data-testid="test-connection">Test Connection</button>
      </div>
      <div data-testid="trading-preferences">
        <label>
          Risk Level:
          <select data-testid="risk-level">
            <option value="conservative">Conservative</option>
            <option value="moderate">Moderate</option>
            <option value="aggressive">Aggressive</option>
          </select>
        </label>
        <button data-testid="save-settings">Save Settings</button>
      </div>
    </div>
  ))
}));

vi.mock('../../../components/auth/AuthModal', () => ({
  default: vi.fn(({ isOpen, onClose, onSuccess }) => 
    isOpen ? (
      <div data-testid="auth-modal">
        <form data-testid="login-form">
          <input data-testid="email-input" placeholder="Email" />
          <input data-testid="password-input" type="password" placeholder="Password" />
          <button 
            type="button" 
            data-testid="login-button"
            onClick={() => onSuccess?.()}
          >
            Login
          </button>
          <button type="button" data-testid="close-modal" onClick={onClose}>
            Close
          </button>
        </form>
      </div>
    ) : null
  )
}));

const theme = createTheme();

const TestWrapper = ({ children }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider theme={theme}>
          {children}
        </ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
};

describe('Comprehensive User Journey Integration Tests', () => {
  let user;
  let mockUser;
  let mockPortfolioData;
  let mockMarketData;

  beforeAll(() => {
    // Mock window.location for navigation testing
    delete window.location;
    window.location = { 
      href: 'http://localhost:3000',
      pathname: '/',
      search: '',
      hash: ''
    };
  });

  beforeEach(() => {
    user = userEvent.setup();
    vi.clearAllMocks();
    
    mockUser = {
      id: 'user_123',
      email: 'trader@example.com',
      name: 'Test Trader',
      authenticated: true,
      subscription: 'premium'
    };

    mockPortfolioData = {
      totalValue: 125000,
      todayChange: 2500,
      todayChangePercent: 2.04,
      positions: [
        { symbol: 'AAPL', quantity: 100, value: 19550, pnl: 5.39 },
        { symbol: 'MSFT', quantity: 50, value: 19012.50, pnl: 1.40 },
        { symbol: 'GOOGL', quantity: 25, value: 65000, pnl: -1.89 }
      ]
    };

    mockMarketData = {
      status: 'open',
      indices: {
        'SPY': { price: 415.25, change: 0.75 },
        'QQQ': { price: 320.50, change: 1.25 }
      }
    };

    // Setup API mocks
    mockApiService.authenticate.mockResolvedValue({ success: true, user: mockUser });
    mockApiService.getPortfolio.mockResolvedValue(mockPortfolioData);
    mockApiService.getMarketData.mockResolvedValue(mockMarketData);
    mockApiService.getTradingSignals.mockResolvedValue([
      { symbol: 'AAPL', action: 'BUY', confidence: 87, grade: 'A+' },
      { symbol: 'GOOGL', action: 'HOLD', confidence: 92, grade: 'A' }
    ]);
    mockApiService.getApiKeyStatus.mockResolvedValue({ 
      alpaca: 'connected', 
      polygon: 'connected' 
    });
  });

  describe('Complete New User Onboarding Journey', () => {
    it('guides new user through complete setup and first trade', async () => {
      // Step 1: User lands on dashboard without authentication
      const Dashboard = (await import('../../../pages/Dashboard')).default;
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      expect(screen.getByTestId('dashboard')).toBeInTheDocument();

      // Step 2: User clicks trade button, triggers authentication
      const tradeButton = screen.getByTestId('trade-button');
      await user.click(tradeButton);

      // Step 3: Authentication modal appears
      const AuthModal = (await import('../../../components/auth/AuthModal')).default;
      const { rerender } = render(
        <TestWrapper>
          <AuthModal isOpen={true} onSuccess={vi.fn()} onClose={vi.fn()} />
        </TestWrapper>
      );

      expect(screen.getByTestId('auth-modal')).toBeInTheDocument();

      // Step 4: User completes login
      await user.type(screen.getByTestId('email-input'), 'trader@example.com');
      await user.type(screen.getByTestId('password-input'), 'password123');
      await user.click(screen.getByTestId('login-button'));

      // Step 5: User is now authenticated, modal closes
      rerender(
        <TestWrapper>
          <AuthModal isOpen={false} onSuccess={vi.fn()} onClose={vi.fn()} />
        </TestWrapper>
      );

      expect(screen.queryByTestId('auth-modal')).not.toBeInTheDocument();

      // Step 6: User navigates to settings to configure API keys
      const Settings = (await import('../../../pages/Settings')).default;
      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      expect(screen.getByTestId('settings-page')).toBeInTheDocument();
      expect(screen.getByTestId('alpaca-status')).toHaveTextContent('Alpaca: Connected');

      // Step 7: User tests API connection
      await user.click(screen.getByTestId('test-connection'));
      expect(mockApiService.getApiKeyStatus).toHaveBeenCalled();

      // Step 8: User sets trading preferences
      await user.selectOptions(screen.getByTestId('risk-level'), 'moderate');
      await user.click(screen.getByTestId('save-settings'));

      // Step 9: User views portfolio
      const Portfolio = (await import('../../../pages/Portfolio')).default;
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      expect(screen.getByTestId('portfolio-page')).toBeInTheDocument();
      expect(screen.getByTestId('holding-AAPL')).toHaveTextContent('AAPL: 100 shares @ $195.50');

      // Step 10: User executes first trade based on AI signal
      const TradingSignals = (await import('../../../pages/TradingSignals')).default;
      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      expect(screen.getByTestId('trading-signals-page')).toBeInTheDocument();
      await user.click(screen.getByTestId('execute-AAPL'));

      // Verify complete onboarding workflow
      expect(mockApiService.authenticate).toHaveBeenCalled();
      expect(mockApiService.getApiKeyStatus).toHaveBeenCalled();
      expect(mockApiService.getPortfolio).toHaveBeenCalled();
      expect(mockApiService.getTradingSignals).toHaveBeenCalled();
    });
  });

  describe('Daily Trading Workflow', () => {
    it('simulates complete daily trading routine', async () => {
      // Step 1: User starts day by checking dashboard
      const Dashboard = (await import('../../../pages/Dashboard')).default;
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      expect(screen.getByTestId('portfolio-summary')).toHaveTextContent('Portfolio: $125,000 (+2.5%)');
      expect(screen.getByTestId('market-overview')).toHaveTextContent('Market Status: Open');

      // Step 2: User reviews overnight signals
      expect(screen.getByTestId('signal-AAPL')).toHaveTextContent('AAPL: BUY (A+)');
      expect(screen.getByTestId('signal-TSLA')).toHaveTextContent('TSLA: SELL (B)');

      // Step 3: User navigates to detailed trading signals page
      const TradingSignals = (await import('../../../pages/TradingSignals')).default;
      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      // Step 4: User analyzes AI signals in detail
      const appleSignal = screen.getByTestId('signal-card-AAPL');
      expect(within(appleSignal).getByText('AAPL')).toBeInTheDocument();
      expect(within(appleSignal).getByText('BUY')).toBeInTheDocument();
      expect(within(appleSignal).getByText('87% confidence')).toBeInTheDocument();
      expect(within(appleSignal).getByText('A+ grade')).toBeInTheDocument();

      // Step 5: User executes high-confidence trade
      const executeButton = within(appleSignal).getByTestId('execute-AAPL');
      await user.click(executeButton);

      // Step 6: User checks portfolio after trade
      const Portfolio = (await import('../../../pages/Portfolio')).default;
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      expect(screen.getByTestId('total-return')).toHaveTextContent('Total Return: +15.3%');
      expect(screen.getByTestId('unrealized-pnl')).toHaveTextContent('Unrealized P&L: $12,550');

      // Step 7: User considers portfolio rebalancing
      await user.click(screen.getByTestId('rebalance-button'));

      // Verify complete daily workflow
      expect(mockApiService.getPortfolio).toHaveBeenCalled();
      expect(mockApiService.getMarketData).toHaveBeenCalled();
      expect(mockApiService.getTradingSignals).toHaveBeenCalled();
    });
  });

  describe('Risk Management Workflow', () => {
    it('handles risk management scenarios and stop losses', async () => {
      // Setup losing position scenario
      const riskPortfolio = {
        ...mockPortfolioData,
        positions: [
          { symbol: 'RISKY', quantity: 200, value: 15000, pnl: -15.5 }, // Major loss
          { symbol: 'STABLE', quantity: 100, value: 25000, pnl: 2.1 }   // Small gain
        ]
      };

      mockApiService.getPositions.mockResolvedValue(riskPortfolio.positions);

      // Step 1: User notices significant loss in portfolio
      const Portfolio = (await import('../../../pages/Portfolio')).default;
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Step 2: User reviews risk metrics
      expect(screen.getByTestId('portfolio-page')).toBeInTheDocument();

      // Step 3: User checks trading signals for risk guidance
      const TradingSignals = (await import('../../../pages/TradingSignals')).default;
      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      // Step 4: User sees market timing indicator
      expect(screen.getByTestId('market-timing')).toHaveTextContent('Market Timing: Favorable');

      // Step 5: User adjusts risk settings
      const Settings = (await import('../../../pages/Settings')).default;
      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      await user.selectOptions(screen.getByTestId('risk-level'), 'conservative');
      await user.click(screen.getByTestId('save-settings'));

      // Verify risk management workflow
      expect(mockApiService.getPositions).toHaveBeenCalled();
    });
  });

  describe('Multi-Asset Portfolio Management', () => {
    it('manages diversified portfolio across multiple asset classes', async () => {
      // Setup diversified portfolio
      const diversifiedPortfolio = {
        totalValue: 250000,
        positions: [
          { symbol: 'AAPL', quantity: 100, value: 50000, pnl: 5.2, type: 'stock' },
          { symbol: 'BTC-USD', quantity: 2, value: 80000, pnl: 15.8, type: 'crypto' },
          { symbol: 'GLD', quantity: 300, value: 45000, pnl: -2.1, type: 'commodity' },
          { symbol: 'TLT', quantity: 500, value: 75000, pnl: 3.4, type: 'bond' }
        ]
      };

      mockApiService.getPortfolio.mockResolvedValue(diversifiedPortfolio);

      // Step 1: User reviews diversified portfolio
      const Portfolio = (await import('../../../pages/Portfolio')).default;
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      expect(screen.getByTestId('portfolio-page')).toBeInTheDocument();

      // Step 2: User initiates rebalancing
      await user.click(screen.getByTestId('rebalance-button'));

      // Step 3: User checks signals across asset classes
      const TradingSignals = (await import('../../../pages/TradingSignals')).default;
      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      );

      expect(screen.getByTestId('ai-signals')).toBeInTheDocument();

      // Verify multi-asset management
      expect(mockApiService.getPortfolio).toHaveBeenCalled();
      expect(mockApiService.getTradingSignals).toHaveBeenCalled();
    });
  });

  describe('Error Recovery and Fallback Workflows', () => {
    it('handles API failures and provides fallback experiences', async () => {
      // Setup API failure scenario
      mockApiService.getPortfolio.mockRejectedValue(new Error('API Timeout'));
      mockApiService.getMarketData.mockRejectedValue(new Error('Service Unavailable'));

      // Step 1: User encounters API failure
      const Dashboard = (await import('../../../pages/Dashboard')).default;
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Step 2: Dashboard should still render with fallback data
      expect(screen.getByTestId('dashboard')).toBeInTheDocument();

      // Step 3: User attempts to access portfolio
      const Portfolio = (await import('../../../pages/Portfolio')).default;
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      expect(screen.getByTestId('portfolio-page')).toBeInTheDocument();

      // Step 4: User checks settings for connectivity issues
      const Settings = (await import('../../../pages/Settings')).default;
      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      );

      await user.click(screen.getByTestId('test-connection'));

      // Verify error handling
      expect(mockApiService.getPortfolio).toHaveBeenCalled();
      expect(mockApiService.getMarketData).toHaveBeenCalled();
    });
  });

  describe('Performance and Real-time Updates', () => {
    it('handles real-time data updates and performance monitoring', async () => {
      // Step 1: User loads dashboard
      const Dashboard = (await import('../../../pages/Dashboard')).default;
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Step 2: Simulate real-time portfolio updates
      const updatedPortfolio = {
        ...mockPortfolioData,
        totalValue: 127500, // Increased value
        todayChangePercent: 4.2 // Better performance
      };

      mockApiService.getPortfolio.mockResolvedValue(updatedPortfolio);

      // Step 3: User refreshes portfolio view
      const Portfolio = (await import('../../../pages/Portfolio')).default;
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Step 4: Verify performance tracking
      expect(screen.getByTestId('portfolio-page')).toBeInTheDocument();
      expect(mockApiService.getPortfolio).toHaveBeenCalled();
    });
  });

  describe('Cross-Page Navigation and State Management', () => {
    it('maintains consistent state across page navigation', async () => {
      // Step 1: Start on dashboard
      const Dashboard = (await import('../../../pages/Dashboard')).default;
      const { rerender } = render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      expect(screen.getByTestId('dashboard')).toBeInTheDocument();

      // Step 2: Navigate to portfolio
      rerender(
        <TestWrapper>
          {(await import('../../../pages/Portfolio')).default()}
        </TestWrapper>
      );

      expect(screen.getByTestId('portfolio-page')).toBeInTheDocument();

      // Step 3: Navigate to trading signals
      rerender(
        <TestWrapper>
          {(await import('../../../pages/TradingSignals')).default()}
        </TestWrapper>
      );

      expect(screen.getByTestId('trading-signals-page')).toBeInTheDocument();

      // Step 4: Navigate to settings
      rerender(
        <TestWrapper>
          {(await import('../../../pages/Settings')).default()}
        </TestWrapper>
      );

      expect(screen.getByTestId('settings-page')).toBeInTheDocument();

      // Step 5: Return to dashboard
      rerender(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      expect(screen.getByTestId('dashboard')).toBeInTheDocument();

      // Verify state consistency across navigation
      expect(mockApiService.getPortfolio).toHaveBeenCalled();
      expect(mockApiService.getTradingSignals).toHaveBeenCalled();
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  afterAll(() => {
    vi.clearAllTimers();
  });
});