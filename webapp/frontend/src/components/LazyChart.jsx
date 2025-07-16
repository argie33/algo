import React, { Suspense, lazy } from 'react';
import { CircularProgress, Box } from '@mui/material';

// Lazy load chart components to reduce bundle size
const LineChart = lazy(() => import('recharts').then(module => ({ default: module.LineChart })));
const AreaChart = lazy(() => import('recharts').then(module => ({ default: module.AreaChart })));
const BarChart = lazy(() => import('recharts').then(module => ({ default: module.BarChart })));
const PieChart = lazy(() => import('recharts').then(module => ({ default: module.PieChart })));
const Line = lazy(() => import('recharts').then(module => ({ default: module.Line })));
const Area = lazy(() => import('recharts').then(module => ({ default: module.Area })));
const Bar = lazy(() => import('recharts').then(module => ({ default: module.Bar })));
const Pie = lazy(() => import('recharts').then(module => ({ default: module.Pie })));
const XAxis = lazy(() => import('recharts').then(module => ({ default: module.XAxis })));
const YAxis = lazy(() => import('recharts').then(module => ({ default: module.YAxis })));
const CartesianGrid = lazy(() => import('recharts').then(module => ({ default: module.CartesianGrid })));
const Tooltip = lazy(() => import('recharts').then(module => ({ default: module.Tooltip })));
const ResponsiveContainer = lazy(() => import('recharts').then(module => ({ default: module.ResponsiveContainer })));
const Cell = lazy(() => import('recharts').then(module => ({ default: module.Cell })));

const ChartLoader = ({ height = 200 }) => (
  <Box 
    sx={{ 
      display: 'flex', 
      justifyContent: 'center', 
      alignItems: 'center', 
      height: height,
      backgroundColor: 'grey.50',
      borderRadius: 1
    }}
  >
    <CircularProgress size={24} />
  </Box>
);

// Wrapper components for lazy-loaded charts
export const LazyLineChart = ({ children, ...props }) => (
  <Suspense fallback={<ChartLoader height={props.height} />}>
    <ResponsiveContainer {...props}>
      <LineChart {...props}>
        {children}
      </LineChart>
    </ResponsiveContainer>
  </Suspense>
);

export const LazyAreaChart = ({ children, ...props }) => (
  <Suspense fallback={<ChartLoader height={props.height} />}>
    <ResponsiveContainer {...props}>
      <AreaChart {...props}>
        {children}
      </AreaChart>
    </ResponsiveContainer>
  </Suspense>
);

export const LazyBarChart = ({ children, ...props }) => (
  <Suspense fallback={<ChartLoader height={props.height} />}>
    <ResponsiveContainer {...props}>
      <BarChart {...props}>
        {children}
      </BarChart>
    </ResponsiveContainer>
  </Suspense>
);

export const LazyPieChart = ({ children, ...props }) => (
  <Suspense fallback={<ChartLoader height={props.height} />}>
    <ResponsiveContainer {...props}>
      <PieChart {...props}>
        {children}
      </PieChart>
    </ResponsiveContainer>
  </Suspense>
);

// Export lazy-loaded components
export {
  LineChart,
  AreaChart,
  BarChart,
  PieChart,
  Line,
  Area,
  Bar,
  Pie,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell
};

// Preload charts on hover for better UX
export const preloadCharts = async () => {
  try {
    const recharts = await import('recharts');
    return recharts;
  } catch (error) {
    console.warn('Failed to preload charts:', error);
    return null;
  }
};

export default LazyLineChart;