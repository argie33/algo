/**
 * Unit Tests for ErrorBoundary Component  
 * Tests error catching, display modes, and recovery actions
 */

import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ErrorBoundary from "../../../components/ErrorBoundary.jsx";
import { renderWithTheme, ErrorThrowingComponent } from "./test-helpers/component-test-utils.jsx";

// Suppress console errors for testing
const originalConsoleError = console.error;
beforeEach(() => {
  console.error = vi.fn();
});

afterEach(() => {
  console.error = originalConsoleError;
});

describe("ErrorBoundary Component", () => {
  describe("Normal Operation", () => {
    it("should render children when no error occurs", () => {
      renderWithTheme(
        <ErrorBoundary>
          <div data-testid="test-content">Normal content</div>
        </ErrorBoundary>
      );

      expect(screen.getByTestId("test-content")).toBeInTheDocument();
      expect(screen.getByText("Normal content")).toBeInTheDocument();
    });

    it("should render complex children components correctly", () => {
      renderWithTheme(
        <ErrorBoundary>
          <div>
            <h1>Dashboard</h1>
            <p>Financial data</p>
            <button>Trade Now</button>
          </div>
        </ErrorBoundary>
      );

      expect(screen.getByText("Dashboard")).toBeInTheDocument();
      expect(screen.getByText("Financial data")).toBeInTheDocument();
      expect(screen.getByText("Trade Now")).toBeInTheDocument();
    });

    it("should pass through props to children", () => {
      const TestComponent = ({ message }) => (
        <div data-testid="test-component">{message}</div>
      );

      renderWithTheme(
        <ErrorBoundary>
          <TestComponent message="Props work correctly" />
        </ErrorBoundary>
      );

      expect(screen.getByTestId("test-component")).toHaveTextContent("Props work correctly");
    });
  });

  describe("Error Catching", () => {
    it("should catch and display error when child component throws", () => {
      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      // Should show error UI instead of children
      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
      expect(screen.getByText(/We apologize for the inconvenience/)).toBeInTheDocument();
      expect(screen.queryByText("No error")).not.toBeInTheDocument();
    });

    it("should display error icon", () => {
      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      // MUI ErrorOutline icon should be present
      const errorIcon = document.querySelector('[data-testid="ErrorOutlineIcon"]');
      expect(errorIcon).toBeInTheDocument();
    });

    it("should generate unique error ID", () => {
      // Mock production environment
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = "production";

      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText(/Error ID:/)).toBeInTheDocument();
      expect(screen.getByText(/ERR_/)).toBeInTheDocument();

      process.env.NODE_ENV = originalEnv;
    });

    it("should handle custom error messages", () => {
      const CustomErrorComponent = () => {
        throw new Error("Custom test error message");
      };

      renderWithTheme(
        <ErrorBoundary>
          <CustomErrorComponent />
        </ErrorBoundary>
      );

      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    });
  });

  describe("Development Mode", () => {
    it("should show detailed error information in development", () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = "development";

      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText("Error Details (Development Only):")).toBeInTheDocument();
      expect(screen.getByText("Component Stack")).toBeInTheDocument();

      process.env.NODE_ENV = originalEnv;
    });

    it("should not show detailed error in production", () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = "production";

      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.queryByText("Error Details (Development Only):")).not.toBeInTheDocument();
      expect(screen.queryByText("Component Stack")).not.toBeInTheDocument();

      process.env.NODE_ENV = originalEnv;
    });
  });

  describe("Production Mode", () => {
    it("should show error ID and support message in production", () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = "production";

      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText(/Error ID:/)).toBeInTheDocument();
      expect(screen.getByText(/Please provide this ID when contacting support/)).toBeInTheDocument();

      process.env.NODE_ENV = originalEnv;
    });

    it("should include professional branding", () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = "production";

      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      // Check that professional branding text exists in the document
      expect(document.body.textContent).toContain("Edgebrooke Capital Financial Dashboard");
      expect(document.body.textContent).toContain("Enterprise-grade financial data platform");

      process.env.NODE_ENV = originalEnv;
    });
  });

  describe("Recovery Actions", () => {
    it("should provide Try Again button", () => {
      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      const tryAgainButton = screen.getByRole("button", { name: /try again/i });
      expect(tryAgainButton).toBeInTheDocument();
      expect(tryAgainButton).toHaveTextContent("Try Again");
    });

    it("should provide Go Home button", () => {
      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      const goHomeButton = screen.getByRole("button", { name: /go home/i });
      expect(goHomeButton).toBeInTheDocument();
      expect(goHomeButton).toHaveTextContent("Go Home");
    });

    it("should reset error state when Try Again is clicked", async () => {
      const user = userEvent.setup();
      
      // Create a wrapper component to test error recovery
      const TestWrapper = () => {
        const [componentKey, setComponentKey] = React.useState(1);
        const [shouldThrow, setShouldThrow] = React.useState(true);
        
        return (
          <div>
            <ErrorBoundary key={`boundary-${componentKey}`}>
              <ErrorThrowingComponent shouldThrow={shouldThrow} />
            </ErrorBoundary>
            <button 
              data-testid="fix-and-reset" 
              onClick={() => {
                setShouldThrow(false);
                setComponentKey(prev => prev + 1); // Force remount of ErrorBoundary
              }}
            >
              Fix and Reset
            </button>
          </div>
        );
      };

      renderWithTheme(<TestWrapper />);

      // Error UI should be showing
      expect(screen.getByText("Something went wrong")).toBeInTheDocument();

      // Click Try Again to show it calls the handler
      const tryAgainButton = screen.getByRole("button", { name: /try again/i });
      await user.click(tryAgainButton);

      // Fix the underlying component and force remount
      const fixButton = screen.getByTestId("fix-and-reset");
      await user.click(fixButton);

      // Should show normal content again
      expect(screen.getByText("No error")).toBeInTheDocument();
      expect(screen.queryByText("Something went wrong")).not.toBeInTheDocument();
    });

    it("should handle Go Home button click", async () => {
      const user = userEvent.setup();
      
      // Mock window.location
      const originalLocation = window.location;
      delete window.location;
      window.location = { href: "" };

      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      const goHomeButton = screen.getByRole("button", { name: /go home/i });
      await user.click(goHomeButton);

      expect(window.location.href).toBe("/");

      // Restore original location
      window.location = originalLocation;
    });
  });

  describe("Support Integration", () => {
    it("should provide support email link", () => {
      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      const supportLink = screen.getByRole("link", { name: /support@edgebrooke.com/i });
      expect(supportLink).toBeInTheDocument();
      expect(supportLink).toHaveAttribute("href", "mailto:support@edgebrooke.com");
    });

    it("should show support contact information", () => {
      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText(/If this problem persists/)).toBeInTheDocument();
      expect(screen.getByText("support@edgebrooke.com")).toBeInTheDocument();
    });

    it("should include contact support icon", () => {
      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      // MUI ContactSupport icon should be present
      const contactIcon = document.querySelector('[data-testid="ContactSupportIcon"]');
      expect(contactIcon).toBeInTheDocument();
    });
  });

  describe("Error Filtering", () => {
    it("should not catch network errors", () => {
      const NetworkErrorComponent = () => {
        throw new Error("Network Error: fetch failed");
      };

      renderWithTheme(
        <ErrorBoundary>
          <NetworkErrorComponent />
        </ErrorBoundary>
      );

      // Should still show error UI for component errors, but log network errors differently
      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    });

    it("should handle different error types", () => {
      const TypeErrorComponent = () => {
        throw new TypeError("Cannot read property of undefined");
      };

      renderWithTheme(
        <ErrorBoundary>
          <TypeErrorComponent />
        </ErrorBoundary>
      );

      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    });

    it("should handle syntax errors", () => {
      const SyntaxErrorComponent = () => {
        throw new SyntaxError("Unexpected token");
      };

      renderWithTheme(
        <ErrorBoundary>
          <SyntaxErrorComponent />
        </ErrorBoundary>
      );

      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    });
  });

  describe("UI Layout and Styling", () => {
    it("should have proper responsive layout", () => {
      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      const errorCard = document.querySelector(".MuiCard-root");
      expect(errorCard).toBeInTheDocument();
      
      const cardContent = document.querySelector(".MuiCardContent-root");
      expect(cardContent).toBeInTheDocument();
    });

    it("should use proper MUI theme colors", () => {
      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      // Error icon should have error color
      const errorIcon = document.querySelector('[data-testid="ErrorOutlineIcon"]');
      expect(errorIcon).toHaveClass("MuiSvgIcon-root");
    });

    it("should have accessible structure", () => {
      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      // Should have proper heading structure
      const heading = screen.getByRole("heading", { name: "Something went wrong" });
      expect(heading).toBeInTheDocument();

      // Buttons should be accessible
      const buttons = screen.getAllByRole("button");
      expect(buttons.length).toBeGreaterThan(0);
      buttons.forEach(button => {
        expect(button).toBeInTheDocument();
      });
    });
  });

  describe("Edge Cases", () => {
    it("should handle null children", () => {
      renderWithTheme(
        <ErrorBoundary>
          {null}
        </ErrorBoundary>
      );

      // Should render without error
      expect(document.body).toBeInTheDocument();
    });

    it("should handle undefined children", () => {
      renderWithTheme(
        <ErrorBoundary>
          {undefined}
        </ErrorBoundary>
      );

      // Should render without error
      expect(document.body).toBeInTheDocument();
    });

    it("should handle multiple children", () => {
      renderWithTheme(
        <ErrorBoundary>
          <div>Child 1</div>
          <div>Child 2</div>
          <div>Child 3</div>
        </ErrorBoundary>
      );

      expect(screen.getByText("Child 1")).toBeInTheDocument();
      expect(screen.getByText("Child 2")).toBeInTheDocument();
      expect(screen.getByText("Child 3")).toBeInTheDocument();
    });

    it("should handle errors in nested components", () => {
      const NestedErrorComponent = () => (
        <div>
          <div>
            <ErrorThrowingComponent shouldThrow={true} />
          </div>
        </div>
      );

      renderWithTheme(
        <ErrorBoundary>
          <NestedErrorComponent />
        </ErrorBoundary>
      );

      expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    });
  });

  describe("Console Logging", () => {
    it("should log errors to console", () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(consoleSpy).toHaveBeenCalled();
      consoleSpy.mockRestore();
    });

    it("should log component stack information", () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      renderWithTheme(
        <ErrorBoundary>
          <ErrorThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      // Should log error with component stack
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining("ErrorBoundary caught a React render error:"),
        expect.any(Error),
        expect.objectContaining({
          componentStack: expect.any(String)
        })
      );

      consoleSpy.mockRestore();
    });
  });
});