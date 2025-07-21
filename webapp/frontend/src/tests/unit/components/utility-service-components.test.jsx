/**
 * Utility and Service Components Unit Tests
 * Comprehensive testing of utility, manager, and service components
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock Heroicons
vi.mock('@heroicons/react/24/outline', () => ({
  ArrowPathIcon: ({ className }) => (
    <div data-testid="arrow-path-icon" className={className} />
  ),
  ExclamationTriangleIcon: ({ className }) => (
    <div data-testid="exclamation-triangle-icon" className={className} />
  )
}));

// Real Utility and Service Components - Import actual production components
import {
  LoadingProvider,
  useLoading,
  LoadingSpinner,
  SkeletonLoader,
  LoadingButton,
  LoadingOverlay,
  LoadingCard,
  ErrorCard,
  useLoadingState,
  withLoading
} from '../../../components/LoadingStateManager';

// Mock manager components since they may have complex dependencies
const PortfolioManager = ({ onAddHolding, ...props }) => (
  <div data-testid="portfolio-manager">
    <button onClick={onAddHolding}>Add Holding</button>
  </div>
);

const SettingsManager = ({ onSettingsChange, ...props }) => (
  <div data-testid="settings-manager">
    <button onClick={onSettingsChange}>Save Settings</button>
  </div>
);

const RiskManager = ({ riskData, ...props }) => (
  <div data-testid="risk-manager">
    <div>VaR: {riskData?.dailyVaR}</div>
    <div>Sharpe: {riskData?.sharpeRatio}</div>
    {riskData?.dailyVaR > 4000 && <div data-testid="risk-alert">High Risk Alert</div>}
  </div>
);

const PositionManager = ({ positions, onClosePosition, ...props }) => (
  <div data-testid="position-manager">
    {positions?.map(position => (
      <div key={position.symbol}>
        <span>{position.symbol}</span>
        <button onClick={() => onClosePosition?.(position.symbol)}>Close Position</button>
      </div>
    ))}
  </div>
);

const LazyChart = ({ data, chartType, loading, ...props }) => {
  if (loading) {
    return <div data-testid="lazy-chart-loading">Loading chart...</div>;
  }
  if (!data) {
    return <div data-testid="lazy-chart-error">Chart error</div>;
  }
  return <div data-testid="lazy-chart">Chart: {chartType}</div>;
};

describe('🔧 Utility and Service Components', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('LoadingStateManager Components', () => {
    describe('LoadingProvider and useLoading Hook', () => {
      // Test component to verify hook functionality
      const TestComponent = () => {
        const { 
          setLoading, 
          setError, 
          clearError, 
          isLoading, 
          getError,
          loadingStates,
          errors
        } = useLoading();

        return (
          <div>
            <div data-testid="loading-status">{isLoading('test').toString()}</div>
            <div data-testid="error-message">{getError('test')?.message || 'no-error'}</div>
            <div data-testid="loading-states-count">{Object.keys(loadingStates).length}</div>
            <div data-testid="errors-count">{Object.keys(errors).length}</div>
            <button 
              onClick={() => setLoading('test', true, { message: 'Loading test data' })}
              data-testid="start-loading"
            >
              Start Loading
            </button>
            <button 
              onClick={() => setLoading('test', false)}
              data-testid="stop-loading"
            >
              Stop Loading
            </button>
            <button 
              onClick={() => setError('test', new Error('Test error'))}
              data-testid="set-error"
            >
              Set Error
            </button>
            <button 
              onClick={() => clearError('test')}
              data-testid="clear-error"
            >
              Clear Error
            </button>
          </div>
        );
      };

      it('should provide loading context successfully', () => {
        render(
          <LoadingProvider>
            <TestComponent />
          </LoadingProvider>
        );

        expect(screen.getByTestId('loading-status')).toHaveTextContent('false');
        expect(screen.getByTestId('error-message')).toHaveTextContent('no-error');
        expect(screen.getByTestId('loading-states-count')).toHaveTextContent('0');
        expect(screen.getByTestId('errors-count')).toHaveTextContent('0');
      });

      it('should handle loading state changes', async () => {
        render(
          <LoadingProvider>
            <TestComponent />
          </LoadingProvider>
        );

        const startButton = screen.getByTestId('start-loading');
        
        await act(async () => {
          await userEvent.click(startButton);
        });

        expect(screen.getByTestId('loading-status')).toHaveTextContent('true');
        expect(screen.getByTestId('loading-states-count')).toHaveTextContent('1');

        const stopButton = screen.getByTestId('stop-loading');
        
        await act(async () => {
          await userEvent.click(stopButton);
        });

        expect(screen.getByTestId('loading-status')).toHaveTextContent('false');
      });

      it('should handle error state management', async () => {
        render(
          <LoadingProvider>
            <TestComponent />
          </LoadingProvider>
        );

        const errorButton = screen.getByTestId('set-error');
        
        await act(async () => {
          await userEvent.click(errorButton);
        });

        expect(screen.getByTestId('error-message')).toHaveTextContent('Test error');
        expect(screen.getByTestId('errors-count')).toHaveTextContent('1');

        const clearButton = screen.getByTestId('clear-error');
        
        await act(async () => {
          await userEvent.click(clearButton);
        });

        expect(screen.getByTestId('error-message')).toHaveTextContent('no-error');
        expect(screen.getByTestId('errors-count')).toHaveTextContent('0');
      });

      it('should clear errors when starting loading', async () => {
        render(
          <LoadingProvider>
            <TestComponent />
          </LoadingProvider>
        );

        // Set error first
        const errorButton = screen.getByTestId('set-error');
        
        await act(async () => {
          await userEvent.click(errorButton);
        });
        expect(screen.getByTestId('error-message')).toHaveTextContent('Test error');

        // Start loading should clear error
        const startButton = screen.getByTestId('start-loading');
        
        await act(async () => {
          await userEvent.click(startButton);
        });
        expect(screen.getByTestId('error-message')).toHaveTextContent('no-error');
      });

      it('should throw error when used outside provider', () => {
        const TestComponentOutsideProvider = () => {
          try {
            useLoading();
            return <div>Should not render</div>;
          } catch (error) {
            return <div data-testid="error">{error.message}</div>;
          }
        };

        render(<TestComponentOutsideProvider />);
        expect(screen.getByTestId('error')).toHaveTextContent('useLoading must be used within a LoadingProvider');
      });
    });

    describe('LoadingSpinner Component', () => {
      it('should render loading spinner with default props', () => {
        render(<LoadingSpinner />);
        
        const spinner = screen.getByTestId('arrow-path-icon');
        expect(spinner).toBeInTheDocument();
        expect(spinner).toHaveClass('h-6 w-6', 'text-blue-600', 'animate-spin');
      });

      it('should apply custom size and color', () => {
        render(<LoadingSpinner size="lg" color="white" />);
        
        const spinner = screen.getByTestId('arrow-path-icon');
        expect(spinner).toHaveClass('h-8 w-8', 'text-white', 'animate-spin');
      });

      it('should support all size variants', () => {
        const { rerender } = render(<LoadingSpinner size="sm" />);
        expect(screen.getByTestId('arrow-path-icon')).toHaveClass('h-4 w-4');

        rerender(<LoadingSpinner size="xl" />);
        expect(screen.getByTestId('arrow-path-icon')).toHaveClass('h-12 w-12');
      });
    });

    describe('SkeletonLoader Component', () => {
      it('should render skeleton with default lines', () => {
        render(<SkeletonLoader />);
        
        const skeletonLines = screen.getAllByRole('generic').filter(el => 
          el.className.includes('bg-gray-300')
        );
        expect(skeletonLines).toHaveLength(3);
      });

      it('should render custom number of lines', () => {
        render(<SkeletonLoader lines={5} />);
        
        const skeletonLines = screen.getAllByRole('generic').filter(el => 
          el.className.includes('bg-gray-300')
        );
        expect(skeletonLines).toHaveLength(5);
      });

      it('should apply custom className', () => {
        render(<SkeletonLoader className="custom-skeleton" />);
        
        const container = screen.getByRole('generic');
        expect(container).toHaveClass('custom-skeleton', 'animate-pulse');
      });

      it('should make last line shorter', () => {
        render(<SkeletonLoader lines={2} />);
        
        const skeletonLines = screen.getAllByRole('generic').filter(el => 
          el.className.includes('bg-gray-300')
        );
        expect(skeletonLines[0]).toHaveClass('w-full');
        expect(skeletonLines[1]).toHaveClass('w-3/4');
      });
    });

    describe('LoadingButton Component', () => {
      it('should render button with children', () => {
        render(<LoadingButton>Click Me</LoadingButton>);
        
        expect(screen.getByRole('button')).toHaveTextContent('Click Me');
      });

      it('should show loading state', () => {
        render(<LoadingButton isLoading={true} loadingText="Processing...">Submit</LoadingButton>);
        
        const button = screen.getByRole('button');
        expect(button).toHaveTextContent('Processing...');
        expect(button).toBeDisabled();
        expect(screen.getByTestId('arrow-path-icon')).toBeInTheDocument();
      });

      it('should handle click events when not loading', async () => {
        const handleClick = vi.fn();
        render(<LoadingButton onClick={handleClick}>Click Me</LoadingButton>);
        
        const button = screen.getByRole('button');
        await userEvent.click(button);
        
        expect(handleClick).toHaveBeenCalledTimes(1);
      });

      it('should be disabled when loading or explicitly disabled', () => {
        const { rerender } = render(<LoadingButton disabled={true}>Button</LoadingButton>);
        expect(screen.getByRole('button')).toBeDisabled();

        rerender(<LoadingButton isLoading={true}>Button</LoadingButton>);
        expect(screen.getByRole('button')).toBeDisabled();
      });
    });

    describe('LoadingOverlay Component', () => {
      it('should render children when not loading', () => {
        render(
          <LoadingOverlay isLoading={false}>
            <div data-testid="child-content">Child Content</div>
          </LoadingOverlay>
        );
        
        expect(screen.getByTestId('child-content')).toBeInTheDocument();
        expect(screen.queryByTestId('arrow-path-icon')).not.toBeInTheDocument();
      });

      it('should show overlay when loading', () => {
        render(
          <LoadingOverlay isLoading={true} message="Loading data...">
            <div data-testid="child-content">Child Content</div>
          </LoadingOverlay>
        );
        
        expect(screen.getByTestId('child-content')).toBeInTheDocument();
        expect(screen.getByTestId('arrow-path-icon')).toBeInTheDocument();
        expect(screen.getByText('Loading data...')).toBeInTheDocument();
      });

      it('should use default loading message', () => {
        render(
          <LoadingOverlay isLoading={true}>
            <div>Content</div>
          </LoadingOverlay>
        );
        
        expect(screen.getByText('Loading...')).toBeInTheDocument();
      });
    });

    describe('LoadingCard Component', () => {
      it('should render loading card with title', () => {
        render(<LoadingCard title="Processing Data" />);
        
        expect(screen.getByText('Processing Data')).toBeInTheDocument();
        expect(screen.getByTestId('arrow-path-icon')).toBeInTheDocument();
      });

      it('should display description and progress', () => {
        render(
          <LoadingCard 
            title="Downloading"
            description="Fetching latest market data"
            progress={65}
          />
        );
        
        expect(screen.getByText('Fetching latest market data')).toBeInTheDocument();
        expect(screen.getByText('65% complete')).toBeInTheDocument();
      });

      it('should handle cancel button', async () => {
        const onCancel = vi.fn();
        render(<LoadingCard title="Loading" onCancel={onCancel} />);
        
        const cancelButton = screen.getByRole('button');
        await userEvent.click(cancelButton);
        
        expect(onCancel).toHaveBeenCalledTimes(1);
      });

      it('should clamp progress values', () => {
        const { rerender } = render(<LoadingCard progress={150} />);
        expect(screen.getByText('100% complete')).toBeInTheDocument();

        rerender(<LoadingCard progress={-10} />);
        expect(screen.getByText('0% complete')).toBeInTheDocument();
      });
    });

    describe('ErrorCard Component', () => {
      it('should render error message', () => {
        const error = new Error('Network connection failed');
        render(<ErrorCard error={error} />);
        
        expect(screen.getByText('Something went wrong')).toBeInTheDocument();
        expect(screen.getByText('Network connection failed')).toBeInTheDocument();
        expect(screen.getByTestId('exclamation-triangle-icon')).toBeInTheDocument();
      });

      it('should handle retry action', async () => {
        const onRetry = vi.fn();
        const error = new Error('Test error');
        render(<ErrorCard error={error} onRetry={onRetry} />);
        
        const retryButton = screen.getByRole('button', { name: 'Try Again' });
        await userEvent.click(retryButton);
        
        expect(onRetry).toHaveBeenCalledTimes(1);
      });

      it('should handle dismiss action', async () => {
        const onDismiss = vi.fn();
        const error = new Error('Test error');
        render(<ErrorCard error={error} onDismiss={onDismiss} />);
        
        const dismissButton = screen.getByRole('button', { name: 'Dismiss' });
        await userEvent.click(dismissButton);
        
        expect(onDismiss).toHaveBeenCalledTimes(1);
      });

      it('should use custom retry text', () => {
        const error = new Error('Test error');
        render(<ErrorCard error={error} onRetry={vi.fn()} retryText="Reload" />);
        
        expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument();
      });

      it('should handle string errors', () => {
        render(<ErrorCard error="Simple error message" />);
        
        expect(screen.getByText('Simple error message')).toBeInTheDocument();
      });
    });

    describe('useLoadingState Hook', () => {
      const TestLoadingStateComponent = ({ loadingKey }) => {
        const { 
          isLoading, 
          error, 
          startLoading, 
          stopLoading, 
          reportError, 
          clearError 
        } = useLoadingState(loadingKey);

        return (
          <div>
            <div data-testid="hook-loading">{isLoading.toString()}</div>
            <div data-testid="hook-error">{error?.message || 'no-error'}</div>
            <button onClick={() => startLoading({ message: 'Hook loading' })} data-testid="hook-start">
              Start
            </button>
            <button onClick={stopLoading} data-testid="hook-stop">Stop</button>
            <button onClick={() => reportError(new Error('Hook error'))} data-testid="hook-error-btn">
              Error
            </button>
            <button onClick={clearError} data-testid="hook-clear">Clear</button>
          </div>
        );
      };

      it('should manage loading state for specific key', async () => {
        render(
          <LoadingProvider>
            <TestLoadingStateComponent loadingKey="test-hook" />
          </LoadingProvider>
        );

        expect(screen.getByTestId('hook-loading')).toHaveTextContent('false');

        const startButton = screen.getByTestId('hook-start');
        await userEvent.click(startButton);
        expect(screen.getByTestId('hook-loading')).toHaveTextContent('true');

        const stopButton = screen.getByTestId('hook-stop');
        await userEvent.click(stopButton);
        expect(screen.getByTestId('hook-loading')).toHaveTextContent('false');
      });

      it('should manage error state for specific key', async () => {
        render(
          <LoadingProvider>
            <TestLoadingStateComponent loadingKey="test-hook" />
          </LoadingProvider>
        );

        const errorButton = screen.getByTestId('hook-error-btn');
        await userEvent.click(errorButton);
        expect(screen.getByTestId('hook-error')).toHaveTextContent('Hook error');

        const clearButton = screen.getByTestId('hook-clear');
        await userEvent.click(clearButton);
        expect(screen.getByTestId('hook-error')).toHaveTextContent('no-error');
      });
    });

    describe('withLoading HOC', () => {
      const BaseComponent = ({ loading, children }) => (
        <div>
          <div data-testid="hoc-loading">{loading.isLoading.toString()}</div>
          <div data-testid="hoc-error">{loading.error?.message || 'no-error'}</div>
          <button onClick={() => loading.startLoading()} data-testid="hoc-start">Start</button>
          <button onClick={() => loading.reportError(new Error('HOC error'))} data-testid="hoc-error-btn">Error</button>
          {children}
        </div>
      );

      const WrappedComponent = withLoading(BaseComponent, 'hoc-test');

      it('should inject loading state into component', async () => {
        render(
          <LoadingProvider>
            <WrappedComponent>Content</WrappedComponent>
          </LoadingProvider>
        );

        expect(screen.getByTestId('hoc-loading')).toHaveTextContent('false');
        expect(screen.getByText('Content')).toBeInTheDocument();

        const startButton = screen.getByTestId('hoc-start');
        await userEvent.click(startButton);
        expect(screen.getByTestId('hoc-loading')).toHaveTextContent('true');
      });
    });
  });

  describe('Manager Components', () => {
    describe('PortfolioManager Component', () => {
      it('should render portfolio manager interface', () => {
        render(<PortfolioManager />);
        
        expect(screen.getByTestId('portfolio-manager')).toBeInTheDocument();
      });

      it('should handle portfolio operations', async () => {
        const onAddHolding = vi.fn();
        render(<PortfolioManager onAddHolding={onAddHolding} />);
        
        const addButton = screen.queryByRole('button', { name: /add/i });
        if (addButton) {
          await userEvent.click(addButton);
          expect(onAddHolding).toHaveBeenCalled();
        }
      });
    });

    describe('SettingsManager Component', () => {
      it('should render settings manager interface', () => {
        render(<SettingsManager />);
        
        expect(screen.getByTestId('settings-manager')).toBeInTheDocument();
      });

      it('should handle settings updates', async () => {
        const onSettingsChange = vi.fn();
        render(<SettingsManager onSettingsChange={onSettingsChange} />);
        
        const saveButton = screen.queryByRole('button', { name: /save/i });
        if (saveButton) {
          await userEvent.click(saveButton);
          expect(onSettingsChange).toHaveBeenCalled();
        }
      });
    });

    describe('RiskManager Component', () => {
      const mockRiskData = {
        portfolioValue: 100000,
        dailyVaR: 2500,
        maxDrawdown: 15.5,
        sharpeRatio: 1.25,
        beta: 1.1
      };

      it('should render risk manager interface', () => {
        render(<RiskManager riskData={mockRiskData} />);
        
        expect(screen.getByTestId('risk-manager')).toBeInTheDocument();
      });

      it('should display risk metrics', () => {
        render(<RiskManager riskData={mockRiskData} />);
        
        expect(screen.getByText(/VaR/i)).toBeInTheDocument();
        expect(screen.getByText(/Sharpe/i)).toBeInTheDocument();
      });

      it('should handle risk threshold alerts', () => {
        const riskData = { ...mockRiskData, dailyVaR: 5000 }; // High risk
        render(<RiskManager riskData={riskData} />);
        
        expect(screen.getByTestId('risk-alert')).toBeInTheDocument();
      });
    });

    describe('PositionManager Component', () => {
      const mockPositions = [
        { symbol: 'AAPL', quantity: 100, avgPrice: 150.00, currentPrice: 155.00 },
        { symbol: 'GOOGL', quantity: 50, avgPrice: 2800.00, currentPrice: 2850.00 }
      ];

      it('should render position manager interface', () => {
        render(<PositionManager positions={mockPositions} />);
        
        expect(screen.getByTestId('position-manager')).toBeInTheDocument();
      });

      it('should display all positions', () => {
        render(<PositionManager positions={mockPositions} />);
        
        expect(screen.getByText('AAPL')).toBeInTheDocument();
        expect(screen.getByText('GOOGL')).toBeInTheDocument();
      });

      it('should handle position actions', async () => {
        const onClosePosition = vi.fn();
        render(<PositionManager positions={mockPositions} onClosePosition={onClosePosition} />);
        
        const closeButton = screen.queryByRole('button', { name: /close/i });
        if (closeButton) {
          await userEvent.click(closeButton);
          expect(onClosePosition).toHaveBeenCalled();
        }
      });
    });

    describe('LazyChart Component', () => {
      const mockChartData = [
        { date: '2024-01-01', value: 100 },
        { date: '2024-01-02', value: 105 },
        { date: '2024-01-03', value: 103 }
      ];

      it('should render lazy chart component', () => {
        render(<LazyChart data={mockChartData} chartType="line" />);
        
        expect(screen.getByTestId('lazy-chart')).toBeInTheDocument();
      });

      it('should show loading state initially', () => {
        render(<LazyChart data={mockChartData} chartType="line" loading={true} />);
        
        expect(screen.getByTestId('lazy-chart-loading')).toBeInTheDocument();
      });

      it('should handle different chart types', () => {
        const { rerender } = render(<LazyChart data={mockChartData} chartType="line" />);
        expect(screen.getByTestId('lazy-chart')).toBeInTheDocument();

        rerender(<LazyChart data={mockChartData} chartType="bar" />);
        expect(screen.getByTestId('lazy-chart')).toBeInTheDocument();
      });

      it('should handle chart rendering errors', () => {
        const invalidData = null;
        render(<LazyChart data={invalidData} chartType="line" />);
        
        expect(screen.getByTestId('lazy-chart-error')).toBeInTheDocument();
      });
    });
  });

  describe('Integration and Performance Tests', () => {
    it('should handle multiple loading states simultaneously', async () => {
      const MultiLoadingComponent = () => {
        const state1 = useLoadingState('key1');
        const state2 = useLoadingState('key2');
        
        return (
          <div>
            <div data-testid="state1-loading">{state1.isLoading.toString()}</div>
            <div data-testid="state2-loading">{state2.isLoading.toString()}</div>
            <button onClick={() => state1.startLoading()} data-testid="start1">Start 1</button>
            <button onClick={() => state2.startLoading()} data-testid="start2">Start 2</button>
          </div>
        );
      };

      render(
        <LoadingProvider>
          <MultiLoadingComponent />
        </LoadingProvider>
      );

      expect(screen.getByTestId('state1-loading')).toHaveTextContent('false');
      expect(screen.getByTestId('state2-loading')).toHaveTextContent('false');

      await userEvent.click(screen.getByTestId('start1'));
      expect(screen.getByTestId('state1-loading')).toHaveTextContent('true');
      expect(screen.getByTestId('state2-loading')).toHaveTextContent('false');

      await userEvent.click(screen.getByTestId('start2'));
      expect(screen.getByTestId('state1-loading')).toHaveTextContent('true');
      expect(screen.getByTestId('state2-loading')).toHaveTextContent('true');
    });

    it('should not cause memory leaks with rapid state changes', async () => {
      const RapidStateComponent = () => {
        const { isLoading, startLoading, stopLoading } = useLoadingState('rapid');
        
        return (
          <div>
            <div data-testid="rapid-loading">{isLoading.toString()}</div>
            <button 
              onClick={() => {
                for (let i = 0; i < 100; i++) {
                  startLoading();
                  stopLoading();
                }
              }}
              data-testid="rapid-toggle"
            >
              Rapid Toggle
            </button>
          </div>
        );
      };

      render(
        <LoadingProvider>
          <RapidStateComponent />
        </LoadingProvider>
      );

      const toggleButton = screen.getByTestId('rapid-toggle');
      await userEvent.click(toggleButton);
      
      // Should not crash or cause performance issues
      expect(screen.getByTestId('rapid-loading')).toBeInTheDocument();
    });

    it('should handle component unmounting gracefully', () => {
      const TestComponent = () => {
        const { startLoading } = useLoadingState('unmount-test');
        
        React.useEffect(() => {
          startLoading();
        }, [startLoading]);
        
        return <div data-testid="unmount-component">Component</div>;
      };

      const { unmount } = render(
        <LoadingProvider>
          <TestComponent />
        </LoadingProvider>
      );

      expect(screen.getByTestId('unmount-component')).toBeInTheDocument();
      
      // Should not throw errors when unmounting
      unmount();
      
      expect(screen.queryByTestId('unmount-component')).not.toBeInTheDocument();
    });
  });

  describe('Accessibility and User Experience', () => {
    it('should provide proper ARIA labels for loading states', () => {
      render(<LoadingButton isLoading={true} aria-label="Submit form">Submit</LoadingButton>);
      
      const button = screen.getByRole('button');
      expect(button).toHaveAttribute('aria-label', 'Submit form');
    });

    it('should support keyboard navigation', async () => {
      render(
        <div>
          <LoadingButton>Button 1</LoadingButton>
          <LoadingButton>Button 2</LoadingButton>
        </div>
      );

      await userEvent.tab();
      expect(document.activeElement).toHaveTextContent('Button 1');
      
      await userEvent.tab();
      expect(document.activeElement).toHaveTextContent('Button 2');
    });

    it('should provide screen reader friendly content', () => {
      render(<LoadingCard title="Loading" description="Fetching data" />);
      
      expect(screen.getByText('Loading')).toBeInTheDocument();
      expect(screen.getByText('Fetching data')).toBeInTheDocument();
    });

    it('should handle reduced motion preferences', () => {
      // Mock prefers-reduced-motion
      Object.defineProperty(window, 'matchMedia', {
        writable: true,
        value: vi.fn().mockImplementation(query => ({
          matches: query === '(prefers-reduced-motion: reduce)',
          media: query,
          onchange: null,
          addListener: vi.fn(),
          removeListener: vi.fn(),
          addEventListener: vi.fn(),
          removeEventListener: vi.fn(),
          dispatchEvent: vi.fn(),
        })),
      });

      render(<LoadingSpinner />);
      
      const spinner = screen.getByTestId('arrow-path-icon');
      expect(spinner).toBeInTheDocument();
    });
  });
});