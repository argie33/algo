import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import ErrorBoundary from "../../../components/ErrorBoundary";

const ThrowError = ({ shouldThrow }) => {
  if (shouldThrow) {
    throw new Error("Test error");
  }
  return <div data-testid="child">No error</div>;
};

describe("ErrorBoundary", () => {
  let consoleError;

  beforeEach(() => {
    consoleError = console.error;
    console.error = vi.fn();
  });

  afterEach(() => {
    console.error = consoleError;
  });

  test("renders children when no error", () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={false} />
      </ErrorBoundary>
    );

    expect(screen.getByTestId("child")).toBeInTheDocument();
  });

  test("renders error UI when error occurs", () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
  });

  test("handles missing error gracefully", () => {
    render(
      <ErrorBoundary>
        <div>Working content</div>
      </ErrorBoundary>
    );

    expect(screen.getByText("Working content")).toBeInTheDocument();
  });
});