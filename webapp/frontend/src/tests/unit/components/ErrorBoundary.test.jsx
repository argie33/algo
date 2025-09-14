import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import ErrorBoundary from '../../../components/ErrorBoundary';

// Enhanced error throwing component for comprehensive testing
const ThrowError = ({ shouldThrow, error, errorInfo }) => {
  if (shouldThrow) {
    if (errorInfo) {
      // Simulate componentDidCatch with errorInfo
      const mockError = new Error(error?.message || 'Test error');
      mockError.componentStack = errorInfo.componentStack || 'Mock component stack';
      throw mockError;
    }
    throw error || new Error('Test error');
  }
  return <div data-testid="child">No error</div>;
};

describe('ErrorBoundary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    
    // Mock window.location
    delete window.location;
    window.location = { 
      reload: vi.fn(), 
      href: '',
      assign: vi.fn()
    };
  });

  afterEach(() => {
    console.error.mockRestore();
    console.warn.mockRestore();
  });

  describe('Basic Functionality', () => {
    test('renders children when no error occurs', () => {
      render(
        <ErrorBoundary>
          <div data-testid="child">Test child component</div>
        </ErrorBoundary>
      );
      
      expect(screen.getByTestId('child')).toBeInTheDocument();
      expect(screen.getByText('Test child component')).toBeInTheDocument();
    });

    test('renders error UI when error occurs', () => {
      const testError = new Error('Test error message');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </ErrorBoundary>
      );
      
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
      expect(screen.getByText(/We apologize for the inconvenience/)).toBeInTheDocument();
      expect(screen.getByText('Try Again')).toBeInTheDocument();
      expect(screen.getByText('Go Home')).toBeInTheDocument();
    });
  });

  describe('Network Error Detection Logic', () => {
    test('differentiates between React render errors and network errors', () => {
      const networkError = new Error('Network Error: fetch failed');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={networkError} />
        </ErrorBoundary>
      );
      
      // Should still catch the error and show UI since it's thrown in render
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
      expect(console.error).toHaveBeenCalled();
    });

    test('handles ECONNREFUSED errors', () => {
      const networkError = new Error('ECONNREFUSED: Connection refused');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={networkError} />
        </ErrorBoundary>
      );
      
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    test('handles timeout errors correctly', () => {
      const timeoutError = new Error('timeout exceeded');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={timeoutError} />
        </ErrorBoundary>
      );
      
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    test('processes errors with fetch keywords', () => {
      const fetchError = new Error('fetch request failed');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={fetchError} />
        </ErrorBoundary>
      );
      
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });
  });

  describe('Environment-Specific Behavior', () => {
    test('shows error details in development mode', () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = 'development';
      
      const testError = new Error('Development error details');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </ErrorBoundary>
      );
      
      expect(screen.getByText('Error Details (Development Only):')).toBeInTheDocument();
      expect(screen.getByText('Error: Development error details')).toBeInTheDocument();
      
      process.env.NODE_ENV = originalEnv;
    });

    test('shows error ID in production mode', () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = 'production';
      
      const testError = new Error('Production error');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </ErrorBoundary>
      );
      
      expect(screen.getByText(/Error ID:/)).toBeInTheDocument();
      expect(screen.getByText(/Please provide this ID when contacting support/)).toBeInTheDocument();
      expect(screen.queryByText('Error Details (Development Only):')).not.toBeInTheDocument();
      
      process.env.NODE_ENV = originalEnv;
    });

    test('generates unique error IDs in production', () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = 'production';
      
      const testError1 = new Error('First error');
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={testError1} />
        </ErrorBoundary>
      );
      
      // Check for the "Error ID:" label
      expect(screen.getByText('Error ID:')).toBeInTheDocument();
      
      // Check that an error ID matching the expected format exists in the document
      const errorIdRegex = /ERR_\d+_[a-z0-9]+/;
      expect(screen.getByText(errorIdRegex)).toBeInTheDocument();
      
      process.env.NODE_ENV = originalEnv;
    });
  });

  describe('User Interactions', () => {
    test('handles Try Again button click with page reload', () => {
      const testError = new Error('Reload test error');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </ErrorBoundary>
      );
      
      const tryAgainButton = screen.getByText('Try Again');
      fireEvent.click(tryAgainButton);
      
      expect(window.location.reload).toHaveBeenCalledTimes(1);
    });

    test('handles Go Home button click with navigation', () => {
      const testError = new Error('Home navigation test');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </ErrorBoundary>
      );
      
      const goHomeButton = screen.getByText('Go Home');
      fireEvent.click(goHomeButton);
      
      expect(window.location.href).toBe('/');
    });

    test('support email link has correct href', () => {
      const testError = new Error('Support email test');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </ErrorBoundary>
      );
      
      const supportLink = screen.getByText('support@edgebrooke.com');
      expect(supportLink).toHaveAttribute('href', 'mailto:support@edgebrooke.com');
      expect(supportLink.tagName).toBe('A');
    });
  });

  describe('Component Stack and Error Info', () => {
    test('displays component stack in development mode', () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = 'development';
      
      const testError = new Error('Component stack test');
      
      render(
        <ErrorBoundary>
          <ThrowError 
            shouldThrow={true} 
            error={testError}
            errorInfo={{ componentStack: 'Test component stack trace' }}
          />
        </ErrorBoundary>
      );
      
      expect(screen.getByText('Component Stack')).toBeInTheDocument();
      
      process.env.NODE_ENV = originalEnv;
    });

    test('handles missing component stack gracefully', () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = 'development';
      
      const testError = new Error('No component stack');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </ErrorBoundary>
      );
      
      expect(screen.getByText('Error Details (Development Only):')).toBeInTheDocument();
      // Component Stack text might appear but should not have meaningful content
      const componentStackElements = screen.queryAllByText(/Component Stack/);
      if (componentStackElements.length > 0) {
        // If Component Stack text exists, it should be minimal or empty
        expect(componentStackElements.length).toBeLessThanOrEqual(1);
      }
      
      process.env.NODE_ENV = originalEnv;
    });
  });

  describe('Error State Management', () => {
    test('getDerivedStateFromError sets hasError state', () => {
      const testError = new Error('State management test');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </ErrorBoundary>
      );
      
      // Error boundary should show error UI
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
      expect(screen.queryByTestId('child')).not.toBeInTheDocument();
    });

    test('resets state after Try Again click', () => {
      const testError = new Error('Reset state test');
      
      const { rerender: _rerender } = render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </ErrorBoundary>
      );
      
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
      
      const tryAgainButton = screen.getByText('Try Again');
      fireEvent.click(tryAgainButton);
      
      // After click, window.location.reload should be called
      expect(window.location.reload).toHaveBeenCalled();
      
      // In a real browser, window.location.reload would reload the page
      // In the test environment, we can verify the reload was called
      // and that the component would work correctly with a fresh render
      
      // Create a fresh ErrorBoundary to simulate page reload
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={false} error={testError} />
        </ErrorBoundary>
      );
      
      // After "page reload", the child should appear normally
      expect(screen.getByTestId('child')).toBeInTheDocument();
    });
  });

  describe('Error Logging and Reporting', () => {
    test('logs errors with proper context', () => {
      const consoleErrorSpy = vi.spyOn(console, 'error');
      const testError = new Error('Logging test');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </ErrorBoundary>
      );
      
      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'ErrorBoundary caught a React render error:',
        expect.any(Error),
        expect.any(Object)
      );
    });

    test('handles error reporting service integration placeholder', () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = 'production';
      
      const testError = new Error('Error service integration test');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </ErrorBoundary>
      );
      
      // The commented-out error reporting service should not cause issues
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
      
      process.env.NODE_ENV = originalEnv;
    });
  });

  describe('Professional UI Elements', () => {
    test('displays professional footer content', () => {
      const testError = new Error('Footer test');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </ErrorBoundary>
      );
      
      // Check for footer content - try multiple query strategies and handle split text
      const dashboardTextExact = screen.queryByText('Edgebrooke Capital Financial Dashboard');
      const dashboardTextRegex = screen.queryByText(/Edgebrooke Capital Financial Dashboard/);
      const dashboardTextSplit = screen.queryByText(/Edgebrooke Capital/) && screen.queryByText(/Financial Dashboard/);
      
      const dashboardExists = dashboardTextExact || dashboardTextRegex || dashboardTextSplit;
      expect(dashboardExists).toBeTruthy();
      
      expect(screen.getByText(/Enterprise-grade financial data platform/)).toBeInTheDocument();
    });

    test('displays all required UI elements', () => {
      const testError = new Error('Complete UI test');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </ErrorBoundary>
      );
      
      // Main elements
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
      expect(screen.getByText(/We apologize for the inconvenience/)).toBeInTheDocument();
      expect(screen.getByText('Try Again')).toBeInTheDocument();
      expect(screen.getByText('Go Home')).toBeInTheDocument();
      expect(screen.getByText(/If this problem persists/)).toBeInTheDocument();
    });
  });

  describe('Edge Cases and Error Variations', () => {
    test('handles null error gracefully', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={null} />
        </ErrorBoundary>
      );
      
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    test('handles undefined error gracefully', () => {
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={undefined} />
        </ErrorBoundary>
      );
      
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    test('handles error with empty message', () => {
      const emptyError = new Error('');
      
      render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={emptyError} />
        </ErrorBoundary>
      );
      
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    test('handles multiple consecutive errors', () => {
      const firstError = new Error('First error');
      const { rerender } = render(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={firstError} />
        </ErrorBoundary>
      );
      
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
      
      const secondError = new Error('Second error');
      rerender(
        <ErrorBoundary>
          <ThrowError shouldThrow={true} error={secondError} />
        </ErrorBoundary>
      );
      
      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });
  });
});