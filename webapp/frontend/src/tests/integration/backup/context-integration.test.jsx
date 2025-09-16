/**
 * React Context Integration Tests
 * Tests how React contexts integrate with components and provide data
 * Focuses on context provider behavior and state management
 */

import React from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Contexts
import { AuthContext } from "../../contexts/AuthContext.jsx";

// Components that use contexts

// Test wrapper

// Mock services
vi.mock("../../services/devAuth.js");
vi.mock("../../services/api.js");

describe("Context Integration", () => {
  let mockAuthContext;

  beforeEach(() => {
    vi.clearAllMocks();

    // Default auth context mock
    mockAuthContext = {
      user: null,
      isAuthenticated: false,
      loading: false,
      signIn: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
      resetPassword: vi.fn(),
      forgotPassword: vi.fn(),
      updateProfile: vi.fn(),
    };
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe("AuthContext Integration", () => {
    it("should provide authentication state to components", async () => {
      // Mock authenticated state
      const authenticatedContext = {
        ...mockAuthContext,
        user: { username: "testuser", email: "test@example.com" },
        isAuthenticated: true,
      };

      const TestComponent = () => {
        const { user, isAuthenticated } = React.useContext(AuthContext);
        return (
          <div>
            <div data-testid="auth-status">
              {isAuthenticated ? "authenticated" : "unauthenticated"}
            </div>
            <div data-testid="user-info">
              {user ? user.username : "no user"}
            </div>
          </div>
        );
      };

      render(
        <AuthContext.Provider value={authenticatedContext}>
          <TestComponent />
        </AuthContext.Provider>
      );

      expect(screen.getByTestId("auth-status")).toHaveTextContent(
        "authenticated"
      );
      expect(screen.getByTestId("user-info")).toHaveTextContent("testuser");
    });

    it("should propagate auth state changes to all consuming components", async () => {
      let contextValue = { ...mockAuthContext };

      const AuthProvider = ({ children }) => (
        <AuthContext.Provider value={contextValue}>
          {children}
        </AuthContext.Provider>
      );

      const Component1 = () => {
        const { isAuthenticated } = React.useContext(AuthContext);
        return (
          <div data-testid="comp1">{isAuthenticated ? "auth" : "no-auth"}</div>
        );
      };

      const Component2 = () => {
        const { user } = React.useContext(AuthContext);
        return <div data-testid="comp2">{user?.username || "no-user"}</div>;
      };

      const { rerender } = render(
        <AuthProvider>
          <Component1 />
          <Component2 />
        </AuthProvider>
      );

      // Initially not authenticated
      expect(screen.getByTestId("comp1")).toHaveTextContent("no-auth");
      expect(screen.getByTestId("comp2")).toHaveTextContent("no-user");

      // Update context value
      contextValue = {
        ...mockAuthContext,
        user: { username: "newuser" },
        isAuthenticated: true,
      };

      rerender(
        <AuthProvider>
          <Component1 />
          <Component2 />
        </AuthProvider>
      );

      // Both components should reflect the change
      expect(screen.getByTestId("comp1")).toHaveTextContent("auth");
      expect(screen.getByTestId("comp2")).toHaveTextContent("newuser");
    });

    it("should handle context method calls from components", async () => {
      const user = userEvent.setup();

      const signInMock = vi.fn().mockResolvedValue({
        user: { username: "testuser" },
      });

      const contextWithMethods = {
        ...mockAuthContext,
        signIn: signInMock,
      };

      const LoginComponent = () => {
        const { signIn } = React.useContext(AuthContext);

        const handleLogin = async () => {
          await signIn("test@example.com", "password123");
        };

        return (
          <button onClick={handleLogin} data-testid="login-btn">
            Login
          </button>
        );
      };

      render(
        <AuthContext.Provider value={contextWithMethods}>
          <LoginComponent />
        </AuthContext.Provider>
      );

      await user.click(screen.getByTestId("login-btn"));

      expect(signInMock).toHaveBeenCalledWith(
        "test@example.com",
        "password123"
      );
    });
  });

  describe("Multiple Context Integration", () => {
    it("should handle multiple contexts in component tree", async () => {
      // Mock additional context
      const ThemeContext = React.createContext();
      const DataContext = React.createContext();

      const themeValue = { theme: "dark", toggleTheme: vi.fn() };
      const dataValue = { data: { stocks: [] }, loading: false };

      const MultiContextComponent = () => {
        const { isAuthenticated } = React.useContext(AuthContext);
        const { theme } = React.useContext(ThemeContext);
        const { data } = React.useContext(DataContext);

        return (
          <div>
            <div data-testid="auth">{isAuthenticated ? "yes" : "no"}</div>
            <div data-testid="theme">{theme}</div>
            <div data-testid="data">{data.stocks.length}</div>
          </div>
        );
      };

      render(
        <AuthContext.Provider
          value={{ ...mockAuthContext, isAuthenticated: true }}
        >
          <ThemeContext.Provider value={themeValue}>
            <DataContext.Provider value={dataValue}>
              <MultiContextComponent />
            </DataContext.Provider>
          </ThemeContext.Provider>
        </AuthContext.Provider>
      );

      expect(screen.getByTestId("auth")).toHaveTextContent("yes");
      expect(screen.getByTestId("theme")).toHaveTextContent("dark");
      expect(screen.getByTestId("data")).toHaveTextContent("0");
    });

    it("should handle context updates independently", async () => {
      const ThemeContext = React.createContext();

      let authValue = { ...mockAuthContext, isAuthenticated: false };
      let themeValue = { theme: "light" };

      const TestComponent = () => {
        const { isAuthenticated } = React.useContext(AuthContext);
        const { theme } = React.useContext(ThemeContext);

        return (
          <div>
            <div data-testid="auth-state">
              {isAuthenticated ? "auth" : "no-auth"}
            </div>
            <div data-testid="theme-state">{theme}</div>
          </div>
        );
      };

      const { rerender } = render(
        <AuthContext.Provider value={authValue}>
          <ThemeContext.Provider value={themeValue}>
            <TestComponent />
          </ThemeContext.Provider>
        </AuthContext.Provider>
      );

      expect(screen.getByTestId("auth-state")).toHaveTextContent("no-auth");
      expect(screen.getByTestId("theme-state")).toHaveTextContent("light");

      // Update only auth context
      authValue = { ...mockAuthContext, isAuthenticated: true };

      rerender(
        <AuthContext.Provider value={authValue}>
          <ThemeContext.Provider value={themeValue}>
            <TestComponent />
          </ThemeContext.Provider>
        </AuthContext.Provider>
      );

      expect(screen.getByTestId("auth-state")).toHaveTextContent("auth");
      expect(screen.getByTestId("theme-state")).toHaveTextContent("light"); // Unchanged

      // Update only theme context
      themeValue = { theme: "dark" };

      rerender(
        <AuthContext.Provider value={authValue}>
          <ThemeContext.Provider value={themeValue}>
            <TestComponent />
          </ThemeContext.Provider>
        </AuthContext.Provider>
      );

      expect(screen.getByTestId("auth-state")).toHaveTextContent("auth"); // Unchanged
      expect(screen.getByTestId("theme-state")).toHaveTextContent("dark");
    });
  });

  describe("Context Error Handling", () => {
    it("should handle missing context provider gracefully", async () => {
      // Component that tries to use context without provider
      const ComponentWithoutProvider = () => {
        try {
          const context = React.useContext(AuthContext);
          return (
            <div data-testid="context-value">
              {context ? "has-context" : "no-context"}
            </div>
          );
        } catch (error) {
          return <div data-testid="context-error">Context Error</div>;
        }
      };

      render(<ComponentWithoutProvider />);

      // Should handle missing provider (React provides undefined by default)
      expect(screen.getByTestId("context-value")).toHaveTextContent(
        "no-context"
      );
    });

    it("should handle context value updates during async operations", async () => {
      let contextValue = { ...mockAuthContext, loading: true };

      const AsyncComponent = () => {
        const { loading, user } = React.useContext(AuthContext);

        if (loading) {
          return <div data-testid="loading">Loading...</div>;
        }

        return <div data-testid="content">{user?.username || "No user"}</div>;
      };

      const { rerender } = render(
        <AuthContext.Provider value={contextValue}>
          <AsyncComponent />
        </AuthContext.Provider>
      );

      expect(screen.getByTestId("loading")).toBeInTheDocument();

      // Simulate async completion
      contextValue = {
        ...mockAuthContext,
        loading: false,
        user: { username: "asyncuser" },
        isAuthenticated: true,
      };

      rerender(
        <AuthContext.Provider value={contextValue}>
          <AsyncComponent />
        </AuthContext.Provider>
      );

      expect(screen.getByTestId("content")).toHaveTextContent("asyncuser");
    });
  });

  describe("Context Performance Integration", () => {
    it("should not cause unnecessary re-renders", async () => {
      let renderCount = 0;

      const OptimizedComponent = React.memo(() => {
        renderCount++;
        const { user } = React.useContext(AuthContext);
        return <div data-testid="optimized">{user?.username || "no-user"}</div>;
      });

      const contextValue = {
        ...mockAuthContext,
        user: { username: "testuser" },
        isAuthenticated: true,
      };

      const { rerender } = render(
        <AuthContext.Provider value={contextValue}>
          <OptimizedComponent />
        </AuthContext.Provider>
      );

      const initialRenderCount = renderCount;

      // Re-render with same context value
      rerender(
        <AuthContext.Provider value={contextValue}>
          <OptimizedComponent />
        </AuthContext.Provider>
      );

      // Should not cause additional renders due to memoization
      expect(renderCount).toBe(initialRenderCount);
    });

    it("should handle context value object stability", async () => {
      let renderCount = 0;

      const StabilityTestComponent = () => {
        renderCount++;
        const { isAuthenticated } = React.useContext(AuthContext);
        return (
          <div data-testid="stability">
            {isAuthenticated ? "auth" : "no-auth"}
          </div>
        );
      };

      // Create new object each time (unstable reference)
      const getContextValue = (authenticated) => ({
        ...mockAuthContext,
        isAuthenticated: authenticated,
        user: authenticated ? { username: "testuser" } : null,
      });

      const { rerender } = render(
        <AuthContext.Provider value={getContextValue(false)}>
          <StabilityTestComponent />
        </AuthContext.Provider>
      );

      const initialRenderCount = renderCount;

      // Re-render with new object but same values
      rerender(
        <AuthContext.Provider value={getContextValue(false)}>
          <StabilityTestComponent />
        </AuthContext.Provider>
      );

      // Will cause re-render due to object reference change
      expect(renderCount).toBeGreaterThan(initialRenderCount);
    });
  });
});
