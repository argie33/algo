/**
 * Real-Time Data Integration Tests
 * Tests WebSocket connections, real-time data flow, and component updates
 * Focuses on live data synchronization across the application
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";

// Components that handle real-time data
import RealTimeDashboard from "../../pages/RealTimeDashboard.jsx";
import MarketStatusBar from "../../components/MarketStatusBar.jsx";
import RealTimePriceWidget from "../../components/RealTimePriceWidget.jsx";

// Hooks
import { useWebSocket } from "../../hooks/useWebSocket.js";

// Test wrapper
import { TestWrapper } from "../test-utils.jsx";

// Mock WebSocket and real-time services
const _mockWebSocket = {
  connect: vi.fn(),
  disconnect: vi.fn(),
  send: vi.fn(),
  subscribe: vi.fn(),
  unsubscribe: vi.fn(),
  isConnected: vi.fn(() => true),
  on: vi.fn(),
  off: vi.fn(),
  readyState: 1, // WebSocket.OPEN
};

const mockRealTimeService = {
  connect: vi.fn(() => Promise.resolve()),
  disconnect: vi.fn(() => Promise.resolve()),
  subscribe: vi.fn(),
  unsubscribe: vi.fn(),
  emit: vi.fn(),
  getLatestPrice: vi.fn(),
  isConnected: vi.fn(() => true),
  getConnectionStatus: vi.fn(() => "connected"),
};

vi.mock("../../services/realTimeDataService.js", () => ({
  default: mockRealTimeService,
}));

vi.mock("../../hooks/useWebSocket.js", () => ({
  useWebSocket: vi.fn(),
}));

describe("Real-Time Data Integration", () => {
  let mockWebSocketHook;

  beforeEach(() => {
    vi.clearAllMocks();

    // Setup WebSocket hook mock
    mockWebSocketHook = {
      isConnected: true,
      connectionState: "connected",
      lastMessage: null,
      sendMessage: vi.fn(),
      connect: vi.fn(),
      disconnect: vi.fn(),
      subscribe: vi.fn(),
      unsubscribe: vi.fn(),
    };

    useWebSocket.mockReturnValue(mockWebSocketHook);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe("WebSocket Connection Integration", () => {
    it("should establish WebSocket connection and maintain state", async () => {
      // Mock connection establishment
      mockRealTimeService.connect.mockResolvedValue();
      mockWebSocketHook.isConnected = true;

      render(
        <TestWrapper>
          <RealTimeDashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByTestId("real-time-dashboard")).toBeInTheDocument();
      });

      // Verify connection was established
      expect(mockRealTimeService.connect).toHaveBeenCalled();
    });

    it("should handle connection failures gracefully", async () => {
      // Mock connection failure
      mockRealTimeService.connect.mockRejectedValue(
        new Error("Connection failed")
      );
      mockWebSocketHook.isConnected = false;
      mockWebSocketHook.connectionState = "disconnected";

      render(
        <TestWrapper>
          <RealTimeDashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        // Should show offline state or connection error
        expect(
          screen.getByText(/connection failed/i) ||
            screen.getByText(/offline/i) ||
            screen.getByTestId("connection-error")
        ).toBeInTheDocument();
      });
    });

    it("should reconnect automatically after connection loss", async () => {
      // Start connected
      mockWebSocketHook.isConnected = true;

      const { rerender } = render(
        <TestWrapper>
          <MarketStatusBar />
        </TestWrapper>
      );

      // Simulate connection loss
      act(() => {
        mockWebSocketHook.isConnected = false;
        mockWebSocketHook.connectionState = "reconnecting";
      });

      rerender(
        <TestWrapper>
          <MarketStatusBar />
        </TestWrapper>
      );

      // Should show reconnecting state
      await waitFor(() => {
        expect(
          screen.getByText(/reconnecting/i) ||
            screen.getByTestId("reconnecting")
        ).toBeInTheDocument();
      });

      // Simulate successful reconnection
      act(() => {
        mockWebSocketHook.isConnected = true;
        mockWebSocketHook.connectionState = "connected";
      });

      rerender(
        <TestWrapper>
          <MarketStatusBar />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(
          screen.getByText(/connected/i) || screen.getByTestId("connected")
        ).toBeInTheDocument();
      });
    });
  });

  describe("Real-Time Data Flow Integration", () => {
    it("should receive and display real-time price updates", async () => {
      const mockPriceData = {
        symbol: "AAPL",
        price: 150.25,
        change: 2.15,
        changePercent: 1.45,
        timestamp: Date.now(),
      };

      // Mock real-time price subscription
      mockRealTimeService.subscribe.mockImplementation((symbol, callback) => {
        setTimeout(() => callback(mockPriceData), 100);
      });

      render(
        <TestWrapper>
          <RealTimePriceWidget symbol="AAPL" />
        </TestWrapper>
      );

      // Should eventually display real-time price
      await waitFor(
        () => {
          expect(screen.getByText(/150\.25/)).toBeInTheDocument();
          expect(screen.getByText(/\+2\.15/)).toBeInTheDocument();
        },
        { timeout: 2000 }
      );
    });

    it("should handle multiple simultaneous subscriptions", async () => {
      const symbols = ["AAPL", "GOOGL", "MSFT"];
      const mockData = symbols.map((symbol) => ({
        symbol,
        price: Math.random() * 1000,
        change: Math.random() * 10 - 5,
        changePercent: Math.random() * 5 - 2.5,
        timestamp: Date.now(),
      }));

      // Mock multiple subscriptions
      mockRealTimeService.subscribe.mockImplementation((symbol, callback) => {
        const data = mockData.find((d) => d.symbol === symbol);
        setTimeout(() => callback(data), 100);
      });

      const MultiSymbolComponent = () => (
        <div>
          {symbols.map((symbol) => (
            <RealTimePriceWidget key={symbol} symbol={symbol} />
          ))}
        </div>
      );

      render(
        <TestWrapper>
          <MultiSymbolComponent />
        </TestWrapper>
      );

      // Should handle all subscriptions
      await waitFor(() => {
        symbols.forEach((symbol) => {
          expect(mockRealTimeService.subscribe).toHaveBeenCalledWith(
            symbol,
            expect.any(Function)
          );
        });
      });
    });

    it("should batch and throttle rapid updates", async () => {
      const rapidUpdates = Array.from({ length: 10 }, (_, i) => ({
        symbol: "AAPL",
        price: 150 + i * 0.1,
        change: i * 0.1,
        timestamp: Date.now() + i * 100,
      }));

      let updateCallback;
      mockRealTimeService.subscribe.mockImplementation((symbol, callback) => {
        updateCallback = callback;
      });

      render(
        <TestWrapper>
          <RealTimePriceWidget symbol="AAPL" />
        </TestWrapper>
      );

      // Send rapid updates
      act(() => {
        rapidUpdates.forEach((update) => {
          updateCallback(update);
        });
      });

      // Should show the latest price (throttled/batched)
      await waitFor(() => {
        expect(screen.getByText(/150\.9/)).toBeInTheDocument();
      });
    });
  });

  describe("Data Synchronization Integration", () => {
    it("should synchronize data across multiple components", async () => {
      const mockMarketData = {
        indices: [
          { symbol: "SPX", value: 4500, change: 25.3 },
          { symbol: "NASDAQ", value: 14000, change: -15.2 },
        ],
        timestamp: Date.now(),
      };

      // Mock market data subscription
      mockRealTimeService.subscribe.mockImplementation((channel, callback) => {
        if (channel === "market-overview") {
          setTimeout(() => callback(mockMarketData), 100);
        }
      });

      const MultiComponentApp = () => (
        <div>
          <MarketStatusBar />
          <RealTimeDashboard />
        </div>
      );

      render(
        <TestWrapper>
          <MultiComponentApp />
        </TestWrapper>
      );

      // Both components should receive the same data
      await waitFor(() => {
        expect(screen.getByText(/4500/)).toBeInTheDocument();
        expect(screen.getByText(/14000/)).toBeInTheDocument();
      });
    });

    it("should handle data conflicts and maintain consistency", async () => {
      // Mock conflicting price data
      const oldPrice = {
        symbol: "AAPL",
        price: 148.5,
        timestamp: Date.now() - 1000,
      };
      const newPrice = { symbol: "AAPL", price: 150.25, timestamp: Date.now() };

      let subscriptionCallback;
      mockRealTimeService.subscribe.mockImplementation((symbol, callback) => {
        subscriptionCallback = callback;
      });

      render(
        <TestWrapper>
          <RealTimePriceWidget symbol="AAPL" />
        </TestWrapper>
      );

      // Send old price first
      act(() => {
        subscriptionCallback(oldPrice);
      });

      await waitFor(() => {
        expect(screen.getByText(/148\.50/)).toBeInTheDocument();
      });

      // Send newer price - should override
      act(() => {
        subscriptionCallback(newPrice);
      });

      await waitFor(() => {
        expect(screen.getByText(/150\.25/)).toBeInTheDocument();
        expect(screen.queryByText(/148\.50/)).not.toBeInTheDocument();
      });
    });
  });

  describe("Error Handling Integration", () => {
    it("should handle WebSocket errors gracefully", async () => {
      // Mock WebSocket error
      mockWebSocketHook.connectionState = "error";
      mockWebSocketHook.isConnected = false;

      render(
        <TestWrapper>
          <RealTimeDashboard />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(
          screen.getByText(/connection error/i) ||
            screen.getByTestId("connection-error")
        ).toBeInTheDocument();
      });
    });

    it("should handle malformed data gracefully", async () => {
      const malformedData = { invalid: "data" };

      let subscriptionCallback;
      mockRealTimeService.subscribe.mockImplementation((symbol, callback) => {
        subscriptionCallback = callback;
      });

      render(
        <TestWrapper>
          <RealTimePriceWidget symbol="AAPL" />
        </TestWrapper>
      );

      // Send malformed data
      act(() => {
        subscriptionCallback(malformedData);
      });

      // Should not crash and show appropriate fallback
      await waitFor(() => {
        expect(screen.getByTestId("price-widget")).toBeInTheDocument();
        expect(
          screen.getByText(/loading/i) || screen.getByText(/--/)
        ).toBeInTheDocument();
      });
    });
  });

  describe("Performance Integration", () => {
    it("should cleanup subscriptions on component unmount", async () => {
      const { unmount } = render(
        <TestWrapper>
          <RealTimePriceWidget symbol="AAPL" />
        </TestWrapper>
      );

      expect(mockRealTimeService.subscribe).toHaveBeenCalledWith(
        "AAPL",
        expect.any(Function)
      );

      unmount();

      expect(mockRealTimeService.unsubscribe).toHaveBeenCalledWith("AAPL");
    });

    it("should prevent memory leaks with proper cleanup", async () => {
      const symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"];

      const DynamicSubscriptions = ({ activeSymbols }) => (
        <div>
          {activeSymbols.map((symbol) => (
            <RealTimePriceWidget key={symbol} symbol={symbol} />
          ))}
        </div>
      );

      const { rerender, unmount } = render(
        <TestWrapper>
          <DynamicSubscriptions activeSymbols={symbols} />
        </TestWrapper>
      );

      // All symbols should be subscribed
      symbols.forEach((symbol) => {
        expect(mockRealTimeService.subscribe).toHaveBeenCalledWith(
          symbol,
          expect.any(Function)
        );
      });

      // Remove some symbols
      const reducedSymbols = symbols.slice(0, 2);
      rerender(
        <TestWrapper>
          <DynamicSubscriptions activeSymbols={reducedSymbols} />
        </TestWrapper>
      );

      // Removed symbols should be unsubscribed
      const removedSymbols = symbols.slice(2);
      removedSymbols.forEach((symbol) => {
        expect(mockRealTimeService.unsubscribe).toHaveBeenCalledWith(symbol);
      });

      unmount();

      // All remaining should be cleaned up
      reducedSymbols.forEach((symbol) => {
        expect(mockRealTimeService.unsubscribe).toHaveBeenCalledWith(symbol);
      });
    });
  });
});
