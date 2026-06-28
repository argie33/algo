import { vi, describe, test, beforeEach, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ThemeProvider } from "@mui/material/styles";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Suspense } from "react";
import { testTheme } from "../test-utils.jsx";
import App from "../../App";

// Mock heavy page components
vi.mock("../../pages/MarketsHealth", () => ({
  default: () => <div data-testid="markets-health-page">Markets Health</div>,
}));

vi.mock("../../pages/PortfolioDashboard", () => ({
  default: () => <div data-testid="portfolio-page">Portfolio</div>,
}));

vi.mock("../../pages/NotFound", () => ({
  default: () => <div data-testid="not-found-page">Not Found</div>,
}));

vi.mock("../../components/ErrorBoundary", () => ({
  default: ({ children }) => children,
}));

vi.mock("../../components/ApiKeyProvider", () => ({
  ApiKeyProvider: ({ children }) => children,
  useApiKeys: () => ({ apiKeys: {}, loading: false, error: null }),
}));

vi.mock("../../components/auth/ProtectedRoute", () => ({
  default: ({ children }) => children,
}));

vi.mock("../../components/AppLayout", () => ({
  default: ({ children }) => <div data-testid="app-layout">{children}</div>,
}));

vi.mock("../../components/LoadingFallback", () => ({
  LoadingFallback: () => <div data-testid="loading-fallback">Loading...</div>,
}));

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

const renderAt = (initialRoute) =>
  render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <ThemeProvider theme={testTheme}>
        <QueryClientProvider client={makeQueryClient()}>
          <Suspense fallback={<div data-testid="loading">Loading...</div>}>
            <App />
          </Suspense>
        </QueryClientProvider>
      </ThemeProvider>
    </MemoryRouter>
  );

describe("App Dashboard Routing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Direct app routes", () => {
    test("/app/markets renders markets health page", async () => {
      renderAt("/app/markets");
      await waitFor(() =>
        expect(screen.getByTestId("markets-health-page")).toBeInTheDocument()
      );
    });

    test("/app/portfolio renders portfolio page", async () => {
      renderAt("/app/portfolio");
      await waitFor(() =>
        expect(screen.getByTestId("portfolio-page")).toBeInTheDocument()
      );
    });

    test("unknown /app route renders not-found page", async () => {
      renderAt("/this-route-does-not-exist");
      await waitFor(() =>
        expect(screen.getByTestId("not-found-page")).toBeInTheDocument()
      );
    });
  });
});
