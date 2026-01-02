/**
 * Vitest Setup File
 * Configures test environment, mocks, and global utilities
 * This file runs once before all tests
 */

import { afterEach, beforeEach, vi, afterAll } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";

// Mock ResizeObserver for recharts and other components
global.ResizeObserver = class ResizeObserver {
  constructor(cb) {
    this.cb = cb;
  }
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Mock window.matchMedia for MUI and media queries
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

// Mock recharts components globally to avoid canvas issues
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children, ...props }) =>
    React.createElement(
      "div",
      { "data-testid": "responsive-container", ...props },
      children
    ),
  LineChart: ({ children, data, ...props }) => (
    React.createElement(
      "div",
      {
        "data-testid": "line-chart",
        "data-chart-data": JSON.stringify(data),
        ...props,
      },
      children
    )
  ),
  Line: ({ dataKey, stroke, ...props }) =>
    React.createElement("div", {
      "data-testid": "chart-line",
      "data-key": dataKey,
      "data-stroke": stroke,
      ...props,
    }),
  AreaChart: ({ children, data, ...props }) =>
    React.createElement(
      "div",
      {
        "data-testid": "area-chart",
        "data-chart-data": JSON.stringify(data),
        ...props,
      },
      children
    ),
  Area: ({ dataKey, fill, ...props }) =>
    React.createElement("div", {
      "data-testid": "chart-area",
      "data-key": dataKey,
      "data-fill": fill,
      ...props,
    }),
  PieChart: ({ children, ...props }) =>
    React.createElement(
      "div",
      { "data-testid": "pie-chart", ...props },
      children
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
    return React.createElement("div", {
      "data-testid": "pie",
      "data-key": dataKey,
      "data-outer-radius": outerRadius,
      "data-inner-radius": innerRadius,
      ...safeProps,
    });
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
    return React.createElement("div", {
      "data-testid": "pie-cell",
      "data-fill": fill,
      "data-value": value,
      "data-name": name,
      ...safeProps,
    });
  },
  XAxis: ({ dataKey, ...props }) =>
    React.createElement("div", {
      "data-testid": "x-axis",
      "data-key": dataKey,
      ...props,
    }),
  YAxis: ({ domain, ...props }) =>
    React.createElement("div", {
      "data-testid": "y-axis",
      "data-domain": JSON.stringify(domain),
      ...props,
    }),
  CartesianGrid: (props) =>
    React.createElement("div", { "data-testid": "cartesian-grid", ...props }),
  Tooltip: ({
    content,
    formatter: _formatter,
    labelFormatter: _labelFormatter,
    ...props
  }) => {
    const { active, payload: _payload, label: _label, ...safeProps } = props;
    return React.createElement(
      "div",
      {
        "data-testid": "chart-tooltip",
        "data-content": typeof content,
        "data-active": active,
        ...safeProps,
      },
      typeof content === "function" ? "Custom Tooltip" : "Default Tooltip"
    );
  },
  Legend: (props) =>
    React.createElement("div", { "data-testid": "chart-legend", ...props }),
  ReferenceLine: ({ y, stroke, ...props }) =>
    React.createElement("div", {
      "data-testid": "reference-line",
      "data-y": y,
      "data-stroke": stroke,
      ...props,
    }),
  ComposedChart: ({ children, data, ...props }) =>
    React.createElement(
      "div",
      {
        "data-testid": "composed-chart",
        "data-chart-data": JSON.stringify(data),
        ...props,
      },
      children
    ),
  Bar: ({ dataKey, fill, ...props }) =>
    React.createElement("div", {
      "data-testid": "chart-bar",
      "data-key": dataKey,
      "data-fill": fill,
      ...props,
    }),
  BarChart: ({ children, data, ...props }) =>
    React.createElement(
      "div",
      {
        "data-testid": "bar-chart",
        "data-chart-data": JSON.stringify(data),
        ...props,
      },
      children
    ),
  ScatterChart: ({ children, data, ...props }) =>
    React.createElement(
      "div",
      {
        "data-testid": "scatter-chart",
        "data-chart-data": JSON.stringify(data),
        ...props,
      },
      children
    ),
  Scatter: ({ dataKey, fill, ...props }) =>
    React.createElement("div", {
      "data-testid": "scatter",
      "data-key": dataKey,
      "data-fill": fill,
      ...props,
    }),
  RadarChart: ({ children, data, ...props }) =>
    React.createElement(
      "div",
      {
        "data-testid": "radar-chart",
        "data-chart-data": JSON.stringify(data),
        ...props,
      },
      children
    ),
  Radar: ({ dataKey, stroke, ...props }) =>
    React.createElement("div", {
      "data-testid": "radar",
      "data-key": dataKey,
      "data-stroke": stroke,
      ...props,
    }),
  PolarGrid: (props) =>
    React.createElement("div", { "data-testid": "polar-grid", ...props }),
  PolarAngleAxis: ({ dataKey, ...props }) =>
    React.createElement("div", {
      "data-testid": "polar-angle-axis",
      "data-key": dataKey,
      ...props,
    }),
  PolarRadiusAxis: ({ domain, ...props }) =>
    React.createElement("div", {
      "data-testid": "polar-radius-axis",
      "data-domain": JSON.stringify(domain),
      ...props,
    }),
}));

// Mock react-chartjs-2 components
vi.mock("react-chartjs-2", () => ({
  Line: ({ data, options: _options, ...props }) =>
    React.createElement(
      "div",
      {
        "data-testid": "chartjs-line",
        "data-chart-data": JSON.stringify(data),
        ...props,
      },
      "Chart.js Line Chart"
    ),
  Doughnut: ({ data, options: _options, ...props }) =>
    React.createElement(
      "div",
      {
        "data-testid": "chartjs-doughnut",
        "data-chart-data": JSON.stringify(data),
        ...props,
      },
      "Chart.js Doughnut Chart"
    ),
  Bar: ({ data, options: _options, ...props }) =>
    React.createElement(
      "div",
      {
        "data-testid": "chartjs-bar",
        "data-chart-data": JSON.stringify(data),
        ...props,
      },
      "Chart.js Bar Chart"
    ),
  Pie: ({ data, options: _options, ...props }) =>
    React.createElement(
      "div",
      {
        "data-testid": "chartjs-pie",
        "data-chart-data": JSON.stringify(data),
        ...props,
      },
      "Chart.js Pie Chart"
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

// Setup before each test
beforeEach(() => {
  // Reset any state needed before each test
});

// Cleanup after each test
afterEach(() => {
  cleanup();
  vi.clearAllTimers();
  vi.clearAllMocks();
});

// Cleanup after all tests
afterAll(() => {
  console.warn = originalConsole.warn;
  console.error = originalConsole.error;
});
