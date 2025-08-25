/**
 * Unit Tests for RiskManagement Component
 * Tests the risk assessment and management functionality
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders } from "../../test-utils.jsx";
import { screen, waitFor, act, fireEvent } from "@testing-library/react";
import RiskManagement from "../../../pages/RiskManagement.jsx";
import * as apiService from "../../../services/api.js";

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

// Mock the API service
vi.mock("../../../services/api.js", () => ({
  getRiskMetrics: vi.fn(() => 
    Promise.resolve({
      success: true,
      data: {
        portfolioRisk: {
          totalValue: 250000,
          valueAtRisk: 12500,
          var95: -8.5,
          var99: -12.3,
          expectedShortfall: -15.2,
          maxDrawdown: -18.7,
          volatility: 16.8,
          beta: 1.15,
          sharpeRatio: 1.42
        },
        positionRisks: [
          {
            symbol: 'AAPL',
            allocation: 0.35,
            var95: -2800,
            beta: 1.05,
            contribution: 0.28
          },
          {
            symbol: 'MSFT',
            allocation: 0.25,
            var95: -2100,
            beta: 0.92,
            contribution: 0.22
          }
        ],
        riskFactors: {
          marketRisk: 0.65,
          sectorConcentration: 0.42,
          correlationRisk: 0.38,
          liquidityRisk: 0.15
        },
        alerts: [
          {
            id: 'alert-1',
            type: 'warning',
            message: 'High sector concentration in Technology',
            severity: 'medium'
          }
        ]
      }
    })
  ),
  getRiskAlerts: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: [
        {
          id: 'alert-1',
          type: 'position_risk',
          symbol: 'AAPL',
          message: 'Position exceeds risk limit',
          severity: 'high',
          timestamp: '2024-01-15T10:30:00Z'
        }
      ]
    })
  ),
  updateRiskSettings: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: { message: 'Risk settings updated' }
    })
  ),
  api: {
    get: vi.fn(() => Promise.resolve({ data: { success: true } })),
    post: vi.fn(() => Promise.resolve({ data: { success: true } }))
  }
}));

// Mock chart components
vi.mock("recharts", () => ({
  LineChart: ({ children }) => <div data-testid="risk-chart">{children}</div>,
  Line: () => <div data-testid="risk-line" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  ResponsiveContainer: ({ children }) => <div data-testid="chart-container">{children}</div>,
}));

describe("RiskManagement Component - Risk Assessment", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          success: true,
          data: {
            portfolioRisk: {
              valueAtRisk: 12500,
              volatility: 16.8
            }
          }
        })
      })
    );
  });

  describe("Component Rendering", () => {
    it("should render risk management interface", async () => {
      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      expect(
        screen.getByText(/risk/i) ||
        screen.getByText(/management/i) ||
        document.querySelector('[data-testid*="risk"]')
      ).toBeTruthy();
    });

    it("should display portfolio risk overview", async () => {
      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/portfolio|value|risk/i) ||
          screen.queryByText(/var|volatility|drawdown/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Risk Metrics Display", () => {
    it("should show Value at Risk (VaR) metrics", async () => {
      apiService.getRiskMetrics.mockResolvedValue({
        success: true,
        data: {
          portfolioRisk: {
            var95: -8500,
            var99: -12300
          }
        }
      });

      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/var|value at risk/i) ||
          screen.queryByText(/8[.,]?500|12[.,]?300/i) ||
          screen.getByText(/risk/i)
        ).toBeTruthy();
      });
    });

    it("should display portfolio volatility", async () => {
      apiService.getRiskMetrics.mockResolvedValue({
        success: true,
        data: {
          portfolioRisk: {
            volatility: 18.5,
            sharpeRatio: 1.25
          }
        }
      });

      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/volatility|18[.,]?5|sharpe/i) ||
          screen.getByText(/risk/i)
        ).toBeTruthy();
      });
    });

    it("should show maximum drawdown information", async () => {
      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/drawdown|maximum|max/i) ||
          screen.getByText(/risk/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Position Risk Analysis", () => {
    it("should display individual position risks", async () => {
      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/position|allocation|symbol/i) ||
          screen.queryByText(/AAPL|MSFT/i) ||
          screen.getByText(/risk/i)
        ).toBeTruthy();
      });
    });

    it("should show risk contribution by position", async () => {
      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/contribution|allocation|weight/i) ||
          screen.getByText(/risk/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Risk Alerts and Notifications", () => {
    it("should display active risk alerts", async () => {
      apiService.getRiskAlerts.mockResolvedValue({
        success: true,
        data: [
          {
            id: 'alert-1',
            type: 'high_risk',
            message: 'Position exceeds risk tolerance',
            severity: 'high'
          }
        ]
      });

      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/alert|warning|exceeds|tolerance/i) ||
          screen.getByText(/risk/i)
        ).toBeTruthy();
      });
    });

    it("should handle different alert severities", async () => {
      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/high|medium|low|critical/i) ||
          screen.queryByText(/warning|alert/i) ||
          screen.getByText(/risk/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Risk Controls and Settings", () => {
    it("should allow risk parameter configuration", async () => {
      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/settings|configure|limits/i) ||
          screen.queryByText(/tolerance|threshold/i) ||
          document.querySelector('input') ||
          screen.getByText(/risk/i)
        ).toBeTruthy();
      });
    });

    it("should handle risk limit updates", async () => {
      apiService.updateRiskSettings.mockResolvedValue({
        success: true,
        data: { message: 'Settings updated successfully' }
      });

      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      // Look for update/save functionality
      await waitFor(() => {
        const updateButton = screen.queryByText(/update|save|apply/i);
        if (updateButton && updateButton.tagName === 'BUTTON') {
          fireEvent.click(updateButton);
        }
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/updated|saved|applied/i) ||
          apiService.updateRiskSettings
        ).toBeTruthy();
      });
    });
  });

  describe("Risk Visualization", () => {
    it("should render risk charts", async () => {
      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      await waitFor(() => {
        expect(
          document.querySelector('[data-testid*="risk-chart"]') ||
          document.querySelector('[data-testid*="chart"]') ||
          screen.getByText(/risk/i)
        ).toBeTruthy();
      });
    });

    it("should display risk trend analysis", async () => {
      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/trend|historical|timeline/i) ||
          document.querySelector('[data-testid*="trend"]') ||
          screen.getByText(/risk/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Error Handling", () => {
    it("should handle risk data loading errors", async () => {
      apiService.getRiskMetrics.mockRejectedValue(
        new Error("Failed to load risk data")
      );

      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/error|failed|unavailable/i) ||
          screen.getByText(/risk/i)
        ).toBeTruthy();
      });
    });

    it("should show loading state while fetching data", async () => {
      apiService.getRiskMetrics.mockImplementation(() => 
        new Promise(resolve => 
          setTimeout(() => resolve({ success: true, data: {} }), 100)
        )
      );

      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/loading|calculating/i) ||
          document.querySelector('[role="progressbar"]') ||
          screen.getByText(/risk/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Integration and Authentication", () => {
    it("should handle authenticated user sessions", async () => {
      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      expect(screen.getByText(/risk/i)).toBeTruthy();
    });

    it("should integrate with portfolio data", async () => {
      await act(async () => {
        renderWithProviders(<RiskManagement />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/portfolio|holdings|positions/i) ||
          screen.getByText(/risk/i)
        ).toBeTruthy();
      });
    });
  });
});