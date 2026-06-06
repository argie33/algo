/**
 * Chart Container Utilities
 * Provides wrapper classes and helpers for proper Recharts ResponsiveContainer sizing
 * Fixes: "width(-1) and height(-1)" errors from missing container dimensions
 */

// CSS-in-JS wrapper for chart containers
export const chartContainerStyles = {
  // Default chart container with guaranteed height
  default: {
    width: '100%',
    minHeight: '300px',
    display: 'flex',
    flexDirection: 'column',
    position: 'relative',
  },
  // Tall chart for detailed data (e.g., historical prices)
  tall: {
    width: '100%',
    minHeight: '500px',
    display: 'flex',
    flexDirection: 'column',
    position: 'relative',
  },
  // Compact chart for secondary data (e.g., breadth)
  compact: {
    width: '100%',
    minHeight: '250px',
    display: 'flex',
    flexDirection: 'column',
    position: 'relative',
  },
};

/**
 * Get inline styles for chart wrapper to ensure ResponsiveContainer can measure
 * @param {string} variant - 'default', 'tall', or 'compact'
 * @param {object} overrides - Additional style overrides
 * @returns {object} Style object safe for inline style prop
 */
export const getChartContainerStyle = (variant = 'default', overrides = {}) => {
  const baseStyle = chartContainerStyles[variant] || chartContainerStyles.default;
  return { ...baseStyle, ...overrides };
};

/**
 * Responsive chart container wrapper properties
 * Use with ResponsiveContainer to ensure proper sizing
 * @example
 * <div style={getChartContainerStyle('default')}>
 *   <ResponsiveContainer width="100%" height="100%">
 *     <LineChart data={data}>...</LineChart>
 *   </ResponsiveContainer>
 * </div>
 */
export const chartSizeProps = {
  // Full-size responsive
  responsive: {
    width: '100%',
    height: '100%',
  },
  // Fixed sizes for specific use cases
  small: {
    width: '100%',
    height: 250,
  },
  medium: {
    width: '100%',
    height: 350,
  },
  large: {
    width: '100%',
    height: 500,
  },
};

/**
 * Get ResponsiveContainer props for safe sizing
 * @param {string} size - 'responsive', 'small', 'medium', or 'large'
 * @returns {object} Props object for ResponsiveContainer
 */
export const getChartSizeProps = (size = 'responsive') => {
  return chartSizeProps[size] || chartSizeProps.responsive;
};
