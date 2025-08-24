/**
 * Simple Portfolio Component Tests
 * Tests basic functionality with real API integration
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders } from "../../test-utils.jsx";
import { screen } from "@testing-library/react";
import Portfolio from "../../../pages/Portfolio.jsx";

// Mock the AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: { id: 'test-user', email: 'test@example.com', name: 'Test User' },
    isAuthenticated: true,
    isLoading: false,
    error: null,
  })),
  AuthProvider: ({ children }) => children,
}));

// Mock recharts components used in Portfolio
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children, ...props }) => (
    <div data-testid="responsive-container" {...props}>{children}</div>
  ),
  LineChart: ({ children, data, ...props }) => (
    <div data-testid="line-chart" data-chart-data={JSON.stringify(data)} {...props}>{children}</div>
  ),
  Line: ({ dataKey, stroke, ...props }) => (
    <div data-testid="chart-line" data-key={dataKey} data-stroke={stroke} {...props} />
  ),
  Area: ({ dataKey, fill, ...props }) => (
    <div data-testid="chart-area" data-key={dataKey} data-fill={fill} {...props} />
  ),
  AreaChart: ({ children, data, ...props }) => (
    <div data-testid="area-chart" data-chart-data={JSON.stringify(data)} {...props}>{children}</div>
  ),
  PieChart: ({ children, data, ...props }) => (
    <div data-testid="pie-chart" data-chart-data={JSON.stringify(data)} {...props}>{children}</div>
  ),
  Pie: ({ dataKey, data, ...props }) => (
    <div data-testid="pie" data-key={dataKey} data-chart-data={JSON.stringify(data)} {...props} />
  ),
  Cell: ({ fill, ...props }) => (
    <div data-testid="chart-cell" data-fill={fill} {...props} />
  ),
  XAxis: ({ dataKey, ...props }) => (
    <div data-testid="x-axis" data-key={dataKey} {...props} />
  ),
  YAxis: ({ domain, ...props }) => (
    <div data-testid="y-axis" data-domain={JSON.stringify(domain)} {...props} />
  ),
  CartesianGrid: (props) => <div data-testid="cartesian-grid" {...props} />,
  RadarChart: ({ children, data, ...props }) => (
    <div data-testid="radar-chart" data-chart-data={JSON.stringify(data)} {...props}>{children}</div>
  ),
  PolarGrid: (props) => <div data-testid="polar-grid" {...props} />,
  PolarAngleAxis: ({ dataKey, ...props }) => (
    <div data-testid="polar-angle-axis" data-key={dataKey} {...props} />
  ),
  PolarRadiusAxis: (props) => <div data-testid="polar-radius-axis" {...props} />,
  Radar: ({ dataKey, ...props }) => (
    <div data-testid="radar" data-key={dataKey} {...props} />
  ),
  ComposedChart: ({ children, data, ...props }) => (
    <div data-testid="composed-chart" data-chart-data={JSON.stringify(data)} {...props}>{children}</div>
  ),
  Tooltip: ({ content, ...props }) => (
    <div data-testid="chart-tooltip" {...props}>
      {typeof content === 'function' ? 'Custom Tooltip' : 'Default Tooltip'}
    </div>
  ),
  Legend: (props) => <div data-testid="chart-legend" {...props} />,
}));

describe("Portfolio Component - Basic Rendering", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should render without crashing", () => {
    // Critical: Component must render without errors
    const { container } = renderWithProviders(<Portfolio />);
    
    expect(container).toBeTruthy();
    expect(container.innerHTML).not.toBe("");
  });

  it("should display portfolio heading or loading state", () => {
    // Critical: Users should see portfolio section or loading indicator
    renderWithProviders(<Portfolio />);
    
    // Should show portfolio related text or loading state
    const portfolioElements = screen.queryAllByText(/portfolio/i);
    const loadingIndicator = screen.queryByRole("progressbar");
    
    // Component should show either portfolio content or loading
    expect(portfolioElements.length > 0 || loadingIndicator).toBeTruthy();
  });

  it("should have proper component structure", () => {
    // Critical: Component should have basic structure
    renderWithProviders(<Portfolio />);
    
    // Should render either main content or loading state
    const hasProgressBar = screen.queryByRole("progressbar");
    const hasMainContainer = document.querySelector('.MuiContainer-root');
    
    // Component should show loading state or main container
    expect(hasProgressBar || hasMainContainer).toBeTruthy();
  });

  it("should handle component lifecycle properly", () => {
    // Critical: Component should mount and unmount without errors
    const { unmount } = renderWithProviders(<Portfolio />);
    
    // Should unmount without errors
    expect(() => unmount()).not.toThrow();
  });
});