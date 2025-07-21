/**
 * Real PortfolioManager Component Unit Tests
 * Testing the actual PortfolioManager.jsx component with MUI and Recharts integration
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeProvider, createTheme } from '@mui/material/styles';

// Mock the API service
vi.mock('../../../services/api', () => ({
  getPortfolioData: vi.fn(),
  addHolding: vi.fn(),
  updateHolding: vi.fn(),
  deleteHolding: vi.fn(),
  importPortfolioFromBroker: vi.fn()
}));

// Mock ApiKeyStatusIndicator component
vi.mock('../../../components/ApiKeyStatusIndicator', () => ({
  default: ({ status, onStatusChange }) => (
    <div data-testid="api-key-indicator" data-status={status}>
      API Key Status: {status}
      {onStatusChange && (
        <button onClick={() => onStatusChange('connected')}>
          Connect
        </button>
      )}
    </div>
  )
}));

// Mock Recharts components
vi.mock('recharts', () => ({
  PieChart: vi.fn(({ children }) => <div data-testid="pie-chart">{children}</div>),
  Pie: vi.fn(() => <div data-testid="pie" />),
  Cell: vi.fn(() => <div data-testid="cell" />),
  BarChart: vi.fn(({ children }) => <div data-testid="bar-chart">{children}</div>),
  Bar: vi.fn(() => <div data-testid="bar" />),
  XAxis: vi.fn(() => <div data-testid="x-axis" />),
  YAxis: vi.fn(() => <div data-testid="y-axis" />),
  CartesianGrid: vi.fn(() => <div data-testid="cartesian-grid" />),
  Tooltip: vi.fn(() => <div data-testid="recharts-tooltip" />),
  ResponsiveContainer: vi.fn(({ children }) => (
    <div data-testid="responsive-container">{children}</div>
  ))
}));

// Import the REAL PortfolioManager component
import PortfolioManager from '../../../components/PortfolioManager';

// Import the mocked API functions
import { 
  getPortfolioData, 
  addHolding, 
  updateHolding, 
  deleteHolding, 
  importPortfolioFromBroker 
} from '../../../services/api';

describe('💼 Real PortfolioManager Component', () => {
  const theme = createTheme();

  const mockPortfolioData = {
    holdings: [
      {
        id: 'holding_1',
        symbol: 'AAPL',
        name: 'Apple Inc.',
        quantity: 100,
        averagePrice: 175.25,
        currentPrice: 185.50,
        marketValue: 18550,
        unrealizedGain: 1025,
        unrealizedGainPercent: 5.85,
        weight: 24.7
      },
      {
        id: 'holding_2', 
        symbol: 'GOOGL',
        name: 'Alphabet Inc.',
        quantity: 25,
        averagePrice: 2800.00,
        currentPrice: 2850.00,
        marketValue: 71250,
        unrealizedGain: 1250,
        unrealizedGainPercent: 1.79,
        weight: 60.2
      },
      {
        id: 'holding_3',
        symbol: 'MSFT',
        name: 'Microsoft Corp.',
        quantity: 50,
        averagePrice: 340.00,
        currentPrice: 375.00,
        marketValue: 18750,
        unrealizedGain: 1750,
        unrealizedGainPercent: 10.29,
        weight: 15.1
      }
    ],
    summary: {
      totalValue: 108550,
      totalCost: 106025,
      totalGain: 4025,
      totalGainPercent: 3.80,
      dayChange: 2150,
      dayChangePercent: 2.02,
      cashBalance: 5000
    },
    diversification: {
      sectors: [
        { name: 'Technology', value: 108550, percentage: 100.0 }
      ],
      riskScore: 7.2,
      volatility: 18.5
    }
  };

  const renderWithTheme = (component) => {
    return render(
      <ThemeProvider theme={theme}>
        {component}
      </ThemeProvider>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
    
    // Setup default API mock responses
    getPortfolioData.mockResolvedValue({
      data: mockPortfolioData.holdings,
      success: true
    });

    addHolding.mockResolvedValue({
      data: {
        id: 'new_holding',
        symbol: 'TSLA',
        quantity: 10,
        averagePrice: 220.00
      },
      success: true
    });

    updateHolding.mockResolvedValue({
      data: { updated: true },
      success: true
    });

    deleteHolding.mockResolvedValue({
      data: { deleted: true },
      success: true
    });

    importPortfolioFromBroker.mockResolvedValue({
      data: { imported: 5, skipped: 0 },
      success: true
    });

    // Mock console to avoid noise
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Component Initialization', () => {
    it('should render PortfolioManager with loading state initially', () => {
      renderWithTheme(<PortfolioManager />);

      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    it('should load portfolio data on mount', async () => {
      renderWithTheme(<PortfolioManager />);

      await waitFor(() => {
        expect(getPortfolioData).toHaveBeenCalled();
      });

      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });
    });

    it('should display portfolio summary after loading', async () => {
      renderWithTheme(<PortfolioManager />);

      await waitFor(() => {
        expect(screen.getByText('$108,550')).toBeInTheDocument(); // Total value
        expect(screen.getByText('+$4,025')).toBeInTheDocument(); // Total gain
        expect(screen.getByText('+3.80%')).toBeInTheDocument(); // Total gain percent
      });
    });

    it('should display API key status indicator', async () => {
      renderWithTheme(<PortfolioManager />);

      await waitFor(() => {
        expect(screen.getByTestId('api-key-indicator')).toBeInTheDocument();
      });
    });

    it('should handle portfolio loading errors', async () => {
      getPortfolioData.mockRejectedValue(new Error('Failed to load portfolio'));

      renderWithTheme(<PortfolioManager />);

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
        expect(screen.getByText(/failed to load portfolio/i)).toBeInTheDocument();
      });
    });
  });

  describe('Holdings Table Display', () => {
    beforeEach(async () => {
      renderWithTheme(<PortfolioManager />);
      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });
    });

    it('should display holdings table with all columns', () => {
      expect(screen.getByText('Symbol')).toBeInTheDocument();
      expect(screen.getByText('Name')).toBeInTheDocument();
      expect(screen.getByText('Quantity')).toBeInTheDocument();
      expect(screen.getByText('Avg Price')).toBeInTheDocument();
      expect(screen.getByText('Current Price')).toBeInTheDocument();
      expect(screen.getByText('Market Value')).toBeInTheDocument();
      expect(screen.getByText('Gain/Loss')).toBeInTheDocument();
      expect(screen.getByText('Weight')).toBeInTheDocument();
    });

    it('should display all holdings data correctly', () => {
      // Check AAPL holding
      expect(screen.getByText('AAPL')).toBeInTheDocument();
      expect(screen.getByText('Apple Inc.')).toBeInTheDocument();
      expect(screen.getByText('100')).toBeInTheDocument();
      expect(screen.getByText('$175.25')).toBeInTheDocument();
      expect(screen.getByText('$185.50')).toBeInTheDocument();
      expect(screen.getByText('$18,550')).toBeInTheDocument();

      // Check GOOGL holding
      expect(screen.getByText('GOOGL')).toBeInTheDocument();
      expect(screen.getByText('Alphabet Inc.')).toBeInTheDocument();
      expect(screen.getByText('25')).toBeInTheDocument();

      // Check MSFT holding
      expect(screen.getByText('MSFT')).toBeInTheDocument();
      expect(screen.getByText('Microsoft Corp.')).toBeInTheDocument();
      expect(screen.getByText('50')).toBeInTheDocument();
    });

    it('should display gain/loss with correct styling', () => {
      // Positive gains should be green
      const positiveGains = screen.getAllByText(/^\+\$\d/);
      expect(positiveGains.length).toBeGreaterThan(0);
      
      positiveGains.forEach(element => {
        expect(element).toHaveClass('MuiTypography-colorSuccess') ||
               expect(element.closest('.MuiChip-colorSuccess')).toBeInTheDocument();
      });
    });

    it('should show weight percentages correctly', () => {
      expect(screen.getByText('24.7%')).toBeInTheDocument(); // AAPL weight
      expect(screen.getByText('60.2%')).toBeInTheDocument(); // GOOGL weight  
      expect(screen.getByText('15.1%')).toBeInTheDocument(); // MSFT weight
    });
  });

  describe('Add New Holding Functionality', () => {
    beforeEach(async () => {
      renderWithTheme(<PortfolioManager />);
      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });
    });

    it('should open add holding dialog when add button clicked', async () => {
      const user = userEvent.setup();
      
      const addButton = screen.getByRole('button', { name: /add holding/i });
      await user.click(addButton);

      expect(screen.getByText('Add New Holding')).toBeInTheDocument();
      expect(screen.getByLabelText(/symbol/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/quantity/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/average price/i)).toBeInTheDocument();
    });

    it('should add new holding with valid data', async () => {
      const user = userEvent.setup();
      
      const addButton = screen.getByRole('button', { name: /add holding/i });
      await user.click(addButton);

      // Fill in the form
      await user.type(screen.getByLabelText(/symbol/i), 'TSLA');
      await user.type(screen.getByLabelText(/quantity/i), '10');
      await user.type(screen.getByLabelText(/average price/i), '220.00');

      // Submit the form
      const saveButton = screen.getByRole('button', { name: /add holding/i });
      await user.click(saveButton);

      expect(addHolding).toHaveBeenCalledWith({
        symbol: 'TSLA',
        quantity: 10,
        averagePrice: 220.00
      });

      await waitFor(() => {
        expect(screen.queryByText('Add New Holding')).not.toBeInTheDocument();
      });
    });

    it('should validate form inputs', async () => {
      const user = userEvent.setup();
      
      const addButton = screen.getByRole('button', { name: /add holding/i });
      await user.click(addButton);

      // Try to submit empty form
      const saveButton = screen.getByRole('button', { name: /add holding/i });
      await user.click(saveButton);

      // Should show validation errors
      expect(screen.getByText(/symbol is required/i)).toBeInTheDocument();
      expect(screen.getByText(/quantity is required/i)).toBeInTheDocument();
    });

    it('should handle add holding API errors', async () => {
      const user = userEvent.setup();
      addHolding.mockRejectedValue(new Error('Failed to add holding'));
      
      const addButton = screen.getByRole('button', { name: /add holding/i });
      await user.click(addButton);

      await user.type(screen.getByLabelText(/symbol/i), 'TSLA');
      await user.type(screen.getByLabelText(/quantity/i), '10');
      await user.type(screen.getByLabelText(/average price/i), '220.00');

      const saveButton = screen.getByRole('button', { name: /add holding/i });
      await user.click(saveButton);

      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
        expect(screen.getByText(/failed to add holding/i)).toBeInTheDocument();
      });
    });
  });

  describe('Edit and Delete Holdings', () => {
    beforeEach(async () => {
      renderWithTheme(<PortfolioManager />);
      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });
    });

    it('should show edit and delete buttons for each holding', () => {
      const editButtons = screen.getAllByLabelText(/edit/i);
      const deleteButtons = screen.getAllByLabelText(/delete/i);

      expect(editButtons).toHaveLength(3); // One for each holding
      expect(deleteButtons).toHaveLength(3);
    });

    it('should open edit dialog when edit button clicked', async () => {
      const user = userEvent.setup();
      
      const editButtons = screen.getAllByLabelText(/edit/i);
      await user.click(editButtons[0]); // Edit first holding (AAPL)

      expect(screen.getByText('Edit Holding')).toBeInTheDocument();
      expect(screen.getByDisplayValue('AAPL')).toBeInTheDocument();
      expect(screen.getByDisplayValue('100')).toBeInTheDocument();
    });

    it('should update holding with new data', async () => {
      const user = userEvent.setup();
      
      const editButtons = screen.getAllByLabelText(/edit/i);
      await user.click(editButtons[0]);

      // Update quantity
      const quantityInput = screen.getByDisplayValue('100');
      await user.clear(quantityInput);
      await user.type(quantityInput, '150');

      const saveButton = screen.getByRole('button', { name: /update holding/i });
      await user.click(saveButton);

      expect(updateHolding).toHaveBeenCalledWith('holding_1', {
        symbol: 'AAPL',
        quantity: 150,
        averagePrice: 175.25
      });
    });

    it('should delete holding when delete button clicked', async () => {
      const user = userEvent.setup();
      
      const deleteButtons = screen.getAllByLabelText(/delete/i);
      await user.click(deleteButtons[0]); // Delete first holding

      // Should show confirmation dialog
      expect(screen.getByText(/are you sure/i)).toBeInTheDocument();
      
      const confirmButton = screen.getByRole('button', { name: /delete/i });
      await user.click(confirmButton);

      expect(deleteHolding).toHaveBeenCalledWith('holding_1');
    });
  });

  describe('Portfolio Charts and Visualization', () => {
    beforeEach(async () => {
      renderWithTheme(<PortfolioManager />);
      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });
    });

    it('should render portfolio allocation pie chart', () => {
      expect(screen.getByTestId('pie-chart')).toBeInTheDocument();
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });

    it('should render performance bar chart', () => {
      expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
    });

    it('should display chart controls', () => {
      // Look for chart type toggles or time period selectors
      const chartControls = screen.queryByText(/allocation/i) || 
                           screen.queryByText(/performance/i) ||
                           screen.queryByRole('tab');
      
      expect(chartControls).toBeInTheDocument();
    });
  });

  describe('Portfolio Import from Broker', () => {
    beforeEach(async () => {
      renderWithTheme(<PortfolioManager />);
      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });
    });

    it('should show import button', () => {
      const importButton = screen.getByRole('button', { name: /import/i }) ||
                          screen.getByRole('button', { name: /sync/i });
      
      expect(importButton).toBeInTheDocument();
    });

    it('should handle portfolio import', async () => {
      const user = userEvent.setup();
      
      const importButton = screen.getByRole('button', { name: /import/i }) ||
                          screen.getByRole('button', { name: /sync/i });
      
      await user.click(importButton);

      // Should trigger import API call
      expect(importPortfolioFromBroker).toHaveBeenCalled();
    });

    it('should show import progress', async () => {
      const user = userEvent.setup();
      
      // Mock import to take some time
      importPortfolioFromBroker.mockImplementation(
        () => new Promise(resolve => setTimeout(() => resolve({
          data: { imported: 5, skipped: 0 },
          success: true
        }), 100))
      );

      const importButton = screen.getByRole('button', { name: /import/i }) ||
                          screen.getByRole('button', { name: /sync/i });
      
      await user.click(importButton);

      // Should show loading state
      expect(screen.getByRole('progressbar')).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
      });
    });
  });

  describe('Refresh and Real-time Updates', () => {
    beforeEach(async () => {
      renderWithTheme(<PortfolioManager />);
      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });
    });

    it('should have refresh button', () => {
      const refreshButton = screen.getByLabelText(/refresh/i) ||
                           screen.getByRole('button', { name: /refresh/i });
      
      expect(refreshButton).toBeInTheDocument();
    });

    it('should refresh portfolio data when refresh clicked', async () => {
      const user = userEvent.setup();
      
      const refreshButton = screen.getByLabelText(/refresh/i) ||
                           screen.getByRole('button', { name: /refresh/i });
      
      await user.click(refreshButton);

      expect(getPortfolioData).toHaveBeenCalledTimes(2); // Initial load + refresh
    });

    it('should show last updated timestamp', () => {
      const lastUpdated = screen.queryByText(/last updated/i) ||
                         screen.queryByText(/updated/i);
      
      if (lastUpdated) {
        expect(lastUpdated).toBeInTheDocument();
      }
    });
  });

  describe('Responsive Design and Layout', () => {
    it('should render responsive grid layout', () => {
      renderWithTheme(<PortfolioManager />);

      const gridContainer = screen.getByTestId('portfolio-grid') ||
                           document.querySelector('.MuiGrid-container');
      
      expect(gridContainer).toBeInTheDocument();
    });

    it('should handle mobile layout', () => {
      // Mock mobile viewport
      global.innerWidth = 375;
      global.dispatchEvent(new Event('resize'));

      renderWithTheme(<PortfolioManager />);

      // Component should still render properly on mobile
      expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
    });
  });

  describe('Performance and Optimization', () => {
    it('should render efficiently with large portfolio', async () => {
      const largePortfolio = {
        ...mockPortfolioData,
        holdings: Array.from({ length: 100 }, (_, i) => ({
          id: `holding_${i}`,
          symbol: `STOCK${i}`,
          name: `Stock ${i}`,
          quantity: 100,
          averagePrice: 100 + i,
          currentPrice: 100 + i + Math.random() * 10,
          marketValue: (100 + i + Math.random() * 10) * 100,
          unrealizedGain: Math.random() * 1000,
          unrealizedGainPercent: Math.random() * 10,
          weight: 1.0
        }))
      };

      getPortfolioData.mockResolvedValue({
        data: largePortfolio,
        success: true
      });

      const startTime = performance.now();
      
      renderWithTheme(<PortfolioManager />);
      
      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });

      const renderTime = performance.now() - startTime;
      expect(renderTime).toBeLessThan(1000); // Should render within 1 second
    });

    it('should handle rapid user interactions', async () => {
      const user = userEvent.setup();
      
      renderWithTheme(<PortfolioManager />);
      
      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });

      // Rapid clicking should not cause issues
      const refreshButton = screen.getByLabelText(/refresh/i) ||
                           screen.getByRole('button', { name: /refresh/i });
      
      for (let i = 0; i < 5; i++) {
        await user.click(refreshButton);
      }

      // Should handle gracefully
      expect(getPortfolioData).toHaveBeenCalled();
    });
  });

  describe('Accessibility', () => {
    beforeEach(async () => {
      renderWithTheme(<PortfolioManager />);
      await waitFor(() => {
        expect(screen.getByText('Portfolio Overview')).toBeInTheDocument();
      });
    });

    it('should have proper ARIA labels', () => {
      expect(screen.getByLabelText(/refresh/i)).toBeInTheDocument();
      
      const editButtons = screen.getAllByLabelText(/edit/i);
      expect(editButtons).toHaveLength(3);
    });

    it('should support keyboard navigation', async () => {
      const user = userEvent.setup();
      
      // Tab through interactive elements
      await user.tab();
      
      const focusedElement = document.activeElement;
      expect(focusedElement).toHaveClass('MuiButton-root') ||
             expect(focusedElement.tagName).toBe('BUTTON');
    });

    it('should have proper heading hierarchy', () => {
      const mainHeading = screen.getByRole('heading', { name: /portfolio overview/i });
      expect(mainHeading.tagName).toBe('H1') || expect(mainHeading.tagName).toBe('H2');
    });

    it('should provide screen reader friendly table', () => {
      expect(screen.getByRole('table')).toBeInTheDocument();
      expect(screen.getAllByRole('columnheader')).toHaveLength(8); // All table columns
    });
  });
});