import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom";

// Clean up after each test
afterEach(() => {
  cleanup();
});

// Mock ResizeObserver for chart components
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

// Minimal recharts mocking using React.createElement
import React from 'react';

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }) => children,
  LineChart: ({ children }) => React.createElement('div', { 'data-testid': 'line-chart' }, children),
  AreaChart: ({ children }) => React.createElement('div', { 'data-testid': 'area-chart' }, children),
  BarChart: ({ children }) => React.createElement('div', { 'data-testid': 'bar-chart' }, children),
  PieChart: ({ children }) => React.createElement('div', { 'data-testid': 'pie-chart' }, children),
  ComposedChart: ({ children }) => React.createElement('div', { 'data-testid': 'composed-chart' }, children),
  Line: () => React.createElement('div', { 'data-testid': 'line' }),
  Area: () => React.createElement('div', { 'data-testid': 'area' }),
  Bar: () => React.createElement('div', { 'data-testid': 'bar' }),
  Pie: () => React.createElement('div', { 'data-testid': 'pie' }),
  Cell: () => React.createElement('div', { 'data-testid': 'cell' }),
  XAxis: () => React.createElement('div', { 'data-testid': 'x-axis' }),
  YAxis: () => React.createElement('div', { 'data-testid': 'y-axis' }),
  CartesianGrid: () => React.createElement('div', { 'data-testid': 'cartesian-grid' }),
  Tooltip: () => React.createElement('div', { 'data-testid': 'tooltip' }),
  Legend: () => React.createElement('div', { 'data-testid': 'legend' }),
  RadarChart: ({ children }) => React.createElement('div', { 'data-testid': 'radar-chart' }, children),
  Radar: () => React.createElement('div', { 'data-testid': 'radar' }),
  PolarGrid: () => React.createElement('div', { 'data-testid': 'polar-grid' }),
  PolarAngleAxis: () => React.createElement('div', { 'data-testid': 'polar-angle-axis' }),
  PolarRadiusAxis: () => React.createElement('div', { 'data-testid': 'polar-radius-axis' }),
}));

// React Router v7 future flag setup - suppress warnings in tests
window.__REACT_ROUTER_FUTURE_FLAGS__ = {
  v7_startTransition: true,
  v7_relativeSplatPath: true
};

// Suppress React Router warnings in tests
const originalWarn = console.warn;
console.warn = (...args) => {
  const message = args.join(' ');
  if (message.includes('React Router Future Flag Warning') || 
      message.includes('deprecated') || 
      message.includes('basic reporter')) {
    return;
  }
  originalWarn.apply(console, args);
};

// No global API mock - let individual tests handle their own mocking needs