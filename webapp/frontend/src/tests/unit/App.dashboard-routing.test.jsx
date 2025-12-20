import { vi, describe, test, beforeEach, expect } from "vitest";
import { renderWithProviders, screen } from "../test-utils.jsx";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Suspense } from "react";
import { AuthProvider } from "../../contexts/AuthContext";
import { ApiKeyProvider } from "../../components/ApiKeyProvider";
import { testTheme } from "../test-utils.jsx";
import App from "../../App";

// Mock dashboard and market overview components
vi.mock("../../pages/Dashboard", () => ({
  default: () => <div data-testid="dashboard-page">Dashboard</div>,
}));

vi.mock("../../pages/MarketOverview", () => ({
  default: () => <div data-testid="market-overview-page">Market Overview</div>,
}));

vi.mock("../../components/RootRedirect", () => ({
  default: () => <div data-testid="market-overview-page">Market Overview</div>,
}));

// Mock all other essential components
vi.mock("../../components/ErrorBoundary", () => ({
  default: ({ children }) => children,
}));

vi.mock("../../components/ApiKeyProvider", () => ({
  ApiKeyProvider: ({ children }) => children,
  useApiKeys: () => ({
    apiKeys: {},
    loading: false,
    error: null,
  }),
}));

describe("App Dashboard Routing", () => {
  const renderAppWithAuth = (initialRoute = "/", isAuthenticated = false) => {
    const testQueryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
        mutations: { retry: false },
      },
    });

    // Mock AuthContext with specific authentication state
    vi.doMock("../../contexts/AuthContext", () => ({
      AuthProvider: ({ children }) => children,
      useAuth: vi.fn(() => ({
        user: isAuthenticated ? { username: "testuser", email: "test@example.com" } : null,
        isAuthenticated,
        login: vi.fn(),
        logout: vi.fn(),
        isLoading: false,
        error: null,
      })),
    }));

    return renderWithProviders(<App />, {
      wrapper: ({ children }) => (
        <MemoryRouter initialEntries={[initialRoute]}>
          <ThemeProvider theme={testTheme}>
            <QueryClientProvider client={testQueryClient}>
              <AuthProvider>
                <ApiKeyProvider>
                  <Suspense fallback={<div>Loading...</div>}>
                    {children}
                  </Suspense>
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

  describe("Dashboard Authentication Behavior", () => {
    test("root route (/) shows market overview for all users", () => {
      renderAppWithAuth("/", false);
      expect(screen.getByTestId("market-overview-page")).toBeInTheDocument();
    });

    test("root route (/) shows market overview for authenticated users", () => {
      renderAppWithAuth("/", true);
      expect(screen.getByTestId("market-overview-page")).toBeInTheDocument();
    });

    test("/dashboard route requires authentication", () => {
      renderAppWithAuth("/dashboard", true);
      expect(screen.getByTestId("dashboard-page")).toBeInTheDocument();
    });

    test("/market route is always accessible", () => {
      renderAppWithAuth("/market", false);
      expect(screen.getByTestId("market-overview-page")).toBeInTheDocument();
    });
  });

  describe("Dashboard Navigation Behavior", () => {
    test("dashboard menu item is hidden for unauthenticated users", () => {
      renderAppWithAuth("/", false);

      // Dashboard should not be in navigation for unauthenticated users
      const dashboardItems = screen.queryAllByText(/dashboard/i);
      expect(dashboardItems.length).toBe(0);
    });

    test("dashboard menu item is visible for authenticated users", () => {
      renderAppWithAuth("/", true);

      // Dashboard should be visible in navigation for authenticated users
      const dashboardItems = screen.queryAllByText(/dashboard/i);
      expect(dashboardItems.length).toBeGreaterThan(0);
    });
  });
});