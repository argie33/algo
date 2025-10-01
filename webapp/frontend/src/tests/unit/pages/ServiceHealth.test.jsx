/**
 * ServiceHealth Page Unit Tests
 * Tests the service health monitoring functionality - database health and ECS tasks
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock import.meta.env BEFORE any imports
Object.defineProperty(import.meta, "env", {
  value: {
    VITE_API_URL: "http://localhost:3001",
    MODE: "test",
    DEV: true,
    PROD: false,
    BASE_URL: "/",
  },
  writable: true,
  configurable: true,
});

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ServiceHealth from "../../../pages/ServiceHealth.jsx";

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: { id: 1, email: "test@example.com" },
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

// Mock API service
vi.mock("../../../services/api.js", async () => {
  const mockApi = await import("../../mocks/apiMock.js");
  return {
    default: mockApi.default,
    api: mockApi.api,
    getApiConfig: mockApi.getApiConfig,
    getDiagnosticInfo: mockApi.getDiagnosticInfo,
    getCurrentBaseURL: mockApi.getCurrentBaseURL,
  };
});

describe("ServiceHealth Component", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../../../services/api");

    // Mock database health endpoint
    api.get.mockImplementation((url) => {
      if (url === '/health/database') {
        return Promise.resolve({
          data: {
            success: true,
            data: {
              database: {
                status: 'connected',
                tables: {
                  price_daily: {
                    status: 'healthy',
                    record_count: 1000,
                    last_updated: '2024-01-25T15:30:00Z',
                    data_freshness: 'current',
                    last_checked: '2024-01-25T15:30:00Z'
                  },
                  stock_symbols: {
                    status: 'healthy',
                    record_count: 500,
                    last_updated: '2024-01-25T15:30:00Z',
                    data_freshness: 'current',
                    last_checked: '2024-01-25T15:30:00Z'
                  }
                },
                summary: {
                  total_tables: 2,
                  healthy_tables: 2,
                  stale_tables: 0
                }
              }
            }
          }
        });
      } else if (url === '/health/ecs-tasks') {
        return Promise.resolve({
          data: {
            success: true,
            tasks: {
              loadinfo: {
                status: 'success',
                last_run: '2024-01-25T06:00:00Z',
                hours_since_run: 10,
                freshness: 'current',
                exit_code: 0
              }
            }
          }
        });
      }
      return Promise.reject(new Error('Unknown endpoint'));
    });
  });

  function renderServiceHealth() {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    return render(
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>
          <ServiceHealth />
        </QueryClientProvider>
      </MemoryRouter>
    );
  }

  it("renders service health page", async () => {
    renderServiceHealth();

    await waitFor(() => {
      expect(screen.getByText(/Database Health/i)).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("displays database health status", async () => {
    renderServiceHealth();

    await waitFor(() => {
      expect(screen.getByText(/Database Health/i)).toBeInTheDocument();
      expect(screen.getByText(/price_daily/i)).toBeInTheDocument();
      expect(screen.getByText(/stock_symbols/i)).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("shows ECS scheduled tasks status", async () => {
    renderServiceHealth();

    await waitFor(() => {
      expect(screen.getByText(/Scheduled Tasks Status/i)).toBeInTheDocument();
      expect(screen.getByText(/loadinfo/i)).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("displays database table information", async () => {
    renderServiceHealth();

    await waitFor(() => {
      expect(screen.getByText(/price_daily/i)).toBeInTheDocument();
      expect(screen.getByText(/stock_symbols/i)).toBeInTheDocument();
      expect(screen.getByText(/1000/i)).toBeInTheDocument(); // record count
      expect(screen.getByText(/500/i)).toBeInTheDocument(); // record count
    }, { timeout: 3000 });
  });

  it("shows task status indicators", async () => {
    renderServiceHealth();

    await waitFor(() => {
      expect(screen.getByText(/success/i)).toBeInTheDocument();
      expect(screen.getByText(/current/i)).toBeInTheDocument();
    }, { timeout: 3000 });
  });
});
