/**
 * Comprehensive Test Setup
 * Ensures consistent mocking and configuration across all tests
 */

import { afterEach, beforeEach, vi, afterAll } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom";
import { apiServiceMock } from "./mocks/api-service-mock";
import React from "react";

// Mock ResizeObserver for recharts
global.ResizeObserver = class ResizeObserver {
  constructor(cb) {
    this.cb = cb;
  }
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Mock window.matchMedia for MUI
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => {},
  }),
});

// Mock environment variables
process.env.VITE_API_URL = "http://localhost:3001";
process.env.NODE_ENV = "test";

// Mock the API service globally
vi.mock("../services/api.js", () => apiServiceMock);
vi.mock("../services/api", () => apiServiceMock);

// Mock recharts components globally to avoid canvas issues
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children, ...props }) =>
    React.createElement(
      "div",
      { "data-testid": "responsive-container", ...props },
      children
    ),
  LineChart: ({ children, data, ...props }) => (
    <div
      data-testid="line-chart"
      data-chart-data={JSON.stringify(data)}
      {...props}
    >
      {children}
    </div>
  ),
  Line: ({ dataKey, stroke, ...props }) => (
    <div
      data-testid="chart-line"
      data-key={dataKey}
      data-stroke={stroke}
      {...props}
    />
  ),
  AreaChart: ({ children, data, ...props }) => (
    <div
      data-testid="area-chart"
      data-chart-data={JSON.stringify(data)}
      {...props}
    >
      {children}
    </div>
  ),
  Area: ({ dataKey, fill, ...props }) => (
    <div
      data-testid="chart-area"
      data-key={dataKey}
      data-fill={fill}
      {...props}
    />
  ),
  PieChart: ({ children, ...props }) => (
    <div data-testid="pie-chart" {...props}>
      {children}
    </div>
  ),
  Pie: ({
    data: _data,
    dataKey,
    outerRadius,
    innerRadius,
    label: _label,
    labelLine: _labelLine,
    ...props
  }) => {
    const {
      cx: _cx,
      cy: _cy,
      startAngle: _startAngle,
      endAngle: _endAngle,
      fill: _fill,
      stroke: _stroke,
      ...safeProps
    } = props;
    return (
      <div
        data-testid="pie"
        data-key={dataKey}
        data-outer-radius={outerRadius}
        data-inner-radius={innerRadius}
        {...safeProps}
      />
    );
  },
  Cell: ({ fill, value, name, payload: _payload, ...props }) => {
    const {
      cx: _cx,
      cy: _cy,
      midAngle: _midAngle,
      innerRadius: _innerRadius,
      outerRadius: _outerRadius,
      percent: _percent,
      index: _index,
      ...safeProps
    } = props;
    return (
      <div
        data-testid="pie-cell"
        data-fill={fill}
        data-value={value}
        data-name={name}
        {...safeProps}
      />
    );
  },
  XAxis: ({ dataKey, ...props }) => (
    <div data-testid="x-axis" data-key={dataKey} {...props} />
  ),
  YAxis: ({ domain, ...props }) => (
    <div data-testid="y-axis" data-domain={JSON.stringify(domain)} {...props} />
  ),
  CartesianGrid: (props) => <div data-testid="cartesian-grid" {...props} />,
  Tooltip: ({
    content,
    formatter: _formatter,
    labelFormatter: _labelFormatter,
    ...props
  }) => {
    const { active, payload: _payload, label: _label, ...safeProps } = props;
    return (
      <div
        data-testid="chart-tooltip"
        data-content={typeof content}
        data-active={active}
        {...safeProps}
      >
        {typeof content === "function" ? "Custom Tooltip" : "Default Tooltip"}
      </div>
    );
  },
  Legend: (props) => <div data-testid="chart-legend" {...props} />,
  ReferenceLine: ({ y, stroke, ...props }) => (
    <div
      data-testid="reference-line"
      data-y={y}
      data-stroke={stroke}
      {...props}
    />
  ),
  ComposedChart: ({ children, data, ...props }) => (
    <div
      data-testid="composed-chart"
      data-chart-data={JSON.stringify(data)}
      {...props}
    >
      {children}
    </div>
  ),
  Bar: ({ dataKey, fill, ...props }) => (
    <div
      data-testid="chart-bar"
      data-key={dataKey}
      data-fill={fill}
      {...props}
    />
  ),
  BarChart: ({ children, data, ...props }) => (
    <div
      data-testid="bar-chart"
      data-chart-data={JSON.stringify(data)}
      {...props}
    >
      {children}
    </div>
  ),
  ScatterChart: ({ children, data, ...props }) => (
    <div
      data-testid="scatter-chart"
      data-chart-data={JSON.stringify(data)}
      {...props}
    >
      {children}
    </div>
  ),
  Scatter: ({ dataKey, fill, ...props }) => (
    <div data-testid="scatter" data-key={dataKey} data-fill={fill} {...props} />
  ),
  RadarChart: ({ children, data, ...props }) => (
    <div
      data-testid="radar-chart"
      data-chart-data={JSON.stringify(data)}
      {...props}
    >
      {children}
    </div>
  ),
  Radar: ({ dataKey, stroke, ...props }) => (
    <div
      data-testid="radar"
      data-key={dataKey}
      data-stroke={stroke}
      {...props}
    />
  ),
  PolarGrid: (props) => <div data-testid="polar-grid" {...props} />,
  PolarAngleAxis: ({ dataKey, ...props }) => (
    <div data-testid="polar-angle-axis" data-key={dataKey} {...props} />
  ),
  PolarRadiusAxis: ({ domain, ...props }) => (
    <div
      data-testid="polar-radius-axis"
      data-domain={JSON.stringify(domain)}
      {...props}
    />
  ),
}));

// Mock react-chartjs-2 components globally
vi.mock("react-chartjs-2", () => ({
  Line: ({ data, options: _options, ...props }) => (
    <div
      data-testid="chartjs-line"
      data-chart-data={JSON.stringify(data)}
      {...props}
    >
      Chart.js Line Chart
    </div>
  ),
  Doughnut: ({ data, options: _options, ...props }) => (
    <div
      data-testid="chartjs-doughnut"
      data-chart-data={JSON.stringify(data)}
      {...props}
    >
      Chart.js Doughnut Chart
    </div>
  ),
  Bar: ({ data, options: _options, ...props }) => (
    <div
      data-testid="chartjs-bar"
      data-chart-data={JSON.stringify(data)}
      {...props}
    >
      Chart.js Bar Chart
    </div>
  ),
  Pie: ({ data, options: _options, ...props }) => (
    <div
      data-testid="chartjs-pie"
      data-chart-data={JSON.stringify(data)}
      {...props}
    >
      Chart.js Pie Chart
    </div>
  ),
}));

// Mock TradingView components
vi.mock("../../components/ProfessionalChart", () => ({
  default: ({ symbol, ...props }) => (
    <div data-testid="tradingview-chart" data-symbol={symbol} {...props}>
      TradingView Chart for {symbol}
    </div>
  ),
}));

// Mock console methods to reduce test noise
const originalConsole = { ...console };
console.error = (...args) => {
  const message = args[0];
  if (
    typeof message === "string" &&
    (message.includes("Warning: An update to") ||
      message.includes("act()") ||
      message.includes("React Router Future Flag") ||
      message.includes("Each child in a list should have a unique"))
  ) {
    return; // Suppress React warnings
  }
  originalConsole.error.apply(console, args);
};

console.warn = (...args) => {
  const message = args[0];
  if (
    typeof message === "string" &&
    (message.includes("React Router") ||
      message.includes("Warning: An update to") ||
      message.includes("componentWillReceiveProps"))
  ) {
    return; // Suppress React warnings
  }
  originalConsole.warn.apply(console, args);
};

// Global test utilities
global.testUtils = {
  mockApiService: apiServiceMock,
  resetAllMocks: () => {
    Object.values(apiServiceMock).forEach((mock) => {
      if (typeof mock === "function" && mock.mockReset) {
        mock.mockReset();
      }
    });
  },
};

// Setup before each test
beforeEach(() => {
  // Reset all API mocks
  if (global.testUtils?.resetAllMocks) {
    global.testUtils.resetAllMocks();
  }
});

// Cleanup after each test
afterEach(() => {
  cleanup();

  // Clear all timers
  vi.clearAllTimers();

  // Clear all mocks
  vi.clearAllMocks();
});

// Cleanup after all tests
afterAll(() => {
  console.warn = originalConsole.warn;
  console.error = originalConsole.error;
});
