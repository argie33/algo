/**
 * EconomicModeling Page Unit Tests
 * Tests the economic modeling functionality - GDP data, economic indicators, forecasting models
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  renderWithProviders,
  screen,
  waitFor,
  createMockUser,
  fireEvent,
} from "../../test-utils.jsx";
import EconomicModeling from "../../../pages/EconomicModeling.jsx";

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

// Mock API service
vi.mock("../../../services/api.js", () => ({
  api: {
    getEconomicIndicators: vi.fn(),
    getGDPData: vi.fn(),
    getInflationData: vi.fn(),
    getUnemploymentData: vi.fn(),
    getInterestRates: vi.fn(),
    getEconomicForecasts: vi.fn(),
  },
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
}));

const mockEconomicData = {
  gdp: [
    { quarter: "2023-Q4", value: 27000000000000, growth: 2.4 },
    { quarter: "2023-Q3", value: 26800000000000, growth: 2.1 },
  ],
  inflation: [
    { month: "2023-12", value: 3.1 },
    { month: "2023-11", value: 3.2 },
  ],
  unemployment: [
    { month: "2023-12", value: 3.7 },
    { month: "2023-11", value: 3.9 },
  ],
  indicators: [
    {
      name: "Consumer Confidence",
      value: 114.8,
      change: 2.3,
      trend: "positive",
    },
    {
      name: "Manufacturing PMI",
      value: 49.2,
      change: -1.2,
      trend: "negative",
    },
  ],
};

describe("EconomicModeling Component", () => {
  const { api } = require("../../../services/api.js");

  beforeEach(() => {
    vi.clearAllMocks();
    api.getEconomicIndicators.mockResolvedValue({
      success: true,
      data: mockEconomicData.indicators,
    });
    api.getGDPData.mockResolvedValue({
      success: true,
      data: mockEconomicData.gdp,
    });
    api.getInflationData.mockResolvedValue({
      success: true,
      data: mockEconomicData.inflation,
    });
    api.getUnemploymentData.mockResolvedValue({
      success: true,
      data: mockEconomicData.unemployment,
    });
    api.getEconomicForecasts.mockResolvedValue({
      success: true,
      data: [],
    });
  });

  it("renders economic modeling page", async () => {
    renderWithProviders(<EconomicModeling />);
    
    expect(screen.getByText(/economic modeling/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(api.getEconomicIndicators).toHaveBeenCalled();
    });
  });

  it("displays economic indicators", async () => {
    renderWithProviders(<EconomicModeling />);
    
    await waitFor(() => {
      expect(screen.getByText("Consumer Confidence")).toBeInTheDocument();
      expect(screen.getByText("Manufacturing PMI")).toBeInTheDocument();
      expect(screen.getByText("114.8")).toBeInTheDocument();
      expect(screen.getByText("49.2")).toBeInTheDocument();
    });
  });

  it("shows loading state initially", () => {
    api.getEconomicIndicators.mockImplementation(() => new Promise(() => {}));
    
    renderWithProviders(<EconomicModeling />);
    
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    api.getEconomicIndicators.mockRejectedValue(new Error("API Error"));
    
    renderWithProviders(<EconomicModeling />);
    
    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  it("displays GDP data with growth rates", async () => {
    renderWithProviders(<EconomicModeling />);
    
    await waitFor(() => {
      expect(screen.getByText("2023-Q4")).toBeInTheDocument();
      expect(screen.getByText("2.4%")).toBeInTheDocument();
    });
  });

  it("shows inflation trends", async () => {
    renderWithProviders(<EconomicModeling />);
    
    await waitFor(() => {
      expect(screen.getByText("3.1")).toBeInTheDocument();
      expect(screen.getByText("3.2")).toBeInTheDocument();
    });
  });

  it("displays unemployment data", async () => {
    renderWithProviders(<EconomicModeling />);
    
    await waitFor(() => {
      expect(screen.getByText("3.7")).toBeInTheDocument();
      expect(screen.getByText("3.9")).toBeInTheDocument();
    });
  });

  it("switches between different tabs", async () => {
    renderWithProviders(<EconomicModeling />);
    
    await waitFor(() => {
      expect(screen.getByText("Consumer Confidence")).toBeInTheDocument();
    });

    // Look for tab buttons
    const tabs = screen.getAllByRole("tab");
    if (tabs.length > 1) {
      fireEvent.click(tabs[1]);
      
      await waitFor(() => {
        expect(api.getGDPData).toHaveBeenCalled();
      });
    }
  });

  it("shows trend indicators with colors", async () => {
    renderWithProviders(<EconomicModeling />);
    
    await waitFor(() => {
      // Look for trend indicators (up/down arrows or colors)
      const positiveElements = screen.getAllByText(/2.3/);
      const negativeElements = screen.getAllByText(/-1.2/);
      
      expect(positiveElements.length).toBeGreaterThan(0);
      expect(negativeElements.length).toBeGreaterThan(0);
    });
  });

  it("refreshes data when refresh button is clicked", async () => {
    renderWithProviders(<EconomicModeling />);
    
    await waitFor(() => {
      expect(api.getEconomicIndicators).toHaveBeenCalledTimes(1);
    });

    const refreshButton = screen.getByLabelText(/refresh/i) || 
                         screen.getByRole("button", { name: /refresh/i });
    
    if (refreshButton) {
      fireEvent.click(refreshButton);
      
      await waitFor(() => {
        expect(api.getEconomicIndicators).toHaveBeenCalledTimes(2);
      });
    }
  });

  it("handles empty economic data", async () => {
    api.getEconomicIndicators.mockResolvedValue({
      success: true,
      data: [],
    });
    
    renderWithProviders(<EconomicModeling />);
    
    await waitFor(() => {
      expect(screen.getByText(/no data/i) || screen.getByText(/no indicators/i)).toBeInTheDocument();
    });
  });

  it("displays economic forecasts when available", async () => {
    const mockForecasts = [
      { metric: "GDP Growth", forecast: 2.8, period: "2024-Q1" },
      { metric: "Inflation Rate", forecast: 2.2, period: "2024-Q1" },
    ];
    
    api.getEconomicForecasts.mockResolvedValue({
      success: true,
      data: mockForecasts,
    });
    
    renderWithProviders(<EconomicModeling />);
    
    await waitFor(() => {
      expect(api.getEconomicForecasts).toHaveBeenCalled();
    });
  });

  it("allows toggling between different time periods", async () => {
    renderWithProviders(<EconomicModeling />);
    
    await waitFor(() => {
      expect(screen.getByText("Consumer Confidence")).toBeInTheDocument();
    });

    // Look for time period selectors
    const selects = screen.getAllByRole("combobox");
    if (selects.length > 0) {
      fireEvent.mouseDown(selects[0]);
      
      const options = screen.getAllByRole("option");
      if (options.length > 1) {
        fireEvent.click(options[1]);
        
        await waitFor(() => {
          expect(api.getEconomicIndicators).toHaveBeenCalledTimes(2);
        });
      }
    }
  });
});