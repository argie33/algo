/**
 * Centralized Chart Gradient Theme System
 * Ensures consistent, professional appearance across all charts site-wide
 *
 * All chart gradients should import and use these definitions to maintain
 * visual consistency and make theme-wide adjustments simple and efficient.
 */

/**
 * Primary chart gradient - Used for main data visualization
 * Professional gradient with good visibility on light backgrounds
 * Top opacity: 0.4 (solid enough to be visible)
 * Bottom opacity: 0.05 (fade to background)
 */
export const PRIMARY_GRADIENT = {
  id: 'primaryGradient',
  stops: [
    { offset: '0%', color: '#1976d2', opacity: 0.4 },
    { offset: '100%', color: '#1976d2', opacity: 0.05 }
  ]
};

/**
 * Secondary chart gradient - Used for comparison or secondary metrics
 * Slightly more transparent than primary for visual hierarchy
 */
export const SECONDARY_GRADIENT = {
  id: 'secondaryGradient',
  stops: [
    { offset: '0%', color: '#1976d2', opacity: 0.25 },
    { offset: '100%', color: '#1976d2', opacity: 0.02 }
  ]
};

/**
 * Accent gradient - Used for highlighted or important indicators
 * More vibrant than primary for visual emphasis
 */
export const ACCENT_GRADIENT = {
  id: 'accentGradient',
  stops: [
    { offset: '0%', color: '#1565c0', opacity: 0.5 },
    { offset: '100%', color: '#1565c0', opacity: 0.08 }
  ]
};

/**
 * Bullish gradient - Green gradient for positive indicators
 * Used for buy signals, gains, uptrends
 */
export const BULLISH_GRADIENT = {
  id: 'bullishGradient',
  stops: [
    { offset: '0%', color: '#4caf50', opacity: 0.4 },
    { offset: '100%', color: '#4caf50', opacity: 0.05 }
  ]
};

/**
 * Bearish gradient - Red gradient for negative indicators
 * Used for sell signals, losses, downtrends
 */
export const BEARISH_GRADIENT = {
  id: 'bearishGradient',
  stops: [
    { offset: '0%', color: '#f44336', opacity: 0.4 },
    { offset: '100%', color: '#f44336', opacity: 0.05 }
  ]
};

/**
 * Neutral gradient - Gray/neutral gradient for neutral indicators
 * Used for balanced signals or neutral price movement
 */
export const NEUTRAL_GRADIENT = {
  id: 'neutralGradient',
  stops: [
    { offset: '0%', color: '#9e9e9e', opacity: 0.3 },
    { offset: '100%', color: '#9e9e9e', opacity: 0.02 }
  ]
};

/**
 * Yield curve gradient - Specialized for yield curve visualization
 * More visible at top for clarity on economic indicators
 */
export const YIELD_CURVE_GRADIENT = {
  id: 'yieldGradient',
  stops: [
    { offset: '0%', color: '#1976d2', opacity: 0.4 },
    { offset: '100%', color: '#1976d2', opacity: 0.08 }
  ]
};

/**
 * Leading indicators gradient - For economic indicators with strong signal
 * Higher opacity for visibility of important economic data
 */
export const LEADING_INDICATORS_GRADIENT = {
  id: 'leadingGradient',
  stops: [
    { offset: '0%', color: '#1976d2', opacity: 0.4 },
    { offset: '100%', color: '#1976d2', opacity: 0.05 }
  ]
};

/**
 * Helper function to get gradient fill reference
 * @param {string} gradientId - The gradient ID
 * @returns {string} URL reference for use in fill attributes
 */
export const getGradientFill = (gradientId) => `url(#${gradientId})`;

/**
 * Color palette - Consistent colors used across site
 * Ensures visual consistency even when not using gradients
 */
export const COLOR_PALETTE = {
  primary: '#1976d2',
  secondary: '#1565c0',
  bullish: '#4caf50',
  bearish: '#f44336',
  neutral: '#9e9e9e',
  accent: '#ff9800',
  warning: '#ff5722',
  info: '#00bcd4'
};

/**
 * Export all gradients as a map for easy access
 */
export const GRADIENTS = {
  PRIMARY: PRIMARY_GRADIENT,
  SECONDARY: SECONDARY_GRADIENT,
  ACCENT: ACCENT_GRADIENT,
  BULLISH: BULLISH_GRADIENT,
  BEARISH: BEARISH_GRADIENT,
  NEUTRAL: NEUTRAL_GRADIENT,
  YIELD_CURVE: YIELD_CURVE_GRADIENT,
  LEADING_INDICATORS: LEADING_INDICATORS_GRADIENT
};

export default {
  getGradientFill,
  GRADIENTS,
  COLOR_PALETTE
};
