/**
 * Enterprise-Grade Chart Theme System
 * Award-winning financial data visualization
 * Designed for wealth management & professional trading platforms
 *
 * Based on:
 * - Google Material Design 3 principles
 * - Bloomberg Terminal aesthetics (refined)
 * - Institutional financial UI standards
 * - WCAG AA accessibility compliance
 */

// ============================================================
// PROFESSIONAL COLOR SYSTEM
// ============================================================

export const FINANCIAL_COLORS = {
  // Bull/Bear (Universal Financial)
  bullish: {
    primary: '#10B981',      // Emerald green - buy, gains, positive
    light: '#D1FAE5',
    lighter: '#ECFDF5',
    dark: '#059669',
    contrast: '#F0FDFA'
  },
  bearish: {
    primary: '#EF4444',      // Bright red - sell, losses, negative
    light: '#FECACA',
    lighter: '#FEE2E2',
    dark: '#DC2626',
    contrast: '#FEF2F2'
  },

  // Neutral (Wait, Hold)
  neutral: {
    primary: '#6B7280',      // Stone gray
    light: '#D1D5DB',
    lighter: '#F3F4F6',
    dark: '#374151',
  },

  // Primary (Informational/Highlights)
  primary: {
    primary: '#3B82F6',      // Bright blue - primary data
    light: '#93C5FD',
    lighter: '#EFF6FF',
    dark: '#1D4ED8',
    contrast: '#F0F9FF'
  },

  // Secondary (Supporting Data)
  secondary: {
    primary: '#8B5CF6',      // Purple - secondary metrics
    light: '#D8B4FE',
    lighter: '#F3E8FF',
    dark: '#6D28D9',
  },

  // Accent (Emphasis/Warnings)
  accent: {
    primary: '#F59E0B',      // Amber - warnings, alerts
    light: '#FCD34D',
    lighter: '#FEF3C7',
    dark: '#D97706',
  },

  // Extended palette for multiple data series
  series: [
    '#3B82F6',  // Blue
    '#10B981',  // Emerald
    '#F59E0B',  // Amber
    '#8B5CF6',  // Purple
    '#EC4899',  // Pink
    '#14B8A6',  // Teal
    '#F97316',  // Orange
    '#6366F1',  // Indigo
  ],

  // Grayscale (Backgrounds, Grids)
  grayscale: {
    50: '#FAFAFA',
    100: '#F5F5F5',
    200: '#EEEEEE',
    300: '#E0E0E0',
    400: '#BDBDBD',
    500: '#9E9E9E',
    600: '#757575',
    700: '#616161',
    800: '#424242',
    900: '#212121',
  }
};

// ============================================================
// CHART STYLING CONFIGURATION
// ============================================================

export const CHART_DEFAULTS = {
  // Responsive Container
  responsiveContainer: {
    width: '100%',
    height: 400,
    margin: { top: 20, right: 30, left: 0, bottom: 20 },
  },

  // Grid Styling (Cartesian)
  grid: {
    light: {
      stroke: FINANCIAL_COLORS.grayscale[200],
      strokeDasharray: '5 5',
      strokeOpacity: 0.3,
      vertical: false,
    },
    dark: {
      stroke: FINANCIAL_COLORS.grayscale[700],
      strokeDasharray: '5 5',
      strokeOpacity: 0.15,
      vertical: false,
    }
  },

  // Axis Styling
  axis: {
    light: {
      stroke: FINANCIAL_COLORS.grayscale[300],
      fill: FINANCIAL_COLORS.grayscale[600],
      fontSize: 12,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      fontWeight: 500,
    },
    dark: {
      stroke: FINANCIAL_COLORS.grayscale[700],
      fill: FINANCIAL_COLORS.grayscale[400],
      fontSize: 12,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      fontWeight: 500,
    }
  },

  // Tooltip Styling
  tooltip: {
    light: {
      backgroundColor: '#FFFFFF',
      border: `1px solid ${FINANCIAL_COLORS.grayscale[200]}`,
      borderRadius: 8,
      padding: '12px 16px',
      boxShadow: '0 10px 25px rgba(0, 0, 0, 0.08)',
      fontSize: 12,
      fontWeight: 500,
    },
    dark: {
      backgroundColor: FINANCIAL_COLORS.grayscale[800],
      border: `1px solid ${FINANCIAL_COLORS.grayscale[700]}`,
      borderRadius: 8,
      padding: '12px 16px',
      boxShadow: '0 10px 25px rgba(0, 0, 0, 0.3)',
      fontSize: 12,
      fontWeight: 500,
      color: FINANCIAL_COLORS.grayscale[50],
    }
  },

  // Legend Styling
  legend: {
    light: {
      fontSize: 12,
      fontWeight: 500,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      fill: FINANCIAL_COLORS.grayscale[700],
    },
    dark: {
      fontSize: 12,
      fontWeight: 500,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      fill: FINANCIAL_COLORS.grayscale[300],
    }
  },

  // Line Styling
  line: {
    strokeWidth: 2.5,
    isAnimationActive: true,
    animationDuration: 800,
  },

  // Bar Styling
  bar: {
    radius: [8, 8, 4, 4],
    isAnimationActive: true,
    animationDuration: 600,
  },

  // Dot Styling (on lines)
  dot: {
    r: 4,
    fill: '#FFFFFF',
    stroke: 'currentColor',
    strokeWidth: 2,
  },
};

// ============================================================
// GRADIENT DEFINITIONS FOR SVG
// ============================================================

export const CHART_GRADIENTS = {
  bullish: {
    id: 'gradientBullish',
    stops: [
      { offset: '0%', color: FINANCIAL_COLORS.bullish.primary, opacity: 0.3 },
      { offset: '100%', color: FINANCIAL_COLORS.bullish.primary, opacity: 0.02 }
    ]
  },
  bearish: {
    id: 'gradientBearish',
    stops: [
      { offset: '0%', color: FINANCIAL_COLORS.bearish.primary, opacity: 0.3 },
      { offset: '100%', color: FINANCIAL_COLORS.bearish.primary, opacity: 0.02 }
    ]
  },
  primary: {
    id: 'gradientPrimary',
    stops: [
      { offset: '0%', color: FINANCIAL_COLORS.primary.primary, opacity: 0.25 },
      { offset: '100%', color: FINANCIAL_COLORS.primary.primary, opacity: 0.02 }
    ]
  },
  secondary: {
    id: 'gradientSecondary',
    stops: [
      { offset: '0%', color: FINANCIAL_COLORS.secondary.primary, opacity: 0.2 },
      { offset: '100%', color: FINANCIAL_COLORS.secondary.primary, opacity: 0.01 }
    ]
  },
  neutral: {
    id: 'gradientNeutral',
    stops: [
      { offset: '0%', color: FINANCIAL_COLORS.neutral.primary, opacity: 0.15 },
      { offset: '100%', color: FINANCIAL_COLORS.neutral.primary, opacity: 0.01 }
    ]
  },
};

// ============================================================
// CHART TYPE PRESETS
// ============================================================

export const CHART_PRESETS = {
  // LineChart - Time Series Data (Price, Performance)
  timeSeries: {
    height: 380,
    margin: { top: 20, right: 30, left: 0, bottom: 50 },
    strokeWidth: 2.5,
    dot: false,
    isAnimationActive: true,
  },

  // BarChart - Categorical Comparison (Sectors, Holdings)
  categorical: {
    height: 360,
    margin: { top: 20, right: 30, left: 80, bottom: 50 },
    radius: [8, 8, 0, 0],
    isAnimationActive: true,
  },

  // PieChart - Allocation/Composition
  composition: {
    height: 400,
    outerRadius: 120,
    innerRadius: 70, // Donut style is more professional
    startAngle: 90,
    endAngle: -270,
  },

  // ComposedChart - Multiple Metrics
  multiMetric: {
    height: 360,
    margin: { top: 20, right: 30, left: 60, bottom: 50 },
    isAnimationActive: true,
  },

  // ScatterChart - Correlation/Relationship
  scatter: {
    height: 380,
    margin: { top: 20, right: 30, left: 60, bottom: 50 },
  },

  // RadarChart - Multi-Factor Analysis
  multiDimensional: {
    height: 400,
    margin: { top: 30, right: 30, left: 30, bottom: 30 },
  },
};

// ============================================================
// TYPOGRAPHY FOR CHARTS
// ============================================================

export const CHART_TYPOGRAPHY = {
  title: {
    fontSize: 18,
    fontWeight: 600,
    letterSpacing: 0,
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  },
  subtitle: {
    fontSize: 13,
    fontWeight: 400,
    letterSpacing: 0,
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  },
  label: {
    fontSize: 12,
    fontWeight: 500,
    letterSpacing: 0,
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  },
  caption: {
    fontSize: 11,
    fontWeight: 400,
    letterSpacing: 0.3,
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  },
};

// ============================================================
// ANIMATION CONFIGS
// ============================================================

export const CHART_ANIMATIONS = {
  default: {
    duration: 600,
    easing: 'ease-out',
  },
  fast: {
    duration: 300,
    easing: 'ease-out',
  },
  slow: {
    duration: 1000,
    easing: 'ease-out',
  },
};

// ============================================================
// HELPER FUNCTIONS
// ============================================================

/**
 * Get color based on data value (bullish/bearish)
 */
export const getValueColor = (value, options = {}) => {
  const { bullishColor = FINANCIAL_COLORS.bullish.primary, bearishColor = FINANCIAL_COLORS.bearish.primary, neutralColor = FINANCIAL_COLORS.neutral.primary } = options;

  if (value > 0) return bullishColor;
  if (value < 0) return bearishColor;
  return neutralColor;
};

/**
 * Get chart defaults for specific theme mode
 */
export const getChartDefaults = (theme = 'light') => ({
  grid: CHART_DEFAULTS.grid[theme],
  axis: CHART_DEFAULTS.axis[theme],
  tooltip: CHART_DEFAULTS.tooltip[theme],
  legend: CHART_DEFAULTS.legend[theme],
});

/**
 * Get gradient fill reference
 */
export const getGradientFill = (gradientId) => `url(#${gradientId})`;

/**
 * Format currency values for chart labels
 */
export const formatChartCurrency = (value) => {
  if (!value) return '$0';
  if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
  return `$${value.toFixed(2)}`;
};

/**
 * Format percentage values
 */
export const formatChartPercent = (value) => {
  if (value === null || value === undefined) return '0%';
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
};

/**
 * Get icon for trend direction
 */
export const getTrendIcon = (value) => {
  if (value > 0) return '↗️';
  if (value < 0) return '↘️';
  return '→';
};

export default {
  FINANCIAL_COLORS,
  CHART_DEFAULTS,
  CHART_GRADIENTS,
  CHART_PRESETS,
  CHART_TYPOGRAPHY,
  CHART_ANIMATIONS,
  getValueColor,
  getChartDefaults,
  getGradientFill,
  formatChartCurrency,
  formatChartPercent,
  getTrendIcon,
};
