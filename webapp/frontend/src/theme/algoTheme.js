/**
 * Bullseye Trading — Unified Design System
 *
 * Single source of truth for colors, typography, spacing, and component styles.
 * Every page imports tokens from here. This is the foundation of the dark
 * institutional aesthetic that gives the platform its brand identity.
 *
 * Usage:
 *   import { C, F, S, comp } from '@/theme/algoTheme';
 *   <Box sx={{ bgcolor: C.card, color: C.text }} />
 *   <SectionCard title="Market Exposure" />
 */

// ============================================================================
// COLOR TOKENS
// ============================================================================
export const C = {
  // Background hierarchy (darker → lighter for layered depth)
  bg:        '#0a0d12',   // page background
  bgElev:    '#0e1116',   // elevated surface
  card:      '#161b22',   // primary card
  cardAlt:   '#1c232c',   // secondary card / hovered row
  cardLift:  '#222a35',   // hovered card / focused element

  // Borders / dividers
  border:    '#30363d',
  borderLight: '#21262d',

  // Text hierarchy
  textBright: '#f0f6fc',  // headers, key values
  text:       '#c9d1d9',  // body
  textDim:    '#8b949e',  // captions, secondary info
  textFaint:  '#6e7681',  // hints, placeholders

  // Brand
  brand:     '#3fb950',   // Bullseye green (primary brand)
  brandDark: '#238636',
  brandSoft: '#0d2818',   // bg for brand-flavored sections

  // Semantic — financial
  bull:      '#3fb950',   // gains, success
  bullDeep:  '#1f6f3b',
  bear:      '#f85149',   // losses, errors
  bearDeep:  '#a32028',
  warn:      '#d29922',   // caution
  warnDeep:  '#7d5c1d',

  // Accents
  blue:      '#388bfd',   // information, links
  blueSoft:  '#0c2d6b',
  purple:    '#a371f7',   // partial exits, special
  cyan:      '#39c5cf',   // multi-timeframe
  pink:      '#db61a2',   // sector rotation alerts
  amber:     '#fb950c',   // approaching threshold

  // Pure utilities
  white:     '#ffffff',
  black:     '#000000',
  transparent: 'transparent',
};

// Tier colors for market exposure / regime
export const tierColor = (name) => ({
  confirmed_uptrend: C.bull,
  healthy_uptrend:   '#56b97a',
  pressure:          C.warn,
  caution:           C.amber,
  correction:        C.bear,
}[name] || C.textDim);

// Letter grade colors
export const gradeColor = (g) => ({
  'A+': C.bull,
  'A':  C.bullDeep,
  'B':  C.blue,
  'C':  C.warn,
  'D':  C.amber,
  'F':  C.bear,
}[g] || C.textDim);

// Severity colors
export const severityColor = (s) => ({
  info:     C.blue,
  warn:     C.warn,
  warning:  C.warn,
  error:    C.bear,
  critical: C.bearDeep,
  ok:       C.bull,
  success:  C.bull,
  stale:    C.warn,
  empty:    C.bear,
}[s] || C.textDim);

// ============================================================================
// TYPOGRAPHY
// ============================================================================
export const F = {
  // Font families
  body: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  mono: '"JetBrains Mono", "Fira Code", "Cascadia Code", "SF Mono", Consolas, monospace',
  display: '"Inter", -apple-system, BlinkMacSystemFont, sans-serif',

  // Sizes (semantic)
  xxs:   '0.65rem',
  xs:    '0.7rem',
  sm:    '0.75rem',
  base:  '0.875rem',
  md:    '1rem',
  lg:    '1.125rem',
  xl:    '1.5rem',
  xxl:   '2rem',
  xxxl:  '2.5rem',

  // Weights
  weight: {
    regular: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
    black: 800,
  },

  // Common label style
  overline: {
    fontSize: '0.65rem',
    letterSpacing: '0.1em',
    fontWeight: 600,
    textTransform: 'uppercase',
  },
};

// ============================================================================
// SPACING & LAYOUT
// ============================================================================
export const S = {
  // Standard spacing scale (matches MUI but documented)
  xs: 0.5,
  sm: 1,
  md: 2,
  lg: 3,
  xl: 4,

  // Layout dimensions
  navWidth: 240,
  navWidthCollapsed: 64,
  headerHeight: 56,
  footerHeight: 32,

  // Border radii
  radiusSm: 4,
  radius:   6,
  radiusLg: 12,
};

// ============================================================================
// COMPONENT STYLE MIXINS
// ============================================================================
export const comp = {
  // Card with subtle border + dark background
  card: {
    bgcolor: C.card,
    color: C.text,
    border: `1px solid ${C.border}`,
    borderRadius: S.radius / 8,
  },

  // Card header strip
  cardHeader: {
    px: 2,
    py: 1,
    borderBottom: `1px solid ${C.border}`,
    bgcolor: C.cardAlt,
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },

  // Table header cell
  thCell: {
    bgcolor: C.cardAlt,
    color: C.textDim,
    borderColor: C.border,
    fontSize: F.xxs,
    letterSpacing: '0.1em',
    fontWeight: F.weight.bold,
  },

  // Table data cell
  tdCell: {
    color: C.text,
    borderColor: C.border,
    fontSize: F.sm,
  },

  // Monospace number cell
  monoCell: {
    color: C.text,
    borderColor: C.border,
    fontFamily: F.mono,
    fontSize: F.sm,
  },

  // Chip / badge
  chip: (bg, fg = 'white') => ({
    bgcolor: bg,
    color: fg,
    height: 20,
    fontSize: F.xs,
    fontWeight: F.weight.bold,
    letterSpacing: '0.04em',
  }),
};

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================
// P&L color from a number
export const pnlColor = (n) => (n > 0 ? C.bull : n < 0 ? C.bear : C.textDim);

// Direction arrow
export const arrowFor = (n) => (n > 0 ? '▲' : n < 0 ? '▼' : '·');

// Format big numbers
export const fmt$ = (n, decimals = 2) => {
  if (n === null || n === undefined || isNaN(n)) return '-';
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${Number(n).toFixed(decimals)}`;
};

export const fmtPct = (n, decimals = 2) => {
  if (n === null || n === undefined || isNaN(n)) return '-';
  const sign = n > 0 ? '+' : '';
  return `${sign}${Number(n).toFixed(decimals)}%`;
};

export const fmtNum = (n, decimals = 0) => {
  if (n === null || n === undefined || isNaN(n)) return '-';
  return Number(n).toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
};

export default { C, F, S, comp, tierColor, gradeColor, severityColor, pnlColor, arrowFor, fmt$, fmtPct, fmtNum };
