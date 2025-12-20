import { screen } from "@testing-library/react";
import { vi } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { renderWithProvidersNoRouter } from "../../../test-utils.jsx";
import UIErrorBoundary from "../../../../components/ErrorBoundary";

const ThrowError = ({ shouldThrow, error }) => {
  if (shouldThrow) {
    throw error;
  }
  return <div data-testid="child">No error</div>;
};

const renderWithRouter = (component) => {
  return renderWithProvidersNoRouter(<BrowserRouter>{component}</BrowserRouter>);
};

describe("UI ErrorBoundary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, "error").mockImplementation(() => {});
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    console.error.mockRestore();
    console.warn.mockRestore();
  });

  describe("Rendering", () => {
    test("renders children when no error occurs", () => {
      renderWithRouter(
        <UIErrorBoundary>
          <div data-testid="child">Test child component</div>
        </UIErrorBoundary>
      );

      expect(screen.getByTestId("child")).toBeInTheDocument();
      expect(screen.getByText("Test child component")).toBeInTheDocument();
    });

    test("renders error UI when error occurs", () => {
      const testError = new Error("UI component error");

      renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </UIErrorBoundary>
      );

      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    });

    test("displays built-in error UI for component errors", () => {
      const testError = new Error("Component rendering failed");

      renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </UIErrorBoundary>
      );

      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
      expect(
        screen.getByText(/We apologize for the inconvenience/)
      ).toBeInTheDocument();
    });
  });

  describe("Error Handling", () => {
    test("catches component rendering errors", () => {
      const testError = new Error("Rendering error");

      renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </UIErrorBoundary>
      );

      expect(console.error).toHaveBeenCalled();
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });

    test("logs error information to console", () => {
      const testError = new Error("Test error for logging");

      renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </UIErrorBoundary>
      );

      expect(console.error).toHaveBeenCalledWith(
        "ErrorBoundary caught a React render error:",
        expect.any(Error),
        expect.any(Object)
      );
    });

    test("handles errors with component stack", () => {
      const testError = new Error("Component stack error");

      renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </UIErrorBoundary>
      );

      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  describe("Error UI Features", () => {
    test("displays error icon and title", () => {
      const testError = new Error("Error UI test");

      renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </UIErrorBoundary>
      );

      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
      expect(screen.getByTestId("ErrorOutlineIcon")).toBeInTheDocument();
    });

    test("provides action buttons for recovery", () => {
      const testError = new Error("Action buttons test");

      renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </UIErrorBoundary>
      );

      expect(
        screen.getByRole("button", { name: /try again/i })
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /go home/i })
      ).toBeInTheDocument();
    });
  });

  describe("Recovery", () => {
    test("resets error state when children change", () => {
      const { rerender } = renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={new Error("Initial error")} />
        </UIErrorBoundary>
      );

      expect(screen.getByText(/error/i)).toBeInTheDocument();

      rerender(
        <UIErrorBoundary>
          <div>New working component</div>
        </UIErrorBoundary>
      );

      expect(screen.getByText("New working component")).toBeInTheDocument();
    });

    test("maintains error state for same component", () => {
      const TestComponent = ({ shouldError }) => {
        if (shouldError) throw new Error("Persistent error");
        return <div>Working</div>;
      };

      const { rerender } = renderWithRouter(
        <UIErrorBoundary>
          <TestComponent shouldError={true} />
        </UIErrorBoundary>
      );

      expect(screen.getByText(/error/i)).toBeInTheDocument();

      rerender(
        <UIErrorBoundary>
          <TestComponent shouldError={true} />
        </UIErrorBoundary>
      );

      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  describe("Built-in UI", () => {
    test("shows standard error message and description", () => {
      const testError = new Error("Built-in UI test");

      renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </UIErrorBoundary>
      );

      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
      expect(
        screen.getByText(/We apologize for the inconvenience/)
      ).toBeInTheDocument();
    });

    test("displays action buttons", () => {
      const testError = new Error("Action buttons test");

      renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </UIErrorBoundary>
      );

      expect(
        screen.getByRole("button", { name: /try again/i })
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /go home/i })
      ).toBeInTheDocument();
    });

    test("displays support information", () => {
      const testError = new Error("Support info test");

      renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={testError} />
        </UIErrorBoundary>
      );

      expect(screen.getByText(/contact our support team/i)).toBeInTheDocument();
      expect(screen.getByText("support@edgebrooke.com")).toBeInTheDocument();
    });
  });

  describe("Error Types", () => {
    test("handles JavaScript errors", () => {
      const jsError = new Error("JavaScript runtime error");

      renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={jsError} />
        </UIErrorBoundary>
      );

      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });

    test("handles TypeError", () => {
      const typeError = new TypeError("Cannot read property of undefined");

      renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={typeError} />
        </UIErrorBoundary>
      );

      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });

    test("handles ReferenceError", () => {
      const refError = new ReferenceError("Variable is not defined");

      renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={refError} />
        </UIErrorBoundary>
      );

      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  describe("Edge Cases", () => {
    test("handles null error", () => {
      renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={null} />
        </UIErrorBoundary>
      );

      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });

    test("handles undefined error", () => {
      renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={undefined} />
        </UIErrorBoundary>
      );

      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });

    test("handles empty error message", () => {
      const emptyError = new Error("");

      renderWithRouter(
        <UIErrorBoundary>
          <ThrowError shouldThrow={true} error={emptyError} />
        </UIErrorBoundary>
      );

      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });

    test("handles nested error boundaries", () => {
      const testError = new Error("Nested boundary test");

      renderWithRouter(
        <UIErrorBoundary>
          <UIErrorBoundary>
            <ThrowError shouldThrow={true} error={testError} />
          </UIErrorBoundary>
        </UIErrorBoundary>
      );

      // Inner error boundary should catch the error and show standard UI
      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
      // Should only see one error UI (from the inner boundary)
      expect(screen.getAllByText("Something went wrong")).toHaveLength(1);
    });
  });
});
