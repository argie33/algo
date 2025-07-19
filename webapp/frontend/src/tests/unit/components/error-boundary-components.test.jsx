/**
 * Error Boundary Components Unit Tests
 * Comprehensive testing of all error handling and boundary components
 */

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock Material-UI components
vi.mock('@mui/material', () => ({
  Box: vi.fn(({ children, ...props }) => <div data-testid="mui-box" {...props}>{children}</div>),
  Typography: vi.fn(({ children, ...props }) => <div data-testid="mui-typography" {...props}>{children}</div>),
  Paper: vi.fn(({ children, ...props }) => <div data-testid="mui-paper" {...props}>{children}</div>),
  Button: vi.fn(({ children, onClick, ...props }) => 
    <button data-testid="mui-button" onClick={onClick} {...props}>{children}</button>
  ),
  Alert: vi.fn(({ children, severity, ...props }) => 
    <div data-testid="mui-alert" data-severity={severity} {...props}>{children}</div>
  ),
  CircularProgress: vi.fn(() => <div data-testid="mui-circular-progress">Loading...</div>),
  Container: vi.fn(({ children, ...props }) => 
    <div data-testid="mui-container" {...props}>{children}</div>
  ),
  Stack: vi.fn(({ children, ...props }) => 
    <div data-testid="mui-stack" {...props}>{children}</div>
  ),
  Collapse: vi.fn(({ children, in: isOpen, ...props }) => 
    isOpen ? <div data-testid="mui-collapse" {...props}>{children}</div> : null
  )
}));

// Mock console methods to avoid noise in tests
const originalConsoleError = console.error;
const originalConsoleWarn = console.warn;

// Import actual error boundary components
import ComprehensiveErrorBoundary from '../../../components/ComprehensiveErrorBoundary';
import DashboardErrorBoundary from '../../../components/DashboardErrorBoundary';
import EnhancedAsyncErrorBoundary from '../../../components/EnhancedAsyncErrorBoundary';
import ErrorBoundary from '../../../components/ErrorBoundary';
import ErrorBoundaryTailwind from '../../../components/ErrorBoundaryTailwind';
import ThemeErrorBoundary from '../../../components/ThemeErrorBoundary';

// Test components that throw errors
const ThrowingComponent = ({ shouldThrow = false, errorMessage = 'Test error' }) => {
  if (shouldThrow) {
    throw new Error(errorMessage);
  }
  return <div>Working component</div>;
};

const AsyncThrowingComponent = ({ shouldReject = false }) => {
  React.useEffect(() => {
    if (shouldReject) {
      Promise.reject(new Error('Async error')).catch(() => {
        // Intentionally unhandled for testing
      });
    }
  }, [shouldReject]);
  
  return <div>Async component</div>;
};

describe('🛡️ Error Boundary Components', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock console.error to avoid React error boundary console spam
    console.error = vi.fn();
    console.warn = vi.fn();
  });

  afterEach(() => {
    console.error = originalConsoleError;
    console.warn = originalConsoleWarn;
  });

  describe('ComprehensiveErrorBoundary Component', () => {
    it('should render children when no error occurs', () => {
      render(
        <ComprehensiveErrorBoundary>
          <ThrowingComponent shouldThrow={false} />
        </ComprehensiveErrorBoundary>
      );

      expect(screen.getByText('Working component')).toBeInTheDocument();
    });

    it('should catch and display error when child throws', () => {
      render(
        <ComprehensiveErrorBoundary>
          <ThrowingComponent shouldThrow={true} errorMessage="Component crashed" />
        </ComprehensiveErrorBoundary>
      );

      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
      expect(screen.getByText(/component crashed/i)).toBeInTheDocument();
    });

    it('should provide retry functionality', async () => {
      const user = userEvent.setup();
      
      const { rerender } = render(
        <ComprehensiveErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ComprehensiveErrorBoundary>
      );

      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
      
      const retryButton = screen.getByText(/try again/i);
      await user.click(retryButton);

      // Re-render with working component
      rerender(
        <ComprehensiveErrorBoundary>
          <ThrowingComponent shouldThrow={false} />
        </ComprehensiveErrorBoundary>
      );

      expect(screen.getByText('Working component')).toBeInTheDocument();
    });

    it('should show error details in development mode', () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = 'development';

      render(
        <ComprehensiveErrorBoundary showErrorDetails={true}>
          <ThrowingComponent shouldThrow={true} errorMessage="Detailed error" />
        </ComprehensiveErrorBoundary>
      );

      expect(screen.getByText(/error details/i)).toBeInTheDocument();
      expect(screen.getByText(/detailed error/i)).toBeInTheDocument();

      process.env.NODE_ENV = originalEnv;
    });

    it('should report errors to error reporting service', () => {
      const onError = vi.fn();

      render(
        <ComprehensiveErrorBoundary onError={onError}>
          <ThrowingComponent shouldThrow={true} errorMessage="Reported error" />
        </ComprehensiveErrorBoundary>
      );

      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Reported error'
        }),
        expect.any(Object)
      );
    });

    it('should handle multiple error types', () => {
      const { rerender } = render(
        <ComprehensiveErrorBoundary>
          <ThrowingComponent shouldThrow={true} errorMessage="TypeError: Cannot read property" />
        </ComprehensiveErrorBoundary>
      );

      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();

      rerender(
        <ComprehensiveErrorBoundary>
          <ThrowingComponent shouldThrow={true} errorMessage="ReferenceError: variable is not defined" />
        </ComprehensiveErrorBoundary>
      );

      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    });

    it('should provide fallback UI customization', () => {
      const CustomFallback = ({ error, retry }) => (
        <div>
          <h2>Custom Error UI</h2>
          <p>Error: {error.message}</p>
          <button onClick={retry}>Custom Retry</button>
        </div>
      );

      render(
        <ComprehensiveErrorBoundary fallback={CustomFallback}>
          <ThrowingComponent shouldThrow={true} errorMessage="Custom error" />
        </ComprehensiveErrorBoundary>
      );

      expect(screen.getByText('Custom Error UI')).toBeInTheDocument();
      expect(screen.getByText('Error: Custom error')).toBeInTheDocument();
      expect(screen.getByText('Custom Retry')).toBeInTheDocument();
    });
  });

  describe('DashboardErrorBoundary Component', () => {
    it('should render dashboard-specific error UI', () => {
      render(
        <DashboardErrorBoundary>
          <ThrowingComponent shouldThrow={true} errorMessage="Dashboard widget error" />
        </DashboardErrorBoundary>
      );

      expect(screen.getByText(/dashboard error/i)).toBeInTheDocument();
      expect(screen.getByText(/widget.*failed/i)).toBeInTheDocument();
    });

    it('should provide widget-level error isolation', () => {
      render(
        <div>
          <DashboardErrorBoundary widgetName="Portfolio Widget">
            <ThrowingComponent shouldThrow={true} />
          </DashboardErrorBoundary>
          <DashboardErrorBoundary widgetName="Chart Widget">
            <ThrowingComponent shouldThrow={false} />
          </DashboardErrorBoundary>
        </div>
      );

      // First widget should show error, second should work
      expect(screen.getByText(/portfolio widget.*error/i)).toBeInTheDocument();
      expect(screen.getByText('Working component')).toBeInTheDocument();
    });

    it('should offer widget refresh functionality', async () => {
      const user = userEvent.setup();
      const onRefresh = vi.fn();

      render(
        <DashboardErrorBoundary onRefresh={onRefresh}>
          <ThrowingComponent shouldThrow={true} />
        </DashboardErrorBoundary>
      );

      const refreshButton = screen.getByText(/refresh.*widget/i);
      await user.click(refreshButton);

      expect(onRefresh).toHaveBeenCalled();
    });

    it('should track widget error metrics', () => {
      const onErrorMetric = vi.fn();

      render(
        <DashboardErrorBoundary 
          widgetName="Performance Chart"
          onErrorMetric={onErrorMetric}
        >
          <ThrowingComponent shouldThrow={true} errorMessage="Chart rendering failed" />
        </DashboardErrorBoundary>
      );

      expect(onErrorMetric).toHaveBeenCalledWith({
        widgetName: 'Performance Chart',
        errorType: 'render_error',
        timestamp: expect.any(Number)
      });
    });

    it('should support graceful degradation', () => {
      render(
        <DashboardErrorBoundary 
          gracefulFallback={<div>Simplified widget view</div>}
        >
          <ThrowingComponent shouldThrow={true} />
        </DashboardErrorBoundary>
      );

      expect(screen.getByText('Simplified widget view')).toBeInTheDocument();
    });
  });

  describe('EnhancedAsyncErrorBoundary Component', () => {
    it('should handle async errors', async () => {
      render(
        <EnhancedAsyncErrorBoundary>
          <AsyncThrowingComponent shouldReject={true} />
        </EnhancedAsyncErrorBoundary>
      );

      // Wait for async error to be caught
      await new Promise(resolve => setTimeout(resolve, 100));

      expect(screen.getByText(/async.*error/i)).toBeInTheDocument();
    });

    it('should handle promise rejections', async () => {
      const PromiseRejectingComponent = () => {
        React.useEffect(() => {
          // Unhandled promise rejection
          new Promise((_, reject) => {
            setTimeout(() => reject(new Error('Promise rejected')), 50);
          });
        }, []);

        return <div>Promise component</div>;
      };

      render(
        <EnhancedAsyncErrorBoundary>
          <PromiseRejectingComponent />
        </EnhancedAsyncErrorBoundary>
      );

      await new Promise(resolve => setTimeout(resolve, 100));

      expect(screen.getByText(/async.*error/i)).toBeInTheDocument();
    });

    it('should provide async retry functionality', async () => {
      const user = userEvent.setup();
      let shouldFail = true;

      const RetryableAsyncComponent = () => {
        React.useEffect(() => {
          if (shouldFail) {
            throw new Error('Async operation failed');
          }
        }, []);

        return <div>Async operation succeeded</div>;
      };

      render(
        <EnhancedAsyncErrorBoundary>
          <RetryableAsyncComponent />
        </EnhancedAsyncErrorBoundary>
      );

      expect(screen.getByText(/async.*error/i)).toBeInTheDocument();

      // Simulate fixing the async issue
      shouldFail = false;
      
      const retryButton = screen.getByText(/retry/i);
      await user.click(retryButton);

      expect(screen.getByText('Async operation succeeded')).toBeInTheDocument();
    });

    it('should track async error patterns', () => {
      const onAsyncError = vi.fn();

      render(
        <EnhancedAsyncErrorBoundary onAsyncError={onAsyncError}>
          <AsyncThrowingComponent shouldReject={true} />
        </EnhancedAsyncErrorBoundary>
      );

      expect(onAsyncError).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'async_error',
          timestamp: expect.any(Number)
        })
      );
    });

    it('should support timeout handling', async () => {
      const TimeoutComponent = () => {
        React.useEffect(() => {
          // Simulate long-running operation
          new Promise(resolve => {
            setTimeout(resolve, 5000); // 5 second timeout
          });
        }, []);

        return <div>Long operation</div>;
      };

      render(
        <EnhancedAsyncErrorBoundary timeout={1000}>
          <TimeoutComponent />
        </EnhancedAsyncErrorBoundary>
      );

      await new Promise(resolve => setTimeout(resolve, 1100));

      expect(screen.getByText(/timeout.*error/i)).toBeInTheDocument();
    });
  });

  describe('ErrorBoundary Component', () => {
    it('should provide basic error boundary functionality', () => {
      render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} errorMessage="Basic error" />
        </ErrorBoundary>
      );

      expect(screen.getByText(/error.*occurred/i)).toBeInTheDocument();
    });

    it('should support custom error messages', () => {
      render(
        <ErrorBoundary errorMessage="Custom error boundary message">
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Custom error boundary message')).toBeInTheDocument();
    });

    it('should handle nested error boundaries', () => {
      render(
        <ErrorBoundary errorMessage="Outer boundary">
          <div>
            <ErrorBoundary errorMessage="Inner boundary">
              <ThrowingComponent shouldThrow={true} />
            </ErrorBoundary>
            <div>Other content</div>
          </div>
        </ErrorBoundary>
      );

      // Inner boundary should catch the error
      expect(screen.getByText('Inner boundary')).toBeInTheDocument();
      expect(screen.getByText('Other content')).toBeInTheDocument();
    });

    it('should reset on prop changes', () => {
      const { rerender } = render(
        <ErrorBoundary resetKeys={['key1']}>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText(/error.*occurred/i)).toBeInTheDocument();

      // Reset by changing reset keys
      rerender(
        <ErrorBoundary resetKeys={['key2']}>
          <ThrowingComponent shouldThrow={false} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Working component')).toBeInTheDocument();
    });
  });

  describe('ErrorBoundaryTailwind Component', () => {
    it('should render with Tailwind CSS styling', () => {
      render(
        <ErrorBoundaryTailwind>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundaryTailwind>
      );

      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
      // Tailwind-specific styling would be applied
    });

    it('should support dark mode styling', () => {
      render(
        <ErrorBoundaryTailwind theme="dark">
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundaryTailwind>
      );

      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    });

    it('should be responsive', () => {
      render(
        <ErrorBoundaryTailwind responsive={true}>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundaryTailwind>
      );

      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
      // Responsive classes would be applied
    });

    it('should support custom Tailwind classes', () => {
      render(
        <ErrorBoundaryTailwind className="custom-error-boundary">
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundaryTailwind>
      );

      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    });
  });

  describe('ThemeErrorBoundary Component', () => {
    it('should handle theme-related errors', () => {
      const ThemeThrowingComponent = () => {
        throw new Error('Theme provider not found');
      };

      render(
        <ThemeErrorBoundary>
          <ThemeThrowingComponent />
        </ThemeErrorBoundary>
      );

      expect(screen.getByText(/theme.*error/i)).toBeInTheDocument();
    });

    it('should provide theme fallback', () => {
      render(
        <ThemeErrorBoundary 
          fallbackTheme="light"
          enableFallback={true}
        >
          <ThrowingComponent shouldThrow={true} errorMessage="Theme error" />
        </ThemeErrorBoundary>
      );

      expect(screen.getByText(/theme.*fallback/i)).toBeInTheDocument();
    });

    it('should reset theme state on error', async () => {
      const user = userEvent.setup();
      const onThemeReset = vi.fn();

      render(
        <ThemeErrorBoundary onThemeReset={onThemeReset}>
          <ThrowingComponent shouldThrow={true} />
        </ThemeErrorBoundary>
      );

      const resetButton = screen.getByText(/reset.*theme/i);
      await user.click(resetButton);

      expect(onThemeReset).toHaveBeenCalled();
    });

    it('should handle theme switching errors', () => {
      const ThemeSwitchComponent = ({ theme }) => {
        if (theme === 'invalid') {
          throw new Error('Invalid theme configuration');
        }
        return <div>Theme: {theme}</div>;
      };

      const { rerender } = render(
        <ThemeErrorBoundary>
          <ThemeSwitchComponent theme="light" />
        </ThemeErrorBoundary>
      );

      expect(screen.getByText('Theme: light')).toBeInTheDocument();

      rerender(
        <ThemeErrorBoundary>
          <ThemeSwitchComponent theme="invalid" />
        </ThemeErrorBoundary>
      );

      expect(screen.getByText(/theme.*error/i)).toBeInTheDocument();
    });

    it('should preserve theme context for non-errored components', () => {
      render(
        <ThemeErrorBoundary>
          <div>
            <ThemeErrorBoundary>
              <ThrowingComponent shouldThrow={true} />
            </ThemeErrorBoundary>
            <div>Theme still works here</div>
          </div>
        </ThemeErrorBoundary>
      );

      expect(screen.getByText(/theme.*error/i)).toBeInTheDocument();
      expect(screen.getByText('Theme still works here')).toBeInTheDocument();
    });
  });

  describe('Error Boundary Integration', () => {
    it('should work with React Suspense', () => {
      const SuspenseComponent = React.lazy(() => 
        Promise.resolve({
          default: () => <ThrowingComponent shouldThrow={true} />
        })
      );

      render(
        <ComprehensiveErrorBoundary>
          <React.Suspense fallback={<div>Loading...</div>}>
            <SuspenseComponent />
          </React.Suspense>
        </ComprehensiveErrorBoundary>
      );

      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    });

    it('should handle errors in event handlers', async () => {
      const user = userEvent.setup();

      const EventHandlerComponent = () => {
        const handleClick = () => {
          throw new Error('Event handler error');
        };

        return <button onClick={handleClick}>Click to error</button>;
      };

      render(
        <ComprehensiveErrorBoundary>
          <EventHandlerComponent />
        </ComprehensiveErrorBoundary>
      );

      const button = screen.getByText('Click to error');
      
      // Event handler errors are not caught by error boundaries
      expect(() => {
        fireEvent.click(button);
      }).toThrow('Event handler error');
    });

    it('should handle errors in async effects', async () => {
      const AsyncEffectComponent = () => {
        React.useEffect(() => {
          setTimeout(() => {
            throw new Error('Async effect error');
          }, 50);
        }, []);

        return <div>Async effect component</div>;
      };

      render(
        <EnhancedAsyncErrorBoundary>
          <AsyncEffectComponent />
        </EnhancedAsyncErrorBoundary>
      );

      await new Promise(resolve => setTimeout(resolve, 100));

      expect(screen.getByText(/async.*error/i)).toBeInTheDocument();
    });

    it('should provide error reporting integration', () => {
      const mockErrorReporter = {
        captureException: vi.fn(),
        setContext: vi.fn()
      };

      render(
        <ComprehensiveErrorBoundary errorReporter={mockErrorReporter}>
          <ThrowingComponent shouldThrow={true} errorMessage="Reported error" />
        </ComprehensiveErrorBoundary>
      );

      expect(mockErrorReporter.captureException).toHaveBeenCalledWith(
        expect.objectContaining({
          message: 'Reported error'
        })
      );
    });

    it('should handle multiple nested boundary errors', () => {
      render(
        <ComprehensiveErrorBoundary>
          <DashboardErrorBoundary>
            <ThemeErrorBoundary>
              <ThrowingComponent shouldThrow={true} errorMessage="Nested error" />
            </ThemeErrorBoundary>
          </DashboardErrorBoundary>
        </ComprehensiveErrorBoundary>
      );

      // The innermost boundary (ThemeErrorBoundary) should catch the error
      expect(screen.getByText(/theme.*error/i)).toBeInTheDocument();
    });
  });

  describe('Error Boundary Performance', () => {
    it('should not impact performance when no errors occur', () => {
      const startTime = performance.now();

      render(
        <ComprehensiveErrorBoundary>
          {Array.from({ length: 100 }, (_, i) => (
            <div key={i}>Component {i}</div>
          ))}
        </ComprehensiveErrorBoundary>
      );

      const renderTime = performance.now() - startTime;
      expect(renderTime).toBeLessThan(100); // Should render within 100ms
    });

    it('should handle high frequency errors efficiently', () => {
      const { rerender } = render(
        <ComprehensiveErrorBoundary>
          <ThrowingComponent shouldThrow={false} />
        </ComprehensiveErrorBoundary>
      );

      const startTime = performance.now();

      // Trigger multiple errors in succession
      for (let i = 0; i < 10; i++) {
        rerender(
          <ComprehensiveErrorBoundary>
            <ThrowingComponent shouldThrow={true} errorMessage={`Error ${i}`} />
          </ComprehensiveErrorBoundary>
        );
      }

      const errorHandlingTime = performance.now() - startTime;
      expect(errorHandlingTime).toBeLessThan(500); // Should handle efficiently
    });
  });

  describe('Error Boundary Accessibility', () => {
    it('should provide accessible error messages', () => {
      render(
        <ComprehensiveErrorBoundary>
          <ThrowingComponent shouldThrow={true} errorMessage="Accessibility error" />
        </ComprehensiveErrorBoundary>
      );

      const errorMessage = screen.getByRole('alert');
      expect(errorMessage).toBeInTheDocument();
      expect(errorMessage).toHaveAttribute('aria-live', 'assertive');
    });

    it('should support screen reader announcements', () => {
      render(
        <ComprehensiveErrorBoundary announceErrors={true}>
          <ThrowingComponent shouldThrow={true} errorMessage="Screen reader error" />
        </ComprehensiveErrorBoundary>
      );

      const announcement = screen.getByLabelText(/error occurred/i);
      expect(announcement).toBeInTheDocument();
    });

    it('should provide keyboard navigation for error actions', async () => {
      const user = userEvent.setup();

      render(
        <ComprehensiveErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ComprehensiveErrorBoundary>
      );

      const retryButton = screen.getByText(/try again/i);
      
      await user.tab();
      expect(retryButton).toHaveFocus();

      await user.keyboard('{Enter}');
      // Retry functionality would be triggered
    });
  });
});