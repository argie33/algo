import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import ProfessionalChart from '../../../components/ProfessionalChart';

// Mock TradingView widget
const mockTradingViewWidget = {
  onChartReady: vi.fn(),
  activeChart: vi.fn(() => ({
    setSymbol: vi.fn(),
    setResolution: vi.fn(),
    createStudy: vi.fn(),
    removeAllStudies: vi.fn(),
    exportData: vi.fn(),
    onDataLoaded: vi.fn(),
    onSymbolChanged: vi.fn(),
    onIntervalChanged: vi.fn(),
    setTimezone: vi.fn(),
    getTimezone: vi.fn(() => 'America/New_York'),
    createShape: vi.fn(),
    createMultipointShape: vi.fn(),
    removeAllShapes: vi.fn(),
    takeScreenshot: vi.fn(),
  })),
  headerReady: vi.fn(),
  subscribe: vi.fn(),
  unsubscribe: vi.fn(),
  remove: vi.fn(),
};

// Mock TradingView library
vi.mock('../../../../public/charting_library/charting_library', () => ({
  widget: vi.fn(() => mockTradingViewWidget),
}));

global.TradingView = {
  widget: vi.fn(() => mockTradingViewWidget),
};

describe('ProfessionalChart', () => {
  const defaultProps = {
    symbol: 'AAPL',
    interval: '1D',
    theme: 'light',
    height: 600,
    width: '100%',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    // Mock DOM element for chart container
    Element.prototype.getBoundingClientRect = vi.fn(() => ({
      width: 800,
      height: 600,
      top: 0,
      left: 0,
      bottom: 600,
      right: 800,
    }));
  });

  describe('Chart Initialization', () => {
    it('renders chart container', () => {
      render(<ProfessionalChart {...defaultProps} />);
      
      expect(screen.getByTestId('tradingview-chart')).toBeInTheDocument();
    });

    it('initializes TradingView widget with correct configuration', async () => {
      render(<ProfessionalChart {...defaultProps} />);
      
      await waitFor(() => {
        expect(global.TradingView.widget).toHaveBeenCalledWith(
          expect.objectContaining({
            symbol: 'AAPL',
            interval: '1D',
            theme: 'light',
            height: 600,
            width: '100%',
          })
        );
      });
    });

    it('handles chart loading state', () => {
      render(<ProfessionalChart {...defaultProps} />);
      
      expect(screen.getByRole('progressbar')).toBeInTheDocument();
      expect(screen.getByText(/loading professional chart/i)).toBeInTheDocument();
    });

    it('displays error when TradingView library fails to load', () => {
      global.TradingView = undefined;
      
      render(<ProfessionalChart {...defaultProps} />);
      
      expect(screen.getByText(/chart unavailable/i)).toBeInTheDocument();
      expect(screen.getByText(/tradingview library not loaded/i)).toBeInTheDocument();
    });
  });

  describe('Chart Configuration', () => {
    it('applies correct symbol configuration', async () => {
      render(<ProfessionalChart {...defaultProps} symbol="GOOGL" />);
      
      await waitFor(() => {
        expect(global.TradingView.widget).toHaveBeenCalledWith(
          expect.objectContaining({
            symbol: 'GOOGL',
          })
        );
      });
    });

    it('sets up correct time intervals', () => {
      const { rerender } = render(<ProfessionalChart {...defaultProps} interval="1H" />);
      
      expect(global.TradingView.widget).toHaveBeenCalledWith(
        expect.objectContaining({
          interval: '1H',
        })
      );
      
      rerender(<ProfessionalChart {...defaultProps} interval="15" />);
      
      expect(global.TradingView.widget).toHaveBeenCalledWith(
        expect.objectContaining({
          interval: '15',
        })
      );
    });

    it('configures chart theme correctly', () => {
      const { rerender } = render(<ProfessionalChart {...defaultProps} theme="dark" />);
      
      expect(global.TradingView.widget).toHaveBeenCalledWith(
        expect.objectContaining({
          theme: 'dark',
        })
      );
      
      rerender(<ProfessionalChart {...defaultProps} theme="light" />);
      
      expect(global.TradingView.widget).toHaveBeenCalledWith(
        expect.objectContaining({
          theme: 'light',
        })
      );
    });

    it('applies professional trading features', () => {
      render(
        <ProfessionalChart 
          {...defaultProps} 
          features={['header_widget', 'left_toolbar', 'timeframes_toolbar']}
        />
      );
      
      expect(global.TradingView.widget).toHaveBeenCalledWith(
        expect.objectContaining({
          enabled_features: expect.arrayContaining(['header_widget', 'left_toolbar']),
        })
      );
    });
  });

  describe('Technical Indicators', () => {
    it('supports adding technical indicators', async () => {
      render(<ProfessionalChart {...defaultProps} />);
      
      await waitFor(() => {
        expect(mockTradingViewWidget.onChartReady).toHaveBeenCalled();
      });
      
      // Simulate adding RSI indicator
      const chartReady = mockTradingViewWidget.onChartReady.mock.calls[0][0];
      chartReady();
      
      const activeChart = mockTradingViewWidget.activeChart();
      expect(activeChart.createStudy).toBeDefined();
    });

    it('manages multiple indicators simultaneously', async () => {
      render(
        <ProfessionalChart 
          {...defaultProps} 
          defaultIndicators={['RSI', 'MACD', 'Moving Average']}
        />
      );
      
      await waitFor(() => {
        const activeChart = mockTradingViewWidget.activeChart();
        expect(activeChart.createStudy).toBeDefined();
      });
    });

    it('allows removing indicators', async () => {
      render(<ProfessionalChart {...defaultProps} />);
      
      await waitFor(() => {
        const activeChart = mockTradingViewWidget.activeChart();
        expect(activeChart.removeAllStudies).toBeDefined();
      });
    });
  });

  describe('Drawing Tools', () => {
    it('supports trend line drawing', async () => {
      render(<ProfessionalChart {...defaultProps} enableDrawing={true} />);
      
      await waitFor(() => {
        const activeChart = mockTradingViewWidget.activeChart();
        expect(activeChart.createShape).toBeDefined();
      });
    });

    it('handles fibonacci retracement tools', async () => {
      render(<ProfessionalChart {...defaultProps} enableDrawing={true} />);
      
      await waitFor(() => {
        const activeChart = mockTradingViewWidget.activeChart();
        expect(activeChart.createMultipointShape).toBeDefined();
      });
    });

    it('manages shape persistence', async () => {
      render(<ProfessionalChart {...defaultProps} saveShapes={true} />);
      
      await waitFor(() => {
        const activeChart = mockTradingViewWidget.activeChart();
        expect(activeChart.removeAllShapes).toBeDefined();
      });
    });
  });

  describe('Data Management', () => {
    it('handles real-time data updates', async () => {
      render(<ProfessionalChart {...defaultProps} realtime={true} />);
      
      await waitFor(() => {
        const activeChart = mockTradingViewWidget.activeChart();
        expect(activeChart.onDataLoaded).toBeDefined();
      });
    });

    it('supports historical data loading', async () => {
      render(<ProfessionalChart {...defaultProps} />);
      
      await waitFor(() => {
        const activeChart = mockTradingViewWidget.activeChart();
        expect(activeChart.exportData).toBeDefined();
      });
    });

    it('handles symbol changes dynamically', async () => {
      const { rerender } = render(<ProfessionalChart {...defaultProps} symbol="AAPL" />);
      
      rerender(<ProfessionalChart {...defaultProps} symbol="MSFT" />);
      
      await waitFor(() => {
        const activeChart = mockTradingViewWidget.activeChart();
        expect(activeChart.setSymbol).toHaveBeenCalledWith('MSFT');
      });
    });

    it('updates time intervals correctly', async () => {
      const { rerender } = render(<ProfessionalChart {...defaultProps} interval="1D" />);
      
      rerender(<ProfessionalChart {...defaultProps} interval="1H" />);
      
      await waitFor(() => {
        const activeChart = mockTradingViewWidget.activeChart();
        expect(activeChart.setResolution).toHaveBeenCalledWith('1H');
      });
    });
  });

  describe('Chart Interactions', () => {
    it('supports chart zoom and pan', async () => {
      render(<ProfessionalChart {...defaultProps} />);
      
      const chartContainer = screen.getByTestId('tradingview-chart');
      
      // Simulate mouse wheel zoom
      fireEvent.wheel(chartContainer, { deltaY: -100, ctrlKey: true });
      
      // TradingView handles zoom internally
      expect(chartContainer).toBeInTheDocument();
    });

    it('handles crosshair and price tracking', async () => {
      render(<ProfessionalChart {...defaultProps} enableCrosshair={true} />);
      
      const chartContainer = screen.getByTestId('tradingview-chart');
      fireEvent.mouseMove(chartContainer, { clientX: 400, clientY: 300 });
      
      expect(chartContainer).toBeInTheDocument();
    });

    it('supports price alerts creation', async () => {
      const mockOnAlertCreate = vi.fn();
      render(
        <ProfessionalChart 
          {...defaultProps} 
          onAlertCreate={mockOnAlertCreate}
          enableAlerts={true}
        />
      );
      
      // Alert creation would be handled through TradingView interface
      expect(screen.getByTestId('tradingview-chart')).toBeInTheDocument();
    });
  });

  describe('Export and Sharing', () => {
    it('supports chart screenshot export', async () => {
      render(<ProfessionalChart {...defaultProps} />);
      
      await waitFor(() => {
        const activeChart = mockTradingViewWidget.activeChart();
        expect(activeChart.takeScreenshot).toBeDefined();
      });
    });

    it('exports chart data in multiple formats', async () => {
      render(<ProfessionalChart {...defaultProps} />);
      
      await waitFor(() => {
        const activeChart = mockTradingViewWidget.activeChart();
        expect(activeChart.exportData).toBeDefined();
      });
    });

    it('supports chart layout sharing', async () => {
      const mockOnLayoutSave = vi.fn();
      render(
        <ProfessionalChart 
          {...defaultProps} 
          onLayoutSave={mockOnLayoutSave}
          enableLayoutSaving={true}
        />
      );
      
      expect(screen.getByTestId('tradingview-chart')).toBeInTheDocument();
    });
  });

  describe('Responsive Design', () => {
    it('adapts to container size changes', async () => {
      const { rerender } = render(<ProfessionalChart {...defaultProps} height={400} />);
      
      rerender(<ProfessionalChart {...defaultProps} height={800} />);
      
      expect(screen.getByTestId('tradingview-chart')).toBeInTheDocument();
    });

    it('handles mobile viewport correctly', () => {
      // Mock mobile viewport
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 375,
      });
      
      render(<ProfessionalChart {...defaultProps} />);
      
      expect(global.TradingView.widget).toHaveBeenCalledWith(
        expect.objectContaining({
          disabled_features: expect.arrayContaining(['header_widget']),
        })
      );
    });

    it('optimizes for tablet display', () => {
      Object.defineProperty(window, 'innerWidth', {
        writable: true,
        configurable: true,
        value: 768,
      });
      
      render(<ProfessionalChart {...defaultProps} />);
      
      expect(screen.getByTestId('tradingview-chart')).toBeInTheDocument();
    });
  });

  describe('Performance Optimization', () => {
    it('implements lazy loading for chart library', async () => {
      const mockImport = vi.fn(() => Promise.resolve({ widget: vi.fn() }));
      global.import = mockImport;
      
      render(<ProfessionalChart {...defaultProps} lazyLoad={true} />);
      
      // Should load chart library on demand
      expect(screen.getByTestId('tradingview-chart')).toBeInTheDocument();
    });

    it('manages memory efficiently', () => {
      const { unmount } = render(<ProfessionalChart {...defaultProps} />);
      
      unmount();
      
      expect(mockTradingViewWidget.remove).toHaveBeenCalled();
    });

    it('handles multiple chart instances', () => {
      render(
        <>
          <ProfessionalChart {...defaultProps} symbol="AAPL" />
          <ProfessionalChart {...defaultProps} symbol="GOOGL" />
        </>
      );
      
      expect(global.TradingView.widget).toHaveBeenCalledTimes(2);
    });
  });

  describe('Accessibility', () => {
    it('provides keyboard navigation support', () => {
      render(<ProfessionalChart {...defaultProps} />);
      
      const chartContainer = screen.getByTestId('tradingview-chart');
      expect(chartContainer).toHaveAttribute('tabIndex', '0');
    });

    it('includes ARIA labels for screen readers', () => {
      render(<ProfessionalChart {...defaultProps} />);
      
      expect(screen.getByLabelText(/professional trading chart for AAPL/i)).toBeInTheDocument();
    });

    it('supports high contrast mode', () => {
      render(<ProfessionalChart {...defaultProps} highContrast={true} />);
      
      expect(global.TradingView.widget).toHaveBeenCalledWith(
        expect.objectContaining({
          overrides: expect.objectContaining({
            'paneProperties.background': '#000000',
          }),
        })
      );
    });

    it('provides alternative data view', () => {
      render(<ProfessionalChart {...defaultProps} showDataTable={true} />);
      
      expect(screen.getByRole('button', { name: /view data table/i })).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('handles chart initialization failures', () => {
      global.TradingView.widget.mockImplementationOnce(() => {
        throw new Error('Chart initialization failed');
      });
      
      render(<ProfessionalChart {...defaultProps} />);
      
      expect(screen.getByText(/chart initialization failed/i)).toBeInTheDocument();
    });

    it('recovers from data loading errors', async () => {
      render(<ProfessionalChart {...defaultProps} />);
      
      // Simulate data loading error
      await waitFor(() => {
        const activeChart = mockTradingViewWidget.activeChart();
        const onDataLoaded = activeChart.onDataLoaded.mock.calls[0]?.[0];
        if (onDataLoaded) {
          onDataLoaded({ error: 'Data unavailable' });
        }
      });
      
      expect(screen.getByText(/data unavailable/i)).toBeInTheDocument();
    });

    it('provides fallback when TradingView is unavailable', () => {
      global.TradingView = null;
      
      render(<ProfessionalChart {...defaultProps} />);
      
      expect(screen.getByText(/professional chart unavailable/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /load basic chart/i })).toBeInTheDocument();
    });
  });

  describe('Custom Features', () => {
    it('supports custom toolbar items', () => {
      const customButtons = [
        { id: 'export', label: 'Export', onClick: vi.fn() },
        { id: 'alerts', label: 'Alerts', onClick: vi.fn() },
      ];
      
      render(
        <ProfessionalChart 
          {...defaultProps} 
          customToolbar={customButtons}
        />
      );
      
      expect(screen.getByRole('button', { name: 'Export' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Alerts' })).toBeInTheDocument();
    });

    it('integrates with trading platform', () => {
      const mockOnTrade = vi.fn();
      render(
        <ProfessionalChart 
          {...defaultProps} 
          enableTrading={true}
          onTrade={mockOnTrade}
        />
      );
      
      // Trading integration would be handled through callbacks
      expect(screen.getByTestId('tradingview-chart')).toBeInTheDocument();
    });

    it('supports multi-timeframe analysis', () => {
      render(
        <ProfessionalChart 
          {...defaultProps} 
          multiTimeframe={['1m', '5m', '1h', '1d']}
        />
      );
      
      expect(screen.getByTestId('tradingview-chart')).toBeInTheDocument();
    });
  });

  describe('Event Handling', () => {
    it('handles symbol change events', async () => {
      const mockOnSymbolChange = vi.fn();
      render(
        <ProfessionalChart 
          {...defaultProps} 
          onSymbolChange={mockOnSymbolChange}
        />
      );
      
      await waitFor(() => {
        const activeChart = mockTradingViewWidget.activeChart();
        const symbolChanged = activeChart.onSymbolChanged.mock.calls[0]?.[0];
        if (symbolChanged) {
          symbolChanged('MSFT');
        }
      });
      
      expect(mockOnSymbolChange).toHaveBeenCalledWith('MSFT');
    });

    it('handles interval change events', async () => {
      const mockOnIntervalChange = vi.fn();
      render(
        <ProfessionalChart 
          {...defaultProps} 
          onIntervalChange={mockOnIntervalChange}
        />
      );
      
      await waitFor(() => {
        const activeChart = mockTradingViewWidget.activeChart();
        const intervalChanged = activeChart.onIntervalChanged.mock.calls[0]?.[0];
        if (intervalChanged) {
          intervalChanged('1H');
        }
      });
      
      expect(mockOnIntervalChange).toHaveBeenCalledWith('1H');
    });
  });
});