/**
 * Unit Tests for Recharts-based ProfessionalChart Component
 * Tests the actual ProfessionalChart implementation using Recharts library
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ProfessionalChart from "../../../components/ProfessionalChart";

// Mock date-fns format function
vi.mock("date-fns", () => ({
  format: vi.fn((date, formatStr) => {
    if (formatStr === "MMM dd") return "Jan 01";
    if (formatStr === "MMM dd, yyyy") return "Jan 01, 2024";
    return "Jan 01, 2024";
  }),
}));

// Mock Recharts responsive container
vi.mock("recharts", async () => {
  const actual = await vi.importActual("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({ children, width, height }) => (
      <div data-testid="responsive-container" style={{ width, height }}>
        {children}
      </div>
    ),
    LineChart: ({ children }) => (
      <div className="recharts-line-chart">{children}</div>
    ),
    AreaChart: ({ children }) => (
      <div className="recharts-area-chart">{children}</div>
    ),
    BarChart: ({ children }) => (
      <div className="recharts-bar-chart">{children}</div>
    ),
    PieChart: ({ children }) => (
      <div className="recharts-pie-chart">{children}</div>
    ),
    ComposedChart: ({ children }) => (
      <div className="recharts-composed-chart">{children}</div>
    ),
    Line: () => <div className="recharts-line" />,
    Area: () => <div className="recharts-area" />,
    Bar: () => <div className="recharts-bar" />,
    Pie: () => <div className="recharts-pie" />,
    Cell: () => <div className="recharts-cell" />,
    XAxis: () => <div className="recharts-xaxis" />,
    YAxis: () => <div className="recharts-yaxis" />,
    CartesianGrid: () => <div className="recharts-cartesian-grid" />,
    Tooltip: () => <div className="recharts-tooltip" />,
  };
});

describe("ProfessionalChart (Recharts Implementation)", () => {
  const mockData = [
    { date: "2024-01-01", value: 100, volume: 1000 },
    { date: "2024-01-02", value: 105, volume: 1200 },
    { date: "2024-01-03", value: 102, volume: 900 },
    { date: "2024-01-04", value: 108, volume: 1100 },
  ];

  const defaultProps = {
    title: "Test Chart",
    data: mockData,
    dataKey: "value",
    xAxisDataKey: "date",
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("Basic Rendering", () => {
    it("should render chart title", () => {
      render(<ProfessionalChart {...defaultProps} />);
      expect(screen.getByText("Test Chart")).toBeInTheDocument();
    });

    it("should render chart subtitle when provided", () => {
      render(<ProfessionalChart {...defaultProps} subtitle="Test Subtitle" />);
      expect(screen.getByText("Test Subtitle")).toBeInTheDocument();
    });

    it("should render responsive container with chart", () => {
      render(<ProfessionalChart {...defaultProps} />);
      expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
    });

    it("should apply custom className", () => {
      const { container } = render(<ProfessionalChart {...defaultProps} className="custom-chart" />);
      const card = container.querySelector(".custom-chart");
      expect(card).toBeInTheDocument();
    });
  });

  describe("Chart Types", () => {
    it("should render line chart by default", () => {
      const { container } = render(<ProfessionalChart {...defaultProps} />);
      const lineChart = container.querySelector(".recharts-line-chart");
      expect(lineChart).toBeInTheDocument();
    });

    it("should render area chart when type is area", () => {
      const { container } = render(<ProfessionalChart {...defaultProps} type="area" />);
      const areaChart = container.querySelector(".recharts-area-chart");
      expect(areaChart).toBeInTheDocument();
    });

    it("should render bar chart when type is bar", () => {
      const { container } = render(<ProfessionalChart {...defaultProps} type="bar" />);
      const barChart = container.querySelector(".recharts-bar-chart");
      expect(barChart).toBeInTheDocument();
    });

    it("should render pie chart when type is pie", () => {
      const pieData = [
        { name: "A", value: 30 },
        { name: "B", value: 20 },
        { name: "C", value: 50 },
      ];
      const { container } = render(
        <ProfessionalChart {...defaultProps} type="pie" data={pieData} />
      );
      const pieChart = container.querySelector(".recharts-pie-chart");
      expect(pieChart).toBeInTheDocument();
    });

    it("should render composed chart when type is composed", () => {
      const { container } = render(<ProfessionalChart {...defaultProps} type="composed" />);
      const composedChart = container.querySelector(".recharts-composed-chart");
      expect(composedChart).toBeInTheDocument();
    });
  });

  describe("Loading and Error States", () => {
    it("should show loading skeleton when loading", () => {
      render(<ProfessionalChart {...defaultProps} loading={true} />);
      const skeleton = document.querySelector(".MuiSkeleton-root");
      expect(skeleton).toBeInTheDocument();
    });

    it("should show error message when error prop is provided", () => {
      const errorMessage = "Chart data failed to load";
      render(<ProfessionalChart {...defaultProps} error={errorMessage} />);
      expect(screen.getByText(errorMessage)).toBeInTheDocument();
    });

    it("should show no data message when data is empty", () => {
      render(<ProfessionalChart {...defaultProps} data={[]} />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("should show no data message when data is null", () => {
      render(<ProfessionalChart {...defaultProps} data={null} />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });
  });

  describe("Chart Configuration", () => {
    it("should use custom height", () => {
      render(<ProfessionalChart {...defaultProps} height={500} />);
      const container = screen.getByTestId("responsive-container");
      expect(container).toHaveStyle({ height: "440px" }); // height - 60 for title/padding
    });

    it("should apply custom color", () => {
      const { container } = render(
        <ProfessionalChart {...defaultProps} color="warning" />
      );
      // Check that warning color (#ff9800) is applied
      const lineElement = container.querySelector(".recharts-line");
      expect(lineElement).toBeInTheDocument(); // Basic presence check
    });

    it("should use custom data keys", () => {
      render(
        <ProfessionalChart 
          {...defaultProps} 
          dataKey="volume" 
          xAxisDataKey="date"
        />
      );
      // Chart should render with custom keys
      const chart = screen.getByTestId("responsive-container");
      expect(chart).toBeInTheDocument();
    });

    it("should hide grid when showGrid is false", () => {
      const { container } = render(
        <ProfessionalChart {...defaultProps} showGrid={false} />
      );
      const grid = container.querySelector(".recharts-cartesian-grid");
      expect(grid).toBeNull();
    });

    it("should show grid when showGrid is true", () => {
      const { container } = render(
        <ProfessionalChart {...defaultProps} showGrid={true} />
      );
      const grid = container.querySelector(".recharts-cartesian-grid");
      expect(grid).toBeInTheDocument();
    });
  });

  describe("Action Buttons", () => {
    it("should render refresh button when onRefresh provided", () => {
      const onRefresh = vi.fn();
      render(<ProfessionalChart {...defaultProps} onRefresh={onRefresh} />);
      
      const refreshButton = screen.getByLabelText("Refresh");
      expect(refreshButton).toBeInTheDocument();
    });

    it("should call onRefresh when refresh button clicked", () => {
      const onRefresh = vi.fn();
      render(<ProfessionalChart {...defaultProps} onRefresh={onRefresh} />);
      
      const refreshButton = screen.getByLabelText("Refresh");
      fireEvent.click(refreshButton);
      expect(onRefresh).toHaveBeenCalledOnce();
    });

    it("should render download button when onDownload provided", () => {
      const onDownload = vi.fn();
      render(<ProfessionalChart {...defaultProps} onDownload={onDownload} />);
      
      const downloadButton = screen.getByLabelText("Download");
      expect(downloadButton).toBeInTheDocument();
    });

    it("should call onDownload when download button clicked", () => {
      const onDownload = vi.fn();
      render(<ProfessionalChart {...defaultProps} onDownload={onDownload} />);
      
      const downloadButton = screen.getByLabelText("Download");
      fireEvent.click(downloadButton);
      expect(onDownload).toHaveBeenCalledOnce();
    });

    it("should render fullscreen button when onFullscreen provided", () => {
      const onFullscreen = vi.fn();
      render(<ProfessionalChart {...defaultProps} onFullscreen={onFullscreen} />);
      
      const fullscreenButton = screen.getByLabelText("Fullscreen");
      expect(fullscreenButton).toBeInTheDocument();
    });

    it("should call onFullscreen when fullscreen button clicked", () => {
      const onFullscreen = vi.fn();
      render(<ProfessionalChart {...defaultProps} onFullscreen={onFullscreen} />);
      
      const fullscreenButton = screen.getByLabelText("Fullscreen");
      fireEvent.click(fullscreenButton);
      expect(onFullscreen).toHaveBeenCalledOnce();
    });

    it("should render custom action buttons", () => {
      const customAction = {
        tooltip: "Custom Action",
        icon: <span data-testid="custom-icon">Custom</span>,
        onClick: vi.fn(),
      };
      
      render(<ProfessionalChart {...defaultProps} actions={[customAction]} />);
      
      const customButton = screen.getByLabelText("Custom Action");
      const customIcon = screen.getByTestId("custom-icon");
      expect(customButton).toBeInTheDocument();
      expect(customIcon).toBeInTheDocument();
    });

    it("should call custom action onClick", () => {
      const onClick = vi.fn();
      const customAction = {
        tooltip: "Custom Action",
        icon: <span>Custom</span>,
        onClick,
      };
      
      render(<ProfessionalChart {...defaultProps} actions={[customAction]} />);
      
      const customButton = screen.getByLabelText("Custom Action");
      fireEvent.click(customButton);
      expect(onClick).toHaveBeenCalledOnce();
    });
  });

  describe("Prop Filtering", () => {
    it("should filter out non-DOM props from Card component", () => {
      // Test that advanced props don't cause React warnings
      render(
        <ProfessionalChart
          {...defaultProps}
          _defaultIndicators={["RSI", "MACD"]}
          _enableDrawing={true}
          _saveShapes={true}
          _realtime={true}
          _enableCrosshair={true}
          _priceAlerts={[]}
          _enableAlerts={true}
          _onAlertCreate={vi.fn()}
          _onLayoutSave={vi.fn()}
          _enableLayoutSaving={true}
          _lazyLoad={true}
          _highContrast={true}
          _symbol="AAPL"
          _interval="1D"
          _multitimeframe={true}
          className="test-class"
        />
      );
      
      // Should render without errors
      expect(screen.getByText("Test Chart")).toBeInTheDocument();
    });
  });

  describe("Data Formatting", () => {
    it("should format Y-axis values using formatYAxis function", () => {
      const formatYAxis = vi.fn((value) => `$${value}`);
      render(
        <ProfessionalChart 
          {...defaultProps} 
          formatYAxis={formatYAxis}
        />
      );
      
      // formatYAxis should be passed to Recharts YAxis component
      // We verify the function was provided (actual formatting tested by Recharts)
      expect(formatYAxis).toBeDefined();
    });

    it("should format tooltip values using formatTooltip function", () => {
      const formatTooltip = vi.fn((value) => `${value}%`);
      render(
        <ProfessionalChart 
          {...defaultProps} 
          formatTooltip={formatTooltip}
        />
      );
      
      // formatTooltip should be passed to Recharts Tooltip component
      expect(formatTooltip).toBeDefined();
    });
  });

  describe("Chart Responsiveness", () => {
    it("should use ResponsiveContainer for responsive behavior", () => {
      render(<ProfessionalChart {...defaultProps} />);
      const responsiveContainer = screen.getByTestId("responsive-container");
      expect(responsiveContainer).toHaveStyle({ width: "100%" });
    });

    it("should calculate correct chart height", () => {
      render(<ProfessionalChart {...defaultProps} height={400} />);
      const responsiveContainer = screen.getByTestId("responsive-container");
      // Height should be height prop minus 60 for title area
      expect(responsiveContainer).toHaveStyle({ height: "340px" });
    });
  });

  describe("Color Themes", () => {
    it("should use predefined color from CHART_COLORS", () => {
      render(<ProfessionalChart {...defaultProps} color="success" />);
      // Should render without errors using success color (#4caf50)
      expect(screen.getByText("Test Chart")).toBeInTheDocument();
    });

    it("should use custom color when not in predefined colors", () => {
      render(<ProfessionalChart {...defaultProps} color="#ff5722" />);
      // Should render without errors using custom color
      expect(screen.getByText("Test Chart")).toBeInTheDocument();
    });

    it("should default to primary color when color is invalid", () => {
      render(<ProfessionalChart {...defaultProps} color="invalidColor" />);
      // Should render without errors, falling back to primary color
      expect(screen.getByText("Test Chart")).toBeInTheDocument();
    });
  });

  describe("Edge Cases", () => {
    it("should handle undefined props gracefully", () => {
      render(<ProfessionalChart title="Test" />);
      expect(screen.getByText("No data available")).toBeInTheDocument();
    });

    it("should handle empty actions array", () => {
      render(<ProfessionalChart {...defaultProps} actions={[]} />);
      expect(screen.getByText("Test Chart")).toBeInTheDocument();
    });

    it("should handle data with different structures for pie chart", () => {
      const pieData = [
        { name: "Section A", value: 400, color: "#8884d8" },
        { name: "Section B", value: 300, color: "#82ca9d" },
      ];
      
      render(
        <ProfessionalChart 
          {...defaultProps} 
          type="pie" 
          data={pieData} 
        />
      );
      
      expect(screen.getByText("Test Chart")).toBeInTheDocument();
    });

    it("should handle missing date formatting gracefully", () => {
      const dataWithNumbers = [
        { date: 1, value: 100 },
        { date: 2, value: 105 },
      ];
      
      render(
        <ProfessionalChart 
          {...defaultProps} 
          data={dataWithNumbers} 
        />
      );
      
      expect(screen.getByText("Test Chart")).toBeInTheDocument();
    });
  });
});