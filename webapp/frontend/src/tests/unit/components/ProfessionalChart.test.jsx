import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { ThemeProvider } from "@mui/material/styles";
import { createTheme } from "@mui/material/styles";
import ProfessionalChart from "../../../components/ProfessionalChart";

// Mock recharts components
vi.mock("recharts", () => ({
  LineChart: ({ children, data, ...props }) => (
    <div
      data-testid="recharts-line-chart"
      data-chart-data={JSON.stringify(data)}
      {...props}
    >
      {children}
    </div>
  ),
  AreaChart: ({ children, data, ...props }) => (
    <div
      data-testid="recharts-area-chart"
      data-chart-data={JSON.stringify(data)}
      {...props}
    >
      {children}
    </div>
  ),
  BarChart: ({ children, data, ...props }) => (
    <div
      data-testid="recharts-bar-chart"
      data-chart-data={JSON.stringify(data)}
      {...props}
    >
      {children}
    </div>
  ),
  PieChart: ({ children, data, ...props }) => (
    <div
      data-testid="recharts-pie-chart"
      data-chart-data={JSON.stringify(data)}
      {...props}
    >
      {children}
    </div>
  ),
  ComposedChart: ({ children, data, ...props }) => (
    <div
      data-testid="recharts-composed-chart"
      data-chart-data={JSON.stringify(data)}
      {...props}
    >
      {children}
    </div>
  ),
  ResponsiveContainer: ({ children, width, height, ...props }) => (
    <div
      data-testid="recharts-responsive-container"
      style={{ width, height }}
      {...props}
    >
      {children}
    </div>
  ),
  Line: (props) => <div data-testid="recharts-line" {...props} />,
  Area: (props) => <div data-testid="recharts-area" {...props} />,
  Bar: (props) => <div data-testid="recharts-bar" {...props} />,
  Pie: (props) => <div data-testid="recharts-pie" {...props} />,
  Cell: (props) => <div data-testid="recharts-cell" {...props} />,
  XAxis: (props) => <div data-testid="recharts-xaxis" {...props} />,
  YAxis: (props) => <div data-testid="recharts-yaxis" {...props} />,
  CartesianGrid: (props) => <div data-testid="recharts-grid" {...props} />,
  Tooltip: (props) => <div data-testid="recharts-tooltip" {...props} />,
}));

// Mock date-fns
vi.mock("date-fns", () => ({
  format: vi.fn((date, formatStr) => {
    if (formatStr === "MMM dd") return "Jan 01";
    if (formatStr === "MMM dd, yyyy") return "Jan 01, 2024";
    return "2024-01-01";
  }),
}));

const theme = createTheme();

const renderWithTheme = (component) => {
  return render(<ThemeProvider theme={theme}>{component}</ThemeProvider>);
};

describe("ProfessionalChart", () => {
  const mockData = [
    { date: "2024-01-01", value: 100, volume: 1000 },
    { date: "2024-01-02", value: 105, volume: 1200 },
    { date: "2024-01-03", value: 98, volume: 900 },
  ];

  const defaultProps = {
    title: "Test Chart",
    data: mockData,
    type: "line",
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Basic Rendering", () => {
    it("renders chart container with title", () => {
      renderWithTheme(<ProfessionalChart {...defaultProps} />);

      expect(screen.getByText("Test Chart")).toBeInTheDocument();
      expect(
        screen.getByTestId("recharts-responsive-container")
      ).toBeInTheDocument();
      expect(screen.getByTestId("recharts-line-chart")).toBeInTheDocument();
    });

    it("renders chart with subtitle", () => {
      renderWithTheme(
        <ProfessionalChart {...defaultProps} subtitle="Test Subtitle" />
      );

      expect(screen.getByText("Test Chart")).toBeInTheDocument();
      expect(screen.getByText("Test Subtitle")).toBeInTheDocument();
    });

    it("renders loading state when loading prop is true", () => {
      const { container } = renderWithTheme(
        <ProfessionalChart {...defaultProps} loading={true} />
      );

      expect(container.querySelector(".MuiSkeleton-root")).toBeInTheDocument();
      expect(
        screen.queryByTestId("recharts-line-chart")
      ).not.toBeInTheDocument();
    });

    it("renders error state when error prop is provided", () => {
      renderWithTheme(
        <ProfessionalChart {...defaultProps} error="Chart error occurred" />
      );

      expect(screen.getByText("Chart error occurred")).toBeInTheDocument();
      expect(
        screen.queryByTestId("recharts-line-chart")
      ).not.toBeInTheDocument();
    });

    it('renders "no data" message when data is empty', () => {
      renderWithTheme(<ProfessionalChart {...defaultProps} data={[]} />);

      expect(screen.getByText("No data available")).toBeInTheDocument();
      expect(
        screen.queryByTestId("recharts-line-chart")
      ).not.toBeInTheDocument();
    });

    it('renders "no data" message when data is null', () => {
      renderWithTheme(<ProfessionalChart {...defaultProps} data={null} />);

      expect(screen.getByText("No data available")).toBeInTheDocument();
      expect(
        screen.queryByTestId("recharts-line-chart")
      ).not.toBeInTheDocument();
    });
  });

  describe("Chart Types", () => {
    it("renders line chart by default", () => {
      renderWithTheme(<ProfessionalChart {...defaultProps} />);

      expect(screen.getByTestId("recharts-line-chart")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-line")).toBeInTheDocument();
    });

    it('renders area chart when type is "area"', () => {
      renderWithTheme(<ProfessionalChart {...defaultProps} type="area" />);

      expect(screen.getByTestId("recharts-area-chart")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-area")).toBeInTheDocument();
    });

    it('renders bar chart when type is "bar"', () => {
      renderWithTheme(<ProfessionalChart {...defaultProps} type="bar" />);

      expect(screen.getByTestId("recharts-bar-chart")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-bar")).toBeInTheDocument();
    });

    it('renders pie chart when type is "pie"', () => {
      renderWithTheme(<ProfessionalChart {...defaultProps} type="pie" />);

      expect(screen.getByTestId("recharts-pie-chart")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-pie")).toBeInTheDocument();
    });

    it('renders composed chart when type is "composed"', () => {
      renderWithTheme(<ProfessionalChart {...defaultProps} type="composed" />);

      expect(screen.getByTestId("recharts-composed-chart")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-bar")).toBeInTheDocument();
    });
  });

  describe("Chart Configuration", () => {
    it("passes data to chart components", () => {
      renderWithTheme(<ProfessionalChart {...defaultProps} />);

      const chartElement = screen.getByTestId("recharts-line-chart");
      const chartData = JSON.parse(
        chartElement.getAttribute("data-chart-data")
      );
      expect(chartData).toEqual(mockData);
    });

    it("renders grid when showGrid is true", () => {
      renderWithTheme(<ProfessionalChart {...defaultProps} showGrid={true} />);

      expect(screen.getByTestId("recharts-grid")).toBeInTheDocument();
    });

    it("does not render grid when showGrid is false", () => {
      renderWithTheme(<ProfessionalChart {...defaultProps} showGrid={false} />);

      expect(screen.queryByTestId("recharts-grid")).not.toBeInTheDocument();
    });

    it("renders tooltip when showTooltip is true", () => {
      renderWithTheme(
        <ProfessionalChart {...defaultProps} showTooltip={true} />
      );

      expect(screen.getByTestId("recharts-tooltip")).toBeInTheDocument();
    });

    it("does not render tooltip when showTooltip is false", () => {
      renderWithTheme(
        <ProfessionalChart {...defaultProps} showTooltip={false} />
      );

      expect(screen.queryByTestId("recharts-tooltip")).not.toBeInTheDocument();
    });

    it("renders X and Y axes", () => {
      renderWithTheme(<ProfessionalChart {...defaultProps} />);

      expect(screen.getByTestId("recharts-xaxis")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-yaxis")).toBeInTheDocument();
    });

    it("applies custom height", () => {
      renderWithTheme(<ProfessionalChart {...defaultProps} height={400} />);

      const container = screen.getByTestId("recharts-responsive-container");
      expect(container.style.height).toBe("340px"); // height - 60
    });
  });

  describe("Action Buttons", () => {
    it("renders refresh button when onRefresh is provided", () => {
      const mockRefresh = vi.fn();
      renderWithTheme(
        <ProfessionalChart {...defaultProps} onRefresh={mockRefresh} />
      );

      expect(
        screen.getByRole("button", { name: /refresh/i })
      ).toBeInTheDocument();
    });

    it("renders download button when onDownload is provided", () => {
      const mockDownload = vi.fn();
      renderWithTheme(
        <ProfessionalChart {...defaultProps} onDownload={mockDownload} />
      );

      expect(
        screen.getByRole("button", { name: /download/i })
      ).toBeInTheDocument();
    });

    it("renders fullscreen button when onFullscreen is provided", () => {
      const mockFullscreen = vi.fn();
      renderWithTheme(
        <ProfessionalChart {...defaultProps} onFullscreen={mockFullscreen} />
      );

      expect(
        screen.getByRole("button", { name: /fullscreen/i })
      ).toBeInTheDocument();
    });

    it("calls onRefresh when refresh button is clicked", () => {
      const mockRefresh = vi.fn();
      renderWithTheme(
        <ProfessionalChart {...defaultProps} onRefresh={mockRefresh} />
      );

      fireEvent.click(screen.getByRole("button", { name: /refresh/i }));
      expect(mockRefresh).toHaveBeenCalledOnce();
    });

    it("calls onDownload when download button is clicked", () => {
      const mockDownload = vi.fn();
      renderWithTheme(
        <ProfessionalChart {...defaultProps} onDownload={mockDownload} />
      );

      fireEvent.click(screen.getByRole("button", { name: /download/i }));
      expect(mockDownload).toHaveBeenCalledOnce();
    });

    it("calls onFullscreen when fullscreen button is clicked", () => {
      const mockFullscreen = vi.fn();
      renderWithTheme(
        <ProfessionalChart {...defaultProps} onFullscreen={mockFullscreen} />
      );

      fireEvent.click(screen.getByRole("button", { name: /fullscreen/i }));
      expect(mockFullscreen).toHaveBeenCalledOnce();
    });
  });

  describe("Custom Actions", () => {
    it("renders custom action buttons", () => {
      const mockAction1 = vi.fn();
      const mockAction2 = vi.fn();

      const customActions = [
        {
          tooltip: "Custom Action 1",
          onClick: mockAction1,
          icon: <span data-testid="custom-icon-1">Icon1</span>,
        },
        {
          tooltip: "Custom Action 2",
          onClick: mockAction2,
          icon: <span data-testid="custom-icon-2">Icon2</span>,
        },
      ];

      renderWithTheme(
        <ProfessionalChart {...defaultProps} actions={customActions} />
      );

      expect(screen.getByTestId("custom-icon-1")).toBeInTheDocument();
      expect(screen.getByTestId("custom-icon-2")).toBeInTheDocument();
    });

    it("calls custom action callbacks when clicked", () => {
      const mockAction = vi.fn();

      const customActions = [
        {
          tooltip: "Custom Action",
          onClick: mockAction,
          icon: <span data-testid="custom-icon">Icon</span>,
        },
      ];

      renderWithTheme(
        <ProfessionalChart {...defaultProps} actions={customActions} />
      );

      fireEvent.click(screen.getByTestId("custom-icon").closest("button"));
      expect(mockAction).toHaveBeenCalledOnce();
    });
  });

  describe("Pie Chart Specific", () => {
    it("renders pie chart with colored cells", () => {
      const pieData = [
        { name: "A", value: 100, color: "#ff0000" },
        { name: "B", value: 200, color: "#00ff00" },
      ];

      renderWithTheme(
        <ProfessionalChart {...defaultProps} type="pie" data={pieData} />
      );

      expect(screen.getByTestId("recharts-pie-chart")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-pie")).toBeInTheDocument();
      // Pie charts render multiple cells
      expect(
        screen.getAllByTestId("recharts-cell").length
      ).toBeGreaterThanOrEqual(1);
    });
  });

  describe("Props Filtering", () => {
    it("filters out invalid DOM props", () => {
      renderWithTheme(
        <ProfessionalChart
          {...defaultProps}
          _defaultIndicators={["RSI"]}
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
          _multitimeframe={["1m", "5m"]}
        />
      );

      // Component should render without warnings about invalid DOM attributes
      expect(screen.getByText("Test Chart")).toBeInTheDocument();
      expect(screen.getByTestId("recharts-line-chart")).toBeInTheDocument();
    });
  });

  describe("Color Configuration", () => {
    it("uses custom color when provided", () => {
      renderWithTheme(<ProfessionalChart {...defaultProps} color="#ff5722" />);

      expect(screen.getByTestId("recharts-line-chart")).toBeInTheDocument();
    });

    it("uses predefined color from CHART_COLORS", () => {
      renderWithTheme(<ProfessionalChart {...defaultProps} color="success" />);

      expect(screen.getByTestId("recharts-line-chart")).toBeInTheDocument();
    });
  });

  describe("Data Keys Configuration", () => {
    it("uses custom dataKey", () => {
      renderWithTheme(
        <ProfessionalChart {...defaultProps} dataKey="customValue" />
      );

      expect(screen.getByTestId("recharts-line-chart")).toBeInTheDocument();
    });

    it("uses custom xAxisDataKey", () => {
      renderWithTheme(
        <ProfessionalChart {...defaultProps} xAxisDataKey="timestamp" />
      );

      expect(screen.getByTestId("recharts-line-chart")).toBeInTheDocument();
    });
  });
});
