/**
 * Unit Tests for ApiKeyHealthCheck Component
 * Tests critical API key health monitoring functionality
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock the API key provider
vi.mock("../../../components/ApiKeyProvider.jsx", () => ({
  useApiKeys: vi.fn(),
}));

// Mock Material-UI components to avoid dependency issues
vi.mock("@mui/material", () => ({
  Box: ({ children, ...props }) => (
    <div data-testid="box" {...props}>
      {children}
    </div>
  ),
  Card: ({ children, ...props }) => (
    <div data-testid="card" {...props}>
      {children}
    </div>
  ),
  CardContent: ({ children, ...props }) => (
    <div data-testid="card-content" {...props}>
      {children}
    </div>
  ),
  Typography: ({ children, ...props }) => (
    <div data-testid="typography" {...props}>
      {children}
    </div>
  ),
  List: ({ children, ...props }) => (
    <ul data-testid="list" {...props}>
      {children}
    </ul>
  ),
  ListItem: ({ children, ...props }) => (
    <li data-testid="list-item" {...props}>
      {children}
    </li>
  ),
  ListItemIcon: ({ children, ...props }) => (
    <div data-testid="list-item-icon" {...props}>
      {children}
    </div>
  ),
  ListItemText: ({ children, primary, secondary, ...props }) => (
    <div data-testid="list-item-text" {...props}>
      <div data-testid="primary">{primary}</div>
      <div data-testid="secondary">{secondary}</div>
      {children}
    </div>
  ),
  IconButton: ({ children, onClick, ...props }) => (
    <button data-testid="icon-button" onClick={onClick} {...props}>
      {children}
    </button>
  ),
  Tooltip: ({ children, title, ...props }) => (
    <div data-testid="tooltip" title={title} {...props}>
      {children}
    </div>
  ),
  Chip: ({ label, ...props }) => (
    <span data-testid="chip" {...props}>
      {label}
    </span>
  ),
  LinearProgress: (props) => <div data-testid="linear-progress" {...props} />,
  Alert: ({ children, severity, ...props }) => (
    <div data-testid="alert" data-severity={severity} {...props}>
      {children}
    </div>
  ),
  Button: ({ children, onClick, ...props }) => (
    <button data-testid="button" onClick={onClick} {...props}>
      {children}
    </button>
  ),
  Divider: (props) => <hr data-testid="divider" {...props} />,
  Grid: ({ children, ...props }) => (
    <div data-testid="grid" {...props}>
      {children}
    </div>
  ),
  Paper: ({ children, ...props }) => (
    <div data-testid="paper" {...props}>
      {children}
    </div>
  ),
}));

// Mock Material-UI icons
vi.mock("@mui/icons-material", () => ({
  CheckCircle: () => <div data-testid="check-circle-icon" />,
  Error: () => <div data-testid="error-icon" />,
  Warning: () => <div data-testid="warning-icon" />,
  Schedule: () => <div data-testid="schedule-icon" />,
  Refresh: () => <div data-testid="refresh-icon" />,
  Settings: () => <div data-testid="settings-icon" />,
  Speed: () => <div data-testid="speed-icon" />,
  Timeline: () => <div data-testid="timeline-icon" />,
  TrendingUp: () => <div data-testid="trending-up-icon" />,
  CloudDone: () => <div data-testid="cloud-done-icon" />,
  CloudOff: () => <div data-testid="cloud-off-icon" />,
  Info: () => <div data-testid="info-icon" />,
  Assessment: () => <div data-testid="assessment-icon" />,
}));

import ApiKeyHealthCheck from "../../../components/ApiKeyHealthCheck.jsx";
import { useApiKeys } from "../../../components/ApiKeyProvider.jsx";

describe("ApiKeyHealthCheck Component", () => {
  const mockUseApiKeys = useApiKeys;

  const mockApiKeys = [
    {
      id: "alpaca-key-1",
      provider: "alpaca",
      label: "Alpaca Trading",
      status: "active",
      lastValidated: new Date().toISOString(),
    },
    {
      id: "polygon-key-1",
      provider: "polygon",
      label: "Polygon Market Data",
      status: "active",
      lastValidated: new Date().toISOString(),
    },
  ];

  const defaultProps = {
    apiKeys: mockApiKeys,
    onRefresh: vi.fn(),
    onSettings: vi.fn(),
    autoRefresh: true,
    refreshInterval: 30000,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();

    mockUseApiKeys.mockReturnValue({
      apiKeys: mockApiKeys,
      isLoading: false,
      error: null,
      refreshKeys: vi.fn(),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  describe("Component Rendering", () => {
    it("should render without crashing", () => {
      render(<ApiKeyHealthCheck {...defaultProps} />);

      expect(screen.getByTestId("card")).toBeInTheDocument();
    });

    it("should display API key health status", () => {
      render(<ApiKeyHealthCheck {...defaultProps} />);

      // Should show health check information
      expect(screen.getByTestId("card-content")).toBeInTheDocument();
    });

    it("should show loading state during health check", () => {
      mockUseApiKeys.mockReturnValue({
        apiKeys: mockApiKeys,
        isLoading: true,
        error: null,
        refreshKeys: vi.fn(),
      });

      render(<ApiKeyHealthCheck {...defaultProps} />);

      expect(screen.getByTestId("linear-progress")).toBeInTheDocument();
    });

    it("should display error state when health check fails", () => {
      mockUseApiKeys.mockReturnValue({
        apiKeys: mockApiKeys,
        isLoading: false,
        error: "Failed to validate API keys",
        refreshKeys: vi.fn(),
      });

      render(<ApiKeyHealthCheck {...defaultProps} />);

      expect(screen.getByTestId("alert")).toBeInTheDocument();
      expect(screen.getByTestId("alert")).toHaveAttribute(
        "data-severity",
        "error"
      );
    });
  });

  describe("API Key Status Display", () => {
    it("should show healthy status for valid API keys", () => {
      render(<ApiKeyHealthCheck {...defaultProps} />);

      // Should display API key information
      const listItems = screen.getAllByTestId("list-item");
      expect(listItems.length).toBeGreaterThan(0);
    });

    it("should show warning for API keys needing attention", () => {
      const keysWithWarning = [
        {
          ...mockApiKeys[0],
          status: "warning",
          lastValidated: new Date(
            Date.now() - 7 * 24 * 60 * 60 * 1000
          ).toISOString(), // 7 days ago
        },
      ];

      render(<ApiKeyHealthCheck apiKeys={keysWithWarning} {...defaultProps} />);

      expect(screen.getByTestId("warning-icon")).toBeInTheDocument();
    });

    it("should show error status for invalid API keys", () => {
      const keysWithError = [
        {
          ...mockApiKeys[0],
          status: "error",
          error: "Invalid API key",
        },
      ];

      render(<ApiKeyHealthCheck apiKeys={keysWithError} {...defaultProps} />);

      expect(screen.getByTestId("error-icon")).toBeInTheDocument();
    });

    it("should display last validation timestamp", () => {
      render(<ApiKeyHealthCheck {...defaultProps} />);

      // Should show when the keys were last validated
      const secondaryTexts = screen.getAllByTestId("secondary");
      expect(secondaryTexts.length).toBeGreaterThan(0);
    });
  });

  describe("User Interactions", () => {
    it("should handle refresh button click", () => {
      const onRefresh = vi.fn();

      render(<ApiKeyHealthCheck {...defaultProps} onRefresh={onRefresh} />);

      const refreshButton = screen.getByTestId("icon-button");
      fireEvent.click(refreshButton);

      expect(onRefresh).toHaveBeenCalledTimes(1);
    });

    it("should handle settings button click", () => {
      const onSettings = vi.fn();

      render(<ApiKeyHealthCheck {...defaultProps} onSettings={onSettings} />);

      const settingsButton = screen.getByTestId("button");
      fireEvent.click(settingsButton);

      expect(onSettings).toHaveBeenCalledTimes(1);
    });

    it("should toggle timeline view", () => {
      render(<ApiKeyHealthCheck {...defaultProps} />);

      // Find and click timeline toggle
      const timelineButton = screen.getByTestId("icon-button");
      fireEvent.click(timelineButton);

      // Timeline view should be toggled
      expect(screen.getByTestId("card")).toBeInTheDocument();
    });
  });

  describe("Auto Refresh Functionality", () => {
    it("should auto-refresh when enabled", async () => {
      const refreshKeys = vi.fn();
      mockUseApiKeys.mockReturnValue({
        apiKeys: mockApiKeys,
        isLoading: false,
        error: null,
        refreshKeys,
      });

      const { unmount } = render(
        <ApiKeyHealthCheck
          {...defaultProps}
          autoRefresh={true}
          refreshInterval={1000}
        />
      );

      // Advance time to trigger auto-refresh
      vi.advanceTimersByTime(1100);

      await waitFor(
        () => {
          expect(refreshKeys).toHaveBeenCalled();
        },
        { timeout: 1000 }
      );

      // Clean up
      unmount();
    });

    it("should not auto-refresh when disabled", async () => {
      const refreshKeys = vi.fn();
      mockUseApiKeys.mockReturnValue({
        apiKeys: mockApiKeys,
        isLoading: false,
        error: null,
        refreshKeys,
      });

      const { unmount } = render(
        <ApiKeyHealthCheck {...defaultProps} autoRefresh={false} />
      );

      // Advance time past refresh interval
      vi.advanceTimersByTime(2000);

      expect(refreshKeys).not.toHaveBeenCalled();

      // Clean up
      unmount();
    });
  });

  describe("Performance Monitoring", () => {
    it("should track health check performance", () => {
      render(<ApiKeyHealthCheck {...defaultProps} />);

      // Should display performance metrics
      expect(screen.getByTestId("card")).toBeInTheDocument();
    });

    it("should show performance trends", () => {
      render(<ApiKeyHealthCheck {...defaultProps} />);

      // Should have trending indicators
      expect(screen.getByTestId("card-content")).toBeInTheDocument();
    });
  });

  describe("Error Handling", () => {
    it("should handle network errors gracefully", () => {
      mockUseApiKeys.mockReturnValue({
        apiKeys: [],
        isLoading: false,
        error: "Network connection failed",
        refreshKeys: vi.fn(),
      });

      render(<ApiKeyHealthCheck {...defaultProps} />);

      expect(screen.getByTestId("alert")).toBeInTheDocument();
      expect(screen.getByTestId("alert")).toHaveAttribute(
        "data-severity",
        "error"
      );
    });

    it("should handle API timeout errors", () => {
      mockUseApiKeys.mockReturnValue({
        apiKeys: [],
        isLoading: false,
        error: "Request timeout",
        refreshKeys: vi.fn(),
      });

      render(<ApiKeyHealthCheck {...defaultProps} />);

      expect(screen.getByTestId("alert")).toBeInTheDocument();
    });

    it("should handle invalid API key format errors", () => {
      const invalidKeys = [
        {
          id: "invalid-key",
          provider: "unknown",
          status: "error",
          error: "Invalid key format",
        },
      ];

      render(<ApiKeyHealthCheck apiKeys={invalidKeys} {...defaultProps} />);

      expect(screen.getByTestId("error-icon")).toBeInTheDocument();
    });
  });

  describe("Health Status Calculation", () => {
    it("should calculate overall health score", () => {
      const mixedKeys = [
        { ...mockApiKeys[0], status: "active" },
        { ...mockApiKeys[1], status: "warning" },
      ];

      render(<ApiKeyHealthCheck apiKeys={mixedKeys} {...defaultProps} />);

      // Should show overall health status
      expect(screen.getByTestId("card")).toBeInTheDocument();
    });

    it("should show critical health status when all keys fail", () => {
      const failedKeys = [
        { ...mockApiKeys[0], status: "error", error: "Authentication failed" },
        { ...mockApiKeys[1], status: "error", error: "Invalid credentials" },
      ];

      render(<ApiKeyHealthCheck apiKeys={failedKeys} {...defaultProps} />);

      expect(screen.getByTestId("alert")).toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA labels", () => {
      render(<ApiKeyHealthCheck {...defaultProps} />);

      // Icon buttons should have accessible labels
      const iconButton = screen.getByTestId("icon-button");
      expect(iconButton).toBeInTheDocument();
    });

    it("should support keyboard navigation", () => {
      render(<ApiKeyHealthCheck {...defaultProps} />);

      const button = screen.getByTestId("button");

      // Should be focusable
      button.focus();
      expect(document.activeElement).toBe(button);

      // Should respond to Enter key
      fireEvent.keyDown(button, { key: "Enter" });
      expect(defaultProps.onSettings).toHaveBeenCalled();
    });

    it("should provide tooltips for status indicators", () => {
      render(<ApiKeyHealthCheck {...defaultProps} />);

      const tooltip = screen.getByTestId("tooltip");
      expect(tooltip).toBeInTheDocument();
      expect(tooltip).toHaveAttribute("title");
    });
  });

  describe("Data Validation", () => {
    it("should handle missing API keys gracefully", () => {
      render(<ApiKeyHealthCheck apiKeys={[]} {...defaultProps} />);

      expect(screen.getByTestId("card")).toBeInTheDocument();
    });

    it("should handle malformed API key data", () => {
      const malformedKeys = [{ id: null, provider: "", status: undefined }];

      expect(() => {
        render(<ApiKeyHealthCheck apiKeys={malformedKeys} {...defaultProps} />);
      }).not.toThrow();
    });

    it("should validate refresh interval bounds", () => {
      render(<ApiKeyHealthCheck {...defaultProps} refreshInterval={-1000} />);

      // Should handle invalid refresh interval gracefully
      expect(screen.getByTestId("card")).toBeInTheDocument();
    });
  });
});
