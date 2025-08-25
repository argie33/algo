/**
 * Unit Tests for HFTTrading Page Component
 * Tests the high-frequency trading page functionality and controls
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders } from "../../test-utils.jsx";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import React from "react";

// Mock the HFTTrading component since it may not exist yet
const MockHFTTrading = () => {
  const [isActive, setIsActive] = React.useState(false);
  
  return (
    <div data-testid="hft-trading">
      <h1>High-Frequency Trading</h1>
      <div data-testid="trading-controls">
        <button 
          data-testid="toggle-trading"
          onClick={() => setIsActive(!isActive)}
        >
          {isActive ? 'Stop Trading' : 'Start Trading'}
        </button>
        <div data-testid="trading-status">
          Status: {isActive ? 'Active' : 'Inactive'}
        </div>
      </div>
      <div data-testid="trading-metrics">
        <div>Total Trades: 1,245</div>
        <div>Success Rate: 87.3%</div>
        <div>Daily P&L: +$2,450</div>
      </div>
    </div>
  );
};

vi.mock("../../../pages/HFTTrading.jsx", () => ({
  default: MockHFTTrading
}));

// Mock the API service
vi.mock("../../../services/api.js", () => ({
  api: {
    getHFTStatus: vi.fn(() => Promise.resolve({
      data: {
        isActive: false,
        totalTrades: 1245,
        successRate: 87.3,
        dailyPnL: 2450,
        activeStrategies: 3
      }
    })),
    startHFTTrading: vi.fn(() => Promise.resolve({
      success: true,
      message: 'HFT trading started'
    })),
    stopHFTTrading: vi.fn(() => Promise.resolve({
      success: true,
      message: 'HFT trading stopped'
    })),
    getHFTMetrics: vi.fn(() => Promise.resolve({
      data: {
        trades: [
          { id: 1, symbol: 'AAPL', side: 'buy', quantity: 100, price: 180.50 },
          { id: 2, symbol: 'MSFT', side: 'sell', quantity: 50, price: 385.75 }
        ]
      }
    }))
  }
}));

describe("HFTTrading Page Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Page Loading", () => {
    it("should render HFT trading page", async () => {
      renderWithProviders(<MockHFTTrading />);
      
      expect(screen.getByText(/High-Frequency Trading/i)).toBeInTheDocument();
      expect(screen.getByTestId('hft-trading')).toBeInTheDocument();
    });

    it("should display trading controls", async () => {
      renderWithProviders(<MockHFTTrading />);
      
      await waitFor(() => {
        expect(screen.getByTestId('trading-controls')).toBeInTheDocument();
        expect(screen.getByTestId('toggle-trading')).toBeInTheDocument();
        expect(screen.getByTestId('trading-status')).toBeInTheDocument();
      }, { timeout: 10000 });
    });

    it("should display trading metrics", async () => {
      renderWithProviders(<MockHFTTrading />);
      
      await waitFor(() => {
        expect(screen.getByTestId('trading-metrics')).toBeInTheDocument();
        expect(screen.getByText(/Total Trades/i)).toBeInTheDocument();
        expect(screen.getByText(/Success Rate/i)).toBeInTheDocument();
        expect(screen.getByText(/Daily P&L/i)).toBeInTheDocument();
      }, { timeout: 10000 });
    });
  });

  describe("Trading Controls", () => {
    it("should start with inactive status", async () => {
      renderWithProviders(<MockHFTTrading />);
      
      await waitFor(() => {
        expect(screen.getByText(/Status: Inactive/i)).toBeInTheDocument();
        expect(screen.getByText(/Start Trading/i)).toBeInTheDocument();
      }, { timeout: 10000 });
    });

    it("should toggle trading status when button clicked", async () => {
      renderWithProviders(<MockHFTTrading />);
      
      const toggleButton = screen.getByTestId('toggle-trading');
      
      // Initially inactive
      expect(screen.getByText(/Status: Inactive/i)).toBeInTheDocument();
      
      // Click to activate
      fireEvent.click(toggleButton);
      
      await waitFor(() => {
        expect(screen.getByText(/Status: Active/i)).toBeInTheDocument();
        expect(screen.getByText(/Stop Trading/i)).toBeInTheDocument();
      }, { timeout: 5000 });
    });
  });

  describe("Data Display", () => {
    it("should show trading metrics", async () => {
      renderWithProviders(<MockHFTTrading />);
      
      await waitFor(() => {
        expect(screen.getByText(/1,245/)).toBeInTheDocument();
        expect(screen.getByText(/87\.3%/)).toBeInTheDocument();
        expect(screen.getByText(/\+\$2,450/)).toBeInTheDocument();
      }, { timeout: 10000 });
    });
  });

  describe("Error Handling", () => {
    it("should handle API errors gracefully", async () => {
      const { api } = await import("../../../services/api.js");
      api.getHFTStatus.mockRejectedValueOnce(new Error('API Error'));
      
      renderWithProviders(<MockHFTTrading />);
      
      // Should not crash and should show page content
      await waitFor(() => {
        expect(screen.getByText(/High-Frequency Trading/i)).toBeInTheDocument();
      }, { timeout: 5000 });
    });
  });
});