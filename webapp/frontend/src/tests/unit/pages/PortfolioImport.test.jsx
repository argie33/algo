import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AuthContext } from "../../../contexts/AuthContext";
import PortfolioHoldings from "../../../pages/PortfolioHoldings";
import * as api from "../../../services/api";

// Mock the API services
jest.mock("../../../services/api", () => ({
  getPortfolioHoldings: jest.fn(),
  getStockPrices: jest.fn(),
  importPortfolioFromBroker: jest.fn(),
  addHolding: jest.fn(),
  updateHolding: jest.fn(),
  deleteHolding: jest.fn(),
}));

// Mock the auth context
const mockAuthContext = {
  user: { id: "test-user-id", userId: "test-user-id" },
  tokens: { accessToken: "test-token" },
  isAuthenticated: true,
};

const renderPortfolioHoldings = () => {
  return render(
    <AuthContext.Provider value={mockAuthContext}>
      <PortfolioHoldings />
    </AuthContext.Provider>
  );
};

describe("Portfolio Import Functionality", () => {
  beforeEach(() => {
    // Reset mocks
    jest.clearAllMocks();

    // Mock successful API responses
    api.getPortfolioHoldings.mockResolvedValue({
      success: true,
      holdings: [],
      summary: { totalValue: 0, totalPnL: 0, totalPnLPercent: 0 },
    });

    api.getStockPrices.mockResolvedValue({
      success: true,
      prices: {},
    });
  });

  test("should display import portfolio button", async () => {
    renderPortfolioHoldings();

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-button")).toBeInTheDocument();
    });

    const importButton = screen.getByTestId("import-portfolio-button");
    expect(importButton).toHaveTextContent("Import Portfolio");
  });

  test("should open import dialog when import button is clicked", async () => {
    renderPortfolioHoldings();

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-button")).toBeInTheDocument();
    });

    const importButton = screen.getByTestId("import-portfolio-button");
    fireEvent.click(importButton);

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-dialog")).toBeInTheDocument();
    });

    expect(screen.getByText("Import Portfolio from Broker")).toBeInTheDocument();
    expect(screen.getByText("Make sure you have configured your API keys in the Settings page")).toBeInTheDocument();
  });

  test("should display broker selection dropdown in import dialog", async () => {
    renderPortfolioHoldings();

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("import-portfolio-button"));

    await waitFor(() => {
      expect(screen.getByTestId("broker-select")).toBeInTheDocument();
    });

    const brokerSelect = screen.getByTestId("broker-select");
    fireEvent.mouseDown(brokerSelect);

    await waitFor(() => {
      expect(screen.getByText("Alpaca")).toBeInTheDocument();
    });
  });

  test("should call import API when broker is selected and import is confirmed", async () => {
    api.importPortfolioFromBroker.mockResolvedValue({
      success: true,
      message: "Portfolio imported successfully",
      holdings: [
        { symbol: "AAPL", shares: 10, avgCost: 150.00 },
        { symbol: "MSFT", shares: 5, avgCost: 300.00 }
      ]
    });

    renderPortfolioHoldings();

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-button")).toBeInTheDocument();
    });

    // Open import dialog
    fireEvent.click(screen.getByTestId("import-portfolio-button"));

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-dialog")).toBeInTheDocument();
    });

    // Select broker
    const brokerSelect = screen.getByTestId("broker-select");
    fireEvent.mouseDown(brokerSelect);

    await waitFor(() => {
      expect(screen.getByText("Alpaca")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Alpaca"));

    // Click import button
    const importConfirmButton = screen.getByTestId("import-confirm-button");
    fireEvent.click(importConfirmButton);

    await waitFor(() => {
      expect(api.importPortfolioFromBroker).toHaveBeenCalledWith("alpaca");
    });
  });

  test("should show error message when import fails", async () => {
    api.importPortfolioFromBroker.mockRejectedValue(new Error("No API key found for this broker"));

    renderPortfolioHoldings();

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-button")).toBeInTheDocument();
    });

    // Open import dialog
    fireEvent.click(screen.getByTestId("import-portfolio-button"));

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-dialog")).toBeInTheDocument();
    });

    // Select broker
    const brokerSelect = screen.getByTestId("broker-select");
    fireEvent.mouseDown(brokerSelect);
    fireEvent.click(screen.getByText("Alpaca"));

    // Click import button
    const importConfirmButton = screen.getByTestId("import-confirm-button");
    fireEvent.click(importConfirmButton);

    await waitFor(() => {
      expect(screen.getByText(/No API key found for this broker/)).toBeInTheDocument();
    });
  });

  test("should disable import button when no broker is selected", async () => {
    renderPortfolioHoldings();

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-button")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("import-portfolio-button"));

    await waitFor(() => {
      expect(screen.getByTestId("import-confirm-button")).toBeInTheDocument();
    });

    const importConfirmButton = screen.getByTestId("import-confirm-button");
    expect(importConfirmButton).toBeDisabled();
  });

  test("should close dialog after successful import", async () => {
    api.importPortfolioFromBroker.mockResolvedValue({
      success: true,
      message: "Portfolio imported successfully",
    });

    renderPortfolioHoldings();

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-button")).toBeInTheDocument();
    });

    // Open import dialog
    fireEvent.click(screen.getByTestId("import-portfolio-button"));

    await waitFor(() => {
      expect(screen.getByTestId("import-portfolio-dialog")).toBeInTheDocument();
    });

    // Select broker and import
    const brokerSelect = screen.getByTestId("broker-select");
    fireEvent.mouseDown(brokerSelect);
    fireEvent.click(screen.getByText("Alpaca"));

    const importConfirmButton = screen.getByTestId("import-confirm-button");
    fireEvent.click(importConfirmButton);

    await waitFor(() => {
      expect(screen.queryByTestId("import-portfolio-dialog")).not.toBeInTheDocument();
    });
  });
});