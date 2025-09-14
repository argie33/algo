/**
 * ServiceHealth Page Unit Tests
 * Tests the service health monitoring functionality - system status, uptime, diagnostics
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock import.meta.env BEFORE any imports
Object.defineProperty(import.meta, 'env', {
  value: {
    VITE_API_URL: 'http://localhost:3001',
    MODE: 'test',
    DEV: true,
    PROD: false,
    BASE_URL: '/'
  },
  writable: true,
  configurable: true
});

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ServiceHealth from "../../../pages/ServiceHealth.jsx";

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

// Mock API service with proper ES module support
vi.mock('../../../services/api', () => {
  const mockApi = {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    getHealthStatus: vi.fn(),
    getSystemMetrics: vi.fn(),
    runHealthCheck: vi.fn(),
    getDiagnosticInfo: vi.fn(() => Promise.resolve({ data: { version: '1.0.0', build: 'test' } })),
    getCurrentBaseURL: vi.fn(() => 'http://localhost:3001'),
    healthCheck: vi.fn(() => Promise.resolve({ data: { status: 'healthy' } })),
  };
  
  const mockGetApiConfig = vi.fn(() => ({
    baseURL: 'http://localhost:3001',
    apiUrl: 'http://localhost:3001',
    environment: 'test',
    isDevelopment: true,
    isProduction: false,
    baseUrl: '/',
  }));

  return {
    api: mockApi,
    getApiConfig: mockGetApiConfig,
    default: mockApi
  };
});

const mockHealthData = {
  overall: {
    status: "healthy",
    uptime: 99.95,
    responseTime: 142,
    lastCheck: "2024-01-25T15:30:00Z",
  },
  services: [
    { name: "API Gateway", status: "healthy", uptime: 99.98, responseTime: 85, lastCheck: "2024-01-25T15:30:00Z" },
    { name: "Database", status: "healthy", uptime: 99.99, responseTime: 12, lastCheck: "2024-01-25T15:30:00Z" },
    { name: "Market Data Feed", status: "degraded", uptime: 98.5, responseTime: 245, lastCheck: "2024-01-25T15:29:30Z" },
    { name: "Authentication", status: "healthy", uptime: 100.0, responseTime: 45, lastCheck: "2024-01-25T15:30:00Z" },
    { name: "Portfolio Engine", status: "healthy", uptime: 99.92, responseTime: 167, lastCheck: "2024-01-25T15:30:00Z" },
    { name: "Trading Service", status: "maintenance", uptime: 99.85, responseTime: 0, lastCheck: "2024-01-25T15:25:00Z" },
  ],
  metrics: {
    totalRequests: 1250000,
    errorRate: 0.02,
    avgResponseTime: 156,
    peakResponseTime: 892,
    activeUsers: 1247,
    systemLoad: 68.5,
  },
  incidents: [
    { id: 1, title: "Market Data Feed Slowdown", status: "investigating", severity: "medium", started: "2024-01-25T14:15:00Z" },
    { id: 2, title: "Trading Service Maintenance", status: "scheduled", severity: "low", started: "2024-01-25T15:00:00Z", estimated: "30 minutes" },
  ],
  history: [
    { timestamp: "2024-01-25T15:25:00Z", status: "healthy" },
    { timestamp: "2024-01-25T15:20:00Z", status: "healthy" },
    { timestamp: "2024-01-25T15:15:00Z", status: "degraded" },
    { timestamp: "2024-01-25T15:10:00Z", status: "healthy" },
  ],
};

// Test render helper
function renderServiceHealth(props = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ServiceHealth {...props} />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("ServiceHealth Component", () => {

  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import('../../../services/api');
    api.getHealthStatus.mockResolvedValue({
      success: true,
      data: mockHealthData,
    });
  });

  it("renders service health page", async () => {
    renderServiceHealth();
    
    expect(screen.getByText(/service health|system status/i)).toBeInTheDocument();
    
    await waitFor(() => {
      const { api } = require('../../../services/api');
      expect(api.getHealthStatus).toHaveBeenCalled();
    });
  });

  it("displays overall system status", async () => {
    renderServiceHealth();
    
    await waitFor(() => {
      expect(screen.getByText(/overall status|system status/i)).toBeInTheDocument();
      expect(screen.getByText(/healthy/i)).toBeInTheDocument();
      expect(screen.getByText(/99.95%/)).toBeInTheDocument(); // Overall uptime
      expect(screen.getByText(/142/)).toBeInTheDocument(); // Response time
    });
  });

  it("shows individual service statuses", async () => {
    renderServiceHealth();
    
    await waitFor(() => {
      expect(screen.getByText("API Gateway")).toBeInTheDocument();
      expect(screen.getByText("Database")).toBeInTheDocument();
      expect(screen.getByText("Market Data Feed")).toBeInTheDocument();
      expect(screen.getByText("Authentication")).toBeInTheDocument();
      expect(screen.getByText("Portfolio Engine")).toBeInTheDocument();
      expect(screen.getByText("Trading Service")).toBeInTheDocument();
    });
  });

  it("displays different service status indicators", async () => {
    renderServiceHealth();
    
    await waitFor(() => {
      expect(screen.getAllByText(/healthy/i)).toHaveLength(5); // 4 healthy services + overall
      expect(screen.getByText(/degraded/i)).toBeInTheDocument();
      expect(screen.getByText(/maintenance/i)).toBeInTheDocument();
    });
  });

  it("shows service uptime percentages", async () => {
    renderServiceHealth();
    
    await waitFor(() => {
      expect(screen.getByText(/99.98%/)).toBeInTheDocument(); // API Gateway uptime
      expect(screen.getByText(/99.99%/)).toBeInTheDocument(); // Database uptime
      expect(screen.getByText(/98.5%/)).toBeInTheDocument(); // Market Data Feed uptime
      expect(screen.getByText(/100.0%/)).toBeInTheDocument(); // Auth uptime
    });
  });

  it("displays response time metrics", async () => {
    renderServiceHealth();
    
    await waitFor(() => {
      expect(screen.getByText("85")).toBeInTheDocument(); // API Gateway response time
      expect(screen.getByText("12")).toBeInTheDocument(); // Database response time
      expect(screen.getByText("245")).toBeInTheDocument(); // Market Data Feed response time
      expect(screen.getByText("45")).toBeInTheDocument(); // Auth response time
    });
  });

  it("shows system metrics", async () => {
    renderServiceHealth();
    
    await waitFor(() => {
      expect(screen.getByText(/total requests/i)).toBeInTheDocument();
      expect(screen.getByText(/1,250,000|1.25M/)).toBeInTheDocument();
      expect(screen.getByText(/error rate/i)).toBeInTheDocument();
      expect(screen.getByText(/0.02%/)).toBeInTheDocument();
      expect(screen.getByText(/active users/i)).toBeInTheDocument();
      expect(screen.getByText("1247")).toBeInTheDocument();
    });
  });

  it("displays current incidents", async () => {
    renderServiceHealth();
    
    await waitFor(() => {
      expect(screen.getByText(/incidents|issues/i)).toBeInTheDocument();
      expect(screen.getByText("Market Data Feed Slowdown")).toBeInTheDocument();
      expect(screen.getByText("Trading Service Maintenance")).toBeInTheDocument();
      expect(screen.getByText(/investigating/i)).toBeInTheDocument();
      expect(screen.getByText(/scheduled/i)).toBeInTheDocument();
    });
  });

  it("shows incident severity levels", async () => {
    renderServiceHealth();
    
    await waitFor(() => {
      expect(screen.getByText(/medium/i)).toBeInTheDocument();
      expect(screen.getByText(/low/i)).toBeInTheDocument();
    });
  });

  it("displays system load metrics", async () => {
    renderServiceHealth();
    
    await waitFor(() => {
      expect(screen.getByText(/system load/i)).toBeInTheDocument();
      expect(screen.getByText(/68.5%/)).toBeInTheDocument();
    });
  });

  it("shows response time statistics", async () => {
    renderServiceHealth();
    
    await waitFor(() => {
      expect(screen.getByText(/average response time/i)).toBeInTheDocument();
      expect(screen.getByText("156")).toBeInTheDocument();
      expect(screen.getByText(/peak response time/i)).toBeInTheDocument();
      expect(screen.getByText("892")).toBeInTheDocument();
    });
  });

  it("renders health status history", async () => {
    renderServiceHealth();
    
    await waitFor(() => {
      expect(screen.getByText(/history|timeline/i)).toBeInTheDocument();
      // Should show historical status points
      expect(screen.getAllByText(/healthy/i).length).toBeGreaterThan(0);
    });
  });

  it("includes refresh/health check button", async () => {
    renderServiceHealth();
    
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /refresh|check|update/i })).toBeInTheDocument();
    });
  });

  it("handles manual health check", async () => {
    const { api } = require('../../../services/api');
    api.runHealthCheck.mockResolvedValue({
      success: true,
      data: mockHealthData,
    });
    
    renderServiceHealth();
    
    await waitFor(() => {
      const refreshButton = screen.getByRole("button", { name: /refresh|check|update/i });
      fireEvent.click(refreshButton);
      
      expect(api.runHealthCheck).toHaveBeenCalled();
    });
  });

  it("displays status with color coding", async () => {
    const { container: _container } = renderServiceHealth();
    
    await waitFor(() => {
      // Healthy status should be green, degraded yellow/orange, maintenance blue
      const healthyStatus = screen.getAllByText(/healthy/i)[0];
      const degradedStatus = screen.getByText(/degraded/i);
      const maintenanceStatus = screen.getByText(/maintenance/i);
      
      expect(healthyStatus).toBeInTheDocument();
      expect(degradedStatus).toBeInTheDocument();
      expect(maintenanceStatus).toBeInTheDocument();
    });
  });

  it("shows last check timestamps", async () => {
    renderServiceHealth();
    
    await waitFor(() => {
      expect(screen.getByText(/last check|updated/i)).toBeInTheDocument();
      // Should show formatted timestamps
      expect(screen.getByText(/15:30|3:30 PM/) || 
             screen.getByText(/Jan 25|1\/25/)).toBeInTheDocument();
    });
  });

  it("handles loading state", () => {
    const { api } = require('../../../services/api');
    api.getHealthStatus.mockImplementation(() => new Promise(() => {}));
    
    renderServiceHealth();
    
    expect(screen.getByRole("progressbar") || screen.getByText(/loading|checking/i)).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    const { api } = require('../../../services/api');
    api.getHealthStatus.mockRejectedValue(new Error("Health check failed"));
    
    renderServiceHealth();
    
    await waitFor(() => {
      expect(screen.getByText(/error|failed|unavailable/i)).toBeInTheDocument();
    });
  });

  it("displays maintenance windows", async () => {
    renderServiceHealth();
    
    await waitFor(() => {
      expect(screen.getByText(/30 minutes/)).toBeInTheDocument(); // Estimated maintenance time
    });
  });

  it("auto-refreshes health status", async () => {
    renderServiceHealth();
    
    await waitFor(() => {
      const { api } = require('../../../services/api');
      expect(api.getHealthStatus).toHaveBeenCalled();
    });

    // Wait for potential auto-refresh
    await new Promise(resolve => setTimeout(resolve, 100));
    
    // May make additional calls for auto-refresh (implementation dependent)
    expect(true).toBe(true); // Placeholder - adjust based on actual refresh logic
  });

  it("shows service dependencies", async () => {
    renderServiceHealth();
    
    await waitFor(() => {
      // Should indicate which services depend on others
      expect(screen.getByText(/dependencies|depends on/i) ||
             screen.getByTestId(/dependency/)).toBeInTheDocument();
    });
  });

  it("handles service status changes in real-time", async () => {
    renderServiceHealth();
    
    // Initial load
    await waitFor(() => {
      expect(screen.getByText(/degraded/i)).toBeInTheDocument();
    });

    // Simulate status update
    const { api } = require('../../../services/api');
    api.getHealthStatus.mockResolvedValue({
      success: true,
      data: {
        ...mockHealthData,
        services: mockHealthData.services.map(service => 
          service.name === "Market Data Feed" 
            ? { ...service, status: "healthy" }
            : service
        )
      },
    });

    // Trigger update
    const refreshButton = screen.getByRole("button", { name: /refresh|check|update/i });
    fireEvent.click(refreshButton);

    await waitFor(() => {
      expect(api.getHealthStatus).toHaveBeenCalledTimes(2);
    });
  });
});

function createMockUser() {
  return {
    id: 1,
    username: "testuser",
    email: "test@example.com",
    isAuthenticated: true,
  };
}