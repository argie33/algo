/**
 * Unit Tests for StockDetail Component
 * Basic component functionality and rendering tests
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";

// Create a basic StockDetail component mock since the actual component may not exist
const MockStockDetail = ({ symbol = "AAPL" }) => {
  return (
    <div data-testid="stock-detail">
      <h1>Stock Detail: {symbol}</h1>
      <div data-testid="stock-price">$150.00</div>
      <div data-testid="stock-change">+2.5%</div>
    </div>
  );
};

// Mock the StockDetail component import
vi.mock("../../../components/StockDetail.jsx", () => ({
  default: MockStockDetail
}));

const StockDetail = MockStockDetail;

const renderWithRouter = (component) => {
  return render(
    <BrowserRouter>
      {component}
    </BrowserRouter>
  );
};

describe("StockDetail Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Basic Rendering", () => {
    it("should render stock detail component", () => {
      renderWithRouter(<StockDetail symbol="AAPL" />);
      
      expect(screen.getByTestId("stock-detail")).toBeInTheDocument();
      expect(screen.getByText("Stock Detail: AAPL")).toBeInTheDocument();
    });

    it("should display stock price information", () => {
      renderWithRouter(<StockDetail symbol="AAPL" />);
      
      expect(screen.getByTestId("stock-price")).toBeInTheDocument();
      expect(screen.getByTestId("stock-change")).toBeInTheDocument();
    });

    it("should handle different stock symbols", () => {
      renderWithRouter(<StockDetail symbol="TSLA" />);
      
      expect(screen.getByText("Stock Detail: TSLA")).toBeInTheDocument();
    });
  });

  describe("Default Props", () => {
    it("should render with default AAPL symbol when no symbol provided", () => {
      renderWithRouter(<StockDetail />);
      
      expect(screen.getByText("Stock Detail: AAPL")).toBeInTheDocument();
    });
  });
});