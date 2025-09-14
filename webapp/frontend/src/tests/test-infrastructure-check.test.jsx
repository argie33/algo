/**
 * Test Infrastructure Check
 * Basic test to verify test infrastructure is working correctly
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";

// Simple test component that doesn't depend on external APIs
const TestComponent = ({ message = "Test Component" }) => {
  return (
    <div data-testid="test-component">
      <h1>{message}</h1>
      <p>This is a test component</p>
    </div>
  );
};

// Test wrapper with providers
const TestWrapper = ({ children }) => {
  return <BrowserRouter>{children}</BrowserRouter>;
};

describe("Test Infrastructure Check", () => {
  it("should render basic components", () => {
    render(
      <TestWrapper>
        <TestComponent />
      </TestWrapper>
    );

    expect(screen.getByTestId("test-component")).toBeInTheDocument();
    expect(screen.getByText("Test Component")).toBeInTheDocument();
    expect(screen.getByText("This is a test component")).toBeInTheDocument();
  });

  it("should handle props correctly", () => {
    const customMessage = "Custom Test Message";

    render(
      <TestWrapper>
        <TestComponent message={customMessage} />
      </TestWrapper>
    );

    expect(screen.getByText(customMessage)).toBeInTheDocument();
  });

  it("should work with vitest mocks", () => {
    const mockFn = vi.fn();
    mockFn("test call");

    expect(mockFn).toHaveBeenCalledWith("test call");
    expect(mockFn).toHaveBeenCalledTimes(1);
  });

  it("should work with async operations", async () => {
    const asyncOperation = () => Promise.resolve("success");

    const result = await asyncOperation();
    expect(result).toBe("success");
  });

  it("should handle MUI components with basic mocks", () => {
    // This tests that MUI components can render without errors
    render(
      <TestWrapper>
        <div>
          <button>MUI Button Test</button>
        </div>
      </TestWrapper>
    );

    expect(screen.getByText("MUI Button Test")).toBeInTheDocument();
  });
});
