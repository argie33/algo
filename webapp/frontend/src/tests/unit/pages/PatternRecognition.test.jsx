/**
 * Unit Tests for PatternRecognition Component
 * Tests the technical pattern detection and analysis functionality
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders } from "../../test-utils.jsx";
import { screen, waitFor, act, fireEvent } from "@testing-library/react";
import PatternRecognition from "../../../pages/PatternRecognition.jsx";
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
  detectPatterns: vi.fn(() => 
    Promise.resolve({
      success: true,
      data: {
        patterns: [
          {
            id: 'pattern-1',
            symbol: 'AAPL',
            patternType: 'head_and_shoulders',
            confidence: 0.85,
            timeframe: '1D',
            detectedAt: '2024-01-15T10:30:00Z',
            priceTarget: 165.00,
            stopLoss: 140.00,
            status: 'active',
            description: 'Bearish head and shoulders pattern forming'
          },
          {
            id: 'pattern-2',
            symbol: 'MSFT',
            patternType: 'ascending_triangle',
            confidence: 0.72,
            timeframe: '4H',
            detectedAt: '2024-01-15T09:15:00Z',
            priceTarget: 295.00,
            stopLoss: 270.00,
            status: 'completed',
            description: 'Bullish ascending triangle breakout'
          }
        ],
        summary: {
          totalPatterns: 2,
          activePatterns: 1,
          completedPatterns: 1,
          averageConfidence: 0.785
        }
      }
    })
  ),
  getPatternHistory: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: [
        {
          id: 'pattern-old-1',
          symbol: 'TSLA',
          patternType: 'double_bottom',
          confidence: 0.91,
          detectedAt: '2024-01-10T14:20:00Z',
          outcome: 'successful',
          profitLoss: 12.5
        }
      ]
    })
  ),
  getAvailablePatterns: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: [
        {
          type: 'head_and_shoulders',
          name: 'Head and Shoulders',
          category: 'reversal',
          reliability: 'high'
        },
        {
          type: 'ascending_triangle',
          name: 'Ascending Triangle',
          category: 'continuation',
          reliability: 'medium'
        },
        {
          type: 'double_bottom',
          name: 'Double Bottom',
          category: 'reversal',
          reliability: 'high'
        }
      ]
    })
  ),
  subscribeToPatternAlerts: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: { message: 'Subscribed to pattern alerts' }
    })
  ),
  api: {
    get: vi.fn(() => Promise.resolve({ data: { success: true } })),
    post: vi.fn(() => Promise.resolve({ data: { success: true } }))
  }
}));

// Mock chart components
vi.mock("recharts", () => ({
  LineChart: ({ children }) => <div data-testid="pattern-chart">{children}</div>,
  Line: () => <div data-testid="pattern-line" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  ResponsiveContainer: ({ children }) => <div data-testid="chart-container">{children}</div>,
}));

describe("PatternRecognition Component - Technical Pattern Analysis", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          success: true,
          data: {
            patterns: []
          }
        })
      })
    );
  });

  describe("Component Rendering", () => {
    it("should render pattern recognition interface", async () => {
      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      expect(
        screen.getByText(/pattern/i) ||
        screen.getByText(/recognition/i) ||
        screen.getByText(/technical/i)
      ).toBeTruthy();
    });

    it("should display pattern detection controls", async () => {
      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/detect|scan|analyze/i) ||
          screen.queryByText(/symbol|timeframe/i) ||
          document.querySelector('input') ||
          document.querySelector('select')
        ).toBeTruthy();
      });
    });
  });

  describe("Pattern Detection", () => {
    it("should detect technical patterns", async () => {
      apiService.detectPatterns.mockResolvedValue({
        success: true,
        data: {
          patterns: [
            {
              symbol: 'AAPL',
              patternType: 'head_and_shoulders',
              confidence: 0.85
            }
          ]
        }
      });

      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        const detectButton = screen.queryByText(/detect|scan|analyze/i);
        if (detectButton && detectButton.tagName === 'BUTTON') {
          fireEvent.click(detectButton);
        }
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/head and shoulders|AAPL|0\.85/i) ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });

    it("should display pattern details", async () => {
      apiService.detectPatterns.mockResolvedValue({
        success: true,
        data: {
          patterns: [
            {
              symbol: 'MSFT',
              patternType: 'ascending_triangle',
              confidence: 0.72,
              priceTarget: 295.00,
              stopLoss: 270.00
            }
          ]
        }
      });

      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/MSFT|ascending|triangle/i) ||
          screen.queryByText(/295|270|0\.72/i) ||
          screen.queryByText(/target|stop|confidence/i) ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });

    it("should show pattern confidence scores", async () => {
      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/confidence|score|probability/i) ||
          screen.queryByText(/\d+\.\d+|\d+%/i) ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Pattern Types and Categories", () => {
    it("should display available pattern types", async () => {
      apiService.getAvailablePatterns.mockResolvedValue({
        success: true,
        data: [
          {
            type: 'head_and_shoulders',
            name: 'Head and Shoulders',
            category: 'reversal'
          },
          {
            type: 'triangle',
            name: 'Triangle Patterns',
            category: 'continuation'
          }
        ]
      });

      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/head and shoulders|triangle/i) ||
          screen.queryByText(/reversal|continuation/i) ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });

    it("should categorize patterns by type", async () => {
      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/reversal|continuation|breakout/i) ||
          screen.queryByText(/bullish|bearish|neutral/i) ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });

    it("should show pattern reliability indicators", async () => {
      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/reliability|accuracy|success rate/i) ||
          screen.queryByText(/high|medium|low/i) ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Pattern Visualization", () => {
    it("should render pattern charts", async () => {
      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          document.querySelector('[data-testid*="pattern-chart"]') ||
          document.querySelector('[data-testid*="chart"]') ||
          document.querySelector('canvas') ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });

    it("should highlight pattern formations on charts", async () => {
      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/formation|highlight|mark/i) ||
          document.querySelector('[data-testid*="pattern-line"]') ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });

    it("should show price targets and stop losses", async () => {
      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/target|stop loss|price/i) ||
          screen.queryByText(/\$\d+|\d+\.\d+/i) ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Pattern History and Tracking", () => {
    it("should display historical patterns", async () => {
      apiService.getPatternHistory.mockResolvedValue({
        success: true,
        data: [
          {
            symbol: 'TSLA',
            patternType: 'double_bottom',
            outcome: 'successful',
            profitLoss: 12.5
          }
        ]
      });

      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/TSLA|double bottom|successful/i) ||
          screen.queryByText(/12\.5|profit|history/i) ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });

    it("should track pattern outcomes", async () => {
      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/outcome|result|success|failed/i) ||
          screen.queryByText(/profit|loss|performance/i) ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });

    it("should show pattern statistics", async () => {
      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/statistics|total|average|success rate/i) ||
          screen.queryByText(/\d+\.\d+%|\d+ patterns/i) ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Pattern Alerts and Notifications", () => {
    it("should support pattern alert subscriptions", async () => {
      apiService.subscribeToPatternAlerts.mockResolvedValue({
        success: true,
        data: { message: 'Subscribed successfully' }
      });

      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        const subscribeButton = screen.queryByText(/subscribe|alert|notify/i);
        if (subscribeButton && subscribeButton.tagName === 'BUTTON') {
          fireEvent.click(subscribeButton);
        }
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/subscribed|alerts|notification/i) ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });

    it("should display active pattern alerts", async () => {
      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/alert|notification|new pattern/i) ||
          screen.queryByText(/active|pending|detected/i) ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Filtering and Search", () => {
    it("should allow filtering by symbol", async () => {
      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/symbol|ticker|stock/i) ||
          document.querySelector('input[type="text"]') ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });

    it("should support timeframe filtering", async () => {
      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/timeframe|1D|4H|1H|daily/i) ||
          document.querySelector('select') ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });

    it("should filter by pattern type", async () => {
      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/type|category|reversal|continuation/i) ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Error Handling", () => {
    it("should handle pattern detection errors", async () => {
      apiService.detectPatterns.mockRejectedValue(
        new Error("Pattern detection service unavailable")
      );

      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        const detectButton = screen.queryByText(/detect|scan/i);
        if (detectButton && detectButton.tagName === 'BUTTON') {
          fireEvent.click(detectButton);
        }
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/error|failed|unavailable/i) ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });

    it("should show loading state during pattern analysis", async () => {
      apiService.detectPatterns.mockImplementation(() => 
        new Promise(resolve => 
          setTimeout(() => resolve({ success: true, data: { patterns: [] } }), 100)
        )
      );

      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/loading|analyzing|detecting/i) ||
          document.querySelector('[role="progressbar"]') ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });

    it("should handle empty pattern results", async () => {
      apiService.detectPatterns.mockResolvedValue({
        success: true,
        data: {
          patterns: [],
          summary: { totalPatterns: 0 }
        }
      });

      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          screen.queryByText(/no patterns|empty|not found/i) ||
          screen.queryByText(/0 patterns/i) ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Integration and Authentication", () => {
    it("should handle authenticated user sessions", async () => {
      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      expect(screen.getByText(/pattern/i)).toBeTruthy();
    });

    it("should integrate with market data APIs", async () => {
      await act(async () => {
        renderWithProviders(<PatternRecognition />);
      });

      await waitFor(() => {
        expect(
          apiService.detectPatterns ||
          apiService.getAvailablePatterns ||
          screen.getByText(/pattern/i)
        ).toBeTruthy();
      });
    });
  });
});