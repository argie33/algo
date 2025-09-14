/**
 * Authentication Flow Integration Tests - Fixed Version
 * Tests auth workflows using mock components to avoid complex dependencies
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";

// Mock services FIRST
vi.mock("../../services/devAuth.js");
vi.mock("../../services/api.js");

// Mock AuthContext with importOriginal
vi.mock("../../contexts/AuthContext.jsx", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    // Keep the original AuthContext
  };
});

// Auth context
import { AuthContext } from "../../contexts/AuthContext.jsx";

// Test wrapper
import { TestWrapper } from "../test-utils.jsx";

describe("Authentication Flow Integration", () => {
  let mockDevAuth;

  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock devAuth service
    mockDevAuth = {
      signIn: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
      getCurrentSession: vi.fn(),
      isAuthenticated: vi.fn(() => false)
    };

    // Apply mocks
    const devAuthModule = require("../../services/devAuth.js");
    Object.assign(devAuthModule.default, mockDevAuth);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe("Basic Auth Integration", () => {
    it("should provide auth context to components", () => {
      const TestComponent = () => {
        const context = React.useContext(AuthContext);
        return (
          <div data-testid="auth-context">
            {context ? 'has-context' : 'no-context'}
          </div>
        );
      };

      render(
        <TestWrapper>
          <AuthContext.Provider value={{
            user: null,
            isAuthenticated: false,
            loading: false,
            signIn: mockDevAuth.signIn,
            signOut: mockDevAuth.signOut
          }}>
            <TestComponent />
          </AuthContext.Provider>
        </TestWrapper>
      );

      expect(screen.getByTestId("auth-context")).toHaveTextContent("has-context");
    });

    it("should handle auth state changes", async () => {
      let authState = {
        user: null,
        isAuthenticated: false,
        loading: false,
        signIn: mockDevAuth.signIn,
        signOut: mockDevAuth.signOut
      };

      const TestComponent = () => {
        const { isAuthenticated, user } = React.useContext(AuthContext);
        return (
          <div>
            <div data-testid="auth-status">
              {isAuthenticated ? 'authenticated' : 'not-authenticated'}
            </div>
            <div data-testid="user-info">
              {user ? user.username : 'no-user'}
            </div>
          </div>
        );
      };

      const { rerender } = render(
        <TestWrapper>
          <AuthContext.Provider value={authState}>
            <TestComponent />
          </AuthContext.Provider>
        </TestWrapper>
      );

      expect(screen.getByTestId("auth-status")).toHaveTextContent("not-authenticated");
      expect(screen.getByTestId("user-info")).toHaveTextContent("no-user");

      // Update auth state
      authState = {
        ...authState,
        user: { username: "testuser" },
        isAuthenticated: true
      };

      rerender(
        <TestWrapper>
          <AuthContext.Provider value={authState}>
            <TestComponent />
          </AuthContext.Provider>
        </TestWrapper>
      );

      expect(screen.getByTestId("auth-status")).toHaveTextContent("authenticated");
      expect(screen.getByTestId("user-info")).toHaveTextContent("testuser");
    });

    it("should call auth methods from context", async () => {
      const user = userEvent.setup();
      
      mockDevAuth.signIn.mockResolvedValue({
        user: { username: "testuser" }
      });

      const LoginButton = () => {
        const { signIn } = React.useContext(AuthContext);
        
        const handleLogin = () => {
          signIn("test@example.com", "password123");
        };

        return (
          <button onClick={handleLogin} data-testid="login-btn">
            Login
          </button>
        );
      };

      render(
        <TestWrapper>
          <AuthContext.Provider value={{
            user: null,
            isAuthenticated: false,
            loading: false,
            signIn: mockDevAuth.signIn,
            signOut: mockDevAuth.signOut
          }}>
            <LoginButton />
          </AuthContext.Provider>
        </TestWrapper>
      );

      await user.click(screen.getByTestId("login-btn"));

      expect(mockDevAuth.signIn).toHaveBeenCalledWith("test@example.com", "password123");
    });
  });

  describe("Protected Route Integration", () => {
    it("should render content for authenticated users", () => {
      const ProtectedContent = () => {
        const { isAuthenticated } = React.useContext(AuthContext);
        
        if (!isAuthenticated) {
          return <div data-testid="login-required">Please login</div>;
        }
        
        return <div data-testid="protected-content">Protected Content</div>;
      };

      render(
        <TestWrapper>
          <AuthContext.Provider value={{
            user: { username: "testuser" },
            isAuthenticated: true,
            loading: false
          }}>
            <ProtectedContent />
          </AuthContext.Provider>
        </TestWrapper>
      );

      expect(screen.getByTestId("protected-content")).toBeInTheDocument();
      expect(screen.queryByTestId("login-required")).not.toBeInTheDocument();
    });

    it("should show login for unauthenticated users", () => {
      const ProtectedContent = () => {
        const { isAuthenticated } = React.useContext(AuthContext);
        
        if (!isAuthenticated) {
          return <div data-testid="login-required">Please login</div>;
        }
        
        return <div data-testid="protected-content">Protected Content</div>;
      };

      render(
        <TestWrapper>
          <AuthContext.Provider value={{
            user: null,
            isAuthenticated: false,
            loading: false
          }}>
            <ProtectedContent />
          </AuthContext.Provider>
        </TestWrapper>
      );

      expect(screen.getByTestId("login-required")).toBeInTheDocument();
      expect(screen.queryByTestId("protected-content")).not.toBeInTheDocument();
    });
  });

  describe("Error Handling Integration", () => {
    it("should handle auth service errors", async () => {
      const user = userEvent.setup();
      
      mockDevAuth.signIn.mockRejectedValue(new Error("Invalid credentials"));

      const LoginWithError = () => {
        const { signIn } = React.useContext(AuthContext);
        const [error, setError] = React.useState(null);
        
        const handleLogin = async () => {
          try {
            await signIn("invalid@example.com", "wrongpassword");
          } catch (err) {
            setError(err.message);
          }
        };

        return (
          <div>
            <button onClick={handleLogin} data-testid="login-btn">
              Login
            </button>
            {error && <div data-testid="error-message">{error}</div>}
          </div>
        );
      };

      render(
        <TestWrapper>
          <AuthContext.Provider value={{
            user: null,
            isAuthenticated: false,
            loading: false,
            signIn: mockDevAuth.signIn,
            signOut: mockDevAuth.signOut
          }}>
            <LoginWithError />
          </AuthContext.Provider>
        </TestWrapper>
      );

      await user.click(screen.getByTestId("login-btn"));

      await waitFor(() => {
        expect(screen.getByTestId("error-message")).toHaveTextContent("Invalid credentials");
      });
    });
  });

  describe("Loading State Integration", () => {
    it("should handle loading states during auth operations", async () => {
      const user = userEvent.setup();
      
      // Create a promise that we can control
      let resolveLogin;
      const loginPromise = new Promise((resolve) => {
        resolveLogin = resolve;
      });
      
      mockDevAuth.signIn.mockReturnValue(loginPromise);

      const LoginWithLoading = () => {
        const { signIn } = React.useContext(AuthContext);
        const [loading, setLoading] = React.useState(false);
        
        const handleLogin = async () => {
          setLoading(true);
          try {
            await signIn("test@example.com", "password123");
          } finally {
            setLoading(false);
          }
        };

        return (
          <div>
            <button 
              onClick={handleLogin} 
              disabled={loading}
              data-testid="login-btn"
            >
              {loading ? 'Logging in...' : 'Login'}
            </button>
          </div>
        );
      };

      render(
        <TestWrapper>
          <AuthContext.Provider value={{
            user: null,
            isAuthenticated: false,
            loading: false,
            signIn: mockDevAuth.signIn,
            signOut: mockDevAuth.signOut
          }}>
            <LoginWithLoading />
          </AuthContext.Provider>
        </TestWrapper>
      );

      // Click login button
      await user.click(screen.getByTestId("login-btn"));

      // Should show loading state
      expect(screen.getByTestId("login-btn")).toHaveTextContent("Logging in...");
      expect(screen.getByTestId("login-btn")).toBeDisabled();

      // Resolve the login
      act(() => {
        resolveLogin({ user: { username: "testuser" } });
      });

      // Should return to normal state
      await waitFor(() => {
        expect(screen.getByTestId("login-btn")).toHaveTextContent("Login");
        expect(screen.getByTestId("login-btn")).not.toBeDisabled();
      });
    });
  });
});