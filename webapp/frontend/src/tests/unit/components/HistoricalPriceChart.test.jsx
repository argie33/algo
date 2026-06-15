import { screen, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { renderWithProviders } from "../../test-utils";
import HistoricalPriceChart from "../../../components/HistoricalPriceChart";

// vi.hoisted ensures this runs before vi.mock factories (which are hoisted above imports)
const mockChartData = vi.hoisted(() =>
  Array.from({ length: 30 }, (_, i) => ({
    date: `2024-01-${String(i + 1).padStart(2, "0")}`,
    close: 150.0,
    open: 149.0,
    high: 152.0,
    low: 148.0,
    volume: 1000000,
  }))
);

// Override the global api mock with chart-specific data
vi.mock("../../../services/api.js", () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    getChartData: vi.fn().mockResolvedValue({ data: mockChartData }),
    getStockPrices: vi.fn().mockResolvedValue({ data: mockChartData }),
    getHistoricalData: vi.fn().mockResolvedValue({ data: [] }),
  },
  getApiConfig: vi.fn(() => ({ apiUrl: "http://localhost:3001", environment: "test" })),
}));

describe("HistoricalPriceChart", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Loading State", () => {
    it("renders without crashing", () => {
      renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);
      // Component renders in loading state initially — no crash
      expect(document.body).toBeInTheDocument();
    });
  });

  describe("Data Rendering", () => {
    it("renders price chart after data loads", async () => {
      renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);
      await waitFor(() => {
        expect(screen.getByTestId("line-chart")).toBeInTheDocument();
      });
    });

    it("renders volume chart after data loads", async () => {
      renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);
      await waitFor(() => {
        expect(screen.getByTestId("bar-chart")).toBeInTheDocument();
      });
    });

    it("renders responsive containers", async () => {
      renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);
      await waitFor(() => {
        const containers = screen.getAllByTestId("responsive-container");
        expect(containers.length).toBeGreaterThanOrEqual(1);
      });
    });

    it("passes correct data to line chart", async () => {
      renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);
      await waitFor(() => {
        const lineChart = screen.getByTestId("line-chart");
        const chartData = JSON.parse(lineChart.getAttribute("data-chart-data"));
        expect(chartData).toHaveLength(30);
        expect(chartData[0]).toHaveProperty("date", "2024-01-01");
        expect(chartData[0]).toHaveProperty("close", 150.0);
      });
    });

    it("renders price lines (close, high, low)", async () => {
      renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);
      await waitFor(() => {
        const lines = screen.getAllByTestId("chart-line");
        expect(lines.length).toBeGreaterThanOrEqual(1);
        const dataKeys = lines.map((l) => l.getAttribute("data-key"));
        expect(dataKeys).toContain("close");
      });
    });

    it("renders axes", async () => {
      renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);
      await waitFor(() => {
        const xAxes = screen.getAllByTestId("x-axis");
        expect(xAxes.length).toBeGreaterThanOrEqual(1);
        expect(xAxes[0]).toHaveAttribute("data-key", "date");
        expect(screen.getAllByTestId("y-axis").length).toBeGreaterThanOrEqual(1);
      });
    });

    it("renders cartesian grid", async () => {
      renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);
      await waitFor(() => {
        expect(screen.getAllByTestId("cartesian-grid").length).toBeGreaterThanOrEqual(1);
      });
    });

    it("renders tooltip", async () => {
      renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);
      await waitFor(() => {
        expect(screen.getAllByTestId("chart-tooltip").length).toBeGreaterThanOrEqual(1);
      });
    });

    it("shows symbol and days in title", async () => {
      renderWithProviders(<HistoricalPriceChart symbol="AAPL" days={90} />);
      await waitFor(() => {
        expect(screen.getByText(/AAPL/)).toBeInTheDocument();
        expect(screen.getByText(/90/)).toBeInTheDocument();
      });
    });

    it("shows volume heading", async () => {
      renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);
      await waitFor(() => {
        expect(screen.getByText(/Trading Volume/i)).toBeInTheDocument();
      });
    });

    it("renders volume bar with correct data key", async () => {
      renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);
      await waitFor(() => {
        const bars = screen.getAllByTestId("chart-bar");
        expect(bars.length).toBeGreaterThanOrEqual(1);
        expect(bars[0]).toHaveAttribute("data-key", "volume");
      });
    });
  });

  describe("Empty State", () => {
    it("shows empty message when API returns no data", async () => {
      const { default: api } = await import("../../../services/api.js");
      vi.mocked(api.getChartData).mockResolvedValueOnce({ data: [] });
      vi.mocked(api.getStockPrices).mockResolvedValueOnce({ data: [] });

      renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);

      await waitFor(() => {
        expect(screen.getByText(/No data available for AAPL/i)).toBeInTheDocument();
      });
    });
  });

  describe("Error State", () => {
    it("shows error message when API throws", async () => {
      const { default: api } = await import("../../../services/api.js");
      vi.mocked(api.getChartData).mockRejectedValueOnce(new Error("Network error"));
      vi.mocked(api.getStockPrices).mockRejectedValueOnce(new Error("Network error"));

      renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);

      await waitFor(() => {
        expect(screen.getByText(/Error:/i)).toBeInTheDocument();
      });
    });
  });

  describe("Symbol prop", () => {
    it("uses default symbol AAPL when none provided", async () => {
      renderWithProviders(<HistoricalPriceChart />);
      await waitFor(() => {
        expect(screen.getByText(/AAPL/)).toBeInTheDocument();
      });
    });

    it("renders with custom symbol", async () => {
      renderWithProviders(<HistoricalPriceChart symbol="TSLA" />);
      await waitFor(() => {
        expect(screen.getByText(/TSLA/)).toBeInTheDocument();
      });
    });

    it("refetches data when symbol changes", async () => {
      const { default: api } = await import("../../../services/api.js");
      const { rerender } = renderWithProviders(
        <HistoricalPriceChart symbol="AAPL" />
      );

      await waitFor(() => {
        expect(screen.getByTestId("line-chart")).toBeInTheDocument();
      });

      rerender(<HistoricalPriceChart symbol="TSLA" />);

      await waitFor(() => {
        expect(api.getChartData).toHaveBeenCalledWith("TSLA", expect.any(Number));
      });
    });
  });

  describe("Days prop", () => {
    it("uses default 90 days when not specified", async () => {
      const { default: api } = await import("../../../services/api.js");
      renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);

      await waitFor(() => {
        expect(api.getChartData).toHaveBeenCalledWith("AAPL", 90);
      });
    });

    it("passes custom days to API", async () => {
      const { default: api } = await import("../../../services/api.js");
      renderWithProviders(<HistoricalPriceChart symbol="AAPL" days={30} />);

      await waitFor(() => {
        expect(api.getChartData).toHaveBeenCalledWith("AAPL", 30);
      });
    });
  });

  describe("Large datasets", () => {
    it("handles 1000 data points without crashing", async () => {
      const { default: api } = await import("../../../services/api.js");
      const largeData = Array.from({ length: 1000 }, (_, i) => ({
        date: `2024-01-${String(i + 1).padStart(4, "0")}`,
        close: 150,
        open: 149,
        high: 152,
        low: 148,
        volume: 1000000,
      }));
      vi.mocked(api.getChartData).mockResolvedValueOnce({ data: largeData });

      renderWithProviders(<HistoricalPriceChart symbol="AAPL" />);

      await waitFor(() => {
        expect(screen.getByTestId("line-chart")).toBeInTheDocument();
      });
    });
  });
});
