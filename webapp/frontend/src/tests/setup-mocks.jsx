/**
 * Comprehensive Test Mocks Setup
 * Global mocks for all React component tests
 */

import { vi } from "vitest";
import { act } from "react";

// Global test utilities
global.act = act;

// Mock recharts with all necessary components
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => children,
  LineChart: ({ children }) => <div data-testid="line-chart">{children}</div>,
  AreaChart: ({ children }) => <div data-testid="area-chart">{children}</div>,
  BarChart: ({ children }) => <div data-testid="bar-chart">{children}</div>,
  PieChart: ({ children }) => <div data-testid="pie-chart">{children}</div>,
  RadarChart: ({ children }) => <div data-testid="radar-chart">{children}</div>,
  ComposedChart: ({ children }) => (
    <div data-testid="composed-chart">{children}</div>
  ),
  Line: () => <div data-testid="line" />,
  Area: () => <div data-testid="area" />,
  Bar: () => <div data-testid="bar" />,
  Cell: () => <div data-testid="cell" />,
  Pie: () => <div data-testid="pie" />,
  Radar: () => <div data-testid="radar" />,
  PolarGrid: () => <div data-testid="polar-grid" />,
  PolarAngleAxis: () => <div data-testid="polar-angle-axis" />,
  PolarRadiusAxis: () => <div data-testid="polar-radius-axis" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
}));

// Mock react-router-dom with all necessary hooks
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: vi.fn(() => vi.fn()),
    useLocation: vi.fn(() => ({ pathname: "/test", search: "", state: null })),
    useParams: vi.fn(() => ({})),
    useSearchParams: vi.fn(() => [new URLSearchParams(), vi.fn()]),
  };
});

// Mock API service with all necessary functions
vi.mock("../services/api", () => ({
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    baseURL: "http://localhost:3001",
    isConfigured: true,
    environment: "test",
  })),
  getPortfolioData: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: { holdings: [], summary: {}, riskMetrics: {} },
    })
  ),
  getMarketData: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: { indices: [], topStocks: [] },
    })
  ),
  getStockPrice: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: { price: 100, change: 1.5 },
    })
  ),
  default: {
    get: vi.fn(() => Promise.resolve({ data: { success: true, data: {} } })),
    post: vi.fn(() => Promise.resolve({ data: { success: true, data: {} } })),
    put: vi.fn(() => Promise.resolve({ data: { success: true, data: {} } })),
    delete: vi.fn(() => Promise.resolve({ data: { success: true, data: {} } })),
  },
}));

// Mock MUI X Data Grid
vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({ children, ...props }) => (
    <div data-testid="data-grid" {...props}>
      {children}
    </div>
  ),
}));

// Mock authentication context
vi.mock("../contexts/AuthContext", () => ({
  default: {
    Provider: ({ children }) => children,
    Consumer: ({ children }) =>
      children(() => ({
        user: { id: "test-user", email: "test@example.com" },
        isAuthenticated: true,
        isLoading: false,
      })),
  },
  AuthProvider: ({ children }) => children,
  useAuth: vi.fn(() => ({
    user: { id: "test-user", email: "test@example.com" },
    isAuthenticated: true,
    isLoading: false,
    tokens: { idToken: "test-token" },
  })),
}));

// Mock session manager
vi.mock("../services/sessionManager", () => ({
  default: {
    startSession: vi.fn(),
    endSession: vi.fn(),
    extendSession: vi.fn(),
    getSessionStatus: vi.fn(() => ({ isActive: true, timeRemaining: 3600 })),
  },
}));

// Mock API key service
vi.mock("../services/apiKeyService", () => ({
  getApiKeys: vi.fn(() => Promise.resolve({})),
  setApiKey: vi.fn(() => Promise.resolve(true)),
  validateApiKeys: vi.fn(() => Promise.resolve(true)),
}));

// Mock chart components that might cause issues
vi.mock("../components/ProfessionalChart", () => ({
  default: ({ children, ...props }) => (
    <div data-testid="professional-chart" {...props}>
      {children}
    </div>
  ),
}));

// Global test setup
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

global.IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

// Mock window.matchMedia
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});
