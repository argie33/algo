import { render, screen } from "@testing-library/react";
import ProtectedRoute from "../../../../components/auth/ProtectedRoute";

describe("ProtectedRoute", () => {
  describe("Basic Functionality", () => {
    test("renders children without authentication", () => {
      render(
        <ProtectedRoute>
          <div data-testid="protected-content">Protected Content</div>
        </ProtectedRoute>
      );

      expect(screen.getByTestId("protected-content")).toBeInTheDocument();
      expect(screen.getByText("Protected Content")).toBeInTheDocument();
    });

    test("renders children with requireAuth prop", () => {
      render(
        <ProtectedRoute requireAuth={true}>
          <div data-testid="protected-content">Protected Content</div>
        </ProtectedRoute>
      );

      expect(screen.getByTestId("protected-content")).toBeInTheDocument();
      expect(screen.getByText("Protected Content")).toBeInTheDocument();
    });

    test("renders children with fallback prop", () => {
      const fallback = <div data-testid="fallback">Loading...</div>;

      render(
        <ProtectedRoute fallback={fallback}>
          <div data-testid="protected-content">Protected Content</div>
        </ProtectedRoute>
      );

      expect(screen.getByTestId("protected-content")).toBeInTheDocument();
      expect(screen.getByText("Protected Content")).toBeInTheDocument();
      expect(screen.queryByTestId("fallback")).not.toBeInTheDocument();
    });

    test("renders complex child components", () => {
      const ComplexChild = () => (
        <div>
          <h1>Complex Component</h1>
          <p>With multiple elements</p>
          <button>Action Button</button>
        </div>
      );

      render(
        <ProtectedRoute>
          <ComplexChild />
        </ProtectedRoute>
      );

      expect(screen.getByText("Complex Component")).toBeInTheDocument();
      expect(screen.getByText("With multiple elements")).toBeInTheDocument();
      expect(screen.getByText("Action Button")).toBeInTheDocument();
    });

    test("renders multiple children", () => {
      render(
        <ProtectedRoute>
          <div data-testid="child-1">First Child</div>
          <div data-testid="child-2">Second Child</div>
        </ProtectedRoute>
      );

      expect(screen.getByTestId("child-1")).toBeInTheDocument();
      expect(screen.getByTestId("child-2")).toBeInTheDocument();
    });

    test("renders null children gracefully", () => {
      render(<ProtectedRoute>{null}</ProtectedRoute>);

      // Should not throw error and render empty
      expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
    });

    test("renders undefined children gracefully", () => {
      render(<ProtectedRoute>{undefined}</ProtectedRoute>);

      // Should not throw error and render empty
      expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
    });
  });

  describe("Props Handling", () => {
    test("ignores requireAuth parameter (legacy support)", () => {
      render(
        <ProtectedRoute requireAuth={false}>
          <div data-testid="content">Always Visible</div>
        </ProtectedRoute>
      );

      expect(screen.getByTestId("content")).toBeInTheDocument();
    });

    test("ignores fallback parameter (legacy support)", () => {
      const fallback = <div data-testid="fallback">Should not show</div>;

      render(
        <ProtectedRoute fallback={fallback}>
          <div data-testid="content">Main Content</div>
        </ProtectedRoute>
      );

      expect(screen.getByTestId("content")).toBeInTheDocument();
      expect(screen.queryByTestId("fallback")).not.toBeInTheDocument();
    });

    test("works with all combinations of legacy props", () => {
      const fallback = <div>Loading...</div>;

      render(
        <ProtectedRoute requireAuth={true} fallback={fallback}>
          <div data-testid="content">Content</div>
        </ProtectedRoute>
      );

      expect(screen.getByTestId("content")).toBeInTheDocument();
    });
  });

  describe("Component Behavior", () => {
    test("maintains component structure", () => {
      const { container } = render(
        <ProtectedRoute>
          <div className="test-class" id="test-id">
            Content
          </div>
        </ProtectedRoute>
      );

      const childElement = container.querySelector("#test-id");
      expect(childElement).toBeInTheDocument();
      expect(childElement).toHaveClass("test-class");
    });

    test("preserves child component props and attributes", () => {
      render(
        <ProtectedRoute>
          <button
            data-testid="action-button"
            className="btn-primary"
            disabled={false}
            onClick={() => console.log("clicked")}
          >
            Click Me
          </button>
        </ProtectedRoute>
      );

      const button = screen.getByTestId("action-button");
      expect(button).toBeInTheDocument();
      expect(button).toHaveClass("btn-primary");
      expect(button).not.toBeDisabled();
    });

    test("preserves React fragments", () => {
      render(
        <ProtectedRoute>
          <>
            <div data-testid="fragment-child-1">First</div>
            <div data-testid="fragment-child-2">Second</div>
          </>
        </ProtectedRoute>
      );

      expect(screen.getByTestId("fragment-child-1")).toBeInTheDocument();
      expect(screen.getByTestId("fragment-child-2")).toBeInTheDocument();
    });
  });

  describe("Development Mode Compatibility", () => {
    test("works in development mode", () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = "development";

      render(
        <ProtectedRoute>
          <div data-testid="dev-content">Development Content</div>
        </ProtectedRoute>
      );

      expect(screen.getByTestId("dev-content")).toBeInTheDocument();

      process.env.NODE_ENV = originalEnv;
    });

    test("works in production mode", () => {
      const originalEnv = process.env.NODE_ENV;
      process.env.NODE_ENV = "production";

      render(
        <ProtectedRoute>
          <div data-testid="prod-content">Production Content</div>
        </ProtectedRoute>
      );

      expect(screen.getByTestId("prod-content")).toBeInTheDocument();

      process.env.NODE_ENV = originalEnv;
    });
  });
});
