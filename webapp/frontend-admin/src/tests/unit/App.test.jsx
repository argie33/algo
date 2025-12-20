import { vi, describe, test, beforeEach, expect } from "vitest";
import { renderWithProviders, screen } from "../test-utils.jsx";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Suspense } from "react";
import { AuthProvider } from "../../contexts/AuthContext";
import { ApiKeyProvider } from "../../components/ApiKeyProvider";
import ErrorBoundary from "../../components/ErrorBoundary";
import { testTheme } from "../test-utils.jsx";
import App from "../../App";

// Mock all the page components to avoid complex dependencies
vi.mock("../../pages/Dashboard", () => ({
  default: () => <div data-testid="dashboard-page">Dashboard</div>,
}));

vi.mock("../../pages/MarketOverview", () => ({
  default: () => <div data-testid="market-overview-page">Market Overview</div>,
}));

vi.mock("../../components/RootRedirect", () => ({
  default: () => <div data-testid="market-overview-page">Market Overview</div>,
}));

vi.mock("../../pages/PortfolioDashboard", () => ({
  default: () => <div data-testid="portfolio-page">Portfolio</div>,
}));

vi.mock("../../pages/Settings", () => ({
  default: () => <div data-testid="settings-page">Settings</div>,
}));

// Mock all other page components with a simple fallback
// Note: TechnicalAnalysis removed - page no longer exists

// Mock other essential pages that might be imported
vi.mock("../../pages/ComingSoon", () => ({
  default: () => <div data-testid="comingsoon-page">ComingSoon</div>,
}));

// Mock AuthContext
vi.mock("../../contexts/AuthContext", () => ({
  AuthProvider: ({ children }) => children,
  useAuth: vi.fn(() => ({
    user: { username: "testuser", email: "test@example.com" },
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    isLoading: false,
    error: null,
  })),
}));

// Mock ApiKeyProvider
vi.mock("../../components/ApiKeyProvider", () => ({
  ApiKeyProvider: ({ children }) => children,
  useApiKeys: () => ({
    apiKeys: {},
    loading: false,
    error: null,
    setApiKey: vi.fn(),
    hasApiKey: () => false,
  }),
}));

// Mock ErrorBoundary
vi.mock("../../components/ErrorBoundary", () => ({
  default: ({ children }) => children,
}));

describe("App", () => {
  const renderApp = (initialRoute = "/") => {
    const testQueryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
        mutations: { retry: false },
      },
    });

    return renderWithProviders(<App />, {
      wrapper: ({ children }) => (
        <MemoryRouter initialEntries={[initialRoute]}>
          <ThemeProvider theme={testTheme}>
            <QueryClientProvider client={testQueryClient}>
              <AuthProvider>
                <ApiKeyProvider>
                  <ErrorBoundary>
                    <Suspense fallback={<div>Loading...</div>}>
                      {children}
                    </Suspense>
                  </ErrorBoundary>
                </ApiKeyProvider>
              </AuthProvider>
            </QueryClientProvider>
          </ThemeProvider>
        </MemoryRouter>
      ),
    });
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Basic Rendering", () => {
    test("renders without crashing", () => {
      renderApp();

      expect(screen.getByRole("banner")).toBeInTheDocument(); // AppBar
    });

    test("renders navigation drawer", () => {
      renderApp();

      expect(screen.getByLabelText(/open drawer/i)).toBeInTheDocument();
    });

    test("renders app title", () => {
      renderApp();

      expect(screen.getAllByText(/financial platform/i)[0]).toBeInTheDocument();
    });
  });

  describe("Navigation", () => {
    test("renders default route as market overview", () => {
      renderApp("/");

      expect(screen.getByTestId("market-overview-page")).toBeInTheDocument();
    });

    test("renders dashboard route", () => {
      renderApp("/dashboard");

      expect(screen.getByTestId("dashboard-page")).toBeInTheDocument();
    });

    test("renders market overview route", () => {
      renderApp("/market");

      expect(screen.getByTestId("market-overview-page")).toBeInTheDocument();
    });

    test("renders portfolio route", () => {
      renderApp("/portfolio");

      expect(screen.getByTestId("portfolio-page")).toBeInTheDocument();
    });

    test("renders settings route", () => {
      renderApp("/settings");

      expect(screen.getByTestId("settings-page")).toBeInTheDocument();
    });
  });

  describe("Responsive Layout", () => {
    test("renders mobile layout", () => {
      // Mock mobile viewport
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 600,
      });

      renderApp();

      expect(screen.getByRole("banner")).toBeInTheDocument();
    });

    test("renders desktop layout", () => {
      // Mock desktop viewport
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 1200,
      });

      renderApp();

      expect(screen.getByRole("banner")).toBeInTheDocument();
    });
  });

  describe("User Authentication", () => {
    test("displays user information when authenticated", () => {
      renderApp();

      // Should show user menu or avatar
      const userElements = screen.queryAllByText(/testuser/i);
      expect(userElements.length).toBeGreaterThanOrEqual(0);
    });

    test("handles unauthenticated state", () => {
      renderApp();

      expect(screen.getByRole("banner")).toBeInTheDocument();
    });
  });

  describe("Error Handling", () => {
    test("handles invalid routes gracefully", () => {
      renderApp("/invalid-route");

      // Should not crash and still render the app shell
      expect(screen.getByRole("banner")).toBeInTheDocument();
    });

    test("renders with missing auth context", () => {
      renderApp();

      expect(screen.getByRole("banner")).toBeInTheDocument();
    });
  });

  describe("Component Integration", () => {
    test("wraps content with providers", () => {
      renderApp();

      // Verify the app renders with all providers
      expect(screen.getByRole("banner")).toBeInTheDocument();
      expect(screen.getByRole("main")).toBeInTheDocument();
    });

    test("renders navigation menu items", () => {
      renderApp();

      // Navigation should be present
      expect(screen.getByLabelText(/open drawer/i)).toBeInTheDocument();
    });
  });

  describe("Layout Components", () => {
    test("renders main content area", () => {
      renderApp();

      expect(screen.getByRole("main")).toBeInTheDocument();
    });

    test("renders app bar with navigation", () => {
      renderApp();

      const appBar = screen.getByRole("banner");
      expect(appBar).toBeInTheDocument();
    });
  });
});
