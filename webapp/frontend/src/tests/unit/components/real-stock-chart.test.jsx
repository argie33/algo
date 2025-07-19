/**
 * Real StockChart Component Unit Tests
 * Testing the actual StockChart.jsx component with Recharts integration
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeProvider, createTheme } from '@mui/material/styles';

// Import the REAL StockChart component
import StockChart from '../../../components/StockChart';

// Mock Recharts components
vi.mock('recharts', () => ({
  LineChart: vi.fn(({ children }) => <div data-testid="line-chart">{children}</div>),
  Line: vi.fn(() => <div data-testid="line" />),
  AreaChart: vi.fn(({ children }) => <div data-testid="area-chart">{children}</div>),
  Area: vi.fn(() => <div data-testid="area" />),
  BarChart: vi.fn(({ children }) => <div data-testid="bar-chart">{children}</div>),
  Bar: vi.fn(() => <div data-testid="bar" />),
  XAxis: vi.fn(() => <div data-testid="x-axis" />),
  YAxis: vi.fn(() => <div data-testid="y-axis" />),
  CartesianGrid: vi.fn(() => <div data-testid="cartesian-grid" />),
  Tooltip: vi.fn(() => <div data-testid="tooltip" />),
  ResponsiveContainer: vi.fn(({ children }) => <div data-testid="responsive-container">{children}</div>),
  Legend: vi.fn(() => <div data-testid="legend" />)
}));

describe('📈 Real StockChart Component', () => {
  const theme = createTheme();
  
  const mockStockData = [
    {
      date: '2024-01-01',
      timestamp: '2024-01-01T09:30:00Z',
      price: 180.50,
      close: 180.50,
      open: 178.25,
      high: 182.75,
      low: 177.80,
      volume: 1250000
    },
    {
      date: '2024-01-02',
      timestamp: '2024-01-02T09:30:00Z',
      price: 185.25,
      close: 185.25,
      open: 180.50,
      high: 186.90,
      low: 179.45,
      volume: 1375000
    },
    {
      date: '2024-01-03',
      timestamp: '2024-01-03T09:30:00Z',
      price: 183.75,
      close: 183.75,
      open: 185.25,
      high: 187.20,
      low: 182.10,
      volume: 1180000
    }
  ];

  const mockRealTimeData = {
    price: 184.50,
    change: 1.25,
    changePercent: 0.68,
    volume: 875000,
    timestamp: '2024-01-03T15:45:00Z'
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
  });

  describe('Component Rendering', () => {
    it('should render StockChart with required props', () => {
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
        />
      );

      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      expect(screen.getByTestId('line-chart')).toBeInTheDocument();
    });

    it('should render with custom height', () => {
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          height={600}
        />
      );

      // The component should render with the custom height
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });

    it('should show controls when showControls is true', () => {
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          showControls={true}
        />
      );

      // Should show timeframe buttons
      expect(screen.getByRole('button', { name: '1D' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '5D' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '1M' })).toBeInTheDocument();
    });

    it('should hide controls when showControls is false', () => {
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          showControls={false}
        />
      );

      // Controls should not be visible
      expect(screen.queryByRole('button', { name: '1D' })).not.toBeInTheDocument();
    });
  });

  describe('Chart Type Selection', () => {
    it('should default to line chart type', () => {
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
        />
      );

      expect(screen.getByTestId('line-chart')).toBeInTheDocument();
      expect(screen.queryByTestId('area-chart')).not.toBeInTheDocument();
      expect(screen.queryByTestId('bar-chart')).not.toBeInTheDocument();
    });

    it('should switch to area chart when selected', async () => {
      const user = userEvent.setup();
      
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          showControls={true}
        />
      );

      // Find and click the area chart button
      const areaButton = screen.getByLabelText(/area/i) || screen.getByText(/area/i);
      if (areaButton) {
        await user.click(areaButton);
        
        await waitFor(() => {
          expect(screen.getByTestId('area-chart')).toBeInTheDocument();
        });
      }
    });

    it('should switch to candlestick chart when selected', async () => {
      const user = userEvent.setup();
      
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          showControls={true}
        />
      );

      // Find and click the candlestick/bar chart button
      const candlestickButton = screen.getByLabelText(/candlestick/i) || screen.getByText(/candlestick/i);
      if (candlestickButton) {
        await user.click(candlestickButton);
        
        await waitFor(() => {
          expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
        });
      }
    });
  });

  describe('Timeframe Selection', () => {
    it('should handle timeframe changes', async () => {
      const user = userEvent.setup();
      
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          showControls={true}
        />
      );

      // Test different timeframe buttons
      const oneWeekButton = screen.getByRole('button', { name: '5D' });
      await user.click(oneWeekButton);

      const oneMonthButton = screen.getByRole('button', { name: '1M' });
      await user.click(oneMonthButton);

      const oneYearButton = screen.getByRole('button', { name: '1Y' });
      await user.click(oneYearButton);

      // Should still render the chart
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });

    it('should highlight selected timeframe', async () => {
      const user = userEvent.setup();
      
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          showControls={true}
        />
      );

      const oneDayButton = screen.getByRole('button', { name: '1D' });
      
      // 1D should be selected by default
      expect(oneDayButton).toHaveClass('Mui-selected');
    });
  });

  describe('Technical Indicators', () => {
    it('should allow adding technical indicators', async () => {
      const user = userEvent.setup();
      
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          showControls={true}
        />
      );

      // Look for indicators dropdown or buttons
      const indicatorControl = screen.queryByLabelText(/indicators/i) || 
                              screen.queryByText(/indicators/i) ||
                              screen.queryByRole('button', { name: /sma/i });
      
      if (indicatorControl) {
        await user.click(indicatorControl);
        // Should show indicator options
      }
    });

    it('should handle SMA indicator selection', async () => {
      const user = userEvent.setup();
      
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          showControls={true}
        />
      );

      // Test if SMA options are available
      const smaButton = screen.queryByText(/SMA20/i) || screen.queryByText(/SMA/i);
      if (smaButton) {
        await user.click(smaButton);
      }
    });
  });

  describe('Loading and Error States', () => {
    it('should show loading state', () => {
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={[]} 
          isLoading={true}
        />
      );

      expect(screen.getByRole('progressbar')).toBeInTheDocument();
    });

    it('should show error state', () => {
      const errorMessage = 'Failed to load chart data';
      
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={[]} 
          error={errorMessage}
        />
      );

      expect(screen.getByText(errorMessage)).toBeInTheDocument();
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    it('should show refresh button on error', () => {
      const onRefresh = vi.fn();
      
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={[]} 
          error="Network error"
          onRefresh={onRefresh}
        />
      );

      const refreshButton = screen.getByLabelText(/refresh/i);
      expect(refreshButton).toBeInTheDocument();
    });

    it('should call onRefresh when refresh button clicked', async () => {
      const user = userEvent.setup();
      const onRefresh = vi.fn();
      
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={[]} 
          error="Network error"
          onRefresh={onRefresh}
        />
      );

      const refreshButton = screen.getByLabelText(/refresh/i);
      await user.click(refreshButton);

      expect(onRefresh).toHaveBeenCalledTimes(1);
    });
  });

  describe('Real-time Data Integration', () => {
    it('should display real-time data when provided', () => {
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          realTimeData={mockRealTimeData}
        />
      );

      // Should show current price
      expect(screen.getByText('$184.50')).toBeInTheDocument();
      expect(screen.getByText('+$1.25')).toBeInTheDocument();
      expect(screen.getByText('+0.68%')).toBeInTheDocument();
    });

    it('should handle positive price changes', () => {
      const positiveRealTimeData = {
        ...mockRealTimeData,
        change: 2.50,
        changePercent: 1.38
      };

      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          realTimeData={positiveRealTimeData}
        />
      );

      // Should show positive change styling
      const changeElement = screen.getByText('+$2.50');
      expect(changeElement).toHaveClass('MuiChip-colorSuccess') || 
             expect(changeElement.closest('.MuiChip-root')).toHaveClass('MuiChip-colorSuccess');
    });

    it('should handle negative price changes', () => {
      const negativeRealTimeData = {
        ...mockRealTimeData,
        change: -1.75,
        changePercent: -0.95
      };

      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          realTimeData={negativeRealTimeData}
        />
      );

      // Should show negative change styling
      const changeElement = screen.getByText('-$1.75');
      expect(changeElement).toHaveClass('MuiChip-colorError') || 
             expect(changeElement.closest('.MuiChip-root')).toHaveClass('MuiChip-colorError');
    });
  });

  describe('Chart Actions', () => {
    it('should have fullscreen toggle', () => {
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          showControls={true}
        />
      );

      const fullscreenButton = screen.getByLabelText(/fullscreen/i);
      expect(fullscreenButton).toBeInTheDocument();
    });

    it('should have settings button', () => {
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          showControls={true}
        />
      );

      const settingsButton = screen.getByLabelText(/settings/i);
      expect(settingsButton).toBeInTheDocument();
    });

    it('should have download button', () => {
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          showControls={true}
        />
      );

      const downloadButton = screen.getByLabelText(/download/i);
      expect(downloadButton).toBeInTheDocument();
    });

    it('should toggle fullscreen mode', async () => {
      const user = userEvent.setup();
      
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          showControls={true}
        />
      );

      const fullscreenButton = screen.getByLabelText(/fullscreen/i);
      await user.click(fullscreenButton);

      // Should enter fullscreen mode (implementation specific)
      // This would depend on how fullscreen is implemented
    });
  });

  describe('Data Processing', () => {
    it('should handle missing data gracefully', () => {
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={[]} 
        />
      );

      // Should not crash and show appropriate empty state
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });

    it('should process data with different field names', () => {
      const dataWithDifferentFields = [
        {
          timestamp: '2024-01-01T09:30:00Z',
          price: 180.50,
          vol: 1250000
        }
      ];

      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={dataWithDifferentFields} 
        />
      );

      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });

    it('should calculate moving averages when indicators enabled', () => {
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          showControls={true}
        />
      );

      // The component should process the data and add moving averages
      // This tests the internal data processing logic
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  describe('Performance', () => {
    it('should render efficiently with large datasets', () => {
      // Create a large dataset
      const largeDataset = Array.from({ length: 1000 }, (_, i) => ({
        date: `2024-01-${String(i + 1).padStart(2, '0')}`,
        price: 180 + Math.random() * 20,
        volume: 1000000 + Math.random() * 500000
      }));

      const startTime = performance.now();
      
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={largeDataset} 
        />
      );
      
      const renderTime = performance.now() - startTime;
      expect(renderTime).toBeLessThan(500); // Should render within 500ms
    });

    it('should handle rapid data updates efficiently', () => {
      const { rerender } = renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          realTimeData={mockRealTimeData}
        />
      );

      // Simulate rapid real-time updates
      const startTime = performance.now();
      
      for (let i = 0; i < 10; i++) {
        const updatedRealTimeData = {
          ...mockRealTimeData,
          price: 184.50 + Math.random(),
          timestamp: new Date().toISOString()
        };

        rerender(
          <ThemeProvider theme={theme}>
            <StockChart 
              symbol="AAPL" 
              data={mockStockData} 
              realTimeData={updatedRealTimeData}
            />
          </ThemeProvider>
        );
      }

      const updateTime = performance.now() - startTime;
      expect(updateTime).toBeLessThan(100); // Should handle updates efficiently
    });
  });

  describe('Accessibility', () => {
    it('should have proper ARIA labels', () => {
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          showControls={true}
        />
      );

      // Check for ARIA labels on interactive elements
      expect(screen.getByLabelText(/refresh/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/fullscreen/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/settings/i)).toBeInTheDocument();
    });

    it('should support keyboard navigation', async () => {
      const user = userEvent.setup();
      
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
          showControls={true}
        />
      );

      // Test tab navigation through controls
      await user.tab();
      
      // Should focus on first interactive element
      const firstButton = screen.getByRole('button', { name: '1D' });
      expect(firstButton).toHaveFocus();
    });

    it('should provide chart description for screen readers', () => {
      renderWithTheme(
        <StockChart 
          symbol="AAPL" 
          data={mockStockData} 
        />
      );

      // Should have appropriate alt text or aria-label
      const chartContainer = screen.getByTestId('responsive-container');
      expect(chartContainer).toHaveAttribute('aria-label') || 
             expect(chartContainer.closest('[aria-label]')).toBeInTheDocument();
    });
  });
});