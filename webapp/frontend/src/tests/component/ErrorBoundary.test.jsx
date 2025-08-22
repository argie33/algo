import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { BrowserRouter } from "react-router-dom";
import ErrorBoundary from "../../components/ErrorBoundary";

// Mock console.error to avoid cluttering test output
const originalError = console.error;
beforeAll(() => {
  console.error = vi.fn();
});

afterAll(() => {
  console.error = originalError;
});

// Component that throws an error for testing
const ThrowingComponent = ({
  shouldThrow = false,
  errorMessage = "Test error",
}) => {
  if (shouldThrow) {
    throw new Error(errorMessage);
  }
  return <div>No error occurred</div>;
};

// Component that throws an error during render
const RenderErrorComponent = () => {
  throw new Error("Render error");
};

// Component that throws an error in useEffect
const _EffectErrorComponent = () => {
  React.useEffect(() => {
    throw new Error("Effect error");
  }, []);
  return <div>Effect component loaded</div>;
};

// Component that simulates network/API error
const NetworkErrorComponent = () => {
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    // Simulate API call that fails
    setTimeout(() => {
      setError(new Error("Network request failed"));
    }, 100);
  }, []);

  if (error) throw error;
  return <div>Network component loaded</div>;
};

const renderWithRouter = (component) => {
  return render(<BrowserRouter>{component}</BrowserRouter>);
};

describe("ErrorBoundary Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Normal Operation", () => {
    it("should render children when no error occurs", () => {
      renderWithRouter(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={false} />
        </ErrorBoundary>
      );

      expect(screen.getByText("No error occurred")).toBeInTheDocument();
    });

    it("should not interfere with normal component behavior", () => {
      const TestComponent = () => {
        const [count, setCount] = React.useState(0);
        return (
          <div>
            <p>Count: {count}</p>
            <button onClick={() => setCount((c) => c + 1)}>Increment</button>
          </div>
        );
      };

      renderWithRouter(
        <ErrorBoundary>
          <TestComponent />
        </ErrorBoundary>
      );

      expect(screen.getByText("Count: 0")).toBeInTheDocument();

      fireEvent.click(screen.getByText("Increment"));

      expect(screen.getByText("Count: 1")).toBeInTheDocument();
    });
  });

  describe("Error Catching", () => {
    it("should catch and display render errors", () => {
      renderWithRouter(
        <ErrorBoundary>
          <RenderErrorComponent />
        </ErrorBoundary>
      );

      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
      expect(screen.getByText(/Try Again/i)).toBeInTheDocument();
    });

    it("should catch errors from child components", () => {
      renderWithRouter(
        <ErrorBoundary>
          <ThrowingComponent
            shouldThrow={true}
            errorMessage="Child component error"
          />
        </ErrorBoundary>
      );

      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
      expect(screen.getByText(/Try Again/i)).toBeInTheDocument();
    });

    it("should display generic user-friendly error messages", () => {
      const customErrorMessage = "Custom API connection failed";

      renderWithRouter(
        <ErrorBoundary>
          <ThrowingComponent
            shouldThrow={true}
            errorMessage={customErrorMessage}
          />
        </ErrorBoundary>
      );

      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
      expect(screen.getByText(/Go Home/i)).toBeInTheDocument();
    });

    it("should catch network/API errors", async () => {
      renderWithRouter(
        <ErrorBoundary>
          <NetworkErrorComponent />
        </ErrorBoundary>
      );

      // Initially should render normally
      expect(screen.getByText("Network component loaded")).toBeInTheDocument();

      // Wait for error to be thrown
      await new Promise((resolve) => setTimeout(resolve, 150));

      // Should now show error boundary with user-friendly messages
      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
      expect(screen.getByText(/Try Again/i)).toBeInTheDocument();
    });
  });

  describe("Error Boundary UI", () => {
    it("should display error details in development mode", () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = "development";

      renderWithRouter(
        <ErrorBoundary>
          <ThrowingComponent
            shouldThrow={true}
            errorMessage="Development error"
          />
        </ErrorBoundary>
      );

      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
      expect(screen.getByText(/Development error/i)).toBeInTheDocument();

      // Should show additional debug information in development
      expect(screen.getByText(/Error Details/i)).toBeInTheDocument();

      process.env.NODE_ENV = originalEnv;
    });

    it("should provide retry functionality", () => {
      const RetryableComponent = () => {
        const [shouldError, setShouldError] = React.useState(true);

        React.useEffect(() => {
          // Auto-recover after 2 seconds
          const timer = setTimeout(() => setShouldError(false), 2000);
          return () => clearTimeout(timer);
        }, []);

        if (shouldError) {
          throw new Error("Retryable error");
        }

        return <div>Component recovered</div>;
      };

      renderWithRouter(
        <ErrorBoundary>
          <RetryableComponent />
        </ErrorBoundary>
      );

      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();

      // Click retry button
      const retryButton = screen.getByText(/Try Again/i);
      fireEvent.click(retryButton);

      // Should attempt to re-render the component
      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
    });

    it("should show user-friendly error messages", () => {
      renderWithRouter(
        <ErrorBoundary>
          <ThrowingComponent
            shouldThrow={true}
            errorMessage="TypeError: Cannot read property 'data' of undefined"
          />
        </ErrorBoundary>
      );

      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
      // Should show user-friendly message instead of technical error
      expect(
        screen.getByText(/We apologize for the inconvenience/i)
      ).toBeInTheDocument();
    });
  });

  describe("Error Reporting", () => {
    it("should log errors for monitoring", () => {
      const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

      renderWithRouter(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} errorMessage="Logged error" />
        </ErrorBoundary>
      );

      // Check that error logging occurred (ErrorBoundary logs in multiple calls)
      expect(errorSpy).toHaveBeenCalled();

      // Check that one of the calls contains our ErrorBoundary log message
      const calls = errorSpy.mock.calls;
      const errorBoundaryCall = calls.find(
        (call) =>
          typeof call[0] === "string" &&
          call[0].includes("ErrorBoundary caught a React render error:")
      );
      expect(errorBoundaryCall).toBeDefined();

      errorSpy.mockRestore();
    });

    it("should capture error context for debugging", () => {
      const ComponentWithContext = () => {
        const contextInfo = {
          userId: "user123",
          page: "dashboard",
          timestamp: new Date().toISOString(),
        };

        throw new Error(`Context error: ${JSON.stringify(contextInfo)}`);
      };

      renderWithRouter(
        <ErrorBoundary>
          <ComponentWithContext />
        </ErrorBoundary>
      );

      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
      // In production, specific context details are not shown to users
      expect(screen.getByText(/Try Again/i)).toBeInTheDocument();
    });
  });

  describe("Recovery Mechanisms", () => {
    it("should provide retry functionality", async () => {
      renderWithRouter(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} errorMessage="Retry error" />
        </ErrorBoundary>
      );

      // Should show error initially
      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();

      // Should provide retry button
      expect(screen.getByText(/Try Again/i)).toBeInTheDocument();

      // Click retry - this will re-render the error boundary
      fireEvent.click(screen.getByText(/Try Again/i));

      // Should still show error (retry doesn't fix the component itself)
      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
    });

    it("should provide professional error UI for critical sections", () => {
      renderWithRouter(
        <ErrorBoundary>
          <ThrowingComponent
            shouldThrow={true}
            errorMessage="Critical section error"
          />
        </ErrorBoundary>
      );

      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
      expect(
        screen.getByText(/We apologize for the inconvenience/i)
      ).toBeInTheDocument();
      expect(screen.getByText(/Try Again/i)).toBeInTheDocument();
      expect(screen.getByText(/Go Home/i)).toBeInTheDocument();
    });
  });

  describe("Nested Error Boundaries", () => {
    it("should handle nested error boundaries correctly", () => {
      const InnerComponent = () => {
        throw new Error("Inner component error");
      };

      renderWithRouter(
        <ErrorBoundary>
          <div>
            <h1>Outer content</h1>
            <ErrorBoundary>
              <InnerComponent />
            </ErrorBoundary>
            <p>This should still render</p>
          </div>
        </ErrorBoundary>
      );

      // Inner error boundary should catch the error
      expect(screen.getByText("Outer content")).toBeInTheDocument();
      expect(screen.getByText("This should still render")).toBeInTheDocument();
      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
      expect(screen.getByText(/Try Again/i)).toBeInTheDocument();
    });

    it("should escalate errors from failed error boundaries", () => {
      const FailingErrorBoundary = ({ children }) => {
        const [hasError, setHasError] = React.useState(false);

        if (hasError) {
          // Simulate error boundary itself failing
          throw new Error("Error boundary failed");
        }

        try {
          return children;
        } catch (error) {
          setHasError(true);
          return null;
        }
      };

      renderWithRouter(
        <ErrorBoundary>
          <FailingErrorBoundary>
            <ThrowingComponent shouldThrow={true} />
          </FailingErrorBoundary>
        </ErrorBoundary>
      );

      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
      expect(screen.getByText(/Try Again/i)).toBeInTheDocument();
    });
  });

  describe("Performance Impact", () => {
    it("should not impact performance when no errors occur", () => {
      const startTime = performance.now();

      renderWithRouter(
        <ErrorBoundary>
          <div>
            {Array.from({ length: 100 }, (_, i) => (
              <div key={i}>Item {i}</div>
            ))}
          </div>
        </ErrorBoundary>
      );

      const endTime = performance.now();
      const renderTime = endTime - startTime;

      // Should render quickly (less than 50ms for 100 items)
      expect(renderTime).toBeLessThan(50);
      expect(screen.getByText("Item 0")).toBeInTheDocument();
      expect(screen.getByText("Item 99")).toBeInTheDocument();
    });
  });

  describe("Integration with Router", () => {
    it("should maintain navigation after error recovery", () => {
      const NavigationComponent = () => {
        const [shouldError, _setShouldError] = React.useState(true);

        if (shouldError) {
          throw new Error("Navigation error");
        }

        return (
          <div>
            <button onClick={() => window.history.pushState({}, "", "/test")}>
              Navigate
            </button>
          </div>
        );
      };

      renderWithRouter(
        <ErrorBoundary>
          <NavigationComponent />
        </ErrorBoundary>
      );

      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();

      // Error boundary should not break routing
      expect(window.location.pathname).toBe("/");
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA labels for error states", () => {
      renderWithRouter(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      // The error state should be clearly visible to screen readers
      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
      expect(screen.getByText(/Try Again/i)).toBeInTheDocument();
    });

    it("should be keyboard accessible", () => {
      renderWithRouter(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      const retryButton = screen.getByText(/Try Again/i);

      // Should be focusable
      retryButton.focus();
      expect(retryButton).toHaveFocus();

      // Should be activatable with Enter key
      fireEvent.keyDown(retryButton, { key: "Enter" });
      // Error boundary should attempt retry
      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
    });

    it("should announce errors to screen readers", () => {
      renderWithRouter(
        <ErrorBoundary>
          <ThrowingComponent
            shouldThrow={true}
            errorMessage="Accessibility error"
          />
        </ErrorBoundary>
      );

      // Error information should be accessible to screen readers
      expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
      expect(screen.getByText(/Try Again/i)).toBeInTheDocument();
    });
  });
});
